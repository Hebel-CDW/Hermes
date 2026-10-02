"""Staffing requests: listing, detail, and manager decisions. Extracted verbatim from main.py."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import get_service, require_api_key, require_roles
from api.validation import CODED_ID_PATTERN, REQUEST_ID_PATTERN
from shared.auth import AuthPrincipal
from shared.demo_identities import MANAGER
from shared.service import HermesService

router = APIRouter()


@router.get("/api/staffing/requests")
def list_staffing_requests(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """The caller's own staffing requests only; ownership is never client-supplied."""
    from shared import read_models

    return {"requests": [read_models.request_summary(r) for r in svc.db.list_staffing_requests(principal.sub)]}


@router.get("/api/staffing/requests/{request_id}")
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


class DecisionBody(BaseModel):
    """``approved_by`` is intentionally absent: it always comes from the verified token."""

    model_config = ConfigDict(extra="forbid")
    status: str  # accepted | rejected | overridden
    chosen_coded_identity: Optional[str] = Field(None, pattern=CODED_ID_PATTERN)
    rejection_reason: Optional[str] = Field(None, max_length=2000)
    override_note: Optional[str] = Field(None, max_length=2000)


@router.post("/api/staffing/{request_id}/decision")
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
