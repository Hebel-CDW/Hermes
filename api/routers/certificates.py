"""Certificate governance queue, dating, and promotion. Extracted verbatim from main.py."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import get_service, require_api_key, require_roles
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN
from shared.service import HermesService

router = APIRouter()


@router.get("/api/certs/pending")
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


class CertDateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    earned_at: str = Field(..., min_length=10, max_length=64)


@router.post("/api/certs/{staging_id}/date")
def cert_date(
    staging_id: str = PathParam(..., min_length=1, max_length=128),
    body: CertDateBody = ...,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    return svc.date_certificate(staging_id, body.earned_at, principal.sub)


@router.post("/api/certs/{staging_id}/promote")
def cert_promote(
    staging_id: str = PathParam(..., min_length=1, max_length=128),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, int]:
    return svc.promote_certificate(staging_id, principal.sub)
