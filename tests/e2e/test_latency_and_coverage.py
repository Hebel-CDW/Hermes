import time
from datetime import datetime

from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel, StaffingRequest


def test_rank_path_under_3_seconds(gate, inference, fitness, fixture_data):
    evidence = []
    for ticket in fixture_data["tickets"]:
        abstracted = gate.abstract_record(ticket)
        occurred = datetime.fromisoformat(ticket["resolved_at"].replace("Z", "+00:00"))
        evidence.extend(
            inference.infer_from_ticket(
                abstracted.coded_identity,
                ticket["short_description"],
                occurred,
                ticket["ticket_number"],
                ticket["ticket_number"],
            )
        )
    matrix = inference.merge_evidence(evidence)
    request = StaffingRequest(
        request_id="lat-1",
        requester_id="mgr",
        required_skills={"container_orchestration": ProficiencyLevel.WORKING},
    )
    start = time.perf_counter()
    result = fitness.rank_candidates(request, matrix)
    elapsed = time.perf_counter() - start
    assert result.candidates
    assert elapsed < 3.0


def test_evidence_coverage_meets_target(gate, inference, fixture_data):
    evidence = []
    for ticket in fixture_data["tickets"]:
        abstracted = gate.abstract_record(ticket)
        occurred = datetime.fromisoformat(ticket["resolved_at"].replace("Z", "+00:00"))
        evidence.extend(
            inference.infer_from_ticket(
                abstracted.coded_identity,
                ticket["short_description"],
                occurred,
                ticket["ticket_number"],
                ticket["ticket_number"],
            )
        )
    demo = {e.coded_identity for e in evidence if e.evidence_type == EvidenceType.DEMONSTRATED}
    population = {gate.tokenize(p["employee_id"]) for p in fixture_data["pilot_population"]}
    coverage = len(demo & population) / len(population)
    assert coverage >= 0.8
