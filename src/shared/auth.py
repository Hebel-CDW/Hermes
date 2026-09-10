"""JWT session auth for Hermes (OIDC-replaceable issuer)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import jwt

from shared.secrets import require_jwt_secret


@dataclass(frozen=True)
class AuthPrincipal:
    sub: str
    roles: tuple
    coded_identity: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    @property
    def is_manager(self) -> bool:
        return "manager" in self.roles or self.is_admin


def issue_token(
    sub: str,
    roles: List[str],
    coded_identity: Optional[str] = None,
    ttl_seconds: int = 3600,
) -> str:
    secret = require_jwt_secret()
    now = int(time.time())
    payload = {
        "sub": sub,
        "roles": roles,
        "coded_identity": coded_identity,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str) -> AuthPrincipal:
    secret = require_jwt_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise PermissionError("invalid or expired token") from exc
    roles = tuple(payload.get("roles") or ())
    return AuthPrincipal(
        sub=str(payload["sub"]),
        roles=roles,
        coded_identity=payload.get("coded_identity"),
    )
