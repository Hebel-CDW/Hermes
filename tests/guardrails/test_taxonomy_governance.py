"""Phase 6 — governed label→skill mapping.

The workflow under test:

    raw_label → normalized_label → candidate canonical skill → confidence
              → HUMAN APPROVAL → canonical skill

Ambiguous labels must stop at `pending` and stay invisible to scoring. These tests
prove the four properties the V2 brief names explicitly, plus the culture-fit policy.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from fitness_gap.engine import FitnessGapEngine  # noqa: E402
from phase8.aliases import SkillAliasResolver, ontology_lookup_map  # noqa: E402
from shared.audit import AuditLedger  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.exclusions import ExclusionLog, classify_assessment_column  # noqa: E402
from shared.models import (  # noqa: E402
    CultureFitForbiddenError,
    ProficiencyLevel,
    SkillRecord,
    StaffingRequest,
)
from shared.taxonomy import load_taxonomy  # noqa: E402


@pytest.fixture()
def resolver(tmp_path):
    db = HermesDB(tmp_path / "gov.db")
    return db, SkillAliasResolver(db, ontology_lookup_map(load_taxonomy()))


def _matrix_row(skill_id: str) -> SkillRecord:
    return SkillRecord(
        coded_identity="EMP-aaaa0001",
        skill_id=skill_id,
        proficiency=ProficiencyLevel.ADVANCED,
        confidence=0.9,
        freshness=0.9,
        volume_score=0.9,
        evidence_ids=["ev-1"],
        scoring_config_version="test",
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _rank_for(skill_id: str, matrix):
    engine = FitnessGapEngine(audit=AuditLedger())
    return engine.rank_candidates(
        StaffingRequest(
            request_id="gov",
            requester_id="mgr",
            required_skills={skill_id: ProficiencyLevel.WORKING},
            shortlist_size=5,
        ),
        matrix,
    )


# --------------------------------------------------------------------------
# 1. Pending aliases never enter scoring
# --------------------------------------------------------------------------

def test_ambiguous_label_stops_at_pending(resolver):
    _db, res = resolver
    out = res.resolve("Kubernetes-ish Container Thing")
    assert out.mapped_by == "pending"
    assert out.skill_id is None
    assert out.match_confidence == 0.0


def test_pending_alias_is_persisted_for_human_review(resolver):
    db, res = resolver
    res.resolve("Totally Unknown Widget")
    assert db.count_pending_aliases() >= 1
    with db.session() as conn:
        row = conn.execute(
            "SELECT skill_id, mapped_by FROM skill_aliases WHERE alias_label = ?",
            ("totally unknown widget",),
        ).fetchone()
    assert row["mapped_by"] == "pending"
    assert row["skill_id"] == ""  # sentinel: no canonical skill claimed


def test_pending_label_produces_no_scoreable_skill(resolver):
    """The load-bearing property: a pending label cannot be ranked against."""
    _db, res = resolver
    out = res.resolve("Some Unmapped Tool")
    assert out.skill_id is None
    # There is no skill_id, so no matrix row can exist for it, so ranking finds nobody.
    result = _rank_for("some_unmapped_tool", [_matrix_row("container_orchestration")])
    assert result.candidates == []
    assert {e["reason"] for e in result.excluded_candidates} == {
        "no_evidence_on_any_required_skill"
    }


def test_pending_aliases_are_never_auto_promoted(resolver):
    """Repeated resolution must not escalate pending → auto."""
    db, res = resolver
    for _ in range(5):
        res.resolve("Persistent Unknown Label")
    with db.session() as conn:
        row = conn.execute(
            "SELECT mapped_by FROM skill_aliases WHERE alias_label = ?",
            ("persistent unknown label",),
        ).fetchone()
    assert row["mapped_by"] == "pending"


# --------------------------------------------------------------------------
# 2. Approved aliases enter scoring
# --------------------------------------------------------------------------

def test_exact_ontology_match_resolves_automatically(resolver):
    _db, res = resolver
    out = res.resolve("Container Orchestration")
    assert out.mapped_by == "auto"
    assert out.skill_id == "container_orchestration"
    assert out.match_confidence == 1.0


def test_human_approved_alias_resolves_and_can_be_scored(tmp_path):
    db = HermesDB(tmp_path / "approved.db")
    # A human curator approves the mapping.
    db.upsert_skill_alias("k8s admin", "container_orchestration", 0.9, "human")
    res = SkillAliasResolver(db, ontology_lookup_map(load_taxonomy()))

    out = res.resolve("K8s Admin")
    assert out.mapped_by == "human"
    assert out.skill_id == "container_orchestration"

    # And that canonical skill is rankable.
    result = _rank_for(out.skill_id, [_matrix_row(out.skill_id)])
    assert [c.coded_identity for c in result.candidates] == ["EMP-aaaa0001"]


def test_approval_is_the_only_transition_from_pending(tmp_path):
    """pending → human is a deliberate write, never inferred."""
    db = HermesDB(tmp_path / "transition.db")
    res = SkillAliasResolver(db, ontology_lookup_map(load_taxonomy()))

    first = res.resolve("Ambiguous Platform Label")
    assert first.mapped_by == "pending" and first.skill_id is None

    db.upsert_skill_alias("ambiguous platform label", "azure_compute", 0.8, "human")
    # Fresh resolver: the in-process cache must not mask the approved row.
    reread = SkillAliasResolver(db, ontology_lookup_map(load_taxonomy()))
    after = reread.resolve("Ambiguous Platform Label")
    assert after.mapped_by == "human"
    assert after.skill_id == "azure_compute"


# --------------------------------------------------------------------------
# 3. Account labels never become skills
# --------------------------------------------------------------------------

def test_account_label_classified_as_account_not_skill():
    log = ExclusionLog()
    assert classify_assessment_column("cottage health", "AWS", log) == "account"
    assert log.entries[0]["reason"] == "client_account_context"


def test_account_context_rows_are_not_scoreable(tmp_path):
    """account_context has no skill_id and no path into the matrix."""
    db = HermesDB(tmp_path / "acct.db")
    db.upsert_identity("EMP-aaaa0001", "src-1", "Display Only")
    db.upsert_account_context("EMP-aaaa0001", "cottage health", 5.0, "AWS")

    assert db.load_skills_matrix() == []
    result = _rank_for("cottage_health", [])
    assert result.candidates == []


def test_account_label_is_not_in_the_ontology():
    tax = load_taxonomy()
    ids = {s.skill_id for s in tax.all_skills()}
    names = {s.name.lower() for s in tax.all_skills()}
    assert "cottage_health" not in ids
    assert "cottage health" not in names


# --------------------------------------------------------------------------
# 4. Soft skills never become skills
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label",
    [
        "customer service",
        "email etiquette",
        "meeting effectiveness",
        "flexibility",
        "knowledge sharing",
        "process awareness",
        "soft-skills",
        "technical expertise",
    ],
)
def test_soft_skill_labels_are_excluded(label):
    log = ExclusionLog()
    assert classify_assessment_column(label, "Tools", log) == "excluded"
    assert log.entries[-1]["reason"] == "soft_skill_excluded"


def test_soft_skill_labels_are_absent_from_the_ontology():
    tax = load_taxonomy()
    names = {s.name.lower() for s in tax.all_skills()}
    for label in ("customer service", "flexibility", "knowledge sharing"):
        assert label not in names


def test_soft_skill_label_is_not_scoreable():
    result = _rank_for("customer_service", [_matrix_row("container_orchestration")])
    assert result.candidates == []


# --------------------------------------------------------------------------
# 5. Culture fit — documented policy
# --------------------------------------------------------------------------

def test_culture_fit_raises_for_direct_callers():
    """Policy part 1: the classifier refuses outright."""
    log = ExclusionLog()
    with pytest.raises(CultureFitForbiddenError):
        classify_assessment_column("Culture Fit", "Tools", log)


def test_culture_fit_is_case_and_space_insensitive():
    log = ExclusionLog()
    for variant in ("culture fit", "Culture Fit", "  CULTURE FIT  "):
        with pytest.raises(CultureFitForbiddenError):
            classify_assessment_column(variant, "AWS", log)


def test_culture_fit_is_stripped_and_logged_during_full_workbook_ingest():
    """Policy part 2 (docs/phase8/BLOCKED.md B-CULTURE-FIT-COLUMNS).

    Most 2025 sheets carry a Culture fit column. Aborting the whole workbook would
    make ingestion impossible, so the parser strips the column and records an
    explicit `culture_fit_forbidden_column` exclusion. The value never becomes an
    assessment either way.
    """
    from openpyxl import Workbook

    from phase8.parsers import parse_standard_people_rows
    from phase8.workbook import sheet_rows

    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "Culture fit", "Kubernetes"])
    ws.append(["Ada Lovelace", 5, 4])

    log = ExclusionLog()
    assessments, _ = parse_standard_people_rows("AWS", sheet_rows(ws), log)

    assert "Culture fit" not in {a.raw_label for a in assessments}
    assert "culture_fit_forbidden_column" in {e["reason"] for e in log.entries}
    # The legitimate skill on the same row still ingests.
    assert "Kubernetes" in {a.raw_label for a in assessments}


def test_culture_fit_is_absent_from_the_ontology():
    tax = load_taxonomy()
    assert "culture fit" not in {s.name.lower() for s in tax.all_skills()}
    assert "culture_fit" not in {s.skill_id for s in tax.all_skills()}
