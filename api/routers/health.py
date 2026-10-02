"""Health/readiness — unauthenticated system status. Extracted verbatim from main.py."""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, HTTPException

from api.dependencies import get_service, get_teams_provider
from shared.oidc_auth import auth_mode

router = APIRouter()


@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "hermes", "mode": "local-first"}


@router.get("/ready")
def ready() -> Dict:
    """Readiness probe: database opens, passes the trust policy, and the audit chain verifies.

    ``auth_mode``/``teams_provider_is_mock`` are operational visibility, not
    secrets — they let a deployment check (or the production smoke test
    automate checking) what mode it's actually running in without needing a
    valid token first. Neither field helps bypass anything.
    """
    svc = get_service()  # UntrustedDatabaseError -> 503 via the shared handler
    if svc.db.verify_audit_chain():
        raise HTTPException(status_code=503, detail="audit chain verification failed")
    try:
        teams_is_mock = bool(getattr(get_teams_provider(), "is_mock", True))
    except Exception:
        # TEAMS_MODE=production with no real registration -> construction itself
        # raises NotImplementedError. Readiness must still report that clearly,
        # not crash the probe over an optional feature.
        teams_is_mock = None
    return {"status": "ready", "auth_mode": auth_mode(), "teams_provider_is_mock": teams_is_mock}
