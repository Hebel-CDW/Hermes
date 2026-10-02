"""Token issuance and session introspection. Extracted verbatim from main.py."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import get_principal, get_service, require_api_key
from shared.auth import AuthPrincipal, issue_token
from shared.demo_identities import demo_auth_enabled
from shared.service import HermesService

router = APIRouter()


class TokenBody(BaseModel):
    """Only the principal id. Roles and coded identity are never client-supplied."""

    model_config = ConfigDict(extra="forbid")
    sub: str = Field(..., min_length=1, max_length=64)


@router.post("/api/auth/token")
def auth_token(body: TokenBody) -> Dict[str, Any]:
    """Local/test issuer for the synthetic demo registry. Replace with OIDC in production."""
    if not demo_auth_enabled():
        raise HTTPException(status_code=403, detail="token stub disabled outside local/test")
    return {"access_token": issue_token(body.sub), "token_type": "bearer"}


@router.get("/api/session")
def session_view(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(get_principal),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """Who the server says the caller is, and whether the served database is synthetic or real.

    The UI uses this instead of any local role state.
    """
    return {
        "sub": principal.sub,
        "roles": list(principal.roles),
        "coded_identity": principal.coded_identity,
        "data_classification": svc.db.get_meta("data_classification"),
    }
