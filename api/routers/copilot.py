"""Copilot: grounded plain-English answers for managers and employees. Advisory only.

Never touches scoring, evidence, ranking or the audit chain. The facts given to the model are
built from what the signed-in principal may already see (a manager sees their own requests and
the workforce; an employee sees only themselves). If the model is down the endpoint answers with
an honest offline summary instead of an error.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ai.services.copilot import ask, employee_facts, manager_facts
from api import dependencies
from api.dependencies import get_llm_provider, get_service, require_api_key, require_roles
from shared.auth import AuthPrincipal
from shared.demo_identities import EMPLOYEE, MANAGER
from shared.errors import ConfigurationError
from shared.rate_limit import PersistentRateLimiter
from shared.service import HermesService

router = APIRouter()

COPILOT_LIMITER = PersistentRateLimiter(max_calls=20, window_seconds=60.0, name="copilot")


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=600)
    request_id: Optional[str] = Field(None, max_length=64)


def _provider():
    try:
        return get_llm_provider()
    except ConfigurationError:
        return None


@router.get("/api/copilot/status")
def copilot_status(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER)),
) -> Dict[str, Any]:
    model = os.getenv("OLLAMA_MODEL")
    base = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
    online = False
    if model:
        try:
            tags = httpx.get(f"{base}/api/tags", timeout=1.5).json()
            online = any(m.get("name") == model for m in tags.get("models", []))
        except (httpx.HTTPError, ValueError):
            online = False
    return {"online": online, "model": model if online else None}


@router.post("/api/copilot/ask")
def copilot_ask(
    body: AskBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    if not COPILOT_LIMITER.allow(principal.sub):
        raise HTTPException(status_code=429, detail="copilot rate limit exceeded")
    is_manager = principal.has_any_role(MANAGER)
    if is_manager:
        facts = manager_facts(svc, principal.sub, body.request_id, body.question)
        role = "manager"
    else:
        if not principal.coded_identity:
            raise HTTPException(status_code=400, detail="principal has no coded identity in this database")
        facts = employee_facts(svc, principal.coded_identity)
        role = "employee"
    result = ask(_provider(), facts, body.question, role)
    result["model"] = os.getenv("OLLAMA_MODEL") if result["source"] == "model" else None
    return result
