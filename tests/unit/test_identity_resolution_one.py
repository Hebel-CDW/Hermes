import pytest

from shared.models import RankedCandidate
from identity_resolution.gateway import ResolutionDenied


def test_resolve_one_success(gate, resolution):
    gate.abstract_record({"employee_id": "E1001", "name": "Alex Rivera"})
    token = gate.tokenize("E1001")
    out = resolution.resolve_one("req-1", "mgr-1", token, [token], "mgr-1")
    assert out["display_name"] == "Alex Rivera"


def test_resolve_one_unknown_token(gate, resolution):
    with pytest.raises(ResolutionDenied):
        resolution.resolve_one("req-1", "mgr-1", "EMP-00009999", ["EMP-00009999"], "mgr-1")
