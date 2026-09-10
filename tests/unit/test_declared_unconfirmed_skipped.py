from datetime import datetime, timezone

from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel


def test_unconfirmed_declared_skipped(inference):
    evidence = [
        EvidenceRecord(
            evidence_id="decl-bad",
            coded_identity="EMP-00000001",
            skill_id="azure_compute",
            evidence_type=EvidenceType.DECLARED,
            proficiency=ProficiencyLevel.WORKING,
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source_ref="form",
            metadata={"manager_confirmed": False},
        )
    ]
    assert inference.merge_evidence(evidence) == []
