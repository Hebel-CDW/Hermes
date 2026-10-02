"""Data-quality/activation status and the legacy baseline/excel-sunset reads. Extracted verbatim."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from api.dependencies import get_service, require_api_key, require_roles
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN, MANAGER
from shared.service import HermesService

router = APIRouter()


@router.get("/api/data-quality")
def data_quality_view(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """Imported / validated / mapped / pending / scored counts. Aggregates only — no names,
    raw workbook rows, client labels or vault contents."""
    from shared import read_models

    return read_models.data_quality(svc.db, svc.inference.taxonomy)


@router.get("/api/baseline/matrix")
def baseline_matrix(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    del principal
    return svc.survey_matrix()


@router.get("/api/excel-sunset")
def excel_sunset(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    del principal
    return svc.excel_sunset()
