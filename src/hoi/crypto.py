"""At-rest encryption for restricted documents and finance data (two independent keys).

Keys come from HOI_DOC_KEY / HOI_FINANCE_KEY (Fernet urlsafe-base64 32-byte keys; a secret manager in
production). A deterministic local key is allowed only where demo auth is already allowed (local/test),
never in a production configuration. Key material is never logged.
"""

from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache

from cryptography.fernet import Fernet

from shared.demo_identities import demo_auth_enabled
from shared.errors import ConfigurationError

_ENV = {"doc": "HOI_DOC_KEY", "finance": "HOI_FINANCE_KEY"}


@lru_cache(maxsize=8)
def _fernet(purpose: str, configured: str) -> Fernet:
    if configured:
        try:
            return Fernet(configured.encode())
        except Exception as exc:  # noqa: BLE001 - never echo the key
            raise ConfigurationError(f"{_ENV[purpose]} is not a valid Fernet key") from exc
    if not demo_auth_enabled():
        raise ConfigurationError(f"{_ENV[purpose]} must be set outside local/test mode")
    digest = hashlib.sha256(f"hermes-hoi-local-{purpose}-key".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def cipher(purpose: str) -> Fernet:
    return _fernet(purpose, os.getenv(_ENV[purpose], "").strip())


def encrypt_text(purpose: str, value: str) -> str:
    return cipher(purpose).encrypt(value.encode()).decode()


def decrypt_text(purpose: str, token: str) -> str:
    return cipher(purpose).decrypt(token.encode()).decode()
