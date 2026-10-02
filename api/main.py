"""FastAPI local runtime for Hermes judgment components + web UI (server-side RBAC).

Authorization model (prototype):
* Authentication: HS256 token carrying only ``sub``; roles and coded identity are
  derived server-side (``shared.auth.build_principal``).
* Roles: ``employee``, ``manager``, ``admin`` — enforced per route below. The
  frontend hides nothing that the server does not also refuse.
* Request ownership: staffing requests belong to the manager who created them;
  rank, resolve and decide all verify ownership in the service layer.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Path as PathParam, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.auth import AuthPrincipal, build_principal, issue_token, verify_token
from shared.db import HermesDB
from shared.db_trust import ensure_database_trusted
from shared.demo_identities import ADMIN, EMPLOYEE, MANAGER, demo_auth_enabled
from shared.errors import AuthorizationError, HermesError, RequestNotFound
from shared.models import EvidenceRecord, ProficiencyLevel, StaffingRequest, TargetRoleProfile
from shared.org import SubjectAccessDenied, require_gap_access
from shared.rate_limit import RateLimiter
from shared.secrets import require_identity_map_secret, require_jwt_secret
from shared.service import HermesService
from shared.taxonomy import load_taxonomy

SKILL_IDS = frozenset(s.skill_id for s in load_taxonomy().all_skills())
REQUEST_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
CODED_ID_PATTERN = r"^EMP-[0-9a-f]{8}$"


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Fail closed on secrets outside test mode.
    require_jwt_secret()
    require_identity_map_secret()
    yield


app = FastAPI(title="Hermes Local API", version="0.3.0", lifespan=_lifespan)

_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)


def _cors_origins() -> List[str]:
    """Allowed browser origins; hosted deployments set HERMES_CORS_ORIGINS (comma-separated)."""
    raw = os.getenv("HERMES_CORS_ORIGINS", "").strip()
    if not raw:
        return list(_DEFAULT_CORS_ORIGINS)
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip() and o.strip() != "*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if not request.url.path.startswith(("/docs", "/redoc")):
        response.headers.setdefault("Content-Security-Policy", _CSP)
    if os.getenv("HERMES_ENV", "").strip().lower() == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

_SERVICE: Optional[HermesService] = None
WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
_RESOLVE_LIMITER = RateLimiter(max_calls=10, window_seconds=60.0)
_DECLARE_LIMITER = RateLimiter(max_calls=10, window_seconds=60.0)


@app.exception_handler(HermesError)
def _hermes_error_handler(_request: Request, exc: HermesError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content={"detail": str(exc), "error": exc.code})


def get_service() -> HermesService:
    """Open the configured database — only if it passes the trust policy."""
    global _SERVICE
    if _SERVICE is None:
        db_path = os.getenv("HERMES_DB_PATH")
        db = HermesDB(Path(db_path) if db_path else None)
        svc = HermesService(db=db)
        ensure_database_trusted(db, svc._identity_secret)  # raises UntrustedDatabaseError -> 503
        _SERVICE = svc
    return _SERVICE


def reset_service_for_tests(service: Optional[HermesService]) -> None:
    """Swap the service and start a fresh resolve rate-limit window (tests / demo only)."""
    global _SERVICE, _RESOLVE_LIMITER, _DECLARE_LIMITER
    _SERVICE = service
    _RESOLVE_LIMITER = RateLimiter(max_calls=10, window_seconds=60.0)
    _DECLARE_LIMITER = RateLimiter(max_calls=10, window_seconds=60.0)


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
    svc: HermesService = Depends(get_service),
) -> AuthPrincipal:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif x_hermes_token:
        token = x_hermes_token.strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    sub = verify_token(token)  # AuthenticationError -> 401

    def resolve(employee_key: str) -> Optional[str]:
        bound = svc.db.coded_for_principal(sub)
        if bound:
            return bound
        return svc.db.resolve_coded_for_source(employee_key)

    return build_principal(sub, resolve)


def require_roles(*allowed: str):
    def _dependency(principal: AuthPrincipal = Depends(get_principal)) -> AuthPrincipal:
        if not principal.has_any_role(*allowed):
            raise AuthorizationError(
                f"role not permitted for this operation (requires one of {sorted(allowed)})"
            )
        return principal

    return _dependency


def _validate_levels(v: Dict[str, int]) -> Dict[str, int]:
    """Reject empty maps, unknown skills, and levels outside 1-5 with 422."""
    if not v:
        raise ValueError("required_skills must not be empty")
    unknown = sorted(k for k in v if k not in SKILL_IDS)
    if unknown:
        raise ValueError(f"unknown skill ids (not in the governed ontology): {unknown}")
    bad = {
        k: lvl
        for k, lvl in v.items()
        if isinstance(lvl, bool) or not isinstance(lvl, int) or not 1 <= lvl <= 5
    }
    if bad:
        raise ValueError(f"proficiency levels must be integers 1-5; got {bad}")
    return v


def _validate_skill_list(v: List[str]) -> List[str]:
    unknown = sorted(k for k in v if k not in SKILL_IDS)
    if unknown:
        raise ValueError(f"unknown skill ids (not in the governed ontology): {unknown}")
    return v


class TokenBody(BaseModel):
    """Only the principal id. Roles and coded identity are never client-supplied."""

    model_config = ConfigDict(extra="forbid")
    sub: str = Field(..., min_length=1, max_length=64)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "hermes", "mode": "local-first"}


@app.get("/ready")
def ready() -> Dict[str, str]:
    """Readiness probe: database opens, passes the trust policy, and the audit chain verifies."""
    svc = get_service()  # UntrustedDatabaseError -> 503 via the shared handler
    if svc.db.verify_audit_chain():
        raise HTTPException(status_code=503, detail="audit chain verification failed")
    return {"status": "ready"}


@app.post("/api/auth/token")
def auth_token(body: TokenBody) -> Dict[str, Any]:
    """Local/test issuer for the synthetic demo registry. Replace with OIDC in production."""
    if not demo_auth_enabled():
        raise HTTPException(status_code=403, detail="token stub disabled outside local/test")
    return {"access_token": issue_token(body.sub), "token_type": "bearer"}


@app.get("/api/dashboard")
def dashboard(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
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
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    with svc.db.session() as conn:
        rows = conn.execute(
            "SELECT role_id, role_name, required_skills_json, critical_skills_json, min_coverage_ratio "
            "FROM role_profiles"
        ).fetchall()
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
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER, ADMIN)),
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
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """Admins see every coded identity; managers see only their direct reports."""
    if principal.is_admin:
        with svc.db.session() as conn:
            rows = conn.execute("SELECT coded_identity FROM identity_map ORDER BY coded_identity").fetchall()
        return {"identities": [r["coded_identity"] for r in rows]}
    if not principal.coded_identity:
        return {"identities": []}
    return {"identities": svc.db.direct_reports(principal.coded_identity)}


@app.get("/api/identity/directory")
def identity_directory(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """Synthetic demo overlay of vault names. Scoring APIs stay coded-only."""
    if svc.db.get_meta("data_classification") != "synthetic":
        raise AuthorizationError(
            "Identity directory is available only for synthetic demo data",
            code="directory_not_synthetic",
        )
    return {"people": svc.db.list_identity_directory()}


@app.get("/api/matrix/runs")
def matrix_runs(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    return {"runs": svc.db.list_computation_runs()}


@app.get("/api/matrix/runs/{run_id}")
def matrix_run(
    run_id: str = PathParam(..., min_length=1, max_length=128),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    return {"computation_run_id": run_id, "records": svc.db.load_matrix_as_of(run_id)}


@app.get("/api/session")
def session_view(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """Who the server says the caller is, and whether the served database is synthetic or real.

    The UI uses this instead of any local role state.
    """
    return {
        "sub": principal.sub,
        "roles": list(principal.roles),
        "coded_identity": principal.coded_identity,
        "data_classification": svc.db.get_meta("data_classification"),
    }


@app.get("/api/data-quality")
def data_quality_view(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """Imported / validated / mapped / pending / scored counts. Aggregates only — no names,
    raw workbook rows, client labels or vault contents."""
    from shared import read_models

    return read_models.data_quality(svc.db, svc.inference.taxonomy)


@app.get("/api/overview")
def overview_view(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    from shared import read_models

    return read_models.overview(svc.db, svc.inference.taxonomy, svc.inference.config)


@app.get("/api/workforce")
def workforce_view(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    from shared import read_models

    return read_models.workforce(svc.db, svc.inference.taxonomy)


@app.get("/api/skills/{skill_id}")
def skill_view(
    skill_id: str = PathParam(..., min_length=1, max_length=128),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    from shared import read_models

    summary = read_models.skill_summary(svc.db, svc.inference.taxonomy, svc.inference.config, skill_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"unknown skill id: {skill_id}")
    return summary


@app.get("/api/staffing/requests")
def list_staffing_requests(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """The caller's own staffing requests only; ownership is never client-supplied."""
    from shared import read_models

    return {"requests": [read_models.request_summary(r) for r in svc.db.list_staffing_requests(principal.sub)]}


@app.get("/api/staffing/requests/{request_id}")
def get_staffing_request_view(
    request_id: str = PathParam(..., pattern=REQUEST_ID_PATTERN),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """Owner-only. Returns the stored ranking response verbatim (never re-ranked)."""
    from shared import read_models
    from shared.errors import RequestNotFound, RequestOwnershipError

    stored = svc.db.get_staffing_request(request_id)
    if stored is None:
        raise RequestNotFound("unknown staffing request")
    if stored["requester_id"] != principal.sub:
        raise RequestOwnershipError("staffing request is owned by another principal")
    return {**read_models.request_summary(stored), "result": stored.get("result") or {}}


class AbstractBody(BaseModel):
    model_config = ConfigDict(extra="allow")
    employee_id: str = Field(..., min_length=1, max_length=128)


@app.post("/api/identity/abstract")
def identity_abstract(
    body: AbstractBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    try:
        return svc.abstract(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class MergeBody(BaseModel):
    evidence: List[EvidenceRecord] = Field(..., min_length=1)


@app.post("/api/inference/merge")
def inference_merge(
    body: MergeBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    merged = svc.stage_and_merge(body.evidence)  # UnknownSkillError -> 422
    return {
        "skills": [m.model_dump(mode="json") for m in merged],
        "computation_run_id": svc.last_computation_run_id,
    }


class RankBody(BaseModel):
    request_id: str = Field(..., pattern=REQUEST_ID_PATTERN)
    requester_id: Optional[str] = None  # ignored — principal.sub wins
    required_skills: Dict[str, int]
    shortlist_size: int = Field(3, ge=1)
    availability_required: bool = True
    availability: Dict[str, bool] = Field(default_factory=dict)
    critical_skills: List[str] = Field(default_factory=list)
    min_coverage_ratio: Optional[float] = Field(None, ge=0.0, le=1.0)
    # G-1: when set, the role's stored critical_skills and min_coverage_ratio are
    # enforced server-side. A client may tighten them but can never loosen them.
    role_id: Optional[str] = Field(None, min_length=1, max_length=128)

    @field_validator("shortlist_size")
    @classmethod
    def cap_shortlist(cls, v: int) -> int:
        return max(1, min(int(v), 10))

    @field_validator("required_skills", mode="before")
    @classmethod
    def check_levels(cls, v: Any) -> Any:
        if not isinstance(v, dict):
            raise ValueError("required_skills must be an object of skill_id -> level")
        return _validate_levels(v)

    @field_validator("critical_skills")
    @classmethod
    def check_critical(cls, v: List[str]) -> List[str]:
        return _validate_skill_list(v)

    @field_validator("availability")
    @classmethod
    def check_availability(cls, v: Dict[str, bool]) -> Dict[str, bool]:
        import re

        bad = [k for k in v if not re.match(CODED_ID_PATTERN, k)]
        if bad:
            raise ValueError(f"availability keys must be coded identities; got {bad}")
        return v


@app.post("/api/fitness/rank")
def fitness_rank(
    body: RankBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    request = StaffingRequest(
        request_id=body.request_id,
        requester_id=principal.sub,
        required_skills={k: ProficiencyLevel(v) for k, v in body.required_skills.items()},
        shortlist_size=body.shortlist_size,
        availability_required=body.availability_required,
    )
    critical = list(body.critical_skills)
    min_cov = body.min_coverage_ratio
    if body.role_id:
        role = svc.db.get_role(body.role_id)
        if role is None:
            raise HTTPException(status_code=404, detail=f"unknown role_id: {body.role_id}")
        critical = sorted(set(critical) | set(role["critical_skills"]))
        role_floor = float(role["min_coverage_ratio"])
        min_cov = role_floor if min_cov is None else max(min_cov, role_floor)
    result = svc.rank(  # RequestOwnershipError -> 403, RequestStateConflict -> 409
        request,
        availability=body.availability,
        critical_skills=critical,
        min_coverage_ratio=min_cov,
    )
    return result.model_dump(mode="json")


class GapBody(BaseModel):
    coded_identity: str = Field(..., pattern=CODED_ID_PATTERN)
    role_id: str = Field(..., min_length=1, max_length=128)
    role_name: str = Field(..., min_length=1, max_length=256)
    required_skills: Dict[str, int]

    @field_validator("required_skills", mode="before")
    @classmethod
    def check_levels(cls, v: Any) -> Any:
        if not isinstance(v, dict):
            raise ValueError("required_skills must be an object of skill_id -> level")
        return _validate_levels(v)


@app.post("/api/fitness/gaps")
def fitness_gaps(
    body: GapBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER, ADMIN)),
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
    request_id: str = Field(..., pattern=REQUEST_ID_PATTERN)
    requester_id: Optional[str] = None  # ignored


@app.post("/api/identity/resolve")
def identity_resolve(
    body: ResolveBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER)),
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
    """``approved_by`` is intentionally absent: it always comes from the verified token."""

    model_config = ConfigDict(extra="forbid")
    status: str  # accepted | rejected | overridden
    chosen_coded_identity: Optional[str] = Field(None, pattern=CODED_ID_PATTERN)
    rejection_reason: Optional[str] = Field(None, max_length=2000)
    override_note: Optional[str] = Field(None, max_length=2000)


@app.post("/api/staffing/{request_id}/decision")
def staffing_decision(
    body: DecisionBody,
    request_id: str = PathParam(..., pattern=REQUEST_ID_PATTERN),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    if body.status not in {"accepted", "rejected", "overridden"}:
        raise HTTPException(status_code=400, detail="invalid status")
    return svc.decide(  # 404 / 403 / 409 / 422 via HermesError
        request_id=request_id,
        approved_by=principal.sub,
        status=body.status,
        chosen_coded_identity=body.chosen_coded_identity,
        rejection_reason=body.rejection_reason,
        override_note=body.override_note,
    )


@app.get("/api/me")
def me(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    coded = principal.coded_identity
    if not coded:
        raise HTTPException(status_code=400, detail="principal has no coded identity in this database")
    return svc.me(coded)


class ContestBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
    skill_id: Optional[str] = None

    @field_validator("skill_id")
    @classmethod
    def check_skill(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SKILL_IDS:
            raise ValueError(f"unknown skill id: {v}")
        return v


def _require_team_subject(principal: AuthPrincipal, coded_identity: str, svc: HermesService) -> None:
    if not svc.db.has_coded_identity(coded_identity):
        raise RequestNotFound("unknown coded identity")
    try:
        require_gap_access(principal, coded_identity, svc.db)
    except SubjectAccessDenied as exc:
        raise AuthorizationError(
            "not authorized for this coded identity", code="not_a_direct_report"
        ) from exc


class DeclareBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coded_identity: str = Field(..., pattern=CODED_ID_PATTERN)
    skill_id: str = Field(..., min_length=1, max_length=128)
    proficiency: int
    note: Optional[str] = Field(None, max_length=2000)

    @field_validator("skill_id")
    @classmethod
    def check_skill(cls, v: str) -> str:
        if v not in SKILL_IDS:
            raise ValueError(f"unknown skill id: {v}")
        return v

    @field_validator("proficiency")
    @classmethod
    def check_level(cls, v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 5:
            raise ValueError("proficiency must be an integer 1-5")
        return v


class ContestResolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["confirmed", "dismissed"]


@app.get("/api/team/skill-review/{coded_identity}")
def team_skill_review(
    coded_identity: str = PathParam(..., pattern=CODED_ID_PATTERN),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    _require_team_subject(principal, coded_identity, svc)
    return svc.skill_review(coded_identity)


@app.post("/api/team/declare")
def team_declare(
    body: DeclareBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    if not _DECLARE_LIMITER.allow(principal.sub):
        raise HTTPException(status_code=429, detail="too many skill updates")
    _require_team_subject(principal, body.coded_identity, svc)
    return svc.declare_skill(
        principal.sub,
        body.coded_identity,
        body.skill_id,
        body.proficiency,
        note=body.note,
    )


@app.post("/api/team/contests/{contest_id}/resolve")
def team_resolve_contest(
    contest_id: str = PathParam(..., min_length=8, max_length=64),
    body: ContestResolveBody = ...,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    contest = svc.db.get_contest(contest_id)
    if not contest:
        raise RequestNotFound("unknown contest")
    _require_team_subject(principal, contest["coded_identity"], svc)
    return svc.resolve_contest(principal.sub, contest_id, body.status)


@app.post("/api/me/contest")
def me_contest(
    body: ContestBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    coded = principal.coded_identity
    if not coded:
        raise HTTPException(status_code=400, detail="principal has no coded identity in this database")
    return svc.contest(coded, body.reason, skill_id=body.skill_id)


class TaxonomyResolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    skill_id: Optional[str] = Field(None, min_length=1, max_length=128)

    @field_validator("skill_id")
    @classmethod
    def check_skill(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SKILL_IDS:
            raise ValueError(f"unknown skill id: {v}")
        return v


class TicketItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: str = Field(..., min_length=1, max_length=128)
    ticket_number: str = Field(..., min_length=1, max_length=128)
    short_description: str = Field(..., min_length=1, max_length=4000)
    resolved_at: str = Field(..., min_length=10, max_length=64)


class TicketsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tickets: List[TicketItem] = Field(..., min_length=1, max_length=200)


class CertDateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    earned_at: str = Field(..., min_length=10, max_length=64)


class BindPrincipalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sub: str = Field(..., min_length=1, max_length=64)
    coded_identity: str = Field(..., pattern=CODED_ID_PATTERN)


class OrgEdgeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manager_coded_id: str = Field(..., pattern=CODED_ID_PATTERN)
    report_coded_id: str = Field(..., pattern=CODED_ID_PATTERN)


@app.get("/api/taxonomy/pending")
def taxonomy_pending(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    del principal
    return svc.taxonomy_pending()


@app.post("/api/taxonomy/aliases/{alias_label}/resolve")
def taxonomy_resolve(
    alias_label: str,
    body: TaxonomyResolveBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    return svc.resolve_taxonomy_alias(principal.sub, alias_label, body.decision, skill_id=body.skill_id)


@app.get("/api/baseline/matrix")
def baseline_matrix(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    del principal
    return svc.survey_matrix()


@app.post("/api/ingest/tickets")
def ingest_tickets(
    body: TicketsBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, int]:
    return svc.ingest_tickets([item.model_dump() for item in body.tickets], principal.sub)


@app.get("/api/certs/pending")
def certs_pending(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """Triage queue: every un-promoted certificate and exactly what blocks it
    (missing date, unmapped label, or both). Backs the admin cert-governance
    workflow — no fuzzy mapping or auto-approval happens here, it is read-only."""
    del principal
    from shared import read_models

    return read_models.cert_governance_queue(svc.db, svc.inference.taxonomy)


@app.post("/api/certs/{staging_id}/date")
def cert_date(
    staging_id: str = PathParam(..., min_length=1, max_length=128),
    body: CertDateBody = ...,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    return svc.date_certificate(staging_id, body.earned_at, principal.sub)


@app.post("/api/certs/{staging_id}/promote")
def cert_promote(
    staging_id: str = PathParam(..., min_length=1, max_length=128),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, int]:
    return svc.promote_certificate(staging_id, principal.sub)


@app.post("/api/org/bind-principal")
def org_bind_principal(
    body: BindPrincipalBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    return svc.bind_principal(principal.sub, body.sub, body.coded_identity)


@app.post("/api/org/edges")
def org_edges(
    body: OrgEdgeBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    return svc.add_org_edge(principal.sub, body.manager_coded_id, body.report_coded_id)


@app.get("/api/excel-sunset")
def excel_sunset(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    del principal
    return svc.excel_sunset()


# Serve built SPA when present (after API routes so /api wins)
if WEB_DIST.is_dir():
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    def _safe_static_candidate(full_path: str) -> Optional[Path]:
        """Resolve full_path under WEB_DIST, or None if it escapes the directory.

        Guardrail: this route is unauthenticated, so it must never be able to read
        a file outside web/dist. Traversal attempts (``../``, percent-encoded
        variants, absolute paths, symlinks) all resolve outside WEB_DIST and are
        rejected here instead of being served.
        """
        if not full_path:
            return None
        root = WEB_DIST.resolve()
        candidate = (root / full_path).resolve()
        if candidate == root or root not in candidate.parents:
            return None
        return candidate if candidate.is_file() else None

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api") or full_path == "health":
            raise HTTPException(status_code=404)
        candidate = _safe_static_candidate(full_path)
        if candidate is not None:
            return FileResponse(candidate)
        index = WEB_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="frontend not built")
