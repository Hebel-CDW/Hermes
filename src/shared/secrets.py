"""Fail-closed secret validation for Hermes."""

from __future__ import annotations

import os
from typing import Optional

DENIED_IDENTITY_SECRETS = frozenset(
    {
        "",
        "local-dev-secret",
        "local-dev-secret-not-for-production",
        "fixture-secret",
        "test-secret",
        "CHANGE_ME",
    }
)


def is_test_mode() -> bool:
    return os.getenv("HERMES_TEST_MODE", "").strip() in {"1", "true", "TRUE", "yes"}


def require_identity_map_secret(explicit: Optional[str] = None) -> str:
    """Return mapping secret or raise. Test mode allows denied defaults."""
    secret = (explicit if explicit is not None else os.getenv("IDENTITY_MAP_SECRET", "")).strip()
    if is_test_mode():
        return secret or "hermes-test-mode-secret-not-for-prod"
    if not secret or secret in DENIED_IDENTITY_SECRETS:
        raise RuntimeError(
            "IDENTITY_MAP_SECRET must be set to a strong unique value "
            "(denied defaults like local-dev-secret). Set HERMES_TEST_MODE=1 only for pytest."
        )
    if len(secret) < 16:
        raise RuntimeError("IDENTITY_MAP_SECRET must be at least 16 characters")
    return secret


def require_jwt_secret() -> str:
    secret = os.getenv("HERMES_JWT_SECRET", "").strip()
    if is_test_mode():
        return secret or "hermes-test-jwt-secret-32chars!!"
    if not secret or secret in DENIED_IDENTITY_SECRETS or len(secret) < 16:
        raise RuntimeError(
            "HERMES_JWT_SECRET must be set to a strong unique value (>=16 chars) outside test mode"
        )
    return secret
