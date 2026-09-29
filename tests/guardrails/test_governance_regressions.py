"""Regression tests for audit findings G-1, G-3, G-4 and API input validation.

G-1  role critical_skills / min_coverage_ratio were stored but only enforced if the
     client volunteered them in the request body.
G-3  certificate labels were mapped to skills by a bidirectional substring match.
G-4  the baseline-isolation test never exercised the DB-backed service path.
API  out-of-range proficiency levels produced HTTP 500 instead of a validation error.

All data is synthetic.
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "phase8"))

from api.main import app, reset_service_for_tests  # noqa: E402
from ingest_certificates import promote_dated_certs, resolve_cert_label  # noqa: E402
from scripts.ingest_fixtures import ingest  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.models import ProficiencyLevel, StaffingRequest, TargetRoleProfile  # noqa: E402
from shared.service import HermesService  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "pilot_population.json"
CODES = {
    "cka": "container_orchestration",
    "ckad": "container_orchestration",
    "az-104": "azure_compute",
    "az-700": "azure_networking",
}


# --------------------------------------------------------------------------
# G-3 — governed certificate mapping
# --------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path):
    return HermesDB(tmp_path / "certs.db")


@pytest.mark.parametrize(
    "label,skill,code",
    [
        ("CKA", "container_orchestration", "CKA"),
        ("CKA - Certified Kubernetes Administrator", "container_orchestration", "CKA"),
        ("AZ-104: Microsoft Azure Administrator", "azure_compute", "AZ-104"),
        ("Microsoft Certified AZ 700", "azure_networking", "AZ-700"),
    ],
)
def test_exact_cert_code_token_maps(db, label, skill, code):
    assert resolve_cert_label(label, CODES, db) == (skill, code, "exact_cert_code")


@pytest.mark.parametrize(
    "label",
    [
        "Certified Kubernetes Administrator",  # no code token: needs a human alias
        "BACKAPPLICATION Specialist",          # contains the letters "cka" — the old substring bug
        "AZ",                                  # partial code
        "Azure 104 fundamentals",              # tokens present but not consecutive as a code
    ],
)
def test_labels_without_an_exact_code_stay_unmapped(db, label):
    assert resolve_cert_label(label, CODES, db) == (None, None, "unmapped_label")


def test_label_matching_codes_for_two_skills_is_ambiguous(db):
    assert resolve_cert_label("CKA and AZ-700 bundle", CODES, db)[2] == "ambiguous_label"


def test_human_alias_takes_precedence(db):
    db.upsert_skill_alias(
        "certified kubernetes administrator", "container_orchestration", 1.0, "human"
    )
    assert resolve_cert_label("Certified Kubernetes Administrator", CODES, db) == (
        "container_orchestration",
        None,
        "human_alias",
    )


def test_pending_alias_does_not_map_a_certificate(db):
    db.upsert_skill_alias(
        "certified kubernetes administrator", "container_orchestration", 0.4, "pending"
    )
    assert resolve_cert_label("Certified Kubernetes Administrator", CODES, db)[2] == "unmapped_label"


def test_promotion_counts_unmapped_and_stores_cert_code_not_skill_id(tmp_path):
    db_path = tmp_path / "promote.db"
    db = HermesDB(db_path)
    svc = HermesService(db=db)
    coded = svc.abstract({"employee_id": "cert-subject", "name": "Cert Subject"})["coded_identity"]
    rows = [
        {"staging_id": "s-ok", "cert_label": "CKA - Certified Kubernetes Administrator"},
        {"staging_id": "s-unmapped", "cert_label": "BACKAPPLICATION Specialist"},
    ]
    with db.session() as conn:
        for r in rows:
            conn.execute(
                "INSERT INTO cert_staging (staging_id, coded_identity, cert_label, promoted) "
                "VALUES (?, ?, ?, 0)",
                (r["staging_id"], coded, r["cert_label"]),
            )
    csv_path = tmp_path / "req.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["staging_id", "person_name", "coded_identity", "cert_label", "earned_at"]
        )
        w.writeheader()
        for r in rows:
            w.writerow(
                {**r, "person_name": "x", "coded_identity": coded, "earned_at": "2025-06-01T00:00:00+00:00"}
            )

    report = promote_dated_certs(csv_path, db_path)
    assert report["promoted"] == 1
    assert report["skipped_unmapped_label"] == 1
    with db.session() as conn:
        ok = conn.execute(
            "SELECT cert_code, promoted FROM cert_staging WHERE staging_id='s-ok'"
        ).fetchone()
        bad = conn.execute(
            "SELECT promoted FROM cert_staging WHERE staging_id='s-unmapped'"
        ).fetchone()
    assert ok["cert_code"] == "CKA"  # a cert code, never a skill_id
    assert ok["promoted"] == 1
    assert bad["promoted"] == 0


# --------------------------------------------------------------------------
# G-4 — baseline isolation through the DB-backed service path
# --------------------------------------------------------------------------

def _strip(result):
    d = result.model_dump(mode="json")
    d.pop("computed_at", None)
    return d


def test_service_rank_and_gaps_unchanged_by_baseline_rows(tmp_path):
    """Runs through HermesService, which loads from SQLite — the path the old test skipped."""
    db_path = tmp_path / "iso.db"
    ingest(FIXTURE, db_path)
    svc = HermesService(db=HermesDB(db_path))
    request = StaffingRequest(
        request_id="iso-svc",
        requester_id="mgr",
        required_skills={"container_orchestration": ProficiencyLevel.PROFICIENT},
        shortlist_size=5,
    )
    role = TargetRoleProfile(
        role_id="r",
        role_name="R",
        required_skills={"container_orchestration": ProficiencyLevel.EXPERT},
    )
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    svc.stage_and_merge([], as_of=as_of, computation_run_id="iso-run")
    before_rank = _strip(svc.rank(request, min_coverage_ratio=0.0))
    shortlisted = [c["coded_identity"] for c in before_rank["candidates"]]
    subject = shortlisted[-1]
    before_gaps = _strip(svc.gaps(subject, role))

    # Flood the baseline: max ratings for the lowest-ranked candidate, min for the rest.
    for i, identity in enumerate(shortlisted):
        for skill in ("container_orchestration", "azure_networking", "infrastructure_as_code"):
            svc.db.insert_baseline(
                baseline_id=f"flood-{i}-{skill}",
                coded_identity=identity,
                raw_label=skill,
                raw_value=5.0,
                normalised_level=5 if identity == subject else 1,
                source_sheet="AWS",
                source_scale="five_point_undefined",
                skill_id=skill,
            )
    assert svc.db.count_baseline() > 0

    svc.stage_and_merge([], as_of=as_of, computation_run_id="iso-run")
    after_rank = _strip(svc.rank(request, min_coverage_ratio=0.0))
    after_gaps = _strip(svc.gaps(subject, role))
    assert after_rank == before_rank
    assert after_gaps == before_gaps


# --------------------------------------------------------------------------
# API validation + G-1 role enforcement
# --------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "api.db"
    ingest(FIXTURE, db_path)
    os.environ["HERMES_DB_PATH"] = str(db_path)
    os.environ.pop("HERMES_API_KEY", None)
    os.environ.pop("FUNCTION_AUTH_KEY", None)
    svc = HermesService(db=HermesDB(db_path))
    reset_service_for_tests(svc)
    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/token", json={"sub": "demo-manager"}
        ).json()
        c.headers.update({"Authorization": f"Bearer {tok['access_token']}"})
        yield c, svc


@pytest.mark.parametrize("level", [0, 6, -1, 99])
def test_out_of_range_level_is_422_not_500(client, level):
    c, _ = client
    r = c.post(
        "/api/fitness/rank",
        json={"request_id": "bad", "required_skills": {"container_orchestration": level}},
    )
    assert r.status_code == 422


def test_empty_required_skills_is_422(client):
    c, _ = client
    assert c.post("/api/fitness/rank", json={"request_id": "e", "required_skills": {}}).status_code == 422


def test_gap_endpoint_also_validates_levels(client):
    c, svc = client
    coded = svc.db.load_skills_matrix()[0].coded_identity
    r = c.post(
        "/api/fitness/gaps",
        json={
            "coded_identity": coded,
            "role_id": "r",
            "role_name": "R",
            "required_skills": {"container_orchestration": 9},
        },
    )
    assert r.status_code == 422


def test_min_coverage_outside_unit_interval_is_422(client):
    c, _ = client
    r = c.post(
        "/api/fitness/rank",
        json={
            "request_id": "cov",
            "required_skills": {"container_orchestration": 3},
            "min_coverage_ratio": 1.5,
        },
    )
    assert r.status_code == 422


def test_unknown_role_id_is_404(client):
    c, _ = client
    r = c.post(
        "/api/fitness/rank",
        json={"request_id": "x", "required_skills": {"container_orchestration": 3}, "role_id": "nope"},
    )
    assert r.status_code == 404


def test_role_critical_skill_is_enforced_even_when_client_omits_it(client):
    """G-1: the role's critical skill applies server-side, with no help from the body."""
    c, svc = client
    svc.db.upsert_role(
        "iac_role",
        "IaC Role",
        {"azure_compute": 2},
        critical_skills=["infrastructure_as_code"],
        min_coverage_ratio=0.0,
    )
    body = {
        "request_id": "g1-loose",
        "required_skills": {"azure_compute": 2},
        "shortlist_size": 10,
        "min_coverage_ratio": 0.0,
    }
    loose = c.post("/api/fitness/rank", json=body).json()
    enforced = c.post(
        "/api/fitness/rank", json={**body, "request_id": "g1-role", "role_id": "iac_role"}
    ).json()

    matrix = svc.db.load_skills_matrix()
    # infrastructure_as_code is satisfied directly, or via its related skill
    # container_orchestration (taxonomy related_skills) at the adjacency discount.
    satisfies_critical = {
        m.coded_identity
        for m in matrix
        if m.skill_id in ("infrastructure_as_code", "container_orchestration")
    }
    loose_ids = {x["coded_identity"] for x in loose["candidates"]}
    enforced_ids = {x["coded_identity"] for x in enforced["candidates"]}

    assert enforced_ids == loose_ids & satisfies_critical
    assert loose_ids - enforced_ids, "fixture must contain someone the role excludes"
    reasons = {e["coded_identity"]: e["reason"] for e in enforced["excluded_candidates"]}
    for dropped in loose_ids - enforced_ids:
        assert reasons[dropped] == "missing_critical_skill"


def test_client_cannot_loosen_role_coverage_floor(client):
    c, svc = client
    svc.db.upsert_role(
        "strict",
        "Strict",
        {"container_orchestration": 3, "azure_networking": 3},
        min_coverage_ratio=1.0,
    )
    result = c.post(
        "/api/fitness/rank",
        json={
            "request_id": "floor",
            "required_skills": {"container_orchestration": 3, "azure_networking": 3},
            "shortlist_size": 5,
            "min_coverage_ratio": 0.0,
            "role_id": "strict",
        },
    ).json()
    for cand in result["candidates"]:
        assert cand["calculation"]["min_coverage_ratio"] == 1.0
        assert cand["calculation"]["coverage_ratio"] == 1.0
    assert all(
        e["reason"] in {"below_min_coverage", "no_evidence_on_any_required_skill"}
        for e in result["excluded_candidates"]
    )
