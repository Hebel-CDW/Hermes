import pytest

from identity_abstraction.gate import IdentityAbstractionGate, scan_for_identity_leakage


def test_tokenize_is_deterministic(gate):
    a = gate.tokenize("E1001")
    b = gate.tokenize("E1001")
    assert a == b
    assert a.startswith("EMP-")


def test_abstract_strips_pii(gate):
    result = gate.abstract_record(
        {
            "employee_id": "E1001",
            "name": "Alex Rivera",
            "email": "alex@example.com",
            "short_description": "k8s issue",
        }
    )
    assert "name" not in result.record
    assert "email" not in result.record
    assert "employee_id" not in result.record
    assert result.record["coded_identity"].startswith("EMP-")
    assert result.record["short_description"] == "k8s issue"
    gate.assert_no_pii(result.record)


def test_rejects_protected_attributes(gate):
    with pytest.raises(ValueError, match="protected"):
        gate.abstract_record({"employee_id": "E1", "gender": "X"})


def test_leakage_scan_finds_email():
    findings = scan_for_identity_leakage(
        [{"coded_identity": "EMP-00000001", "note": "mail me at a@b.com"}]
    )
    assert any(f["reason"] == "email_pattern" for f in findings)


def test_leakage_scan_clean_matrix():
    findings = scan_for_identity_leakage(
        [{"coded_identity": "EMP-00000001", "skill_id": "container_orchestration", "confidence": 0.9}]
    )
    assert findings == []
