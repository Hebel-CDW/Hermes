"""End-to-end in-process pipeline: abstract -> infer -> rank -> resolve."""

from datetime import datetime, timezone

from shared.models import (
    EvidenceRecord,
    EvidenceType,
    ProficiencyLevel,
    StaffingRequest,
)


def test_kubernetes_staffing_worked_example(gate, inference, fitness, resolution, fixture_data):
    evidence = []
    for person in fixture_data["pilot_population"]:
        gate.abstract_record({"employee_id": person["employee_id"], "name": person["display_name"]})
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
    for cert in fixture_data["certifications"]:
        abstracted = gate.abstract_record(cert)
        evidence.append(
            EvidenceRecord(
                evidence_id=f"cert-{cert['cert_code']}",
                coded_identity=abstracted.coded_identity,
                skill_id=cert["skill_id"],
                evidence_type=EvidenceType.CERTIFIED,
                proficiency=ProficiencyLevel(cert["proficiency"]),
                occurred_at=datetime.fromisoformat(cert["earned_at"].replace("Z", "+00:00")),
                source_ref=cert["cert_code"],
            )
        )

    matrix = inference.merge_evidence(evidence)
    assert matrix
    # every identity with ticket history has a skill
    ticket_tokens = {gate.tokenize(t["employee_id"]) for t in fixture_data["tickets"]}
    scored_tokens = {m.coded_identity for m in matrix}
    assert ticket_tokens <= scored_tokens

    top_token = gate.tokenize("E1001")
    request = StaffingRequest(
        request_id="k8s-migration",
        requester_id="mgr-delivery",
        required_skills={"container_orchestration": ProficiencyLevel.PROFICIENT},
        shortlist_size=3,
    )
    ranked = fitness.rank_candidates(request, matrix)
    assert ranked.candidates
    assert ranked.candidates[0].coded_identity == top_token
    for cand in ranked.candidates:
        assert cand.evidence_ids

    resolved = resolution.resolve_shortlist(
        "k8s-migration",
        "mgr-delivery",
        ranked.candidates,
        "mgr-delivery",
    )
    assert resolved[0]["display_name"] == "Alex Rivera"


def test_learning_path_gap_example(gate, inference, fitness, fixture_data):
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
    fitness.demand_weights = fixture_data["demand_weights"]
    role = fixture_data["role_senior_cloud"]
    from shared.models import TargetRoleProfile

    profile = TargetRoleProfile(
        role_id=role["role_id"],
        role_name=role["role_name"],
        required_skills={k: ProficiencyLevel(v) for k, v in role["required_skills"].items()},
    )
    # EMP for E1003 has terraform but thin networking
    token = gate.tokenize("E1003")
    gaps = fitness.compute_gaps(token, profile, matrix)
    skill_ids = [g.skill_id for g in gaps.gaps]
    assert "azure_networking" in skill_ids or "container_orchestration" in skill_ids
