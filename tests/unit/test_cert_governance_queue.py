"""Phase 2 Step A/B — the admin cert-governance triage queue.

Covers the four lifecycle states a staged certificate can be in before promotion:
needs date + mapping, needs date only, needs mapping only, ready to promote; plus
confirms a promoted cert drops out of ``items`` but is still counted.
"""

from __future__ import annotations

import os

os.environ.setdefault("HERMES_TEST_MODE", "1")

from shared.db import HermesDB  # noqa: E402
from shared.read_models import cert_governance_queue  # noqa: E402
from shared.service import HermesService  # noqa: E402


def _stage_cert(db, staging_id, coded, label, code=None, earned_at=None, promoted=0):
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO cert_staging (staging_id, coded_identity, cert_label, cert_code, earned_at, promoted)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (staging_id, coded, label, code, earned_at, promoted),
        )


def test_queue_buckets_every_lifecycle_state(tmp_path):
    db = HermesDB(tmp_path / "queue.db")
    svc = HermesService(db=db)
    coded = svc.abstract({"employee_id": "cert-queue-person", "name": "Queue Person"})["coded_identity"]

    _stage_cert(db, "s-neither", coded, "Totally Unknown Label")
    _stage_cert(db, "s-date-only", coded, "Still Unknown Label", earned_at="2025-01-01T00:00:00Z")
    # A governed human alias makes the label resolve to a real skill without a date.
    db.upsert_skill_alias("security specialty", "python", 1.0, "human")
    _stage_cert(db, "s-mapping-only", coded, "Security Specialty")
    _stage_cert(db, "s-ready", coded, "Security Specialty", earned_at="2025-01-01T00:00:00Z")
    _stage_cert(db, "s-done", coded, "Security Specialty", earned_at="2025-01-01T00:00:00Z", promoted=1)

    result = cert_governance_queue(db, svc.inference.taxonomy)

    by_id = {item["staging_id"]: item for item in result["items"]}
    assert by_id["s-neither"]["status"] == "needs_date_and_mapping"
    assert by_id["s-date-only"]["status"] == "needs_mapping"
    assert by_id["s-mapping-only"]["status"] == "needs_date"
    assert by_id["s-mapping-only"]["resolved_skill_id"] == "python"
    assert by_id["s-ready"]["status"] == "ready_to_promote"
    assert "s-done" not in by_id, "a promoted cert must not appear in the actionable queue"

    assert result["counts"]["promoted"] == 1
    assert result["counts"]["ready_to_promote"] == 1
    assert result["counts"]["needs_date"] == 2  # s-neither, s-mapping-only
    assert result["counts"]["needs_mapping"] == 2  # s-neither, s-date-only


def test_empty_cert_staging_returns_zero_counts(tmp_path):
    db = HermesDB(tmp_path / "empty.db")
    svc = HermesService(db=db)
    result = cert_governance_queue(db, svc.inference.taxonomy)
    assert result == {
        "counts": {"needs_date": 0, "needs_mapping": 0, "ready_to_promote": 0, "promoted": 0},
        "items": [],
    }
