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

from ai.provider import LLMProvider
from shared.auth import AuthPrincipal, build_principal, verify_token
from shared.db import HermesDB
from shared.db_trust import ensure_database_trusted
from shared.errors import AuthorizationError
from shared.oidc_auth import build_oidc_principal, is_production_auth, load_oidc_config
from shared.rate_limit import PersistentRateLimiter
from shared.service import HermesService

_SERVICE: Optional[HermesService] = None
_LLM_PROVIDER: Optional[LLMProvider] = None

#: Shared across routers that rate-limit a specific action (identity/resolve, team/declare,
#: requests/parse). Reset alongside the service singleton so tests get a clean window per
#: request/service swap. PersistentRateLimiter.allow(key, db) checks db.dialect itself:
#: in-memory (unchanged) for SQLite, a shared `rate_limit_hits` table for PostgreSQL — a real
#: replica-bypass gap found via a two-instance test during the PostgreSQL migration spike.
RESOLVE_LIMITER = PersistentRateLimiter(max_calls=10, window_seconds=60.0, name="resolve")
DECLARE_LIMITER = PersistentRateLimiter(max_calls=10, window_seconds=60.0, name="declare")
#: requests/parse calls a synchronous, potentially-slow external LLM — found during the V3
#: QA pass to be the one write-adjacent endpoint with no limiter at all (every comparable
#: endpoint has one). A single-process local Ollama is cheap to hammer into unresponsiveness
#: otherwise, and a future hosted LLM provider would make that an unbounded cost, not just latency.
PARSE_LIMITER = PersistentRateLimiter(max_calls=10, window_seconds=60.0, name="parse")


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
    global _SERVICE, RESOLVE_LIMITER, DECLARE_LIMITER, PARSE_LIMITER
    _SERVICE = service
    RESOLVE_LIMITER = PersistentRateLimiter(max_calls=10, window_seconds=60.0, name="resolve")
    DECLARE_LIMITER = PersistentRateLimiter(max_calls=10, window_seconds=60.0, name="declare")
    PARSE_LIMITER = PersistentRateLimiter(max_calls=10, window_seconds=60.0, name="parse")


def get_llm_provider() -> LLMProvider:
    """Lazily construct the configured LLM provider (Ollama by default).

    Deliberately lazy and fail-at-call-time, not at import time: a repo clone
    with no Ollama configured must still import, start, and serve every other
    route. Only the assist router (api/routers/assist.py) ever calls this, and
    it catches ConfigurationError/LLMUnavailableError and answers with a clean
    "assist unavailable, continue manually" response (Phase 16).
    """
    global _LLM_PROVIDER
    if _LLM_PROVIDER is None:
        from ai.ollama_provider import OllamaProvider

        _LLM_PROVIDER = OllamaProvider()  # raises ConfigurationError if OLLAMA_MODEL unset
    return _LLM_PROVIDER


def reset_llm_provider_for_tests(provider: Optional[LLMProvider]) -> None:
    """Swap the LLM provider (tests only) — e.g. inject a MockLLMProvider so no
    test depends on a running Ollama. Passing None forces the next call to
    reconstruct the real OllamaProvider from the current environment."""
    global _LLM_PROVIDER
    _LLM_PROVIDER = provider


_TEAMS_PROVIDER = None


def get_teams_provider():
    """TEAMS_MODE=production constructs MicrosoftTeamsProvider, which raises
    NotImplementedError on construction (it is a documented stub, not a
    working integration — see integrations/teams/microsoft_provider.py).
    Anything else (the default) uses MockTeamsProvider. Never silently
    substitutes one for the other — the caller finds out exactly which it got
    via the provider's own ``is_mock`` attribute.
    """
    global _TEAMS_PROVIDER
    if _TEAMS_PROVIDER is None:
        if os.getenv("TEAMS_MODE", "development").strip().lower() == "production":
            from integrations.teams.microsoft_provider import MicrosoftTeamsProvider

            _TEAMS_PROVIDER = MicrosoftTeamsProvider()  # raises NotImplementedError today
        else:
            from integrations.teams.mock_provider import MockTeamsProvider

            _TEAMS_PROVIDER = MockTeamsProvider()
    return _TEAMS_PROVIDER


def reset_teams_provider_for_tests(provider) -> None:
    global _TEAMS_PROVIDER
    _TEAMS_PROVIDER = provider


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

    if is_production_auth():
        # Real OIDC: signature/issuer/audience/expiry verified against the IdP's own
        # published keys. No hardcoded registry — every claim comes from the token.
        # ConfigurationError (missing OIDC_* env) -> 500; AuthenticationError -> 401.
        # Both already route through api/main.py's global HermesError handler.
        config = load_oidc_config()
        return build_oidc_principal(token, config, resolve_coded=svc.db.coded_for_principal)

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
