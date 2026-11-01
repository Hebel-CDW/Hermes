"""Employee proposals, manager approvals, bulk update, what-if preview, custom roles.

The rules under test: a proposal counts for nothing until a manager approves it; managers only act on
their own team; the what-if preview stores nothing; every write lands in the audit chain.
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
from shared.db import HermesDB  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "pilot_population.json"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db_path = tmp_path / "workflow.db"
    ingest(FIXTURE, db_path, write_samples=False)
    monkeypatch.setenv("HERMES_DB_PATH", str(db_path))
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.delenv("FUNCTION_AUTH_KEY", raising=False)
    monkeypatch.delenv("HERMES_ENV", raising=False)
    api_main.reset_service_for_tests(None)
    with TestClient(api_main.app) as client:
        yield client, db_path
    api_main.reset_service_for_tests(None)


def token(client, sub):
    r = client.post("/api/auth/token", json={"sub": sub})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def coded(db_path, key):
    return HermesDB(db_path).resolve_coded_for_source(key)


def rows(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def claim(client, emp, skill="python", level=4, note="used it daily"):
    return client.post(
        "/api/me/requests",
        headers=emp,
        json={"kind": "skill_claim", "skill_id": skill, "proficiency": level, "note": note},
    )


# ------------------------------------------------------------------ employee
def test_proposal_is_pending_and_changes_nothing_until_approved(env):
    client, db_path = env
    emp, mgr = token(client, "demo-employee"), token(client, "demo-manager")
    me = coded(db_path, "E1003")
    before = rows(db_path, "SELECT COUNT(*) FROM evidence_staging WHERE coded_identity=?", (me,))[0][0]

    r = claim(client, emp)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    assert rows(db_path, "SELECT COUNT(*) FROM evidence_staging WHERE coded_identity=?", (me,))[0][0] == before

    inbox = client.get("/api/team/inbox", headers=mgr).json()
    assert [x["request_id"] for x in inbox["requests"]] == [r.json()["request_id"]]
    assert inbox["requests"][0]["skill_name"]


def test_approval_runs_the_governed_declare_path_and_is_audited(env):
    client, db_path = env
    emp, mgr = token(client, "demo-employee"), token(client, "demo-manager")
    me = coded(db_path, "E1003")
    rid = claim(client, emp, "ansible", 3).json()["request_id"]

    done = client.post(f"/api/team/inbox/{rid}/decide", headers=mgr, json={"decision": "approve", "proficiency": 3})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "approved"
    ev = rows(db_path, "SELECT evidence_type, source_ref FROM evidence_staging WHERE coded_identity=? AND skill_id='ansible'", (me,))
    assert ("declared", "mgr:demo-manager") in ev
    kinds = {r[0] for r in rows(db_path, "SELECT event_type FROM audit_ledger")}
    assert {"employee_request_submitted", "manager_declared_skill", "manager_request_decided"} <= kinds
    assert HermesDB(db_path).verify_audit_chain() == []

    again = client.post(f"/api/team/inbox/{rid}/decide", headers=mgr, json={"decision": "approve", "proficiency": 3})
    assert again.status_code == 409


def test_decline_writes_no_evidence(env):
    client, db_path = env
    emp, mgr = token(client, "demo-employee"), token(client, "demo-manager")
    me = coded(db_path, "E1003")
    rid = claim(client, emp, "ansible", 5).json()["request_id"]
    before = rows(db_path, "SELECT COUNT(*) FROM evidence_staging WHERE coded_identity=?", (me,))[0][0]
    r = client.post(f"/api/team/inbox/{rid}/decide", headers=mgr, json={"decision": "decline", "note": "not yet"})
    assert r.status_code == 200 and r.json()["status"] == "declined"
    assert rows(db_path, "SELECT COUNT(*) FROM evidence_staging WHERE coded_identity=?", (me,))[0][0] == before


def test_duplicate_pending_proposal_is_refused_and_withdraw_frees_it(env):
    client, _ = env
    emp = token(client, "demo-employee")
    first = claim(client, emp).json()
    assert claim(client, emp).status_code == 409
    w = client.post(f"/api/me/requests/{first['request_id']}/withdraw", headers=emp)
    assert w.status_code == 200 and w.json()["status"] == "withdrawn"
    assert claim(client, emp).status_code == 200


def test_proposal_validation(env):
    client, _ = env
    emp = token(client, "demo-employee")
    assert claim(client, emp, skill="not_a_skill").status_code == 422
    assert claim(client, emp, level=9).status_code == 422
    assert client.post("/api/me/requests", headers=emp, json={"kind": "skill_claim", "skill_id": "python", "proficiency": 3, "coded_identity": "EMP-00000000"}).status_code == 422
    bad_cert = client.post("/api/me/requests", headers=emp, json={"kind": "certificate", "cert_code": "NOPE-1", "earned_at": "2024-01-01"})
    assert bad_cert.status_code == 422
    future = client.post("/api/me/requests", headers=emp, json={"kind": "certificate", "cert_code": "CKA", "earned_at": "2999-01-01"})
    assert future.status_code == 422


def test_certificate_flows_through_the_governed_date_and_promote_path(env):
    client, db_path = env
    emp, mgr = token(client, "demo-employee"), token(client, "demo-manager")
    me = coded(db_path, "E1003")
    r = client.post("/api/me/requests", headers=emp, json={"kind": "certificate", "cert_code": "CKA", "earned_at": "2025-03-01"})
    assert r.status_code == 200, r.text
    rid = r.json()["request_id"]
    ok = client.post(f"/api/team/inbox/{rid}/decide", headers=mgr, json={"decision": "approve"})
    assert ok.status_code == 200, ok.text
    assert rows(db_path, "SELECT promoted FROM cert_staging WHERE coded_identity=?", (me,)) == [(1,)]
    assert rows(db_path, "SELECT evidence_type FROM evidence_staging WHERE evidence_id=?", (f"cert-selfcert-{rid}",)) == [("certified",)]


def test_goal_set_replace_and_clear(env):
    client, _ = env
    emp, mgr = token(client, "demo-employee"), token(client, "demo-manager")
    client.post("/api/roles/custom", headers=mgr, json={"role_name": "Second Role", "required_skills": {"python": 3}})
    roles = client.get("/api/roles", headers=emp).json()["roles"]
    assert len(roles) >= 2
    assert client.put("/api/me/goal", headers=emp, json={"role_id": roles[0]["role_id"]}).status_code == 200
    assert client.put("/api/me/goal", headers=emp, json={"role_id": roles[1]["role_id"]}).status_code == 200
    goal = client.get("/api/me/workflow", headers=emp).json()["goal"]
    assert goal["role_id"] == roles[1]["role_id"]
    assert client.put("/api/me/goal", headers=emp, json={"role_id": "nope"}).status_code == 404
    assert client.delete("/api/me/goal", headers=emp).status_code == 200
    assert client.get("/api/me/workflow", headers=emp).json()["goal"] is None


def test_timeline_shows_only_my_events(env):
    client, _ = env
    emp, emp2 = token(client, "demo-employee"), token(client, "demo-employee-2")
    claim(client, emp)
    mine = client.get("/api/me/timeline", headers=emp).json()["events"]
    theirs = client.get("/api/me/timeline", headers=emp2).json()["events"]
    assert any(e["event_type"] == "employee_request_submitted" for e in mine)
    assert not any(e["event_type"] == "employee_request_submitted" for e in theirs)


# --------------------------------------------------------------- permissions
def test_a_manager_cannot_act_on_someone_elses_team(env):
    client, _ = env
    emp, mgr2 = token(client, "demo-employee"), token(client, "demo-manager-2")
    rid = claim(client, emp).json()["request_id"]
    assert client.get("/api/team/inbox", headers=mgr2).json()["requests"] == []
    r = client.post(f"/api/team/inbox/{rid}/decide", headers=mgr2, json={"decision": "approve", "proficiency": 3})
    assert r.status_code == 403


def test_role_boundaries(env):
    client, _ = env
    emp, mgr = token(client, "demo-employee"), token(client, "demo-manager")
    assert client.get("/api/team/inbox", headers=emp).status_code == 403
    assert client.get("/api/team/grid", headers=emp).status_code == 403
    assert client.post("/api/team/bulk-declare", headers=emp, json={"items": []}).status_code in (403, 422)
    assert client.post("/api/me/requests", headers=mgr, json={"kind": "skill_check", "skill_id": "python"}).status_code == 403
    assert client.post("/api/roles/custom", headers=emp, json={"role_name": "x" * 5, "required_skills": {"python": 3}}).status_code == 403
    assert client.get("/api/me/timeline", headers=mgr).status_code == 403


def test_requests_need_a_token(env):
    client, _ = env
    for method, path in (("get", "/api/team/inbox"), ("get", "/api/me/workflow"), ("get", "/api/team/grid")):
        assert getattr(client, method)(path).status_code in (401, 403)


# ------------------------------------------------------------ manager tools
def test_grid_is_scoped_to_the_team(env):
    client, db_path = env
    mgr, mgr2 = token(client, "demo-manager"), token(client, "demo-manager-2")
    grid = client.get("/api/team/grid", headers=mgr).json()
    assert coded(db_path, "E1002") in grid["people"] and coded(db_path, "E1003") in grid["people"]
    assert coded(db_path, "E1005") not in grid["people"]
    assert client.get("/api/team/grid", headers=mgr2).json()["people"] != grid["people"]


def test_bulk_declare_is_all_or_nothing_for_team_scope(env):
    client, db_path = env
    mgr = token(client, "demo-manager")
    mine, stranger = coded(db_path, "E1002"), coded(db_path, "E1005")
    before = rows(db_path, "SELECT COUNT(*) FROM evidence_staging")[0][0]
    bad = client.post(
        "/api/team/bulk-declare",
        headers=mgr,
        json={"items": [{"coded_identity": mine, "skill_id": "python", "proficiency": 3}, {"coded_identity": stranger, "skill_id": "python", "proficiency": 3}]},
    )
    assert bad.status_code == 403
    assert rows(db_path, "SELECT COUNT(*) FROM evidence_staging")[0][0] == before
    ok = client.post(
        "/api/team/bulk-declare",
        headers=mgr,
        json={"items": [{"coded_identity": mine, "skill_id": "python", "proficiency": 3}, {"coded_identity": mine, "skill_id": "ansible", "proficiency": 2}]},
    )
    assert ok.status_code == 200 and ok.json()["saved"] == 2
    assert HermesDB(db_path).verify_audit_chain() == []


def test_preview_matches_rank_and_stores_nothing(env):
    client, db_path = env
    mgr = token(client, "demo-manager")
    payload = {"request_id": "whatif-1", "required_skills": {"container_orchestration": 3, "azure_networking": 3}, "shortlist_size": 3}
    req_before = rows(db_path, "SELECT COUNT(*) FROM staffing_requests")[0][0]
    audit_before = rows(db_path, "SELECT COUNT(*) FROM audit_ledger")[0][0]
    preview = client.post("/api/fitness/preview", headers=mgr, json=payload)
    assert preview.status_code == 200, preview.text
    assert rows(db_path, "SELECT COUNT(*) FROM staffing_requests")[0][0] == req_before
    assert rows(db_path, "SELECT COUNT(*) FROM audit_ledger")[0][0] == audit_before
    ranked = client.post("/api/fitness/rank", headers=mgr, json=payload).json()
    assert [c["coded_identity"] for c in preview.json()["candidates"]] == [c["coded_identity"] for c in ranked["candidates"]]
    assert [c["fitness_score"] for c in preview.json()["candidates"]] == [c["fitness_score"] for c in ranked["candidates"]]


def test_custom_role_create_use_and_delete(env):
    client, db_path = env
    mgr = token(client, "demo-manager")
    made = client.post(
        "/api/roles/custom",
        headers=mgr,
        json={"role_name": "Platform Hero", "required_skills": {"container_orchestration": 3, "azure_networking": 3}, "critical_skills": ["container_orchestration"], "min_coverage_ratio": 0.5},
    )
    assert made.status_code == 200, made.text
    role = made.json()
    assert role["role_id"].startswith("custom_")
    assert any(r["role_id"] == role["role_id"] for r in client.get("/api/roles", headers=mgr).json()["roles"])
    bad = client.post("/api/roles/custom", headers=mgr, json={"role_name": "Broken", "required_skills": {"python": 3}, "critical_skills": ["ansible"]})
    assert bad.status_code == 422
    assert client.post("/api/roles/custom", headers=mgr, json={"role_name": "Broken", "required_skills": {"nope": 3}}).status_code == 422
    assert client.delete(f"/api/roles/custom/{role['role_id']}", headers=mgr).status_code == 200
    assert client.delete("/api/roles/custom/senior_cloud_engineer", headers=mgr).status_code == 422
    assert client.get("/api/roles", headers=mgr).json()["roles"][0]["role_id"] == "senior_cloud_engineer"
    assert HermesDB(db_path).verify_audit_chain() == []
