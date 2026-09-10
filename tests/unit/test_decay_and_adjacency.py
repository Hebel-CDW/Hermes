from datetime import datetime, timedelta, timezone

from fitness_gap.engine import FitnessGapEngine
from shared.audit import AuditLedger
from shared.models import ProficiencyLevel, SkillRecord, StaffingRequest
from skill_inference.engine import SkillInferenceEngine
from shared.taxonomy import load_taxonomy, validate_taxonomy_completeness


def test_taxonomy_requires_decay_and_keywords():
    tax = load_taxonomy()
    assert validate_taxonomy_completeness(tax) == []


def test_fast_decays_faster_than_slow():
    eng = SkillInferenceEngine()
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    occurred = as_of - timedelta(days=180)
    fast = eng.freshness_score(occurred, skill_id="container_orchestration", as_of=as_of)
    slow = eng.freshness_score(occurred, skill_id="incident_management", as_of=as_of)
    assert fast < slow


def test_adjacency_discount_nonzero():
    engine = FitnessGapEngine(
        audit=AuditLedger(),
        adjacency={"container_orchestration": ["azure_compute"]},
    )
    matrix = [
        SkillRecord(
            coded_identity="EMP-aaaa1111",
            skill_id="azure_compute",
            proficiency=ProficiencyLevel.ADVANCED,
            confidence=0.8,
            freshness=0.9,
            volume_score=0.7,
            evidence_ids=["e1"],
            scoring_config_version="t",
            computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    ]
    req = StaffingRequest(
        request_id="adj",
        requester_id="mgr",
        required_skills={"container_orchestration": ProficiencyLevel.WORKING},
        shortlist_size=3,
    )
    result = engine.rank_candidates(req, matrix, min_coverage_ratio=0.5)
    assert result.candidates
    detail = result.candidates[0].reasoning_detail["container_orchestration"]
    assert detail["adjacency_discount"] == 0.5
    assert result.candidates[0].fitness_score > 0
