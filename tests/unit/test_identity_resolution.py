import pytest

from shared.models import RankedCandidate
from identity_resolution.gateway import ResolutionDenied


def test_resolve_shortlist_only(gate, resolution):
    gate.abstract_record({"employee_id": "E1001", "name": "Alex Rivera"})
    token = gate.tokenize("E1001")
    other = gate.tokenize("E1002")
    shortlist = [
        RankedCandidate(
            coded_identity=token,
            fitness_score=0.9,
            rank=1,
            per_skill_reasoning={"container_orchestration": "ok"},
            evidence_ids=["e1"],
        )
    ]
    resolved = resolution.resolve_shortlist("req-1", "mgr-1", shortlist, "mgr-1")
    assert resolved[0]["display_name"] == "Alex Rivera"
    with pytest.raises(ResolutionDenied):
        resolution.resolve_one("req-1", "mgr-1", other, [token], "mgr-1")


def test_wrong_requester_denied(gate, resolution):
    gate.abstract_record({"employee_id": "E1001", "name": "Alex Rivera"})
    token = gate.tokenize("E1001")
    shortlist = [
        RankedCandidate(
            coded_identity=token,
            fitness_score=0.9,
            rank=1,
            per_skill_reasoning={},
            evidence_ids=["e1"],
        )
    ]
    with pytest.raises(ResolutionDenied):
        resolution.resolve_shortlist("req-1", "mgr-2", shortlist, "mgr-1")
