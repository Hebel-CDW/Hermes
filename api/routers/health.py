"""Health/readiness — unauthenticated system status. Extracted verbatim from main.py."""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, HTTPException

from api.dependencies import get_service

router = APIRouter()


@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "hermes", "mode": "local-first"}


@router.get("/ready")
def ready() -> Dict[str, str]:
    """Readiness probe: database opens, passes the trust policy, and the audit chain verifies."""
    svc = get_service()  # UntrustedDatabaseError -> 503 via the shared handler
    if svc.db.verify_audit_chain():
        raise HTTPException(status_code=503, detail="audit chain verification failed")
    return {"status": "ready"}
