"""JWT session auth for Hermes (OIDC-replaceable issuer); claims are server-derived.

The token proves *who* the caller is (``sub``) and nothing else. Roles and coded
identity are resolved server-side from :mod:`shared.demo_identities` and the
database on every request. A token that carries ``roles`` or ``coded_identity``
claims was not minted by this issuer and is rejected as forged.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

import jwt

from shared.demo_identities import ADMIN, EMPLOYEE, MANAGER, demo_auth_enabled, lookup
from shared.errors import AuthenticationError
from shared.secrets import require_jwt_secret

#: Claims this issuer never emits; their presence means the token was forged.
FORBIDDEN_CLAIMS = ("roles", "coded_identity", "role", "groups")


@dataclass(frozen=True)
class AuthPrincipal:
    sub: str
    roles: tuple
    coded_identity: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return ADMIN in self.roles

    @property
    def is_manager(self) -> bool:
        return MANAGER in self.roles

    @property
    def is_employee(self) -> bool:
        return EMPLOYEE in self.roles

    def has_any_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)


def issue_token(sub: str, ttl_seconds: int = 3600) -> str:
    """Mint a token for a registered synthetic principal. Unknown subjects are refused."""
    if not demo_auth_enabled():
        raise AuthenticationError("local token issuer disabled outside local/test mode")
    if lookup(sub) is None:
        raise AuthenticationError("unknown principal", code="unknown_principal")
    now = int(time.time())
    return jwt.encode(
        {"sub": sub, "iat": now, "exp": now + ttl_seconds},
        require_jwt_secret(),
        algorithm="HS256",
    )


def verify_token(token: str) -> str:
    """Return the verified subject. Raises AuthenticationError on any defect."""
    try:
        payload = jwt.decode(
            token,
            require_jwt_secret(),
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("invalid or expired token") from exc
    if any(claim in payload for claim in FORBIDDEN_CLAIMS):
        raise AuthenticationError(
            "token carries client-asserted role or identity claims", code="forged_claims"
        )
    return str(payload["sub"])


def build_principal(
    sub: str, resolve_coded: Callable[[str], Optional[str]]
) -> AuthPrincipal:
    """Derive roles and coded identity server-side for a verified subject."""
    if not demo_auth_enabled():
        raise AuthenticationError(
            "no identity provider configured outside local/test mode", code="no_identity_provider"
        )
    entry = lookup(sub)
    if entry is None:
        raise AuthenticationError("unknown principal", code="unknown_principal")
    coded = resolve_coded(entry.employee_key) if entry.employee_key else None
    return AuthPrincipal(sub=entry.sub, roles=tuple(entry.roles), coded_identity=coded)
