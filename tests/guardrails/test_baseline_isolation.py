"""Load-bearing: baseline_assessments must not affect scoring."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from fitness_gap.engine import FitnessGapEngine
from shared.audit import AuditLedger
from shared.db import HermesDB
from shared.models import (
    EvidenceRecord,
    EvidenceType,
    ProficiencyLevel,
    StaffingRequest,
    TargetRoleProfile,
)
from skill_inference.engine import SkillInferenceEngine


def _matrix_evidence():
    return [
        EvidenceRecord(
            evidence_id="demo-1",
            coded_identity="EMP-bbbb0001",
            skill_id="container_orchestration",
            evidence_type=EvidenceType.DEMONSTRATED,
            proficiency=ProficiencyLevel.PROFICIENT,
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source_ref="INC1",
            metadata={"matched_keywords": ["kubernetes"], "source_ref": "INC1"},
        )
    ]


def test_merge_rank_gaps_identical_with_baseline_populated_or_empty(tmp_path):
    db = HermesDB(tmp_path / "iso.db")
    db.upsert_identity("EMP-bbbb0001", "e-bb", "Baseline Subject")
    evidence = _matrix_evidence()
    inference = SkillInferenceEngine()
    fitness = FitnessGapEngine(audit=AuditLedger())

    def dump_skills(records):
        out = []
        for m in records:
            d = m.model_dump(mode="json")
            d.pop("computed_at", None)
            out.append(d)
        return out

    def dump_result(result):
        d = result.model_dump(mode="json")
        d.pop("computed_at", None)
        return d

    merged_empty = inference.merge_evidence(evidence)
    req = StaffingRequest(
        request_id="iso",
        requester_id="mgr",
        required_skills={"container_orchestration": ProficiencyLevel.WORKING},
        shortlist_size=3,
    )
    rank_empty = dump_result(fitness.rank_candidates(req, merged_empty))
    role = TargetRoleProfile(
        role_id="r",
        role_name="R",
        required_skills={"container_orchestration": ProficiencyLevel.ADVANCED},
    )
    gaps_empty = dump_result(fitness.compute_gaps("EMP-bbbb0001", role, merged_empty))

    for i in range(5):
        db.insert_baseline(
            baseline_id=f"bl-{i}",
            coded_identity="EMP-bbbb0001",
            raw_label="kubernetes",
            raw_value=5.0,
            normalised_level=5,
            source_sheet="AWS",
            source_scale="five_point_undefined",
            skill_id="container_orchestration",
            assessed_at=None,
        )
    assert db.count_baseline() == 5

    merged_full = inference.merge_evidence(evidence)
    rank_full = dump_result(fitness.rank_candidates(req, merged_full))
    gaps_full = dump_result(fitness.compute_gaps("EMP-bbbb0001", role, merged_full))

    assert dump_skills(merged_empty) == dump_skills(merged_full)
    assert rank_empty == rank_full
    assert gaps_empty == gaps_full


def test_scoring_modules_do_not_import_baseline_table():
    root = Path(__file__).resolve().parents[2] / "src"
    forbidden_readers = [
        root / "skill_inference" / "engine.py",
        root / "fitness_gap" / "engine.py",
        root / "shared" / "service.py",
    ]
    for path in forbidden_readers:
        text = path.read_text(encoding="utf-8")
        assert "baseline_assessments" not in text, f"{path} must not reference baseline_assessments"
