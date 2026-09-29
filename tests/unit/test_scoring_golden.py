"""Golden scoring tests — pin exact numeric outputs and config-hash faithfulness.

Two properties are asserted here, both of which the Phase 1 audit found unpinned:

1. **Golden values.** A fixed matrix produces an exact, hand-derivable fitness
   score. Any silent change to the ranking formula fails this test.
2. **Config-hash faithfulness (C-3).** ``scoring_config_version`` must change
   *if and only if* scores can change. Before the fix, ``allocation_weight`` was
   part of the version hash but unused by the engine, so tuning
   ``HERMES_ALLOC_W`` changed the recorded version while leaving every score
   byte-identical — an unsound reproducibility claim.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from fitness_gap.engine import FitnessGapEngine  # noqa: E402
from shared.audit import AuditLedger  # noqa: E402
from shared.config import DEFAULT_SCORING, load_scoring_config  # noqa: E402
from shared.models import ProficiencyLevel, SkillRecord, StaffingRequest  # noqa: E402

# --- Fixed inputs (the worked example documented in SCORING_SPECIFICATION.md) ---
CODED = "EMP-aaaa0001"
SKILL = "container_orchestration"
LEVEL = 4
REQUIRED = ProficiencyLevel.PROFICIENT  # 3
CONFIDENCE = 0.90
FRESHNESS = 0.80
VOLUME = 0.70

# level_ratio  = min(1, 4/3)          = 1.00
# contribution = 1.00*0.90*0.70*0.80  = 0.504   (adjacency_discount = 1.0)
# mean over 1 required skill          = 0.504
EXPECTED_CONTRIBUTION = 0.504


def _record(version: str) -> SkillRecord:
    return SkillRecord(
        coded_identity=CODED,
        skill_id=SKILL,
        proficiency=ProficiencyLevel(LEVEL),
        confidence=CONFIDENCE,
        freshness=FRESHNESS,
        volume_score=VOLUME,
        evidence_ids=[f"{CODED}-{SKILL}"],
        scoring_config_version=version,
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _request() -> StaffingRequest:
    return StaffingRequest(
        request_id="golden",
        requester_id="mgr-golden",
        required_skills={SKILL: REQUIRED},
        shortlist_size=3,
    )


def _score(config, allocation: float) -> float:
    engine = FitnessGapEngine(config=config, audit=AuditLedger())
    result = engine.rank_candidates(
        _request(), [_record(config.version)], allocation={CODED: allocation}
    )
    return result.candidates[0].fitness_score


# --------------------------------------------------------------------------
# 1. Golden values
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "allocation,expected",
    [
        (1.0, 0.504),   # 0.504 * (0.85 + 0.15*1.0) = 0.504 * 1.000
        (0.5, 0.4662),  # 0.504 * (0.85 + 0.15*0.5) = 0.504 * 0.925
        (0.0, 0.4284),  # 0.504 * (0.85 + 0.15*0.0) = 0.504 * 0.850
    ],
)
def test_golden_fitness_score_at_default_config(allocation, expected):
    """Exact score for a fixed matrix under the default scoring config."""
    assert _score(DEFAULT_SCORING, allocation) == expected


def test_golden_contribution_is_product_of_the_five_factors():
    """The documented formula is reproducible from reasoning_detail alone."""
    engine = FitnessGapEngine(config=DEFAULT_SCORING, audit=AuditLedger())
    result = engine.rank_candidates(
        _request(), [_record(DEFAULT_SCORING.version)], allocation={CODED: 1.0}
    )
    detail = result.candidates[0].reasoning_detail[SKILL]
    level_ratio = min(1.0, detail["level"] / detail["required"])
    recomputed = (
        level_ratio
        * detail["confidence"]
        * detail["volume_score"]
        * detail["freshness"]
        * detail["adjacency_discount"]
    )
    assert round(recomputed, 4) == EXPECTED_CONTRIBUTION
    # allocation 1.0 leaves the mean untouched
    assert result.candidates[0].fitness_score == EXPECTED_CONTRIBUTION


def test_default_config_version_is_pinned():
    """A change to any scoring constant must be a deliberate, visible event."""
    # Moved from e0014592104e in V2 hardening: the hash now also covers the decay-class
    # effective per-skill half-lives, the adjacency discount, and ontology keywords/relations.
    assert DEFAULT_SCORING.version == "9220dcfdfcf3", (
        "Default scoring config changed. This is allowed, but it invalidates every "
        "stored score: update this pin, recompute the matrix, and record the change "
        "in docs/SCORING_SPECIFICATION.md."
    )


# --------------------------------------------------------------------------
# 2. Config-hash faithfulness (C-3 regression)
# --------------------------------------------------------------------------

def test_changing_allocation_weight_changes_both_version_and_score(monkeypatch):
    """C-3: a config field in the version hash must actually affect scores.

    Regression guard — previously HERMES_ALLOC_W moved the hash but not the score.
    """
    baseline_cfg = load_scoring_config()
    baseline_score = _score(baseline_cfg, allocation=0.0)

    monkeypatch.setenv("HERMES_ALLOC_W", "0.40")
    tuned_cfg = load_scoring_config()
    tuned_score = _score(tuned_cfg, allocation=0.0)

    assert tuned_cfg.version != baseline_cfg.version, "version hash must track config"
    assert tuned_score != baseline_score, (
        "allocation_weight is in the version hash but did not change the score — "
        "the scoring_config_version claim is unsound (C-3)"
    )
    # 0.504 * (1 - 0.40) = 0.3024
    assert tuned_score == 0.3024


def test_allocation_weight_default_reproduces_historical_formula():
    """Refactor safety: w=0.15 must equal the previously hardcoded 0.85 + 0.15*a."""
    for allocation in (0.0, 0.25, 0.5, 0.75, 1.0):
        expected = round(EXPECTED_CONTRIBUTION * (0.85 + 0.15 * allocation), 4)
        assert _score(DEFAULT_SCORING, allocation) == expected


def test_version_is_stable_for_identical_config():
    """Determinism: the hash is a pure function of the config values."""
    assert load_scoring_config().version == load_scoring_config().version


def test_allocation_is_clamped_to_unit_interval():
    """Out-of-range allocation cannot inflate or negate a score."""
    assert _score(DEFAULT_SCORING, allocation=5.0) == _score(DEFAULT_SCORING, allocation=1.0)
    assert _score(DEFAULT_SCORING, allocation=-3.0) == _score(DEFAULT_SCORING, allocation=0.0)
