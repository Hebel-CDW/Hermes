import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HERMES_TEST_MODE", "1")

from shared.db import HermesDB
from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel, StaffingRequest
from shared.service import HermesService
from shared.taxonomy import load_taxonomy
from scripts.ingest_fixtures import ingest


def test_keyword_precision_fixture_runs():
    tickets = json.loads(Path("data/fixtures/validation/held_out_tickets.json").read_text())[
        "tickets"
    ]
    tax = load_taxonomy()
    assert len(tickets) >= 10
    hits = 0
    for t in tickets:
        pred = set(tax.match_keywords(t["short_description"]))
        hits += len(pred & set(t["expected_skills"]))
    assert hits >= 5


def test_manager_decisions_count_30():
    decisions = json.loads(
        Path("data/fixtures/validation/manager_decisions.json").read_text()
    )["decisions"]
    assert len(decisions) == 30


def test_cold_start_visible(tmp_path):
    db_path = tmp_path / "cold.db"
    ingest(Path("data/fixtures/pilot_population.json"), db_path)
    svc = HermesService(db=HermesDB(db_path))
    new = svc.abstract({"employee_id": "E-NEWJOIN", "name": "New Joiner"})
    coded = new["coded_identity"]
    svc.stage_and_merge(
        [
            EvidenceRecord(
                evidence_id="decl-new",
                coded_identity=coded,
                skill_id="container_orchestration",
                evidence_type=EvidenceType.DECLARED,
                proficiency=ProficiencyLevel.WORKING,
                occurred_at=datetime.now(timezone.utc),
                source_ref="declared",
                metadata={"manager_confirmed": False},
            )
        ]
    )
    result = svc.rank(
        StaffingRequest(
            request_id="cold",
            requester_id="mgr",
            required_skills={"container_orchestration": ProficiencyLevel.PROFICIENT},
            shortlist_size=5,
        )
    )
    shortlisted = {c.coded_identity for c in result.candidates}
    assert coded not in shortlisted
    me = svc.me(coded)
    assert me["coded_identity"] == coded
