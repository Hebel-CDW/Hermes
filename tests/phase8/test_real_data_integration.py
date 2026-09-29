"""Governed REAL-data ingestion: identity protection, taxonomy governance, no fake scoring.

Uses an invented workbook with the real workbook's structure (scripts/phase8/synthetic_workbook.py)
and runs the real-data path exactly as production would: no HERMES_TEST_MODE, a strong
unpublished secret, a dedicated database.
"""

from __future__ import annotations

import importlib.util
import json
import secrets
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
import shared.models as models
from scripts.phase8.synthetic_workbook import CLIENT_LABEL, EXPECTED, FAKE_PEOPLE, build
from shared.db import HermesDB
from shared.errors import UntrustedDatabaseError
from shared.secrets import PUBLISHED_SECRETS

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_t_{name}", ROOT / "scripts" / "phase8" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ingest_real = _load("ingest_real")
real_data_report = _load("real_data_report")


@pytest.fixture()
def real_env(tmp_path, monkeypatch):
    """Production-like real-data environment with a strong random secret."""
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("IDENTITY_MAP_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("HERMES_JWT_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("HERMES_ENV", "local")
    monkeypatch.setattr(models, "CLIENT_NAME_BLOCKLIST", frozenset({CLIENT_LABEL}))
    workbook = build(tmp_path / "source" / "Fake_Skill_Matrix.xlsx")
    db_path = tmp_path / "real" / "hermes_real.db"
    reports = tmp_path / "reports"
    return {"workbook": workbook, "db": db_path, "reports": reports, "tmp": tmp_path}


@pytest.fixture()
def ingested(real_env):
    result = ingest_real.run(real_env["workbook"], real_env["db"], real_env["reports"])
    return {**real_env, "result": result}


@pytest.fixture()
def client(ingested, monkeypatch):
    monkeypatch.setenv("HERMES_DB_PATH", str(ingested["db"]))
    api_main.reset_service_for_tests(None)
    with TestClient(api_main.app) as c:
        yield c
    api_main.reset_service_for_tests(None)


def _token(client, sub):
    return {"Authorization": "Bearer " + client.post("/api/auth/token", json={"sub": sub}).json()["access_token"]}


def _q(db_path, sql):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


# -- ingestion results --------------------------------------------------------------


def test_real_ingest_counts_match_workbook_and_database(ingested):
    summary = ingested["result"]["summary"]
    assert summary["people_detected"] == EXPECTED["people"]
    assert summary["cells"]["accepted"] == EXPECTED["cells_accepted"]
    assert summary["cells"]["rejected"] == EXPECTED["cells_rejected"]
    assert summary["cells"]["rejections_by_reason"] == EXPECTED["rejections_by_reason"]
    assert summary["cells"]["accepted_skill_cells"] == EXPECTED["accepted_skill_cells"]
    assert summary["cells"]["accepted_account_cells"] == EXPECTED["accepted_account_cells"]
    labels = summary["labels"]
    assert (labels["skill_labels"], labels["mapped"], labels["pending"]) == (
        EXPECTED["skill_labels"],
        EXPECTED["mapped"],
        EXPECTED["pending"],
    )
    assert labels["rejected"] == EXPECTED["rejected"]
    certs = summary["certificates"]
    assert certs["cells"] == EXPECTED["certificate_cells"]
    assert certs["classification"]["exact_cert_code"] == EXPECTED["certificates_exact"]
    assert certs["classification"]["unmapped_label"] == EXPECTED["certificates_pending"]

    db = HermesDB(ingested["db"])
    assert db.get_meta("data_classification") == "real"
    dq = real_data_report.load(ingested["db"])
    assert real_data_report.consistency_failures(dq) == []
    assert dq["pipeline"] == {
        "imported": EXPECTED["people"],
        "validated": EXPECTED["cells_accepted"],
        "mapped": EXPECTED["mapped"],
        "pending": EXPECTED["pending"],
        "scored": 0,
    }
    assert dq["certificates"]["exact_mapped"] == EXPECTED["certificates_exact"]
    assert dq["certificates"]["pending"] == EXPECTED["certificates_pending"]


def test_mapped_labels_are_traceable_to_a_governed_canonical_skill(ingested):
    trace = ingested["result"]["summary"]["labels"]["mapped_trace"]
    assert trace == [{"label": "azure compute", "skill_id": "azure_compute", "mapped_by": "auto", "match_confidence": 1.0}]
    pending = {r[0] for r in _q(ingested["db"], "SELECT alias_label FROM skill_aliases WHERE mapped_by='pending'")}
    assert pending == {"terraform modules"}


def test_reingest_is_deterministic_and_idempotent(ingested):
    first = sorted(r[0] for r in _q(ingested["db"], "SELECT coded_identity FROM identity_map"))
    rows = _q(ingested["db"], "SELECT COUNT(*) FROM baseline_assessments")[0][0]
    ingest_real.run(ingested["workbook"], ingested["db"], ingested["reports"])
    assert sorted(r[0] for r in _q(ingested["db"], "SELECT coded_identity FROM identity_map")) == first
    assert _q(ingested["db"], "SELECT COUNT(*) FROM baseline_assessments")[0][0] == rows
    assert real_data_report.consistency_failures(real_data_report.load(ingested["db"])) == []


def test_identity_abstraction_is_audited_per_person_not_per_cell(ingested):
    events = _q(ingested["db"], "SELECT COUNT(*) FROM audit_ledger WHERE event_type='evidence_ingestion'")[0][0]
    assert events == EXPECTED["people"]
    assert _q(ingested["db"], "SELECT COUNT(*) FROM audit_ledger WHERE event_type='phase8_workbook_ingest'")[0][0] == 1
    assert HermesDB(ingested["db"]).verify_audit_chain() == []


# -- identity protection -------------------------------------------------------------


def test_names_exist_only_in_the_identity_vault(ingested):
    con = sqlite3.connect(ingested["db"])
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] != "identity_vault"]
        for table in tables:
            for row in con.execute(f"SELECT * FROM {table}"):
                text = " ".join(str(v).lower() for v in row if isinstance(v, str))
                for person in FAKE_PEOPLE:
                    assert person.lower() not in text, f"name leaked into {table}"
        assert con.execute("SELECT COUNT(*) FROM identity_vault").fetchone()[0] == EXPECTED["people"]
    finally:
        con.close()


def test_reports_written_by_ingestion_contain_no_names(ingested):
    files = [p for p in ingested["reports"].rglob("*") if p.is_file()]
    assert files, "ingestion should write aggregate reports"
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for person in FAKE_PEOPLE:
            assert person.lower() not in text, f"name leaked into {path.name}"
    dropped = json.loads((ingested["reports"] / "phase8_dropped_rows.json").read_text())["dropped"]
    assert all(set(d) == {"sheet", "reason"} for d in dropped)


def test_coded_identities_are_deterministic_and_not_derivable_from_published_secrets(ingested):
    import hashlib
    import hmac

    coded = {r[0] for r in _q(ingested["db"], "SELECT coded_identity FROM identity_map")}
    for person in FAKE_PEOPLE:
        for published in PUBLISHED_SECRETS:
            guess = "EMP-" + hmac.new(published.encode(), person.lower().encode(), hashlib.sha256).hexdigest()[:8]
            assert guess not in coded


@pytest.mark.parametrize("sub", ["demo-manager", "demo-admin", "demo-employee"])
def test_no_api_response_contains_names_vault_or_client_labels(client, sub):
    headers = _token(client, sub)
    paths = [
        "/api/session", "/api/overview", "/api/workforce", "/api/skills", "/api/skills/azure_compute",
        "/api/roles", "/api/dashboard", "/api/identities", "/api/matrix/runs", "/api/staffing/requests",
        "/api/data-quality", "/api/me", "/api/team/skill-review/EMP-00000000",
    ]
    for path in paths:
        response = client.get(path, headers=headers)
        assert response.status_code in (200, 400, 403, 404), path
        body = response.text.lower()
        for person in FAKE_PEOPLE:
            assert person.lower() not in body, f"{path} leaked a name"
        for forbidden in ("identity_vault", "display_name", "source_employee_key", "source_hash", CLIENT_LABEL,
                          "vendor partner badge", "terraform modules", "customer service"):
            assert forbidden not in body, f"{path} leaked {forbidden}"


def test_data_quality_endpoint_matches_database_and_is_role_gated(client, ingested):
    assert client.get("/api/data-quality", headers=_token(client, "demo-employee")).status_code == 403
    assert client.get("/api/data-quality").status_code == 401
    dq = client.get("/api/data-quality", headers=_token(client, "demo-manager")).json()
    assert dq == real_data_report.load(ingested["db"])
    assert dq["data_classification"] == "real"
    assert client.get("/api/session", headers=_token(client, "demo-manager")).json()["data_classification"] == "real"


# -- taxonomy governance / no fake scoring --------------------------------------------


def test_pending_and_mapped_baseline_labels_never_score(client, ingested):
    assert _q(ingested["db"], "SELECT COUNT(*) FROM skills_matrix")[0][0] == 0
    assert _q(ingested["db"], "SELECT COUNT(*) FROM evidence_staging")[0][0] == 0
    workforce = client.get("/api/workforce", headers=_token(client, "demo-manager")).json()
    assert len(workforce["identities"]) == EXPECTED["people"]
    assert all(i["skill_count"] == 0 and i["mean_confidence"] is None for i in workforce["identities"])
    assert client.get("/api/dashboard", headers=_token(client, "demo-manager")).json()["skill_distribution"] == []
    rank = client.post(
        "/api/fitness/rank",
        json={"request_id": "real-1", "required_skills": {"azure_compute": 1}, "shortlist_size": 3},
        headers=_token(client, "demo-manager"),
    ).json()
    assert rank["candidates"] == []  # nobody is scored from baseline ratings, mapped or not


def test_client_labels_never_reach_scoring_tables(ingested):
    for table, column in (("baseline_assessments", "raw_label"), ("evidence_staging", "skill_id"), ("skills_matrix", "skill_id"), ("skill_aliases", "alias_label")):
        values = {str(r[0]).lower() for r in _q(ingested["db"], f"SELECT {column} FROM {table}")}
        assert CLIENT_LABEL not in values, table
    assert _q(ingested["db"], "SELECT COUNT(*) FROM account_context")[0][0] == EXPECTED["accepted_account_cells"]


def test_certificates_keep_null_dates_and_are_not_promoted(ingested):
    rows = _q(ingested["db"], "SELECT earned_at, promoted, cert_code FROM cert_staging")
    assert all(earned is None and promoted == 0 for earned, promoted, _ in rows)
    assert sorted(code for *_, code in rows if code) == ["AZ-104", "CKA"]


# -- secrets, modes, separation --------------------------------------------------------


@pytest.mark.parametrize("secret", sorted(PUBLISHED_SECRETS) + ["short-secret", ""])
def test_published_or_weak_secret_is_rejected(real_env, monkeypatch, secret):
    monkeypatch.setenv("IDENTITY_MAP_SECRET", secret)
    with pytest.raises(RuntimeError):
        ingest_real.run(real_env["workbook"], real_env["db"], real_env["reports"])
    assert not real_env["db"].exists()


def test_test_mode_is_rejected_for_real_ingestion(real_env, monkeypatch):
    monkeypatch.setenv("HERMES_TEST_MODE", "1")
    with pytest.raises(RuntimeError, match="TEST_MODE"):
        ingest_real.run(real_env["workbook"], real_env["db"], real_env["reports"])
    assert not real_env["db"].exists()


@pytest.mark.parametrize("name", ["hermes.db", "hermes_demo.db", "hermes_validation.db", "hermes_phase8.db"])
def test_demo_synthetic_and_validation_databases_are_refused(real_env, name):
    with pytest.raises(ingest_real.RealIngestRefused):
        ingest_real.guard_db_path(ROOT / "data" / name)


def test_real_database_is_not_served_in_test_mode(ingested, monkeypatch):
    monkeypatch.setenv("HERMES_TEST_MODE", "1")
    monkeypatch.setenv("HERMES_DB_PATH", str(ingested["db"]))
    api_main.reset_service_for_tests(None)
    try:
        with TestClient(api_main.app) as c:
            token = c.post("/api/auth/token", json={"sub": "demo-manager"}).json()["access_token"]
            response = c.get("/api/data-quality", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 503
            assert response.json()["error"] == "real_database_in_test_mode"
    finally:
        api_main.reset_service_for_tests(None)


def test_real_workbook_cannot_be_ingested_into_a_synthetic_database(real_env, monkeypatch):
    from scripts.ingest_fixtures import ingest as ingest_fixtures

    synthetic = real_env["tmp"] / "synthetic.db"
    monkeypatch.setenv("HERMES_TEST_MODE", "1")
    ingest_fixtures(ROOT / "data" / "fixtures" / "pilot_population.json", synthetic, write_samples=False)
    monkeypatch.delenv("HERMES_TEST_MODE")
    with pytest.raises(UntrustedDatabaseError):
        ingest_real.run(real_env["workbook"], synthetic, real_env["reports"])
    assert _q(synthetic, "SELECT COUNT(*) FROM baseline_assessments")[0][0] == 0
    assert HermesDB(synthetic).get_meta("data_classification") == "synthetic"


def test_raw_workbook_database_and_secrets_are_not_downloadable(client, ingested):
    workbook_bytes = ingested["workbook"].read_bytes()
    for url in (
        "/data/source/Skill_Matrix_2025.xlsx",
        "/../data/source/Skill_Matrix_2025.xlsx",
        "/%2e%2e/data/source/Skill_Matrix_2025.xlsx",
        "/assets/../../data/source/Skill_Matrix_2025.xlsx",
        "/data/real/hermes_real.db",
        "/secrets/hermes_real_data.env",
    ):
        response = client.get(url)
        assert response.content[:2] != b"PK", url
        assert not response.content.startswith(b"SQLite format"), url
        assert response.content != workbook_bytes
        assert b"IDENTITY_MAP_SECRET" not in response.content


def test_frontend_bundle_contains_no_real_data_markers():
    dist = ROOT / "web" / "dist"
    if not dist.is_dir():
        pytest.skip("web/dist not built")
    text = "\n".join(p.read_text(errors="ignore") for p in dist.rglob("*") if p.suffix in {".js", ".css", ".html"})
    for forbidden in ("identity_vault", "source_employee_key", "source_hash", "IDENTITY_MAP_SECRET", "HERMES_JWT_SECRET", "Skill_Matrix_2025"):
        assert forbidden not in text
    for person in FAKE_PEOPLE:
        assert person not in text
