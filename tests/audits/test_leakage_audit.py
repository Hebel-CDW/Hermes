import json
from pathlib import Path

from identity_abstraction.gate import IdentityAbstractionGate, scan_for_identity_leakage
from scripts.seed_local_matrix import main as seed_main


def test_seeded_matrix_has_zero_leakage(tmp_path, monkeypatch):
    # run seeder from repo root
    seed_main()
    records = json.loads(Path("data/fixtures/coded_matrix_sample.json").read_text())["records"]
    blocklist = {x.lower() for x in json.loads(Path("data/fixtures/identity_blocklist.json").read_text())}
    findings = scan_for_identity_leakage(records, blocklist=blocklist)
    assert findings == []


def test_gate_output_passes_assert_no_pii():
    gate = IdentityAbstractionGate("audit-secret")
    result = gate.abstract_record(
        {"employee_id": "E9", "name": "Secret Person", "category": "network"}
    )
    gate.assert_no_pii(result.record)
