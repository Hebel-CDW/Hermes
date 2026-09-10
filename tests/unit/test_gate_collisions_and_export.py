import pytest

from identity_abstraction.gate import IdentityAbstractionGate


def test_missing_employee_key(gate):
    with pytest.raises(ValueError, match="missing employee key"):
        gate.abstract_record({"name": "Nobody"})


def test_export_map(gate):
    gate.tokenize("E42")
    exported = gate.export_map()
    assert "e42" in exported


def test_empty_secret_rejected():
    with pytest.raises(ValueError):
        IdentityAbstractionGate("")
