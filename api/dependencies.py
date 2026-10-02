"""Shared FastAPI dependencies: auth, the service singleton, and its test-reset hook.

Extracted verbatim from ``api/main.py`` — no behavior changed. Every route across
every router depends on these the same way the monolithic ``main.py`` did.

Import direction: routers -> this module -> shared.* -> database. This module
never imports from ``api.routers`` or ``api.main`` (no reverse/circular import).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, Header, HTTPException

from shared.auth import AuthPrincipal, build_principal, verify_token
from shared.db import HermesDB
from shared.db_trust import ensure_database_trusted
from shared.errors import AuthorizationError
from shared.rate_limit import RateLimiter
from shared.service import HermesService

_SERVICE: Optional[HermesService] = None

#: Shared across routers that rate-limit a specific action (identity/resolve, team/declare).
#: Reset alongside the service singleton so tests get a clean window per request/service swap.
RESOLVE_LIMITER = RateLimiter(max_calls=10, window_seconds=60.0)
DECLARE_LIMITER = RateLimiter(max_calls=10, window_seconds=60.0)


def get_service() -> HermesService:
    """Open the configured database — only if it passes the trust policy."""
    global _SERVICE
    if _SERVICE is None:
        db_path = os.getenv("HERMES_DB_PATH")
        db = HermesDB(Path(db_path) if db_path else None)
        svc = HermesService(db=db)
        ensure_database_trusted(db, svc._identity_secret)  # raises UntrustedDatabaseError -> 503
        _SERVICE = svc
    return _SERVICE


def reset_service_for_tests(service: Optional[HermesService]) -> None:
    """Swap the service and start fresh rate-limit windows (tests / demo only)."""
    global _SERVICE, RESOLVE_LIMITER, DECLARE_LIMITER
    _SERVICE = service
    RESOLVE_LIMITER = RateLimiter(max_calls=10, window_seconds=60.0)
    DECLARE_LIMITER = RateLimiter(max_calls=10, window_seconds=60.0)


def require_api_key(
    x_api_key: Optional[str] = Header(default=None),
    x_functions_key: Optional[str] = Header(default=None),
) -> None:
    expected = os.getenv("HERMES_API_KEY") or os.getenv("FUNCTION_AUTH_KEY") or ""
    if not expected:
        return
    provided = x_api_key or x_functions_key
    if provided != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def get_principal(
    authorization: Optional[str] = Header(default=None),
    x_hermes_token: Optional[str] = Header(default=None),
    svc: HermesService = Depends(get_service),
) -> AuthPrincipal:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif x_hermes_token:
        token = x_hermes_token.strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    sub = verify_token(token)  # AuthenticationError -> 401

    def resolve(employee_key: str) -> Optional[str]:
        bound = svc.db.coded_for_principal(sub)
        if bound:
            return bound
        return svc.db.resolve_coded_for_source(employee_key)

    return build_principal(sub, resolve)


def require_roles(*allowed: str):
    def _dependency(principal: AuthPrincipal = Depends(get_principal)) -> AuthPrincipal:
        if not principal.has_any_role(*allowed):
            raise AuthorizationError(
                f"role not permitted for this operation (requires one of {sorted(allowed)})"
            )
        return principal

    return _dependency
