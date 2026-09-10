"""FastAPI local runtime for Hermes judgment components + web UI."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from shared.auth import AuthPrincipal, issue_token, verify_token
from shared.models import EvidenceRecord, ProficiencyLevel, StaffingRequest, TargetRoleProfile
from shared.org import SubjectAccessDenied, require_gap_access
from shared.rate_limit import RateLimiter
from shared.secrets import is_test_mode, require_identity_map_secret, require_jwt_secret
from shared.service import HermesService
from shared.taxonomy import load_taxonomy

app = FastAPI(title="Hermes Local API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SERVICE: Optional[HermesService] = None
WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
_RESOLVE_LIMITER = RateLimiter(max_calls=10, window_seconds=60.0)


@app.on_event("startup")
def _startup_fail_closed() -> None:
    # Fail closed on secrets outside test mode
    require_jwt_secret()
    require_identity_map_secret()


def get_service() -> HermesService:
    global _SERVICE
    if _SERVICE is None:
        db_path = os.getenv("HERMES_DB_PATH")
        from shared.db import HermesDB

        db = HermesDB(Path(db_path) if db_path else None)
        _SERVICE = HermesService(db=db)
    return _SERVICE


def reset_service_for_tests(service: HermesService) -> None:
    global _SERVICE
    _SERVICE = service


def require_api_key(
    x_api_key: Optional[str] = Header(default=None),
    x_functions_key: Optional[str] = Header(default=None),
) -> None:
    expected = os.getenv("HERMES_API_KEY") or os.getenv("FUNCTION_AUTH_KEY") or ""
    if not expected:
        return
    provided = x_api_key or x_functions_key
    if provided != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def get_principal(
    authorization: Optional[str] = Header(default=None),
    x_hermes_token: Optional[str] = Header(default=None),
) -> AuthPrincipal:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif x_hermes_token:
        token = x_hermes_token.strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        return verify_token(token)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


class TokenBody(BaseModel):
    sub: str
    roles: List[str] = Field(default_factory=lambda: ["manager"])
    coded_identity: Optional[str] = None


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "hermes", "mode": "local-first"}


@app.post("/api/auth/token")
def auth_token(body: TokenBody) -> Dict[str, Any]:
    """Dev/test JWT issuer. Replace with OIDC/Entra in production."""
    if not (is_test_mode() or os.getenv("HERMES_ENV", "local") == "local"):
        raise HTTPException(status_code=403, detail="token stub disabled outside local/test")
    token = issue_token(body.sub, body.roles, coded_identity=body.coded_identity)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/dashboard")
def dashboard(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    matrix = svc.db.matrix_records_as_dicts()
    coverage = svc.db.pilot_coverage()
    by_skill: Dict[str, List[float]] = defaultdict(list)
    for row in matrix:
        by_skill[row["skill_id"]].append(float(row["freshness"]))
    freshness = {
        skill: round(sum(vals) / len(vals), 4) if vals else 0.0
        for skill, vals in sorted(by_skill.items())
    }
    return {
        "coverage": coverage,
        "avg_freshness_by_skill": freshness,
        "skill_distribution": [
            {
                "coded_identity": r["coded_identity"],
                "skill_id": r["skill_id"],
                "proficiency": r["proficiency"],
                "confidence": r["confidence"],
                "freshness": r["freshness"],
                "volume_score": r.get("volume_score", 0),
            }
            for r in matrix
        ],
        "actor": principal.sub,
    }


@app.get("/api/roles")
def list_roles(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    with svc.db.session() as conn:
        rows = conn.execute(
            "SELECT role_id, role_name, required_skills_json, critical_skills_json, min_coverage_ratio "
            "FROM role_profiles"
        ).fetchall()
    import json

    roles = [
        {
            "role_id": r["role_id"],
            "role_name": r["role_name"],
            "required_skills": json.loads(r["required_skills_json"]),
            "critical_skills": json.loads(r["critical_skills_json"] or "[]"),
            "min_coverage_ratio": float(r["min_coverage_ratio"] or 0.6),
        }
        for r in rows
    ]
    return {"roles": roles}


@app.get("/api/skills")
def list_skills(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
) -> Dict[str, Any]:
    tax = load_taxonomy()
    skills = [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "domain_id": d.domain_id,
            "domain_name": d.name,
            "relations": list(getattr(s, "relations", []) or []),
        }
        for d in tax.domains
        for s in d.skills
    ]
    return {"skills": skills}


@app.get("/api/identities")
def list_identities(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    with svc.db.session() as conn:
        rows = conn.execute(
            "SELECT coded_identity FROM identity_map ORDER BY coded_identity"
        ).fetchall()
    return {"identities": [r["coded_identity"] for r in rows]}


@app.get("/api/matrix/runs")
def matrix_runs(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    return {"runs": svc.db.list_computation_runs()}


@app.get("/api/matrix/runs/{run_id}")
def matrix_run(
    run_id: str,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    return {"computation_run_id": run_id, "records": svc.db.load_matrix_as_of(run_id)}


@app.post("/api/identity/abstract")
def identity_abstract(
    body: Dict[str, Any],
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    try:
        return svc.abstract(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class MergeBody(BaseModel):
    evidence: list


@app.post("/api/inference/merge")
def inference_merge(
    body: MergeBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    evidence = [EvidenceRecord.model_validate(item) for item in body.evidence]
    merged = svc.stage_and_merge(evidence)
    return {
        "skills": [m.model_dump(mode="json") for m in merged],
        "computation_run_id": svc.last_computation_run_id,
    }


class RankBody(BaseModel):
    request_id: str
    requester_id: Optional[str] = None  # ignored — principal.sub wins
    required_skills: Dict[str, int]
    shortlist_size: int = Field(3, ge=1)
    availability_required: bool = True
    availability: Dict[str, bool] = Field(default_factory=dict)
    critical_skills: List[str] = Field(default_factory=list)
    min_coverage_ratio: Optional[float] = None

    @field_validator("shortlist_size")
    @classmethod
    def cap_shortlist(cls, v: int) -> int:
        return max(1, min(int(v), 10))


@app.post("/api/fitness/rank")
def fitness_rank(
    body: RankBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    request = StaffingRequest(
        request_id=body.request_id,
        requester_id=principal.sub,
        required_skills={k: ProficiencyLevel(v) for k, v in body.required_skills.items()},
        shortlist_size=body.shortlist_size,
        availability_required=body.availability_required,
    )
    result = svc.rank(
        request,
        availability=body.availability,
        critical_skills=body.critical_skills,
        min_coverage_ratio=body.min_coverage_ratio,
    )
    return result.model_dump(mode="json")


class GapBody(BaseModel):
    coded_identity: str
    role_id: str
    role_name: str
    required_skills: Dict[str, int]


@app.post("/api/fitness/gaps")
def fitness_gaps(
    body: GapBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    try:
        require_gap_access(principal, body.coded_identity, svc.db)
    except SubjectAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if principal.is_admin:
        svc.audit.append(
            "gap_admin_access",
            actor=principal.sub,
            payload={"subject": body.coded_identity},
        )
    role = TargetRoleProfile(
        role_id=body.role_id,
        role_name=body.role_name,
        required_skills={k: ProficiencyLevel(v) for k, v in body.required_skills.items()},
    )
    result = svc.gaps(body.coded_identity, role)
    return result.model_dump(mode="json")


class ResolveBody(BaseModel):
    request_id: str
    requester_id: Optional[str] = None  # ignored


@app.post("/api/identity/resolve")
def identity_resolve(
    body: ResolveBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    from identity_resolution.gateway import ResolutionDenied

    if not _RESOLVE_LIMITER.allow(principal.sub):
        raise HTTPException(status_code=429, detail="resolve rate limit exceeded")
    try:
        resolved = svc.resolve(body.request_id, principal.sub)
        return {"resolved": resolved}
    except ResolutionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


class DecisionBody(BaseModel):
    status: str  # accepted | rejected | overridden
    chosen_coded_identity: Optional[str] = None
    rejection_reason: Optional[str] = None
    override_note: Optional[str] = None


@app.post("/api/staffing/{request_id}/decision")
def staffing_decision(
    request_id: str,
    body: DecisionBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    if body.status not in {"accepted", "rejected", "overridden"}:
        raise HTTPException(status_code=400, detail="invalid status")
    try:
        return svc.decide(
            request_id=request_id,
            approved_by=principal.sub,
            status=body.status,
            chosen_coded_identity=body.chosen_coded_identity,
            rejection_reason=body.rejection_reason,
            override_note=body.override_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/me")
def me(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    coded = principal.coded_identity
    if not coded:
        raise HTTPException(status_code=400, detail="token missing coded_identity claim")
    return svc.me(coded)


class ContestBody(BaseModel):
    reason: str
    skill_id: Optional[str] = None


@app.post("/api/me/contest")
def me_contest(
    body: ContestBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    coded = principal.coded_identity
    if not coded:
        raise HTTPException(status_code=400, detail="token missing coded_identity claim")
    return svc.contest(coded, body.reason, skill_id=body.skill_id)


# Serve built SPA when present (after API routes so /api wins)
if WEB_DIST.is_dir():
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api") or full_path == "health":
            raise HTTPException(status_code=404)
        index = WEB_DIST / "index.html"
        candidate = WEB_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="frontend not built")
