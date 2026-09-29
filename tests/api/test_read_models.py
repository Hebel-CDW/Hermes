"""UI read-model endpoints: RBAC, ownership, verbatim results, no side effects (synthetic data)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("HERMES_TEST_MODE", "1")

import api.main as api_main  # noqa: E402
from scripts.ingest_fixtures import ingest  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "pilot_population.json"
RANK = {"request_id": "rm-1", "required_skills": {"container_orchestration": 3, "azure_networking": 2},
        "shortlist_size": 3, "min_coverage_ratio": 0.5}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "rm.db"
    ingest(FIXTURE, db, write_samples=False)
    monkeypatch.setenv("HERMES_DB_PATH", str(db))
    api_main.reset_service_for_tests(None)
    with TestClient(api_main.app) as client:
        yield client, db
    api_main.reset_service_for_tests(None)


def tok(client, sub):
    return {"Authorization": "Bearer " + client.post("/api/auth/token", json={"sub": sub}).json()["access_token"]}


def _audit_count(db):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT COUNT(*) FROM audit_ledger").fetchone()[0]
    finally:
        con.close()


@pytest.mark.parametrize("path", ["/api/overview", "/api/workforce", "/api/skills/container_orchestration", "/api/identity/directory"])
def test_read_models_require_manager_or_admin(env, path):
    client, _ = env
    assert client.get(path).status_code == 401
    assert client.get(path, headers=tok(client, "demo-employee")).status_code == 403
    assert client.get(path, headers=tok(client, "demo-manager")).status_code == 200
    assert client.get(path, headers=tok(client, "demo-admin")).status_code == 200


def test_read_models_have_no_audit_side_effects(env):
    client, db = env
    h = tok(client, "demo-manager")
    before = _audit_count(db)
    for path in ("/api/overview", "/api/workforce", "/api/skills/azure_compute", "/api/staffing/requests", "/api/identity/directory"):
        assert client.get(path, headers=h).status_code == 200
    assert _audit_count(db) == before


def test_overview_counts_match_database(env):
    client, db = env
    body = client.get("/api/overview", headers=tok(client, "demo-manager")).json()
    con = sqlite3.connect(db)
    people = con.execute("SELECT COUNT(*) FROM identity_map").fetchone()[0]
    holders = con.execute("SELECT COUNT(DISTINCT coded_identity) FROM skills_matrix").fetchone()[0]
    rows = con.execute("SELECT COUNT(*) FROM skills_matrix").fetchone()[0]
    con.close()
    assert body["people"] == people
    assert body["identities_with_evidence"] == holders
    assert body["skill_records"] == rows
    assert body["skill_coverage_ratio"] == round(holders / people, 4)
    assert body["audit_chain_verified"] is True
    assert sum(d["skill_records"] for d in body["domains"]) == rows


def test_workforce_is_coded_only_and_matches_matrix(env):
    client, db = env
    body = client.get("/api/workforce", headers=tok(client, "demo-admin")).json()
    blob = json.dumps(body)
    assert "display_name" not in blob and "source_employee_key" not in blob
    con = sqlite3.connect(db)
    matrix = {(c, s): (p, conf) for c, s, p, conf in con.execute(
        "SELECT coded_identity, skill_id, proficiency, confidence FROM skills_matrix")}
    con.close()
    seen = {(i["coded_identity"], s["skill_id"]): (s["proficiency"], s["confidence"])
            for i in body["identities"] for s in i["skills"]}
    assert seen == matrix
    for ident in body["identities"]:
        assert ident["coded_identity"].startswith("EMP-") and ident["skill_count"] == len(ident["skills"])


def test_identity_directory_returns_synthetic_fixture_names(env):
    client, db = env
    body = client.get("/api/identity/directory", headers=tok(client, "demo-manager")).json()
    names = {p["display_name"] for p in body["people"]}
    assert names == {"Alex Rivera", "Jordan Lee", "Sam Patel", "Casey Nguyen", "Riley Brooks"}
    assert all(p["coded_identity"].startswith("EMP-") for p in body["people"])
    dash = json.dumps(client.get("/api/dashboard", headers=tok(client, "demo-manager")).json())
    work = json.dumps(client.get("/api/workforce", headers=tok(client, "demo-admin")).json())
    assert "display_name" not in dash and "Alex Rivera" not in work


def test_identity_directory_refused_when_not_synthetic(env, monkeypatch):
    client, _ = env
    svc = api_main.get_service()
    original = svc.db.get_meta

    def _meta(key: str):
        return "real" if key == "data_classification" else original(key)

    monkeypatch.setattr(svc.db, "get_meta", _meta)
    r = client.get("/api/identity/directory", headers=tok(client, "demo-manager"))
    assert r.status_code == 403
    assert r.json()["error"] == "directory_not_synthetic"


def test_skill_summary_and_unknown_skill(env):
    client, db = env
    h = tok(client, "demo-manager")
    assert client.get("/api/skills/not_a_skill", headers=h).status_code == 404
    body = client.get("/api/skills/container_orchestration", headers=h).json()
    con = sqlite3.connect(db)
    holders = con.execute("SELECT COUNT(*) FROM skills_matrix WHERE skill_id='container_orchestration'").fetchone()[0]
    con.close()
    assert body["identities_with_evidence"] == holders == len(body["holders"])
    assert sum(body["level_distribution"].values()) == holders
    assert body["effective_half_life_days"] == 120.0
    assert {r["skill_id"] for r in body["related_skills"]} == {"azure_compute"}


def test_request_detail_is_the_verbatim_rank_response(env):
    client, _ = env
    h = tok(client, "demo-manager")
    ranked = client.post("/api/fitness/rank", headers=h, json=RANK).json()
    detail = client.get("/api/staffing/requests/rm-1", headers=h).json()
    assert detail["result"] == ranked
    assert detail["owner"] == "demo-manager"
    assert detail["candidate_count"] == len(ranked["candidates"])
    assert detail["excluded_count"] == len(ranked["excluded_candidates"])
    assert detail["requirements"]["required_skills"] == RANK["required_skills"]


def test_request_list_and_detail_are_owner_scoped(env):
    client, _ = env
    a, b = tok(client, "demo-manager"), tok(client, "demo-manager-2")
    client.post("/api/fitness/rank", headers=a, json=RANK)
    assert [r["request_id"] for r in client.get("/api/staffing/requests", headers=a).json()["requests"]] == ["rm-1"]
    assert client.get("/api/staffing/requests", headers=b).json()["requests"] == []
    assert client.get("/api/staffing/requests/rm-1", headers=b).status_code == 403
    assert client.get("/api/staffing/requests/nope", headers=a).status_code == 404
    assert client.get("/api/staffing/requests", headers=tok(client, "demo-employee")).status_code == 403
    assert client.get("/api/staffing/requests/rm-1", headers=tok(client, "demo-admin")).status_code == 403


def test_request_detail_reflects_decision(env):
    client, _ = env
    h = tok(client, "demo-manager")
    top = client.post("/api/fitness/rank", headers=h, json=RANK).json()["candidates"][0]["coded_identity"]
    client.post("/api/staffing/rm-1/decision", headers=h, json={"status": "accepted", "chosen_coded_identity": top})
    detail = client.get("/api/staffing/requests/rm-1", headers=h).json()
    assert detail["status"] == "accepted"
    assert detail["decision"]["chosen_coded_identity"] == top
    assert detail["decision"]["approved_by"] == "demo-manager"


@pytest.mark.parametrize(
    "sub,roles,key",
    [("demo-manager", ["manager"], "E1001"), ("demo-employee", ["employee"], "E1003"), ("demo-admin", ["admin"], None)],
)
def test_session_reports_server_derived_principal(env, sub, roles, key):
    client, db = env
    body = client.get("/api/session", headers=tok(client, sub)).json()
    from shared.db import HermesDB

    assert body["sub"] == sub and body["roles"] == roles
    assert body["coded_identity"] == (HermesDB(db).resolve_coded_for_source(key) if key else None)
    assert client.get("/api/session").status_code == 401
