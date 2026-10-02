"""Evidence staging/merge and the skills_matrix computation-run history. Extracted verbatim."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import get_service, require_api_key, require_roles
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN, MANAGER
from shared.models import EvidenceRecord
from shared.service import HermesService

router = APIRouter()


@router.get("/api/matrix/runs")
def matrix_runs(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    return {"runs": svc.db.list_computation_runs()}


@router.get("/api/matrix/runs/{run_id}")
def matrix_run(
    run_id: str = PathParam(..., min_length=1, max_length=128),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    return {"computation_run_id": run_id, "records": svc.db.load_matrix_as_of(run_id)}


class MergeBody(BaseModel):
    evidence: List[EvidenceRecord] = Field(..., min_length=1)


@router.post("/api/inference/merge")
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


class TicketItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: str = Field(..., min_length=1, max_length=128)
    ticket_number: str = Field(..., min_length=1, max_length=128)
    short_description: str = Field(..., min_length=1, max_length=4000)
    resolved_at: str = Field(..., min_length=10, max_length=64)


class TicketsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tickets: List[TicketItem] = Field(..., min_length=1, max_length=200)


@router.post("/api/ingest/tickets")
def ingest_tickets(
    body: TicketsBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, int]:
    return svc.ingest_tickets([item.model_dump() for item in body.tickets], principal.sub)
