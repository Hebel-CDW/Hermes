"""Employee proposals, manager approvals, bulk team updates, what-if ranking and custom roles.

Nothing here changes how anyone is scored. An employee proposal counts for nothing until a manager
approves it, and approval runs through the same governed ``declare_skill`` / certificate paths the
rest of the app already uses. Every write is audited.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.dependencies import get_service, require_api_key, require_roles
from api.routers.candidates import RankBody
from api.validation import CODED_ID_PATTERN, SKILL_IDS, validate_levels, validate_skill_list
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN, EMPLOYEE, MANAGER
from shared.errors import AuthorizationError
from shared.models import ProficiencyLevel, StaffingRequest
from shared.rate_limit import PersistentRateLimiter
from shared.service import HermesService

router = APIRouter()

WORKFLOW_LIMITER = PersistentRateLimiter(max_calls=60, window_seconds=60.0, name="workflow")

REQUEST_ID = r"^(chg|goal)-[0-9a-f-]{36}$"


def _limit(principal: AuthPrincipal, svc: HermesService) -> None:
    if not WORKFLOW_LIMITER.allow(principal.sub, svc.db):
        raise HTTPException(status_code=429, detail="too many requests, slow down a little")


def _own_identity(principal: AuthPrincipal) -> str:
    if not principal.coded_identity:
        raise HTTPException(status_code=400, detail="principal has no coded identity in this database")
    return principal.coded_identity


# ----------------------------------------------------------------- employee side
class SubmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["skill_claim", "certificate", "skill_check"]
    skill_id: Optional[str] = None
    proficiency: Optional[int] = None
    cert_code: Optional[str] = Field(None, max_length=64)
    earned_at: Optional[str] = Field(None, max_length=40)
    note: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode="after")
    def check_shape(self) -> "SubmitBody":
        if self.kind in ("skill_claim", "skill_check") and self.skill_id not in SKILL_IDS:
            raise ValueError("choose a skill from the list")
        if self.kind == "skill_claim" and (
            isinstance(self.proficiency, bool) or not isinstance(self.proficiency, int) or not 1 <= self.proficiency <= 5
        ):
            raise ValueError("choose your level, 1 to 5")
        if self.kind == "certificate" and (not self.cert_code or not self.earned_at):
            raise ValueError("choose a certificate and the date you earned it")
        return self


@router.get("/api/cert-catalog")
def cert_catalog(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    return {"certificates": svc.workflow.cert_catalog()}


@router.get("/api/me/workflow")
def me_workflow(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    coded = _own_identity(principal)
    reqs = [r for r in svc.workflow.for_person(coded) if r["kind"] != "goal"]
    for r in reqs:
        r["skill_name"] = svc.workflow._skill_name(r["payload"].get("skill_id"))
    return {"requests": reqs, "goal": svc.workflow.goal(coded)}


@router.post("/api/me/requests")
def me_submit(
    body: SubmitBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    _limit(principal, svc)
    coded = _own_identity(principal)
    payload = {k: v for k, v in body.model_dump().items() if k != "kind" and v is not None}
    return svc.workflow.submit(coded, body.kind, payload)


@router.post("/api/me/requests/{request_id}/withdraw")
def me_withdraw(
    request_id: str = PathParam(..., pattern=REQUEST_ID),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    _limit(principal, svc)
    return svc.workflow.withdraw(_own_identity(principal), request_id)


class GoalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_id: str = Field(..., min_length=1, max_length=128)


@router.put("/api/me/goal")
def me_set_goal(
    body: GoalBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    _limit(principal, svc)
    return svc.workflow.set_goal(_own_identity(principal), body.role_id)


@router.delete("/api/me/goal")
def me_clear_goal(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    _limit(principal, svc)
    svc.workflow.clear_goal(_own_identity(principal))
    return {"status": "cleared"}


@router.get("/api/me/timeline")
def me_timeline(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    return {"events": svc.workflow.timeline(_own_identity(principal))}


# ----------------------------------------------------------------- manager side
@router.get("/api/team/inbox")
def team_inbox(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    return svc.workflow.inbox(svc.workflow.team_scope(principal))


class DecideBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "decline"]
    proficiency: Optional[int] = Field(None, ge=1, le=5)
    earned_at: Optional[str] = Field(None, max_length=40)
    note: Optional[str] = Field(None, max_length=1000)


@router.post("/api/team/inbox/{request_id}/decide")
def team_decide(
    body: DecideBody,
    request_id: str = PathParam(..., pattern=REQUEST_ID),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    _limit(principal, svc)
    record = svc.workflow._get(request_id)
    if record["coded_identity"] not in set(svc.workflow.team_scope(principal)):
        raise AuthorizationError("not authorized for this person", code="not_a_direct_report")
    return svc.workflow.decide(
        principal.sub, request_id, body.decision, body.proficiency, body.earned_at, body.note
    )


@router.get("/api/team/grid")
def team_grid(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    return svc.workflow.team_grid(svc.workflow.team_scope(principal))


class BulkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coded_identity: str = Field(..., pattern=CODED_ID_PATTERN)
    skill_id: str
    proficiency: int = Field(..., ge=1, le=5)
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("skill_id")
    @classmethod
    def check_skill(cls, v: str) -> str:
        if v not in SKILL_IDS:
            raise ValueError(f"unknown skill id: {v}")
        return v


class BulkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[BulkItem] = Field(..., min_length=1, max_length=200)


@router.post("/api/team/bulk-declare")
def team_bulk_declare(
    body: BulkBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    _limit(principal, svc)
    scope = set(svc.workflow.team_scope(principal))
    outside = sorted({i.coded_identity for i in body.items} - scope)
    if outside:
        # Nothing is written if any one row is outside the manager's team.
        raise AuthorizationError("not authorized for every person in this update", code="not_a_direct_report")
    return svc.workflow.bulk_declare(principal.sub, [i.model_dump() for i in body.items])


@router.post("/api/fitness/preview")
def fitness_preview(
    body: RankBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """What-if: the same ranking engine, nothing saved, nothing audited, no request created."""
    _limit(principal, svc)
    request = StaffingRequest(
        request_id=f"preview-{body.request_id}",
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
        floor = float(role["min_coverage_ratio"])
        min_cov = floor if min_cov is None else max(min_cov, floor)
    result = svc.preview_rank(request, availability=body.availability, critical_skills=critical, min_coverage_ratio=min_cov)
    return result.model_dump(mode="json")


class CustomRoleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_name: str = Field(..., min_length=3, max_length=80)
    required_skills: Dict[str, int]
    critical_skills: List[str] = Field(default_factory=list, max_length=6)
    min_coverage_ratio: float = Field(0.6, ge=0.3, le=1.0)

    @field_validator("required_skills", mode="before")
    @classmethod
    def check_levels(cls, v: Any) -> Any:
        if not isinstance(v, dict):
            raise ValueError("required_skills must be an object of skill_id -> level")
        if len(v) > 12:
            raise ValueError("a role can list at most 12 skills")
        return validate_levels(v)

    @field_validator("critical_skills")
    @classmethod
    def check_critical(cls, v: List[str]) -> List[str]:
        return validate_skill_list(v)


@router.post("/api/roles/custom")
def create_custom_role(
    body: CustomRoleBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    _limit(principal, svc)
    return svc.workflow.save_custom_role(
        principal.sub, body.role_name, body.required_skills, body.critical_skills, body.min_coverage_ratio
    )


@router.delete("/api/roles/custom/{role_id}")
def delete_custom_role(
    role_id: str = PathParam(..., pattern=r"^custom_[0-9a-f]{10}$"),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    _limit(principal, svc)
    svc.workflow.delete_custom_role(principal.sub, role_id)
    return {"status": "deleted"}
