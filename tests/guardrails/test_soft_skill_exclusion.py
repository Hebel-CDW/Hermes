"""D2: Soft-skill exclusion and culture-fit hard raise."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from shared.exclusions import ExclusionLog, classify_assessment_column
from shared.models import CultureFitForbiddenError, EXCLUDED_ASSESSMENT_FIELDS


def test_culture_fit_raises():
    log = ExclusionLog()
    with pytest.raises(CultureFitForbiddenError):
        classify_assessment_column("Culture Fit", "Tools", log)


def test_soft_skills_excluded_and_logged():
    log = ExclusionLog()
    for label in (
        "customer service",
        "email ethiquette",
        "meeting effectiveness",
        "soft-skills",
        "process awareness",
    ):
        assert classify_assessment_column(label, "Tools", log) == "excluded"
    reasons = {e["reason"] for e in log.entries}
    assert reasons == {"soft_skill_excluded"}
    assert len(log.entries) == 5


def test_client_column_classified_as_account():
    log = ExclusionLog()
    assert classify_assessment_column("cottage health", "AWS", log) == "account"
    assert log.entries[0]["reason"] == "client_account_context"


def test_excluded_set_covers_brief_list():
    required = {
        "customer service",
        "email etiquette",
        "email ethiquette",
        "culture fit",
        "flexibility",
        "knowledge sharing",
        "soft-skills",
        "tools expertise",
        "technical expertise",
        "additional skills",
        "process awareness",
    }
    assert required <= EXCLUDED_ASSESSMENT_FIELDS


def test_excluded_labels_never_written_as_skill_rows(tmp_path):
    """Simulate ingest classification — excluded never become baseline skill rows."""
    from shared.db import HermesDB
    from shared.exclusions import ExclusionLog, classify_assessment_column

    db = HermesDB(tmp_path / "ex.db")
    db.upsert_identity("EMP-cccc0001", "ex1", "Ex Person")
    log = ExclusionLog()
    columns = [
        "customer service",
        "kubernetes",
        "cottage health",
        "email ethiquette",
        "disaster recovery",
    ]
    for col in columns:
        kind = classify_assessment_column(col, "Tools", log)
        if kind == "skill":
            db.insert_baseline(
                baseline_id=f"b-{col}",
                coded_identity="EMP-cccc0001",
                raw_label=col,
                raw_value=3.0,
                normalised_level=3,
                source_sheet="Tools",
                source_scale="five_point_undefined",
                skill_id=col.replace(" ", "_"),
            )
        elif kind == "account":
            db.upsert_account_context("EMP-cccc0001", col, 3.0, "Tools")
    with db.session() as conn:
        labels = [r["raw_label"] for r in conn.execute("SELECT raw_label FROM baseline_assessments").fetchall()]
        accounts = [r["account_label"] for r in conn.execute("SELECT account_label FROM account_context").fetchall()]
    assert "customer service" not in labels
    assert "email ethiquette" not in labels
    assert "cottage health" not in labels
    assert "cottage health" in accounts
    assert set(labels) == {"kubernetes", "disaster recovery"}
