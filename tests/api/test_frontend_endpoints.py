import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app, reset_service_for_tests
from scripts.ingest_fixtures import ingest
from shared.db import HermesDB
from shared.service import HermesService


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "fe.db"
    os.environ["HERMES_TEST_MODE"] = "1"
    ingest(Path("data/fixtures/pilot_population.json"), db_path)
    os.environ["HERMES_DB_PATH"] = str(db_path)
    os.environ.pop("HERMES_API_KEY", None)
    os.environ.pop("FUNCTION_AUTH_KEY", None)
    svc = HermesService(db=HermesDB(db_path))
    reset_service_for_tests(svc)
    with TestClient(app) as c:
        yield c


def _h(client):
    tok = client.post(
        "/api/auth/token",
        json={"sub": "demo-admin"},  # registry principal; roles are server-derived
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_dashboard_coded_only(client):
    r = client.get("/api/dashboard", headers=_h(client))
    assert r.status_code == 200
    body = r.json()
    assert body["coverage"]["coverage_pct"] >= 80
    for row in body["skill_distribution"]:
        assert "coded_identity" in row
        assert "display_name" not in row
        assert "name" not in row


def test_skills_and_roles(client):
    h = _h(client)
    skills = client.get("/api/skills", headers=h).json()["skills"]
    roles = client.get("/api/roles", headers=h).json()["roles"]
    ids = client.get("/api/identities", headers=h).json()["identities"]
    assert any(s["skill_id"] == "container_orchestration" for s in skills)
    assert any(r["role_id"] == "senior_cloud_engineer" for r in roles)
    assert all(i.startswith("EMP-") and len(i) == 12 for i in ids)
