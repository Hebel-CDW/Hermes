"""Fail-closed secret validation for Hermes (explicit secret trust policy).

Policy
------
* **Test / synthetic mode** (``HERMES_TEST_MODE=1``): the published fixture secrets
  are allowed, because only synthetic people are tokenised.
* **Everything else**: published fixture secrets and known weak defaults are
  rejected outright, whether or not the test-mode flag is set.
* **Real-data ingestion**: additionally refuses test mode, and requires a secret of
  at least ``REAL_DATA_MIN_LENGTH`` characters with reasonable variety.

Secrets are never logged or echoed in error messages.
"""

from __future__ import annotations

import os
from typing import Optional

#: Secrets committed to this repository (conftest, CI, fallbacks). Anyone with the
#: source knows them, so any identity derived from them is reversible.
PUBLISHED_SECRETS = frozenset(
    {
        "hermes-test-mode-secret-not-for-prod",
        "hermes-test-jwt-secret-32chars!!",
    }
)

DENIED_IDENTITY_SECRETS = frozenset(
    {
        "",
        "local-dev-secret",
        "local-dev-secret-not-for-production",
        "fixture-secret",
        "test-secret",
        "CHANGE_ME",
    }
) | PUBLISHED_SECRETS

REAL_DATA_MIN_LENGTH = 32
REAL_DATA_MIN_DISTINCT_CHARS = 10


def is_test_mode() -> bool:
    return os.getenv("HERMES_TEST_MODE", "").strip() in {"1", "true", "TRUE", "yes"}


def require_identity_map_secret(explicit: Optional[str] = None) -> str:
    """Return mapping secret or raise. Only test mode may use the fixture secret."""
    secret = (explicit if explicit is not None else os.getenv("IDENTITY_MAP_SECRET", "")).strip()
    if is_test_mode():
        return secret or "hermes-test-mode-secret-not-for-prod"
    if not secret or secret in DENIED_IDENTITY_SECRETS:
        raise RuntimeError(
            "IDENTITY_MAP_SECRET must be set to a strong unique value "
            "(published fixture secrets and denied defaults are rejected). "
            "Set HERMES_TEST_MODE=1 only for synthetic data."
        )
    if len(secret) < 16:
        raise RuntimeError("IDENTITY_MAP_SECRET must be at least 16 characters")
    return secret


def validate_real_data_secret(secret: str) -> None:
    """Raise unless ``secret`` is acceptable for tokenising real people."""
    if not secret or secret in DENIED_IDENTITY_SECRETS:
        raise RuntimeError(
            "Refusing to tokenise real data with a missing, denylisted, or published "
            "secret: coded identities would be reversible by anyone with the repository."
        )
    if len(secret) < REAL_DATA_MIN_LENGTH:
        raise RuntimeError(
            f"Real-data IDENTITY_MAP_SECRET must be at least {REAL_DATA_MIN_LENGTH} characters"
        )
    if len(set(secret)) < REAL_DATA_MIN_DISTINCT_CHARS:
        raise RuntimeError("Real-data IDENTITY_MAP_SECRET has too little character variety")


def require_real_data_ingest_secret() -> str:
    """Secret for ingesting REAL people (Phase 8 workbook / certificates).

    Refuses test mode outright, then applies :func:`validate_real_data_secret`.
    The test-mode flag is not the only check: supplying the published fixture
    secret *without* the flag is also rejected.
    """
    if is_test_mode():
        raise RuntimeError(
            "Refusing to tokenise real data in HERMES_TEST_MODE. Coded identities "
            "would be derived from the published fixture secret and be trivially "
            "reversible. Unset HERMES_TEST_MODE and export a strong unique "
            "IDENTITY_MAP_SECRET before ingesting the real workbook."
        )
    secret = os.getenv("IDENTITY_MAP_SECRET", "").strip()
    validate_real_data_secret(secret)
    return secret


def require_jwt_secret() -> str:
    secret = os.getenv("HERMES_JWT_SECRET", "").strip()
    if is_test_mode():
        return secret or "hermes-test-jwt-secret-32chars!!"
    if not secret or secret in DENIED_IDENTITY_SECRETS or len(secret) < 16:
        raise RuntimeError(
            "HERMES_JWT_SECRET must be set to a strong unique value (>=16 chars, not a "
            "published fixture secret) outside test mode"
        )
    return secret
