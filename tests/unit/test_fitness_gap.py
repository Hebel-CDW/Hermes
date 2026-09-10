from datetime import datetime, timezone

from shared.models import (
    ProficiencyLevel,
    SkillRecord,
    StaffingRequest,
    TargetRoleProfile,
)


def _skill(eid, skill, level, conf=0.9, fresh=0.9, volume=0.8, evidence=None):
    return SkillRecord(
        coded_identity=eid,
        skill_id=skill,
        proficiency=ProficiencyLevel(level),
        confidence=conf,
        freshness=fresh,
        volume_score=volume,
        evidence_ids=evidence or [f"{eid}-{skill}"],
        scoring_config_version="1.0.0",
        computed_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def test_ranking_prefers_strong_fresh_evidence(fitness):
    matrix = [
        _skill("EMP-00000142", "container_orchestration", 4, conf=0.95, fresh=0.95, volume=0.9, evidence=["t1", "t2", "c1"]),
        _skill("EMP-00000087", "container_orchestration", 3, conf=0.5, fresh=0.2, volume=0.3, evidence=["old1"]),
        _skill("EMP-00000003", "azure_networking", 4, conf=0.9, fresh=0.9, evidence=["n1"]),
    ]
    request = StaffingRequest(
        request_id="req-k8s",
        requester_id="mgr-1",
        required_skills={"container_orchestration": ProficiencyLevel.PROFICIENT},
        shortlist_size=5,
    )
    result = fitness.rank_candidates(request, matrix, allocation={"EMP-00000142": 1.0, "EMP-00000087": 1.0})
    assert result.candidates[0].coded_identity == "EMP-00000142"
    assert result.candidates[0].evidence_ids
    assert result.candidates[0].reasoning_detail


def test_shortlist_hard_cap(fitness):
    matrix = [
        _skill(f"EMP-{i:08x}", "container_orchestration", 3, volume=0.5)
        for i in range(20)
    ]
    request = StaffingRequest(
        request_id="cap",
        requester_id="mgr",
        required_skills={"container_orchestration": ProficiencyLevel.WORKING},
        shortlist_size=10,
    )
    result = fitness.rank_candidates(request, matrix)
    assert len(result.candidates) <= 10


def test_coverage_floor_excludes(fitness):
    matrix = [
        _skill("EMP-00000142", "container_orchestration", 4),
        # missing second required skill → coverage 0.5 < 0.6
        _skill("EMP-00000087", "container_orchestration", 5, volume=0.99),
    ]
    request = StaffingRequest(
        request_id="cov",
        requester_id="mgr",
        required_skills={
            "container_orchestration": ProficiencyLevel.WORKING,
            "azure_networking": ProficiencyLevel.WORKING,
        },
        shortlist_size=5,
    )
    result = fitness.rank_candidates(request, matrix, min_coverage_ratio=0.6)
    assert result.candidates == []


def test_gap_prioritization(fitness):
    matrix = [
        _skill("EMP-00000087", "container_orchestration", 4),
        _skill("EMP-00000087", "infrastructure_as_code", 3),
    ]
    role = TargetRoleProfile(
        role_id="senior_cloud_engineer",
        role_name="Senior Cloud Engineer",
        required_skills={
            "container_orchestration": ProficiencyLevel.ADVANCED,
            "azure_networking": ProficiencyLevel.PROFICIENT,
            "infrastructure_as_code": ProficiencyLevel.PROFICIENT,
        },
    )
    gaps = fitness.compute_gaps("EMP-00000087", role, matrix)
    assert gaps.gaps
    assert gaps.gaps[0].skill_id == "azure_networking"


def test_depth_outranks_shallow_volume(fitness):
    """One deep migration demo beats many shallow keyword hits on volume alone."""
    deep = _skill(
        "EMP-00000dee",
        "container_orchestration",
        4,
        conf=0.7,
        fresh=0.95,
        volume=0.5,
        evidence=["mig-1"],
    )
    shallow = _skill(
        "EMP-00000sha",
        "container_orchestration",
        2,
        conf=0.35,
        fresh=0.9,
        volume=0.95,
        evidence=[f"s{i}" for i in range(8)],
    )
    request = StaffingRequest(
        request_id="depth",
        requester_id="mgr",
        required_skills={"container_orchestration": ProficiencyLevel.PROFICIENT},
        shortlist_size=2,
    )
    result = fitness.rank_candidates(request, [deep, shallow])
    assert result.candidates[0].coded_identity == "EMP-00000dee"
