"""LLM-assisted work-request parsing. Advisory only.

This endpoint never touches ranking, evidence, or audit. It takes a manager's
free-text description and returns a *proposal* the manager must still confirm;
the confirmed skills then go to the existing, completely unchanged
POST /api/fitness/rank. If the LLM is unavailable or misconfigured, this
endpoint answers with ``available: false`` rather than an error — Hermes's
core ranking workflow must never depend on the LLM (Phase 16).
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ai.provider import LLMUnavailableError
from ai.services.work_requirement import LLMExtractionError, extract_work_requirement
from api.dependencies import get_llm_provider, require_api_key, require_roles
from shared.auth import AuthPrincipal
from shared.demo_identities import MANAGER
from shared.errors import ConfigurationError

router = APIRouter()


class ParseRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(..., min_length=1, max_length=2000)


@router.post("/api/requests/parse")
def parse_work_request(
    body: ParseRequestBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER)),
) -> Dict[str, Any]:
    del principal
    try:
        provider = get_llm_provider()
        proposal = extract_work_requirement(provider, body.description)
    except (ConfigurationError, LLMUnavailableError, LLMExtractionError) as exc:
        return {"available": False, "proposal": None, "reason": str(exc)}
    return {"available": True, "proposal": proposal.model_dump(), "reason": None}
