"""Phase 3 — calculation inspector contract.

The inspector exists to answer, without reading source code:
    "Why did this candidate score 0.82?"

These tests assert that the structured payload is *sufficient* for that: every
operand of the documented formula is present, and the score is recomputable from
the payload alone. Explainability must not depend on the formatted
``per_skill_reasoning`` strings.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

os.environ.setdefault("HERMES_TEST_MODE", "1")

from fitness_gap.engine import ADJACENCY_DISCOUNT, FitnessGapEngine  # noqa: E402
from shared.audit import AuditLedger  # noqa: E402
from shared.config import DEFAULT_SCORING  # noqa: E402
from shared.models import ProficiencyLevel, SkillRecord, StaffingRequest  # noqa: E402

# Every field the brief requires the inspector to expose, per skill.
REQUIRED_SKILL_FIELDS = {
    "skill_id",
    "status",
    "required_level",
    "actual_level",
    "level_ratio",
    "confidence",
    "volume_score",
    "freshness",
    "decay_class",
    "adjacency_discount",
    "contribution",
    "evidence_ids",
    "source_refs",
}

REQUIRED_ENVELOPE_FIELDS = {
    "allocation",
    "allocation_weight",
    "allocation_multiplier",
    "coverage_ratio",
    "min_coverage_ratio",
    "mean_contribution",
    "fitness_score",
    "scoring_config_version",
    "computation_run_id",
    "formula",
}


def _rec(skill, level, conf=0.9, fresh=0.8, vol=0.7, coded="EMP-aaaa0001"):
    return SkillRecord(
        coded_identity=coded,
        skill_id=skill,
        proficiency=ProficiencyLevel(level),
        confidence=conf,
        freshness=fresh,
        volume_score=vol,
        evidence_ids=[f"ev-{skill}"],
        scoring_config_version=DEFAULT_SCORING.version,
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _request(required, size=5):
    return StaffingRequest(
        request_id="inspect",
        requester_id="mgr",
        required_skills=required,
        shortlist_size=size,
    )


def _engine(**kw):
    return FitnessGapEngine(config=DEFAULT_SCORING, audit=AuditLedger(), **kw)


def test_every_required_inspector_field_is_present():
    engine = _engine()
    result = engine.rank_candidates(
        _request({"container_orchestration": ProficiencyLevel.PROFICIENT}),
        [_rec("container_orchestration", 4)],
        allocation={"EMP-aaaa0001": 1.0},
        computation_run_id="run-fixed-001",
    )
    detail = result.candidates[0].reasoning_detail["container_orchestration"]
    missing = REQUIRED_SKILL_FIELDS - set(detail)
    assert not missing, f"inspector missing per-skill fields: {sorted(missing)}"

    envelope = result.candidates[0].calculation.model_dump()
    missing_env = REQUIRED_ENVELOPE_FIELDS - set(envelope)
    assert not missing_env, f"inspector missing envelope fields: {sorted(missing_env)}"


def test_score_is_recomputable_from_payload_alone():
    """The whole point: the arithmetic closes without touching the engine."""
    engine = _engine()
    result = engine.rank_candidates(
        _request(
            {
                "container_orchestration": ProficiencyLevel.PROFICIENT,
                "incident_management": ProficiencyLevel.WORKING,
            }
        ),
        [_rec("container_orchestration", 4), _rec("incident_management", 2)],
        allocation={"EMP-aaaa0001": 0.5},
    )
    cand = result.candidates[0]
    calc = cand.calculation

    contributions = []
    for detail in cand.reasoning_detail.values():
        if detail["status"] == "missing":
            contributions.append(0.0)
            continue
        level_ratio = min(1.0, detail["actual_level"] / detail["required_level"])
        assert round(level_ratio, 6) == detail["level_ratio"]
        contributions.append(
            level_ratio
            * detail["confidence"]
            * detail["volume_score"]
            * detail["freshness"]
            * detail["adjacency_discount"]
        )

    mean = sum(contributions) / len(contributions)
    multiplier = (1 - calc.allocation_weight) + calc.allocation_weight * calc.allocation
    assert round(mean * multiplier, 4) == cand.fitness_score
    assert round(mean, 6) == calc.mean_contribution
    assert round(multiplier, 6) == calc.allocation_multiplier


def test_missing_skill_is_explicit_not_absent():
    """A skill with no evidence must appear with status='missing', not vanish."""
    engine = _engine()
    result = engine.rank_candidates(
        _request(
            {
                "container_orchestration": ProficiencyLevel.PROFICIENT,
                "infrastructure_as_code": ProficiencyLevel.PROFICIENT,
            }
        ),
        [_rec("container_orchestration", 5)],
        min_coverage_ratio=0.5,
    )
    detail = result.candidates[0].reasoning_detail
    assert set(detail) == {"container_orchestration", "infrastructure_as_code"}
    gap = detail["infrastructure_as_code"]
    assert gap["status"] == "missing"
    assert gap["contribution"] == 0.0
    assert gap["required_level"] == 3
    assert gap["actual_level"] is None
    assert gap["evidence_ids"] == []


def test_adjacent_credit_is_labelled_and_attributed():
    """Adjacency must be visible, discounted, and name its source skill."""
    engine = _engine(adjacency={"container_orchestration": ["azure_compute"]})
    result = engine.rank_candidates(
        _request({"container_orchestration": ProficiencyLevel.WORKING}),
        [_rec("azure_compute", 4)],
        min_coverage_ratio=0.5,
    )
    detail = result.candidates[0].reasoning_detail["container_orchestration"]
    assert detail["status"] == "adjacent"
    assert detail["adjacency_discount"] == ADJACENCY_DISCOUNT
    assert detail["adjacency_source_skill"] == "azure_compute"


def test_direct_match_has_no_adjacency_source():
    engine = _engine(adjacency={"container_orchestration": ["azure_compute"]})
    result = engine.rank_candidates(
        _request({"container_orchestration": ProficiencyLevel.WORKING}),
        [_rec("container_orchestration", 4)],
    )
    detail = result.candidates[0].reasoning_detail["container_orchestration"]
    assert detail["status"] == "matched"
    assert detail["adjacency_discount"] == 1.0
    assert detail["adjacency_source_skill"] is None


def test_reasoning_detail_contains_only_skill_keys():
    """Regression: no more `_allocation` / `_exclusion` magic keys in the skill map."""
    engine = _engine()
    required = {"container_orchestration": ProficiencyLevel.PROFICIENT}
    result = engine.rank_candidates(
        _request(required), [_rec("container_orchestration", 4)]
    )
    detail = result.candidates[0].reasoning_detail
    assert set(detail) == set(required)
    assert not any(k.startswith("_") for k in detail)


def test_excluded_candidates_carry_machine_readable_reasons():
    """'Why was X not shortlisted?' must have an answer."""
    engine = _engine()
    matrix = [
        _rec("container_orchestration", 4, coded="EMP-covered0"),
        _rec("container_orchestration", 4, coded="EMP-thincov0"),
        _rec("incident_management", 4, coded="EMP-covered0"),
    ]
    result = engine.rank_candidates(
        _request(
            {
                "container_orchestration": ProficiencyLevel.PROFICIENT,
                "incident_management": ProficiencyLevel.PROFICIENT,
            }
        ),
        matrix,
        min_coverage_ratio=0.75,
    )
    reasons = {e["coded_identity"]: e["reason"] for e in result.excluded_candidates}
    assert reasons.get("EMP-thincov0") == "below_min_coverage"
    assert "EMP-covered0" not in reasons


def test_missing_critical_skill_is_reported_as_such():
    engine = _engine()
    result = engine.rank_candidates(
        _request({"container_orchestration": ProficiencyLevel.PROFICIENT}),
        [_rec("container_orchestration", 4)],
        critical_skills=["infrastructure_as_code"],
    )
    assert result.candidates == []
    reasons = {e["reason"] for e in result.excluded_candidates}
    assert reasons == {"missing_critical_skill"}


def test_run_id_and_config_version_are_carried_on_the_result():
    """Reproducibility keys travel with the answer, not just the database."""
    engine = _engine()
    result = engine.rank_candidates(
        _request({"container_orchestration": ProficiencyLevel.PROFICIENT}),
        [_rec("container_orchestration", 4)],
        computation_run_id="run-fixed-002",
    )
    assert result.computation_run_id == "run-fixed-002"
    assert result.scoring_config_version == DEFAULT_SCORING.version
    calc = result.candidates[0].calculation
    assert calc.computation_run_id == "run-fixed-002"
    assert calc.scoring_config_version == DEFAULT_SCORING.version


def test_formula_string_matches_the_implemented_arithmetic():
    """The stated formula must name exactly the operands the code multiplies."""
    engine = _engine()
    result = engine.rank_candidates(
        _request({"container_orchestration": ProficiencyLevel.PROFICIENT}),
        [_rec("container_orchestration", 4)],
    )
    formula = result.candidates[0].calculation.formula
    for operand in (
        "level_ratio",
        "confidence",
        "volume_score",
        "freshness",
        "adjacency_discount",
        "allocation_weight",
        "allocation",
    ):
        assert operand in formula, f"formula omits {operand}"
