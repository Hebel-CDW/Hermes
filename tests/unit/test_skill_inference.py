from datetime import datetime, timezone

from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel
from skill_inference.engine import SkillInferenceEngine


def test_infer_from_kubernetes_ticket(inference):
    records = inference.infer_from_ticket(
        "EMP-00000142",
        "Kubernetes migration for payment cluster",
        datetime(2026, 7, 1, tzinfo=timezone.utc),
        "INC001",
        "INC001",
    )
    assert any(r.skill_id == "container_orchestration" for r in records)


def test_merge_weights_demonstrated_over_declared(inference):
    evidence = [
        EvidenceRecord(
            evidence_id="d1",
            coded_identity="EMP-00000001",
            skill_id="container_orchestration",
            evidence_type=EvidenceType.DEMONSTRATED,
            proficiency=ProficiencyLevel.ADVANCED,
            occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source_ref="INC1",
        ),
        EvidenceRecord(
            evidence_id="c1",
            coded_identity="EMP-00000001",
            skill_id="container_orchestration",
            evidence_type=EvidenceType.CERTIFIED,
            proficiency=ProficiencyLevel.PROFICIENT,
            occurred_at=datetime(2025, 11, 1, tzinfo=timezone.utc),
            source_ref="CKA",
        ),
        EvidenceRecord(
            evidence_id="decl1",
            coded_identity="EMP-00000001",
            skill_id="container_orchestration",
            evidence_type=EvidenceType.DECLARED,
            proficiency=ProficiencyLevel.WORKING,
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source_ref="form",
            metadata={"manager_confirmed": True},
        ),
    ]
    merged = inference.merge_evidence(evidence)
    assert len(merged) == 1
    rec = merged[0]
    assert rec.confidence > 0
    assert rec.freshness > 0
    assert "d1" in rec.evidence_ids
    assert rec.proficiency.value >= ProficiencyLevel.PROFICIENT.value


def test_freshness_decays(inference):
    recent = inference.freshness_score(datetime(2026, 8, 1, tzinfo=timezone.utc), as_of=datetime(2026, 9, 1, tzinfo=timezone.utc))
    old = inference.freshness_score(datetime(2024, 1, 1, tzinfo=timezone.utc), as_of=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert recent > old
