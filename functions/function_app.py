"""Azure Functions v4 HTTP entrypoints for Hermes judgment components."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

import azure.functions as func

from fitness_gap.engine import FitnessGapEngine
from identity_abstraction.gate import IdentityAbstractionGate
from identity_resolution.gateway import IdentityResolutionGateway, ResolutionDenied
from shared.audit import AuditLedger
from shared.models import (
    EvidenceRecord,
    EvidenceType,
    ProficiencyLevel,
    RankedCandidate,
    SkillRecord,
    StaffingRequest,
    TargetRoleProfile,
)
from skill_inference.engine import SkillInferenceEngine

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Process-local state for prototype; production uses Azure SQL + Key Vault.
_AUDIT = AuditLedger()
_GATE = IdentityAbstractionGate(os.getenv("IDENTITY_MAP_SECRET", "local-dev-secret"))
_INFERENCE = SkillInferenceEngine()
_FITNESS = FitnessGapEngine(audit=_AUDIT)
_RESOLUTION = IdentityResolutionGateway(_GATE, audit=_AUDIT)
_MATRIX: List[SkillRecord] = []
_EVIDENCE: List[EvidenceRecord] = []
_REQUEST_OWNERS: Dict[str, str] = {}
_SHORTLISTS: Dict[str, List[str]] = {}


def _auth_ok(req: func.HttpRequest) -> bool:
    expected = os.getenv("FUNCTION_AUTH_KEY", "")
    if not expected:
        return True
    return req.headers.get("x-functions-key") == expected or req.params.get("code") == expected


def _json_response(payload: Any, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )


@app.route(route="identity/abstract", methods=["POST"])
def identity_abstract(req: func.HttpRequest) -> func.HttpResponse:
    """Single identity abstraction entry point."""
    if not _auth_ok(req):
        return _json_response({"error": "unauthorized"}, 401)
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "invalid json"}, 400)
    try:
        result = _GATE.abstract_record(body)
        _GATE.assert_no_pii(result.record)
        _AUDIT.append("evidence_ingestion", actor="power_automate", payload={"coded_identity": result.coded_identity})
        return _json_response(
            {
                "coded_identity": result.coded_identity,
                "record": result.record,
                "stripped_fields": list(result.stripped_fields),
            }
        )
    except ValueError as exc:
        return _json_response({"error": str(exc)}, 400)


@app.route(route="inference/merge", methods=["POST"])
def inference_merge(req: func.HttpRequest) -> func.HttpResponse:
    if not _auth_ok(req):
        return _json_response({"error": "unauthorized"}, 401)
    body = req.get_json()
    evidence_payload = body.get("evidence", [])
    evidence = [EvidenceRecord.model_validate(item) for item in evidence_payload]
    global _EVIDENCE, _MATRIX
    _EVIDENCE = list(_EVIDENCE) + evidence
    merged = _INFERENCE.merge_evidence(_EVIDENCE)
    _MATRIX = merged
    _AUDIT.append("inference_computation", actor="skill_inference", payload={"count": len(merged)})
    return _json_response({"skills": [m.model_dump(mode="json") for m in merged]})


@app.route(route="fitness/rank", methods=["POST"])
def fitness_rank(req: func.HttpRequest) -> func.HttpResponse:
    if not _auth_ok(req):
        return _json_response({"error": "unauthorized"}, 401)
    body = req.get_json()
    request = StaffingRequest(
        request_id=body["request_id"],
        requester_id=body["requester_id"],
        required_skills={k: ProficiencyLevel(v) for k, v in body["required_skills"].items()},
        shortlist_size=body.get("shortlist_size", 3),
        availability_required=body.get("availability_required", True),
    )
    availability = body.get("availability", {})
    result = _FITNESS.rank_candidates(request, _MATRIX, availability=availability)
    _REQUEST_OWNERS[request.request_id] = request.requester_id
    _SHORTLISTS[request.request_id] = [c.coded_identity for c in result.candidates]
    return _json_response(result.model_dump(mode="json"))


@app.route(route="fitness/gaps", methods=["POST"])
def fitness_gaps(req: func.HttpRequest) -> func.HttpResponse:
    if not _auth_ok(req):
        return _json_response({"error": "unauthorized"}, 401)
    body = req.get_json()
    role = TargetRoleProfile(
        role_id=body["role_id"],
        role_name=body["role_name"],
        required_skills={k: ProficiencyLevel(v) for k, v in body["required_skills"].items()},
    )
    result = _FITNESS.compute_gaps(body["coded_identity"], role, _MATRIX)
    return _json_response(result.model_dump(mode="json"))


@app.route(route="identity/resolve", methods=["POST"])
def identity_resolve(req: func.HttpRequest) -> func.HttpResponse:
    if not _auth_ok(req):
        return _json_response({"error": "unauthorized"}, 401)
    body = req.get_json()
    request_id = body["request_id"]
    requester_id = body["requester_id"]
    owner = _REQUEST_OWNERS.get(request_id)
    tokens = _SHORTLISTS.get(request_id, [])
    shortlist = [
        RankedCandidate(
            coded_identity=t,
            fitness_score=0.0,
            rank=i + 1,
            per_skill_reasoning={},
            evidence_ids=[],
        )
        for i, t in enumerate(tokens)
    ]
    try:
        resolved = _RESOLUTION.resolve_shortlist(
            request_id=request_id,
            requester_id=requester_id,
            shortlist=shortlist,
            allowed_requester_id=owner or "",
        )
        return _json_response({"resolved": resolved})
    except ResolutionDenied as exc:
        return _json_response({"error": str(exc)}, 403)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return _json_response({"status": "ok", "service": "hermes"})
