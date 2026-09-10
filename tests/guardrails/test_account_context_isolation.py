"""D3: account_context must not feed FitnessGapEngine."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from fitness_gap.engine import FitnessGapEngine
from shared.audit import AuditLedger
from shared.db import HermesDB
from shared.models import ProficiencyLevel, SkillRecord, StaffingRequest
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]


def test_fitness_engine_source_never_reads_account_context():
    """Static: FitnessGapEngine module must not reference account_context."""
    src = (ROOT / "src" / "fitness_gap" / "engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    text = ast.dump(tree)
    assert "account_context" not in src.lower()
    assert "account_context" not in text


def test_account_context_rows_do_not_change_rank(tmp_path):
    db = HermesDB(tmp_path / "ac.db")
    db.upsert_identity("EMP-aaaa0001", "e1", "Person One")
    db.upsert_account_context("EMP-aaaa0001", "cottage health", 5.0, "AWS")
    matrix = [
        SkillRecord(
            coded_identity="EMP-aaaa0001",
            skill_id="container_orchestration",
            proficiency=ProficiencyLevel.PROFICIENT,
            confidence=0.7,
            freshness=0.9,
            volume_score=0.5,
            evidence_ids=["e1"],
            scoring_config_version="t",
            computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    ]
    engine = FitnessGapEngine(audit=AuditLedger())
    req = StaffingRequest(
        request_id="r1",
        requester_id="mgr",
        required_skills={"container_orchestration": ProficiencyLevel.WORKING},
        shortlist_size=3,
    )
    def strip(result):
        data = result.model_dump(mode="json")
        data.pop("computed_at", None)
        return data

    a = strip(engine.rank_candidates(req, matrix))
    db.upsert_account_context("EMP-aaaa0001", "orthocarolina, p.a.", 4.0, "AWS")
    b = strip(engine.rank_candidates(req, matrix))
    assert a == b
