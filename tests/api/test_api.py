import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app, reset_service_for_tests
from shared.db import HermesDB
from shared.service import HermesService
from scripts.ingest_fixtures import ingest


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["HERMES_TEST_MODE"] = "1"
    os.environ["IDENTITY_MAP_SECRET"] = "hermes-test-mode-secret-not-for-prod"
    os.environ["HERMES_JWT_SECRET"] = "hermes-test-jwt-secret-32chars!!"
    ingest(Path("data/fixtures/pilot_population.json"), db_path)
    os.environ["HERMES_DB_PATH"] = str(db_path)
    os.environ.pop("HERMES_API_KEY", None)
    os.environ.pop("FUNCTION_AUTH_KEY", None)
    svc = HermesService(db=HermesDB(db_path))
    reset_service_for_tests(svc)
    with TestClient(app) as c:
        yield c


# V2 auth: roles and coded identity are derived server-side from the synthetic demo
# registry; the token endpoint accepts only ``sub``. Legacy test principal names map to
# registry principals holding the role each test relies on.
_REGISTRY = {
    "mgr-1": "demo-manager",
    "mgr-2": "demo-manager-2",
    "stranger": "demo-employee-2",
    "admin-1": "demo-admin",
}


def _token(client, sub="mgr-1", roles=None, coded_identity=None):
    r = client.post("/api/auth/token", json={"sub": _REGISTRY.get(sub, sub)})
    assert r.status_code == 200
    return r.json()["access_token"]


def _auth(client, **kwargs):
    return {"Authorization": f"Bearer {_token(client, **kwargs)}"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["mode"] == "local-first"


def test_rank_and_resolve(client):
    h = _auth(client, sub="mgr-1")
    rank = client.post(
        "/api/fitness/rank",
        headers=h,
        json={
            "request_id": "api-k8s",
            "requester_id": "ignored-spoof",
            "required_skills": {"container_orchestration": 3},
            "shortlist_size": 3,
        },
    )
    assert rank.status_code == 200
    body = rank.json()
    assert body["candidates"]
    assert body["candidates"][0]["evidence_ids"]

    resolved = client.post(
        "/api/identity/resolve",
        headers=h,
        json={"request_id": "api-k8s", "requester_id": "ignored"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved"][0]["display_name"]


def test_shortlist_cap(client):
    h = _auth(client)
    rank = client.post(
        "/api/fitness/rank",
        headers=h,
        json={
            "request_id": "cap-test",
            "required_skills": {"container_orchestration": 2},
            "shortlist_size": 9999,
        },
    )
    assert rank.status_code == 200
    assert len(rank.json()["candidates"]) <= 10


def test_resolve_mismatch_forbidden(client):
    h1 = _auth(client, sub="mgr-1")
    client.post(
        "/api/fitness/rank",
        headers=h1,
        json={
            "request_id": "own-req",
            "required_skills": {"container_orchestration": 3},
            "shortlist_size": 2,
        },
    )
    h2 = _auth(client, sub="mgr-2")
    bad = client.post(
        "/api/identity/resolve",
        headers=h2,
        json={"request_id": "own-req"},
    )
    assert bad.status_code == 403


def test_gaps_acl(client):
    db = HermesDB(Path(os.environ["HERMES_DB_PATH"]))
    matrix = db.load_skills_matrix()
    # The subject must not be the stranger's own identity (self-access is allowed).
    stranger_coded = db.resolve_coded_for_source("E1005")
    coded = next(m.coded_identity for m in matrix if m.coded_identity != stranger_coded)
    role = db.get_role("senior_cloud_engineer")
    # employee without matching coded_identity and not manager of subject
    h = _auth(client, sub="stranger", roles=["employee"], coded_identity="EMP-deadbeef")
    r = client.post(
        "/api/fitness/gaps",
        headers=h,
        json={
            "coded_identity": coded,
            "role_id": role["role_id"],
            "role_name": role["role_name"],
            "required_skills": role["required_skills"],
        },
    )
    assert r.status_code == 403

    # admin allowed
    ha = _auth(client, sub="admin-1", roles=["admin"], coded_identity=None)
    ok = client.post(
        "/api/fitness/gaps",
        headers=ha,
        json={
            "coded_identity": coded,
            "role_id": role["role_id"],
            "role_name": role["role_name"],
            "required_skills": role["required_skills"],
        },
    )
    assert ok.status_code == 200


def test_decision_lifecycle(client):
    h = _auth(client, sub="mgr-1")
    rank = client.post(
        "/api/fitness/rank",
        headers=h,
        json={
            "request_id": "dec-1",
            "required_skills": {"container_orchestration": 3},
            "shortlist_size": 3,
        },
    )
    chosen = rank.json()["candidates"][0]["coded_identity"]
    d = client.post(
        "/api/staffing/dec-1/decision",
        headers=h,
        json={"status": "accepted", "chosen_coded_identity": chosen},
    )
    assert d.status_code == 200
    assert d.json()["status"] == "accepted"
    assert d.json()["engine_rank_of_choice"] == 1
