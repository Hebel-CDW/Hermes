"""Workforce/identity views and admin identity/org operations. Extracted verbatim from main.py."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import get_service, require_api_key, require_roles
from api.validation import CODED_ID_PATTERN
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN, EMPLOYEE, MANAGER
from shared.errors import AuthorizationError
from shared.service import HermesService

router = APIRouter()


@router.get("/api/dashboard")
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


@router.get("/api/identities")
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


@router.get("/api/identity/directory")
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


@router.get("/api/overview")
def overview_view(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    from shared import read_models

    return read_models.overview(svc.db, svc.inference.taxonomy, svc.inference.config)


@router.get("/api/workforce")
def workforce_view(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    from shared import read_models

    return read_models.workforce(svc.db, svc.inference.taxonomy)


class AbstractBody(BaseModel):
    model_config = ConfigDict(extra="allow")
    employee_id: str = Field(..., min_length=1, max_length=128)


@router.post("/api/identity/abstract")
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


@router.get("/api/me")
def me(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    coded = principal.coded_identity
    if not coded:
        raise HTTPException(status_code=400, detail="principal has no coded identity in this database")
    return svc.me(coded)


class BindPrincipalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sub: str = Field(..., min_length=1, max_length=64)
    coded_identity: str = Field(..., pattern=CODED_ID_PATTERN)


@router.post("/api/org/bind-principal")
def org_bind_principal(
    body: BindPrincipalBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    return svc.bind_principal(principal.sub, body.sub, body.coded_identity)


class OrgEdgeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manager_coded_id: str = Field(..., pattern=CODED_ID_PATTERN)
    report_coded_id: str = Field(..., pattern=CODED_ID_PATTERN)


@router.post("/api/org/edges")
def org_edges(
    body: OrgEdgeBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    return svc.add_org_edge(principal.sub, body.manager_coded_id, body.report_coded_id)
