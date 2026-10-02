"""Fitness ranking, gap computation, and post-rank identity resolution.

Grouped together (not split across requests.py/people.py) because all three are
FitnessGapEngine/IdentityResolutionGateway operations on a ranked shortlist, the
same cohesion the original main.py used implicitly. Extracted verbatim.

Note: ``identity_resolve`` reads ``dependencies.RESOLVE_LIMITER`` through the module
object (not a direct name import) so that ``reset_service_for_tests``'s reassignment
of that global is actually observed here — a plain ``from ... import RESOLVE_LIMITER``
would bind a stale reference, which the original single-module code never risked.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from api import dependencies
from api.dependencies import get_service, require_api_key, require_roles
from api.validation import CODED_ID_PATTERN, REQUEST_ID_PATTERN, validate_levels, validate_skill_list
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN, EMPLOYEE, MANAGER
from shared.models import ProficiencyLevel, StaffingRequest, TargetRoleProfile
from shared.org import SubjectAccessDenied, require_gap_access
from shared.service import HermesService

router = APIRouter()


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
        return validate_levels(v)

    @field_validator("critical_skills")
    @classmethod
    def check_critical(cls, v: List[str]) -> List[str]:
        return validate_skill_list(v)

    @field_validator("availability")
    @classmethod
    def check_availability(cls, v: Dict[str, bool]) -> Dict[str, bool]:
        bad = [k for k in v if not re.match(CODED_ID_PATTERN, k)]
        if bad:
            raise ValueError(f"availability keys must be coded identities; got {bad}")
        return v


@router.post("/api/fitness/rank")
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
        return validate_levels(v)


@router.post("/api/fitness/gaps")
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


@router.post("/api/identity/resolve")
def identity_resolve(
    body: ResolveBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    from identity_resolution.gateway import ResolutionDenied

    if not dependencies.RESOLVE_LIMITER.allow(principal.sub):
        raise HTTPException(status_code=429, detail="resolve rate limit exceeded")
    try:
        resolved = svc.resolve(body.request_id, principal.sub)
        return {"resolved": resolved}
    except ResolutionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
