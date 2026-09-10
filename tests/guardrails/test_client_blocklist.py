"""D1: Client name blocklist must fail leakage audit."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from identity_abstraction.gate import scan_for_identity_leakage
from scripts.leakage_audit import main as leakage_main
from shared.models import CLIENT_NAME_BLOCKLIST, is_client_name_label


def test_client_blocklist_loaded():
    assert is_client_name_label("cottage health")
    assert "cottage health" in {c.lower() for c in CLIENT_NAME_BLOCKLIST}


def test_scan_flags_cottage_health_skill_label():
    findings = scan_for_identity_leakage(
        [{"coded_identity": "EMP-abcd1234", "skill_id": "cottage health", "confidence": 0.9}]
    )
    assert any(f["reason"] == "client_name_label" for f in findings)


def test_leakage_audit_exits_nonzero_on_client_skill(tmp_path, monkeypatch):
    fixture = tmp_path / "leaky.json"
    fixture.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "coded_identity": "EMP-abcd1234",
                        "skill_id": "cottage health",
                        "confidence": 0.5,
                        "freshness": 0.5,
                        "evidence_ids": [],
                        "scoring_config_version": "x",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(Path.cwd())
    rc = leakage_main([str(fixture)])
    assert rc == 1
