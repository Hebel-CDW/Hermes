"""Production OIDC/JWT authentication boundary (Entra ID, or any standard OIDC IdP).

``AUTH_MODE=development`` (the default) keeps the existing demo registry
(shared.auth) exactly as it was — this module changes nothing about it and is
never consulted. ``AUTH_MODE=production`` switches ``get_principal``
(api/dependencies.py) to real signature validation via the IdP's published
JWKS (fetched through standard OIDC discovery, not a guessed URL), plus
issuer, audience and expiry checks.

Fail-closed, same policy as shared/secrets.py: missing OIDC_ISSUER /
OIDC_AUDIENCE / OIDC_CLIENT_ID while AUTH_MODE=production raises
ConfigurationError at startup (api/main.py's lifespan), not on first request.

Role mapping is deliberately conservative: a claim value that isn't exactly
one of the three known role names is dropped, not granted. A typo in an
Entra App Role, or a role claim nobody configured yet, costs access — it
never grants it. There is no hardcoded identity registry here at all; every
claim comes from the token the IdP actually signed. Binding a sign-in to a
coded identity reuses the existing admin action (POST /api/org/bind-principal
-> db.coded_for_principal), not a new mechanism.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, FrozenSet, Tuple

import httpx
import jwt
from jwt import PyJWKClient

from shared.auth import AuthPrincipal
from shared.errors import AuthenticationError, ConfigurationError

_KNOWN_ROLES: FrozenSet[str] = frozenset({"employee", "manager", "admin", "sales", "finance", "hr"})
_DISCOVERY_TIMEOUT_S = 10.0


def auth_mode() -> str:
    mode = os.getenv("AUTH_MODE", "development").strip().lower()
    if mode not in ("development", "production"):
        raise ConfigurationError(f"AUTH_MODE must be 'development' or 'production', got {mode!r}")
    return mode


def is_production_auth() -> bool:
    return auth_mode() == "production"


@dataclass(frozen=True)
class OIDCConfig:
    issuer: str
    audience: str
    client_id: str
    role_claim: str = "roles"


def load_oidc_config() -> OIDCConfig:
    """Fail-closed: raises ConfigurationError if any required variable is missing.

    Called once at startup (api/main.py's lifespan) so a misconfigured
    deployment never starts, and again per-request here (cheap: just env
    reads) so the two can never drift.
    """
    issuer = os.getenv("OIDC_ISSUER", "").strip()
    audience = os.getenv("OIDC_AUDIENCE", "").strip()
    client_id = os.getenv("OIDC_CLIENT_ID", "").strip()
    role_claim = os.getenv("OIDC_ROLE_CLAIM", "roles").strip() or "roles"
    missing = [name for name, value in (
        ("OIDC_ISSUER", issuer), ("OIDC_AUDIENCE", audience), ("OIDC_CLIENT_ID", client_id),
    ) if not value]
    if missing:
        raise ConfigurationError(
            f"AUTH_MODE=production requires {', '.join(missing)} to be set"
        )
    return OIDCConfig(issuer=issuer, audience=audience, client_id=client_id, role_claim=role_claim)


# Per-issuer caches: real OIDC discovery + JWKS fetches are network calls, and
# JWKS endpoints are built to be cached (keys rotate rarely, on their own schedule).
_discovery_cache: Dict[str, dict] = {}
_jwks_client_cache: Dict[str, PyJWKClient] = {}


def reset_oidc_caches_for_tests() -> None:
    _discovery_cache.clear()
    _jwks_client_cache.clear()


def _discover(issuer: str) -> dict:
    if issuer not in _discovery_cache:
        url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
        resp = httpx.get(url, timeout=_DISCOVERY_TIMEOUT_S)
        resp.raise_for_status()
        _discovery_cache[issuer] = resp.json()
    return _discovery_cache[issuer]


def _jwks_client(issuer: str) -> PyJWKClient:
    if issuer not in _jwks_client_cache:
        jwks_uri = _discover(issuer)["jwks_uri"]
        _jwks_client_cache[issuer] = PyJWKClient(jwks_uri)
    return _jwks_client_cache[issuer]


def verify_oidc_token(token: str, config: OIDCConfig) -> dict:
    """Validate signature (against the IdP's own published key, fetched via
    standard discovery), issuer, audience, and expiry. Returns the decoded
    claims only on success. Raises AuthenticationError on any defect —
    bad signature, wrong issuer/audience, expired, malformed, or the IdP
    being unreachable. Never returns a partially-validated claim set.
    """
    try:
        signing_key = _jwks_client(config.issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.audience,
            issuer=config.issuer,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError(f"invalid OIDC token: {exc}") from exc
    except httpx.HTTPError as exc:
        raise AuthenticationError(f"could not reach identity provider: {exc}") from exc
    return claims


def map_roles(claims: dict, config: OIDCConfig) -> Tuple[str, ...]:
    raw = claims.get(config.role_claim) or []
    if isinstance(raw, str):
        raw = [raw]
    return tuple(sorted({r for r in raw if r in _KNOWN_ROLES}))


def build_oidc_principal(token: str, config: OIDCConfig, resolve_coded) -> AuthPrincipal:
    """``resolve_coded(sub) -> Optional[str]`` — callers pass
    ``svc.db.coded_for_principal``, the same lookup the demo path uses after
    an admin has linked this sign-in via POST /api/org/bind-principal.
    """
    claims = verify_oidc_token(token, config)
    sub = str(claims["sub"])
    roles = map_roles(claims, config)
    coded = resolve_coded(sub)
    return AuthPrincipal(sub=sub, roles=roles, coded_identity=coded)
