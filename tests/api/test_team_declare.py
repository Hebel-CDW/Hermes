"""Manager skill declare: org-scoped, ontology-only, declared weight, no baseline writes."""

from __future__ import annotations

import json
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
    db_path = tmp_path / "declare.db"
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


def coded(db_path, employee_key):
    return HermesDB(db_path).resolve_coded_for_source(employee_key)


def _q(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def test_manager_can_review_and_declare_for_a_direct_report(env):
    client, db_path = env
    mgr = token(client, "demo-manager")
    report = coded(db_path, "E1002")
    review = client.get(f"/api/team/skill-review/{report}", headers=mgr)
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["coded_identity"] == report
    assert isinstance(body["matrix"], list)
    assert isinstance(body["contests"], list)
    networking = next(r for r in body["matrix"] if r["skill_id"] == "azure_networking")
    assert networking["proficiency"] >= 1
    assert "demonstrated" in networking["sources"] or "certified" in networking["sources"]
    before = networking["proficiency"]

    declared = client.post(
        "/api/team/declare",
        headers=mgr,
        json={"coded_identity": report, "skill_id": "azure_networking", "proficiency": 5},
    )
    assert declared.status_code == 200, declared.text
    saved = declared.json()
    assert saved["coded_identity"] == report
    assert saved["skill_id"] == "azure_networking"
    assert "evidence_id" in saved

    after = client.get(f"/api/team/skill-review/{report}", headers=mgr).json()
    networking_after = next(r for r in after["matrix"] if r["skill_id"] == "azure_networking")
    assert networking_after["proficiency"] != 5
    assert networking_after["proficiency"] == before
    assert "declared" in networking_after["sources"]

    rows = _q(
        db_path,
        "SELECT evidence_type, source_ref FROM evidence_staging WHERE evidence_id=?",
        (saved["evidence_id"],),
    )
    assert rows == [("declared", "mgr:demo-manager")]

    payload = json.loads(
        _q(
            db_path,
            "SELECT payload_json FROM audit_ledger WHERE event_type='manager_declared_skill' ORDER BY seq DESC LIMIT 1",
        )[0][0]
    )
    assert payload["coded_identity"] == report
    assert payload["skill_id"] == "azure_networking"
    assert payload["actor"] == "demo-manager"
    blob = json.dumps(payload)
    assert "Alex" not in blob and "Jordan" not in blob and "display_name" not in blob


def test_manager_cannot_declare_for_someone_elses_report(env):
    client, db_path = env
    other = token(client, "demo-manager-2")
    report = coded(db_path, "E1002")
    assert client.get(f"/api/team/skill-review/{report}", headers=other).status_code == 403
    r = client.post(
        "/api/team/declare",
        headers=other,
        json={"coded_identity": report, "skill_id": "incident_management", "proficiency": 3},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "not_a_direct_report"
    assert not _q(db_path, "SELECT 1 FROM evidence_staging WHERE source_ref='mgr:demo-manager-2'")


def test_employee_cannot_use_team_skill_endpoints(env):
    client, db_path = env
    emp = token(client, "demo-employee")
    self_id = coded(db_path, "E1003")
    assert client.get(f"/api/team/skill-review/{self_id}", headers=emp).status_code == 403
    assert (
        client.post(
            "/api/team/declare",
            headers=emp,
            json={"coded_identity": self_id, "skill_id": "incident_management", "proficiency": 3},
        ).status_code
        == 403
    )


def test_admin_can_declare_for_any_coded_identity(env):
    client, db_path = env
    admin = token(client, "demo-admin")
    outsider = coded(db_path, "E1005")
    assert client.get(f"/api/team/skill-review/{outsider}", headers=admin).status_code == 200
    r = client.post(
        "/api/team/declare",
        headers=admin,
        json={"coded_identity": outsider, "skill_id": "incident_management", "proficiency": 2, "note": "seen in standup"},
    )
    assert r.status_code == 200, r.text


def test_unknown_skill_and_bad_level_are_422(env):
    client, db_path = env
    mgr = token(client, "demo-manager")
    report = coded(db_path, "E1002")
    unknown = client.post(
        "/api/team/declare",
        headers=mgr,
        json={"coded_identity": report, "skill_id": "not_a_skill", "proficiency": 3},
    )
    assert unknown.status_code == 422
    bad = client.post(
        "/api/team/declare",
        headers=mgr,
        json={"coded_identity": report, "skill_id": "incident_management", "proficiency": 6},
    )
    assert bad.status_code == 422
    zero = client.post(
        "/api/team/declare",
        headers=mgr,
        json={"coded_identity": report, "skill_id": "incident_management", "proficiency": 0},
    )
    assert zero.status_code == 422


def test_declare_rejects_spoofed_fields(env):
    client, db_path = env
    mgr = token(client, "demo-manager")
    report = coded(db_path, "E1002")
    r = client.post(
        "/api/team/declare",
        headers=mgr,
        json={
            "coded_identity": report,
            "skill_id": "incident_management",
            "proficiency": 3,
            "requester_id": "demo-admin",
            "name": "Jordan Lee",
        },
    )
    assert r.status_code == 422


def test_declare_does_not_insert_baseline_assessments(env):
    client, db_path = env
    before = _q(db_path, "SELECT COUNT(*) FROM baseline_assessments")[0][0]
    mgr = token(client, "demo-manager")
    report = coded(db_path, "E1002")
    assert (
        client.post(
            "/api/team/declare",
            headers=mgr,
            json={"coded_identity": report, "skill_id": "incident_management", "proficiency": 4},
        ).status_code
        == 200
    )
    assert _q(db_path, "SELECT COUNT(*) FROM baseline_assessments")[0][0] == before


def test_manager_can_declare_for_self(env):
    client, db_path = env
    mgr = token(client, "demo-manager")
    self_id = coded(db_path, "E1001")
    assert client.get(f"/api/team/skill-review/{self_id}", headers=mgr).status_code == 200
    r = client.post(
        "/api/team/declare",
        headers=mgr,
        json={"coded_identity": self_id, "skill_id": "incident_management", "proficiency": 3},
    )
    assert r.status_code == 200, r.text


def test_contest_confirm_writes_declared_dismiss_does_not(env):
    client, db_path = env
    emp = token(client, "demo-employee")
    mgr = token(client, "demo-manager")
    other = token(client, "demo-manager-2")
    subject = coded(db_path, "E1003")

    opened = client.post(
        "/api/me/contest",
        headers=emp,
        json={"reason": "I have handled sev1 bridges", "skill_id": "incident_management"},
    )
    assert opened.status_code == 200
    contest_id = opened.json()["contest_id"]

    review = client.get(f"/api/team/skill-review/{subject}", headers=mgr).json()
    assert any(c["contest_id"] == contest_id for c in review["contests"])

    hijack = client.post(
        f"/api/team/contests/{contest_id}/resolve",
        headers=other,
        json={"status": "confirmed"},
    )
    assert hijack.status_code == 403

    confirmed = client.post(
        f"/api/team/contests/{contest_id}/resolve",
        headers=mgr,
        json={"status": "confirmed"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    declared = _q(
        db_path,
        "SELECT 1 FROM evidence_staging WHERE coded_identity=? AND skill_id=? AND evidence_type='declared' AND source_ref=?",
        (subject, "incident_management", "mgr:demo-manager"),
    )
    assert declared

    second = client.post(
        "/api/me/contest",
        headers=emp,
        json={"reason": "also compute", "skill_id": "azure_compute"},
    )
    dismissed_id = second.json()["contest_id"]
    before_compute = _q(
        db_path,
        "SELECT COUNT(*) FROM evidence_staging WHERE coded_identity=? AND skill_id=? AND evidence_type='declared'",
        (subject, "azure_compute"),
    )[0][0]
    gone = client.post(
        f"/api/team/contests/{dismissed_id}/resolve",
        headers=mgr,
        json={"status": "dismissed"},
    )
    assert gone.status_code == 200
    assert gone.json()["status"] == "dismissed"
    after_compute = _q(
        db_path,
        "SELECT COUNT(*) FROM evidence_staging WHERE coded_identity=? AND skill_id=? AND evidence_type='declared'",
        (subject, "azure_compute"),
    )[0][0]
    assert after_compute == before_compute
    assert _q(db_path, "SELECT status FROM evidence_contests WHERE contest_id=?", (dismissed_id,))[0][0] == "dismissed"


def test_declare_is_rate_limited(env):
    client, db_path = env
    mgr = token(client, "demo-manager")
    report = coded(db_path, "E1002")
    body = {"coded_identity": report, "skill_id": "incident_management", "proficiency": 3}
    statuses = [client.post("/api/team/declare", headers=mgr, json=body).status_code for _ in range(11)]
    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429
