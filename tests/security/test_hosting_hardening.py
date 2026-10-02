"""Hosting readiness regressions (all data synthetic).

Pins the behaviours a host relies on:
  * security headers on every response, CSP relaxed only for the interactive API docs
  * /ready proves the DB is trusted and the audit chain verifies; a tampered chain -> 503
  * CORS origins come from HERMES_CORS_ORIGINS and a wildcard is never honoured
  * HERMES_ENV=production closes the demo token issuer and turns on HSTS
  * .env.example must load cleanly (it once set a removed variable and crashed startup)
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

import api.main as api_main  # noqa: E402
from scripts.ingest_fixtures import ingest  # noqa: E402
from shared.config import load_scoring_config  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "fixtures" / "pilot_population.json"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db_path = tmp_path / "hosting.db"
    ingest(FIXTURE, db_path, write_samples=False)
    monkeypatch.setenv("HERMES_DB_PATH", str(db_path))
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.delenv("FUNCTION_AUTH_KEY", raising=False)
    monkeypatch.delenv("HERMES_ENV", raising=False)
    api_main.reset_service_for_tests(None)
    with TestClient(api_main.app) as client:
        yield client, db_path
    api_main.reset_service_for_tests(None)


def test_security_headers_on_api_and_errors(env):
    client, _ = env
    for path in ("/health", "/api/overview", "/no-such-page"):
        resp = client.get(path)
        assert resp.headers["x-content-type-options"] == "nosniff", path
        assert resp.headers["x-frame-options"] == "DENY", path
        assert resp.headers["referrer-policy"] == "no-referrer", path
        assert "default-src 'self'" in resp.headers["content-security-policy"], path


def test_csp_forbids_third_party_scripts_and_framing(env):
    client, _ = env
    csp = client.get("/health").headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "http" not in csp  # no external origin is allow-listed anywhere


def test_docs_page_keeps_its_cdn_scripts(env):
    client, _ = env
    assert "content-security-policy" not in client.get("/docs").headers


def test_hsts_only_in_production(env, monkeypatch):
    client, _ = env
    assert "strict-transport-security" not in client.get("/health").headers
    monkeypatch.setenv("HERMES_ENV", "production")
    assert client.get("/health").headers["strict-transport-security"].startswith("max-age=")


def test_ready_ok_on_trusted_database(env):
    client, _ = env
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    # auth_mode/teams_provider_is_mock are operational visibility added for the
    # production smoke test (Phase 12) — additive, not a breaking change, but
    # this test originally pinned an exact {"status": "ready"} body and needs
    # updating to match rather than the feature being reverted to fit it.
    assert body["auth_mode"] == "development"
    assert body["teams_provider_is_mock"] is True


def test_ready_fails_when_audit_chain_is_tampered(env):
    client, db_path = env
    assert client.get("/ready").status_code == 200
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE audit_ledger SET payload_json = '{\"tampered\": true}' WHERE seq = 1")
    resp = client.get("/ready")
    assert resp.status_code == 503


def test_ready_fails_closed_on_untrusted_database(tmp_path, monkeypatch):
    """A legacy DB (data but no trust metadata) must never be reported ready."""
    good = tmp_path / "good.db"
    ingest(FIXTURE, good, write_samples=False)
    legacy = tmp_path / "legacy.db"
    legacy.write_bytes(good.read_bytes())
    with sqlite3.connect(legacy) as conn:
        conn.execute(
            "DELETE FROM hermes_meta "
            "WHERE key IN ('data_classification','identity_secret_fingerprint')"
        )
    monkeypatch.setenv("HERMES_DB_PATH", str(legacy))
    api_main.reset_service_for_tests(None)
    try:
        with TestClient(api_main.app) as client:
            resp = client.get("/ready")
            assert resp.status_code == 503
            assert resp.json()["error"] == "missing_trust_metadata"
    finally:
        api_main.reset_service_for_tests(None)


def test_cors_origins_default_and_env_override(monkeypatch):
    monkeypatch.delenv("HERMES_CORS_ORIGINS", raising=False)
    assert "http://localhost:5173" in api_main._cors_origins()
    monkeypatch.setenv("HERMES_CORS_ORIGINS", "https://hermes.example.com/, https://b.example.com")
    assert api_main._cors_origins() == ["https://hermes.example.com", "https://b.example.com"]


def test_cors_wildcard_is_never_honoured(monkeypatch):
    monkeypatch.setenv("HERMES_CORS_ORIGINS", "*, https://ok.example.com")
    assert api_main._cors_origins() == ["https://ok.example.com"]


def test_production_mode_closes_demo_token_issuer(env, monkeypatch):
    client, _ = env
    assert client.post("/api/auth/token", json={"sub": "demo-manager"}).status_code == 200
    monkeypatch.setenv("HERMES_ENV", "production")
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    try:
        assert client.post("/api/auth/token", json={"sub": "demo-manager"}).status_code == 403
    finally:
        monkeypatch.setenv("HERMES_TEST_MODE", "1")


def _parse_env_file(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def test_env_example_loads_without_configuration_error():
    values = _parse_env_file(ROOT / ".env.example")
    assert "HERMES_HALF_LIFE" not in values, "removed variable must not be shipped in the example"
    assert "HERMES_API_KEY" not in values, "the bundled UI cannot send an API key"
    load_scoring_config(env={k: v for k, v in values.items() if k.startswith("HERMES_")})


def test_dockerfile_copies_every_runtime_path():
    """The image once crashed on first boot: the DB schema and client-label guard were missing."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    required = (
        "COPY infra",
        "COPY taxonomy",
        "COPY api",
        "COPY src",
        "COPY data/fixtures",
        "client_names.example",
    )
    for needed in required:
        assert needed in dockerfile, f"Dockerfile does not copy {needed}"
    assert "client_names.txt" not in dockerfile.replace("client_names.example", "")
