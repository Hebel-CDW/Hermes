"""Excel-sunset APIs: taxonomy inbox, dual-run survey, tickets, org bind, kill gate."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

import api.main as api_main  # noqa: E402
from scripts.ingest_fixtures import ingest  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.excel_sunset import freeze_database  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "pilot_population.json"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db_path = tmp_path / "sunset.db"
    ingest(FIXTURE, db_path, write_samples=False)
    freeze_database(HermesDB(db_path))
    monkeypatch.setenv("HERMES_DB_PATH", str(db_path))
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    api_main.reset_service_for_tests(None)
    with TestClient(api_main.app) as client:
        yield client, db_path
    api_main.reset_service_for_tests(None)


def token(client, sub="demo-manager"):
    r = client.post("/api/auth/token", json={"sub": sub})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def coded(db_path, key):
    return HermesDB(db_path).resolve_coded_for_source(key)


def test_taxonomy_inbox_approve_is_human_only_and_does_not_score(env):
    client, db_path = env
    db = HermesDB(db_path)
    db.upsert_skill_alias("k8s admin", "", 0.0, "pending")
    mgr, adm, emp = token(client), token(client, "demo-admin"), token(client, "demo-employee")

    listed = client.get("/api/taxonomy/pending", headers=mgr)
    assert listed.status_code == 200
    labels = {row["alias_label"] for row in listed.json()["pending"]}
    assert "k8s admin" in labels

    assert (
        client.post(
            "/api/taxonomy/aliases/k8s admin/resolve",
            headers=emp,
            json={"decision": "approve", "skill_id": "container_orchestration"},
        ).status_code
        == 403
    )

    ok = client.post(
        "/api/taxonomy/aliases/k8s admin/resolve",
        headers=adm,
        json={"decision": "approve", "skill_id": "container_orchestration"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["mapped_by"] == "human"
    with db.session() as conn:
        row = conn.execute(
            "SELECT skill_id, mapped_by FROM skill_aliases WHERE alias_label='k8s admin'"
        ).fetchone()
    assert row["mapped_by"] == "human" and row["skill_id"] == "container_orchestration"


def test_taxonomy_reject_never_becomes_a_skill(env):
    client, db_path = env
    HermesDB(db_path).upsert_skill_alias("mystery widget", "", 0.0, "pending")
    r = client.post(
        "/api/taxonomy/aliases/mystery widget/resolve",
        headers=token(client, "demo-admin"),
        json={"decision": "reject"},
    )
    assert r.status_code == 200
    assert r.json()["mapped_by"] == "rejected"
    assert r.json()["skill_id"] == ""


def test_baseline_matrix_is_labelled_survey_and_isolated_from_rank(env):
    client, db_path = env
    db = HermesDB(db_path)
    person = coded(db_path, "E1002")
    headers = token(client)
    assert client.get("/api/skills", headers=headers).status_code == 200
    db.insert_baseline(
        baseline_id="bl-survey-1",
        coded_identity=person,
        skill_id="container_orchestration",
        raw_label="Kubernetes",
        raw_value=4.0,
        normalised_level=4,
        source_sheet="Azure",
        source_scale="five_point",
        assessed_at=None,
    )
    before = client.post(
        "/api/fitness/rank",
        headers=headers,
        json={
            "request_id": "sunset-rank",
            "required_skills": {"container_orchestration": 3},
            "shortlist_size": 3,
        },
    )
    assert before.status_code == 200
    survey = client.get("/api/baseline/matrix", headers=headers)
    assert survey.status_code == 200, survey.text
    body = survey.json()
    assert body["kind"] == "survey_2025"
    assert body["used_for_fitness"] is False
    assert any(
        c["coded_identity"] == person and c["skill_id"] == "container_orchestration" and c["level"] == 4
        for c in body["cells"]
    )
    after = client.post(
        "/api/fitness/rank",
        headers=headers,
        json={
            "request_id": "sunset-rank-2",
            "required_skills": {"container_orchestration": 3},
            "shortlist_size": 3,
        },
    )
    assert [c["coded_identity"] for c in before.json()["candidates"]] == [
        c["coded_identity"] for c in after.json()["candidates"]
    ]
    assert [c["fitness_score"] for c in before.json()["candidates"]] == [
        c["fitness_score"] for c in after.json()["candidates"]
    ]


def test_employee_cannot_read_baseline_matrix(env):
    client, _ = env
    assert client.get("/api/baseline/matrix", headers=token(client, "demo-employee")).status_code == 403


def test_ticket_ingest_scores_from_work_not_excel(env):
    client, db_path = env
    person = coded(db_path, "E1002")
    r = client.post(
        "/api/ingest/tickets",
        headers=token(client, "demo-admin"),
        json={
            "tickets": [
                {
                    "employee_id": "E1002",
                    "ticket_number": "INC9001",
                    "short_description": "kubernetes cluster production upgrade",
                    "resolved_at": "2026-03-01T00:00:00+00:00",
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["ingested"] == 1
    assert r.json()["scored"] >= 1
    matrix = HermesDB(db_path).load_skills_matrix()
    assert any(m.coded_identity == person and m.skill_id == "container_orchestration" for m in matrix)


def test_cert_date_then_promote(env):
    client, db_path = env
    person = coded(db_path, "E1002")
    headers = token(client, "demo-admin")
    assert client.get("/api/skills", headers=headers).status_code == 200
    HermesDB(db_path).insert_cert_stagings(
        [("stg-cka-1", person, "CKA - Certified Kubernetes Administrator", "CKA")]
    )
    dated = client.post(
        "/api/certs/stg-cka-1/date",
        headers=headers,
        json={"earned_at": "2026-02-01T00:00:00+00:00"},
    )
    assert dated.status_code == 200, dated.text
    promoted = client.post("/api/certs/stg-cka-1/promote", headers=headers)
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["promoted"] == 1
    with HermesDB(db_path).session() as conn:
        row = conn.execute("SELECT earned_at, promoted FROM cert_staging WHERE staging_id='stg-cka-1'").fetchone()
    assert row["promoted"] == 1 and row["earned_at"]


def test_bind_principal_and_org_edge_unlocks_skill_review(env):
    client, db_path = env
    mgr, report = coded(db_path, "E1001"), coded(db_path, "E1002")
    bind = client.post(
        "/api/org/bind-principal",
        headers=token(client, "demo-admin"),
        json={"sub": "demo-manager", "coded_identity": mgr},
    )
    assert bind.status_code == 200, bind.text
    edge = client.post(
        "/api/org/edges",
        headers=token(client, "demo-admin"),
        json={"manager_coded_id": mgr, "report_coded_id": report},
    )
    assert edge.status_code == 200
    review = client.get(f"/api/team/skill-review/{report}", headers=token(client))
    assert review.status_code == 200


def test_kill_gate_endpoint_and_rbac(env):
    client, _ = env
    emp = client.get("/api/excel-sunset", headers=token(client, "demo-employee"))
    assert emp.status_code == 403
    gate = client.get("/api/excel-sunset", headers=token(client))
    assert gate.status_code == 200
    body = gate.json()
    assert body["next_workbook_allowed"] is False
    assert body["survey_year_frozen"] == 2025
    assert "ready_to_retire_excel" in body
