"""Manager/employee skill-review, declaration, and contest workflow. Extracted verbatim.

Not in the suggested template list, but it's a cohesive, self-contained feature
(its own body models, its own shared ``_require_team_subject`` guard, its own
rate limiter) distinct from the general people/workforce reads — splitting it
into people.py would just relocate the grab-bag problem rather than fix it.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api import dependencies
from api.dependencies import get_service, get_teams_provider, require_api_key, require_roles
from api.validation import CODED_ID_PATTERN, SKILL_IDS
from integrations.teams.provider import TeamsUnavailableError
from integrations.teams.service import record_assessment_response, send_capability_check
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN, EMPLOYEE, MANAGER
from shared.errors import AuthorizationError, RequestNotFound, UnknownSkillError
from shared.org import SubjectAccessDenied, require_gap_access
from shared.service import HermesService

router = APIRouter()


def _require_team_subject(principal: AuthPrincipal, coded_identity: str, svc: HermesService) -> None:
    if not svc.db.has_coded_identity(coded_identity):
        raise RequestNotFound("unknown coded identity")
    try:
        require_gap_access(principal, coded_identity, svc.db)
    except SubjectAccessDenied as exc:
        raise AuthorizationError(
            "not authorized for this coded identity", code="not_a_direct_report"
        ) from exc


@router.get("/api/team/skill-review/{coded_identity}")
def team_skill_review(
    coded_identity: str = PathParam(..., pattern=CODED_ID_PATTERN),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    _require_team_subject(principal, coded_identity, svc)
    return svc.skill_review(coded_identity)


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


@router.post("/api/team/declare")
def team_declare(
    body: DeclareBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    if not dependencies.DECLARE_LIMITER.allow(principal.sub, svc.db):
        raise HTTPException(status_code=429, detail="too many skill updates")
    _require_team_subject(principal, body.coded_identity, svc)
    return svc.declare_skill(
        principal.sub,
        body.coded_identity,
        body.skill_id,
        body.proficiency,
        note=body.note,
    )


class ContestResolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["confirmed", "dismissed"]


@router.post("/api/team/contests/{contest_id}/resolve")
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


class ContestBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
    skill_id: Optional[str] = None

    @field_validator("skill_id")
    @classmethod
    def check_skill(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SKILL_IDS:
            raise ValueError(f"unknown skill id: {v}")
        return v


class CapabilityCheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_ids: list = Field(..., min_length=1, max_length=10)

    @field_validator("skill_ids")
    @classmethod
    def check_skills(cls, v: list) -> list:
        unknown = sorted(s for s in v if s not in SKILL_IDS)
        if unknown:
            raise ValueError(f"unknown skill ids: {unknown}")
        return v


@router.post("/api/team/{coded_identity}/capability-check")
def send_team_capability_check(
    coded_identity: str = PathParam(..., pattern=CODED_ID_PATTERN),
    body: CapabilityCheckBody = ...,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """Manager -> employee, over Teams (or the dev mock — see
    integrations/teams/mock_provider.py). Creates no evidence by itself;
    that only happens once the employee actually answers, via the response
    endpoint below."""
    _require_team_subject(principal, coded_identity, svc)
    try:
        provider = get_teams_provider()
        assessment_id = send_capability_check(provider, svc.inference.taxonomy, coded_identity, body.skill_ids)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except TeamsUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"assessment_id": assessment_id, "sent_to": coded_identity, "mock": getattr(provider, "is_mock", True)}


class CapabilityCheckResponseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list


@router.post("/api/me/capability-check/respond")
def respond_to_capability_check(
    body: CapabilityCheckResponseBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """The employee's own response. ``coded_identity`` is never taken from the
    request body — it is always the caller's own server-derived identity, the
    same rule every other evidence-writing route in this app follows. In
    production this endpoint is superseded by the Teams webhook handler
    (not built — see integrations/teams/microsoft_provider.py), which would
    resolve identity from the Bot Framework's own channel binding instead."""
    coded = principal.coded_identity
    if not coded:
        raise HTTPException(status_code=400, detail="principal has no coded identity in this database")
    from pydantic import ValidationError

    raw_response = {"coded_identity": coded, "answers": body.answers}
    try:
        merged = record_assessment_response(svc, raw_response, source_ref=f"teams-self-{principal.sub}")
    except (UnknownSkillError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"declared_skill_count": len(merged), "skill_ids": [m.skill_id for m in merged]}


@router.post("/api/me/contest")
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
