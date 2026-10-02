"""Real OIDC validation, end-to-end — not mocked.

Spins up a real local HTTP server serving a real OIDC discovery document and a
real JWKS, signs real RS256 tokens with a real RSA keypair, and proves
verify_oidc_token/build_oidc_principal perform genuine signature, issuer,
audience and expiry validation against it — the same code path a real IdP
(Entra ID or otherwise) would be validated through, minus the live tenant.
"""

from __future__ import annotations

import http.server
import json
import os
import threading
import time
from contextlib import contextmanager

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

os.environ.setdefault("HERMES_TEST_MODE", "1")

from shared.auth import AuthPrincipal  # noqa: E402
from shared.errors import AuthenticationError, ConfigurationError  # noqa: E402
from shared.oidc_auth import (  # noqa: E402
    OIDCConfig,
    auth_mode,
    build_oidc_principal,
    is_production_auth,
    load_oidc_config,
    map_roles,
    reset_oidc_caches_for_tests,
    verify_oidc_token,
)

AUDIENCE = "hermes-api"
KID = "test-key-1"


def _make_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _jwk(public_key) -> dict:
    jwk = json.loads(RSAAlgorithm(RSAAlgorithm.SHA256).to_jwk(public_key))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return jwk


class _Handler(http.server.BaseHTTPRequestHandler):
    jwks: dict = {}
    issuer: str = ""

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        if self.path == "/.well-known/openid-configuration":
            body = json.dumps({"issuer": self.issuer, "jwks_uri": f"{self.issuer}/jwks.json"}).encode()
        elif self.path == "/jwks.json":
            body = json.dumps(self.jwks).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@contextmanager
def _real_idp(jwk: dict):
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_port
    issuer = f"http://127.0.0.1:{port}"
    _Handler.jwks = {"keys": [jwk]}
    _Handler.issuer = issuer
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield issuer
    finally:
        server.shutdown()
        reset_oidc_caches_for_tests()


def _sign(private_key, **claims) -> str:
    now = int(time.time())
    payload = {"iat": now, "exp": now + 300, **claims}
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": KID})


def test_auth_mode_defaults_to_development(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    assert auth_mode() == "development"
    assert is_production_auth() is False


def test_auth_mode_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "yolo")
    with pytest.raises(ConfigurationError):
        auth_mode()


def test_load_oidc_config_fails_closed_when_unset(monkeypatch):
    for var in ("OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_CLIENT_ID"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ConfigurationError):
        load_oidc_config()


def test_valid_real_rs256_token_verifies_end_to_end():
    private_key, public_key = _make_keypair()
    jwk = _jwk(public_key)
    with _real_idp(jwk) as issuer:
        token = _sign(private_key, sub="user-1", iss=issuer, aud=AUDIENCE, roles=["manager"])
        config = OIDCConfig(issuer=issuer, audience=AUDIENCE, client_id="client-1")
        claims = verify_oidc_token(token, config)
        assert claims["sub"] == "user-1"
        assert map_roles(claims, config) == ("manager",)


def test_wrong_issuer_is_rejected():
    private_key, public_key = _make_keypair()
    jwk = _jwk(public_key)
    with _real_idp(jwk) as issuer:
        # Token claims a DIFFERENT issuer than the one it was actually fetched from.
        token = _sign(private_key, sub="user-1", iss="https://not-the-real-idp.test", aud=AUDIENCE)
        config = OIDCConfig(issuer=issuer, audience=AUDIENCE, client_id="client-1")
        with pytest.raises(AuthenticationError):
            verify_oidc_token(token, config)


def test_wrong_audience_is_rejected():
    private_key, public_key = _make_keypair()
    jwk = _jwk(public_key)
    with _real_idp(jwk) as issuer:
        token = _sign(private_key, sub="user-1", iss=issuer, aud="some-other-app")
        config = OIDCConfig(issuer=issuer, audience=AUDIENCE, client_id="client-1")
        with pytest.raises(AuthenticationError):
            verify_oidc_token(token, config)


def test_expired_token_is_rejected():
    private_key, public_key = _make_keypair()
    jwk = _jwk(public_key)
    with _real_idp(jwk) as issuer:
        now = int(time.time())
        token = jwt.encode(
            {"sub": "user-1", "iss": issuer, "aud": AUDIENCE, "iat": now - 1000, "exp": now - 500},
            private_key, algorithm="RS256", headers={"kid": KID},
        )
        config = OIDCConfig(issuer=issuer, audience=AUDIENCE, client_id="client-1")
        with pytest.raises(AuthenticationError):
            verify_oidc_token(token, config)


def test_tampered_signature_is_rejected():
    private_key, public_key = _make_keypair()
    jwk = _jwk(public_key)
    with _real_idp(jwk) as issuer:
        token = _sign(private_key, sub="user-1", iss=issuer, aud=AUDIENCE)
        tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]
        config = OIDCConfig(issuer=issuer, audience=AUDIENCE, client_id="client-1")
        with pytest.raises(AuthenticationError):
            verify_oidc_token(tampered, config)


def test_token_signed_by_a_different_key_is_rejected():
    """Defense against a forged token that supplies its OWN valid-looking kid/key
    but was never signed by the real IdP's private key."""
    _, public_key = _make_keypair()
    attacker_key, _ = _make_keypair()
    jwk = _jwk(public_key)
    with _real_idp(jwk) as issuer:
        forged = _sign(attacker_key, sub="user-1", iss=issuer, aud=AUDIENCE, roles=["admin"])
        config = OIDCConfig(issuer=issuer, audience=AUDIENCE, client_id="client-1")
        with pytest.raises(AuthenticationError):
            verify_oidc_token(forged, config)


def test_unknown_role_claims_are_dropped_not_granted():
    private_key, public_key = _make_keypair()
    jwk = _jwk(public_key)
    with _real_idp(jwk) as issuer:
        token = _sign(private_key, sub="user-1", iss=issuer, aud=AUDIENCE, roles=["manager", "super-admin-typo"])
        config = OIDCConfig(issuer=issuer, audience=AUDIENCE, client_id="client-1")
        claims = verify_oidc_token(token, config)
        assert map_roles(claims, config) == ("manager",)


def test_no_role_claim_at_all_grants_nothing():
    private_key, public_key = _make_keypair()
    jwk = _jwk(public_key)
    with _real_idp(jwk) as issuer:
        token = _sign(private_key, sub="user-1", iss=issuer, aud=AUDIENCE)
        config = OIDCConfig(issuer=issuer, audience=AUDIENCE, client_id="client-1")
        claims = verify_oidc_token(token, config)
        assert map_roles(claims, config) == ()


def test_build_oidc_principal_resolves_coded_identity_via_callback():
    private_key, public_key = _make_keypair()
    jwk = _jwk(public_key)
    with _real_idp(jwk) as issuer:
        token = _sign(private_key, sub="user-1", iss=issuer, aud=AUDIENCE, roles=["employee"])
        config = OIDCConfig(issuer=issuer, audience=AUDIENCE, client_id="client-1")
        principal = build_oidc_principal(token, config, resolve_coded=lambda sub: f"EMP-{sub}")
        assert principal == AuthPrincipal(sub="user-1", roles=("employee",), coded_identity="EMP-user-1")
