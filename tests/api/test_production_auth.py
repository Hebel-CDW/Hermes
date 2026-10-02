"""AUTH_MODE=production end-to-end, through the real API — not just the OIDC
module in isolation. Proves: the demo registry is truly dead, a real OIDC
token reaches a route and gets the right role-gated response, RBAC is
unchanged (same AuthPrincipal/require_roles as development mode), and the
app refuses to even start with AUTH_MODE=production and no OIDC config.
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
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

import api.main as api_main  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.errors import ConfigurationError  # noqa: E402
from shared.oidc_auth import reset_oidc_caches_for_tests  # noqa: E402
from shared.service import HermesService  # noqa: E402

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

    def log_message(self, *a):
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
    issuer = f"http://127.0.0.1:{server.server_port}"
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


@contextmanager
def _prod_client(tmp_path, monkeypatch, issuer: str):
    """Everything AUTH_MODE=production needs to even START must be set BEFORE
    TestClient enters (that's what runs api/main.py's lifespan) — that ordering
    is itself the fail-closed property under test, not an incidental detail."""
    db_path = tmp_path / "prod.db"
    db = HermesDB(db_path)
    svc = HermesService(db=db)
    monkeypatch.setenv("AUTH_MODE", "production")
    monkeypatch.setenv("OIDC_ISSUER", issuer)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("OIDC_CLIENT_ID", "client-1")
    api_main.reset_service_for_tests(svc)
    with TestClient(api_main.app) as client:
        yield client
    api_main.reset_service_for_tests(None)


def test_demo_token_endpoint_is_disabled_in_production_auth_mode(tmp_path, monkeypatch):
    _, public_key = _make_keypair()
    with _real_idp(_jwk(public_key)) as issuer:
        with _prod_client(tmp_path, monkeypatch, issuer) as client:
            resp = client.post("/api/auth/token", json={"sub": "demo-admin"})
            assert resp.status_code == 403


def test_real_oidc_token_reaches_a_role_gated_route(tmp_path, monkeypatch):
    private_key, public_key = _make_keypair()
    with _real_idp(_jwk(public_key)) as issuer:
        with _prod_client(tmp_path, monkeypatch, issuer) as client:
            token = _sign(private_key, sub="real-user-1", iss=issuer, aud=AUDIENCE, roles=["manager"])
            resp = client.get("/api/skills", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200


def test_oidc_employee_cannot_reach_manager_only_route(tmp_path, monkeypatch):
    """Same RBAC model as development mode — require_roles is untouched."""
    private_key, public_key = _make_keypair()
    with _real_idp(_jwk(public_key)) as issuer:
        with _prod_client(tmp_path, monkeypatch, issuer) as client:
            token = _sign(private_key, sub="real-user-2", iss=issuer, aud=AUDIENCE, roles=["employee"])
            resp = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 403


def test_oidc_token_with_no_role_claim_is_denied_everywhere(tmp_path, monkeypatch):
    private_key, public_key = _make_keypair()
    with _real_idp(_jwk(public_key)) as issuer:
        with _prod_client(tmp_path, monkeypatch, issuer) as client:
            token = _sign(private_key, sub="real-user-3", iss=issuer, aud=AUDIENCE)
            resp = client.get("/api/skills", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 403


def test_forged_oidc_token_is_rejected_through_the_real_route(tmp_path, monkeypatch):
    _, public_key = _make_keypair()
    attacker_key, _ = _make_keypair()
    with _real_idp(_jwk(public_key)) as issuer:
        with _prod_client(tmp_path, monkeypatch, issuer) as client:
            forged = _sign(attacker_key, sub="real-user-4", iss=issuer, aud=AUDIENCE, roles=["admin"])
            resp = client.get("/api/skills", headers={"Authorization": f"Bearer {forged}"})
            assert resp.status_code == 401


def test_app_refuses_to_start_with_auth_mode_production_and_no_oidc_config(tmp_path, monkeypatch):
    """Phase 9: 'Production startup must reject unsafe authentication
    configuration.' Verified at the actual startup boundary (the lifespan
    context manager), not inferred from an HTTP response."""
    db_path = tmp_path / "prod2.db"
    db = HermesDB(db_path)
    svc = HermesService(db=db)
    monkeypatch.setenv("AUTH_MODE", "production")
    for var in ("OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_CLIENT_ID"):
        monkeypatch.delenv(var, raising=False)
    api_main.reset_service_for_tests(svc)
    try:
        with pytest.raises(ConfigurationError):
            with TestClient(api_main.app):
                pass
    finally:
        api_main.reset_service_for_tests(None)
