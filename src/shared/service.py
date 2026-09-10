"""Application service wiring engines to SQLite for local-first runtime."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence

from fitness_gap.engine import FitnessGapEngine
from identity_abstraction.gate import IdentityAbstractionGate
from identity_resolution.gateway import IdentityResolutionGateway, ResolutionDenied
from shared.audit import AuditLedger
from shared.db import HermesDB
from shared.models import (
    EvidenceRecord,
    RankedCandidate,
    SkillRecord,
    StaffingRequest,
    TargetRoleProfile,
)
from shared.secrets import require_identity_map_secret
from shared.taxonomy import load_taxonomy
from skill_inference.engine import SkillInferenceEngine


class HermesService:
    def __init__(self, db: Optional[HermesDB] = None, mapping_secret: Optional[str] = None) -> None:
        self.db = db or HermesDB()
        secret = require_identity_map_secret(mapping_secret)
        # Hydrate existing map from DB first so tokens stay stable
        existing = self._load_existing_map()
        self.gate = IdentityAbstractionGate(secret, existing_map=existing)
        self._hydrate_display_names()
        self.audit = AuditLedger(db=self.db)
        self.inference = SkillInferenceEngine()
        tax = load_taxonomy()
        adjacency = {}
        for s in tax.all_skills():
            related = list(getattr(s, "related_skills", None) or []) + list(
                getattr(s, "relations", None) or []
            )
            if related:
                adjacency[s.skill_id] = list(dict.fromkeys(related))
        demand = self.db.get_demand()
        self.fitness = FitnessGapEngine(audit=self.audit, demand_weights=demand, adjacency=adjacency)
        self.resolution = IdentityResolutionGateway(self.gate, audit=self.audit)
        self.last_computation_run_id = ""

    def _load_existing_map(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT coded_identity, source_employee_key FROM identity_vault"
            ).fetchall()
        for row in rows:
            out[row["source_employee_key"].strip().lower()] = row["coded_identity"]
        return out

    def _hydrate_display_names(self) -> None:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT coded_identity, display_name, source_employee_key FROM identity_vault"
            ).fetchall()
        for row in rows:
            key = row["source_employee_key"].strip().lower()
            token = row["coded_identity"]
            self.gate._forward[key] = token
            self.gate._reverse[token] = key
            self.gate._display_names[token] = row["display_name"]

    def abstract(self, raw: Mapping[str, Any], employee_key_field: str = "employee_id") -> Dict[str, Any]:
        # Prefer DB-stored token for known source keys
        employee_key = str(raw[employee_key_field]).strip().lower()
        stored = self.db.resolve_coded_for_source(employee_key)
        if stored:
            self.gate._forward[employee_key] = stored
            self.gate._reverse[stored] = employee_key
        result = self.gate.abstract_record(raw, employee_key_field=employee_key_field)
        self.gate.assert_no_pii(result.record)
        display = self.gate._display_names.get(result.coded_identity, employee_key)
        self.db.upsert_identity(result.coded_identity, employee_key, display_name=display)
        # Re-read authority token after upsert
        authority = self.db.resolve_coded_for_source(employee_key) or result.coded_identity
        if authority != result.coded_identity:
            self.gate._forward[employee_key] = authority
            self.gate._reverse[authority] = employee_key
            result = type(result)(
                coded_identity=authority,
                record={**result.record, "coded_identity": authority},
                stripped_fields=result.stripped_fields,
            )
        self.db.set_availability(authority, True)
        self.audit.append(
            "evidence_ingestion",
            actor="ingest",
            payload={"coded_identity": authority},
        )
        return {
            "coded_identity": authority,
            "record": result.record,
            "stripped_fields": list(result.stripped_fields),
        }

    def stage_and_merge(self, evidence: Sequence[EvidenceRecord]) -> List[SkillRecord]:
        for item in evidence:
            with self.db.session() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM identity_map WHERE coded_identity = ?",
                    (item.coded_identity,),
                ).fetchone()
            if not exists:
                self.db.upsert_identity(
                    item.coded_identity, item.coded_identity, display_name=item.coded_identity
                )
            self.db.stage_evidence(item)
        all_evidence = self.db.load_all_evidence()
        merged = self.inference.merge_evidence(all_evidence)
        run_id = str(uuid.uuid4())
        self.last_computation_run_id = run_id
        self.db.replace_skills_matrix(merged, computation_run_id=run_id)
        self.audit.append(
            "inference_computation",
            actor="skill_inference",
            payload={"count": len(merged), "computation_run_id": run_id},
        )
        return merged

    def rank(
        self,
        request: StaffingRequest,
        availability: Optional[Mapping[str, bool]] = None,
        critical_skills: Optional[Sequence[str]] = None,
        min_coverage_ratio: Optional[float] = None,
    ):
        matrix = self.db.load_skills_matrix()
        alloc = dict(self.db.get_allocation())
        if availability:
            for k, v in availability.items():
                alloc[k] = 1.0 if v else 0.0
        self.fitness.demand_weights = self.db.get_demand()
        run_id = self.last_computation_run_id
        if not run_id:
            with self.db.session() as conn:
                row = conn.execute(
                    "SELECT computation_run_id FROM skills_matrix LIMIT 1"
                ).fetchone()
            run_id = row["computation_run_id"] if row and row["computation_run_id"] else ""
        result = self.fitness.rank_candidates(
            request,
            matrix,
            allocation=alloc,
            computation_run_id=run_id or "",
            critical_skills=critical_skills,
            min_coverage_ratio=min_coverage_ratio,
        )
        self.db.save_staffing_request(
            request.request_id,
            request.requester_id,
            [c.coded_identity for c in result.candidates],
            computation_run_id=run_id or "",
        )
        return result

    def gaps(self, coded_identity: str, role: TargetRoleProfile):
        matrix = self.db.load_skills_matrix()
        self.fitness.demand_weights = self.db.get_demand()
        return self.fitness.compute_gaps(coded_identity, role, matrix)

    def resolve(self, request_id: str, requester_id: str) -> List[Dict[str, str]]:
        stored = self.db.get_staffing_request(request_id)
        if not stored:
            raise ResolutionDenied("unknown staffing request")
        if stored["requester_id"] != requester_id:
            raise ResolutionDenied("requester does not own this staffing request")
        shortlist = [
            RankedCandidate(
                coded_identity=t,
                fitness_score=0.0,
                rank=i + 1,
                per_skill_reasoning={},
                evidence_ids=[],
            )
            for i, t in enumerate(stored["shortlist"])
        ]
        self._hydrate_display_names()
        return self.resolution.resolve_shortlist(
            request_id=request_id,
            requester_id=requester_id,
            shortlist=shortlist,
            allowed_requester_id=stored["requester_id"],
        )

    def decide(
        self,
        request_id: str,
        approved_by: str,
        status: str,
        chosen_coded_identity: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        override_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        stored = self.db.get_staffing_request(request_id)
        if not stored:
            raise ValueError("unknown staffing request")
        rank_of = None
        if chosen_coded_identity and chosen_coded_identity in stored["shortlist"]:
            rank_of = stored["shortlist"].index(chosen_coded_identity) + 1
        self.db.record_staffing_decision(
            request_id=request_id,
            status=status,
            approved_by=approved_by,
            chosen_coded_identity=chosen_coded_identity,
            rejection_reason=rejection_reason,
            override_note=override_note,
            engine_rank_of_choice=rank_of,
        )
        # Guardrail 8: never feed decisions back into scoring — audit only
        self.audit.append(
            "staffing_decision",
            actor=approved_by,
            payload={
                "request_id": request_id,
                "status": status,
                "chosen_coded_identity": chosen_coded_identity,
                "engine_rank_of_choice": rank_of,
                "override_note": override_note,
                "rejection_reason": rejection_reason,
                "guardrail": "never_score_on_historical_staffing_decisions",
            },
        )
        return self.db.get_staffing_request(request_id) or {}

    def me(self, coded_identity: str) -> Dict[str, Any]:
        matrix = [r for r in self.db.load_skills_matrix() if r.coded_identity == coded_identity]
        evidence = self.db.evidence_for_identity(coded_identity)
        return {
            "coded_identity": coded_identity,
            "skills": [m.model_dump(mode="json") for m in matrix],
            "evidence": [
                {
                    "evidence_id": e["evidence_id"],
                    "skill_id": e["skill_id"],
                    "evidence_type": e["evidence_type"],
                    "source_ref": e["source_ref"],
                    "occurred_at": e["occurred_at"],
                    "payload": __import__("json").loads(e["payload_json"] or "{}"),
                }
                for e in evidence
            ],
        }

    def contest(
        self, coded_identity: str, reason: str, skill_id: Optional[str] = None
    ) -> Dict[str, str]:
        contest_id = str(uuid.uuid4())
        self.db.add_contest(contest_id, coded_identity, skill_id, reason)
        self.audit.append(
            "evidence_contest",
            actor=coded_identity,
            payload={"contest_id": contest_id, "skill_id": skill_id, "reason": reason},
        )
        return {"contest_id": contest_id, "status": "open"}
