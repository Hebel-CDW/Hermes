import os
from pathlib import Path

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from identity_abstraction.gate import IdentityAbstractionGate, scan_for_identity_leakage
from shared.db import HermesDB
from shared.secrets import require_identity_map_secret
from shared.service import HermesService
from scripts.ingest_fixtures import ingest


def test_nested_pii_blocked():
    gate = IdentityAbstractionGate("hermes-test-mode-secret-not-for-prod")
    with pytest.raises(AssertionError):
        gate.assert_no_pii({"coded_identity": "EMP-abcd1234", "meta": {"contact": "a@b.com"}})


def test_nested_email_leakage_scan():
    findings = scan_for_identity_leakage(
        [{"coded_identity": "EMP-abcd1234", "nested": {"x": "leak@example.com"}}]
    )
    assert any(f["reason"] == "email_pattern" for f in findings)


def test_token_stable_across_shuffle_orders(tmp_path):
    import json
    from pathlib import Path as P
    fixture = json.loads(P("data/fixtures/pilot_population.json").read_text())
    people = list(fixture["pilot_population"])

    maps = []
    for order in (people, list(reversed(people)), sorted(people, key=lambda p: p["employee_id"])):
        db_path = tmp_path / f"ord-{len(maps)}.db"
        if db_path.exists():
            db_path.unlink()
        db = HermesDB(db_path)
        svc = HermesService(db=db)
        mapping = {}
        for person in order:
            out = svc.abstract({"employee_id": person["employee_id"], "name": person["display_name"]})
            mapping[person["employee_id"]] = out["coded_identity"]
        maps.append(mapping)
    assert maps[0] == maps[1] == maps[2]
    for token in maps[0].values():
        assert token.startswith("EMP-") and len(token) == 12


def test_no_ticket_excerpt_in_db(tmp_path):
    db_path = tmp_path / "ex.db"
    ingest(Path("data/fixtures/pilot_population.json"), db_path)
    db = HermesDB(db_path)
    for row in db.load_all_evidence():
        assert "ticket_excerpt" not in row.metadata
        blob = str(row.metadata)
        assert "ticket_excerpt" not in blob


def test_fail_closed_secret_outside_test_mode(monkeypatch):
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("IDENTITY_MAP_SECRET", "local-dev-secret")
    with pytest.raises(RuntimeError):
        require_identity_map_secret()


def test_short_secret_rejected_outside_test_mode(monkeypatch):
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("IDENTITY_MAP_SECRET", "tooshort")
    with pytest.raises(RuntimeError, match="at least 16"):
        require_identity_map_secret()


def test_jwt_secret_fails_closed_outside_test_mode(monkeypatch):
    from shared.secrets import require_jwt_secret

    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("HERMES_JWT_SECRET", "")
    with pytest.raises(RuntimeError):
        require_jwt_secret()


# --- C-2: real-data ingestion must never use the published fixture secret ---

def test_real_data_ingest_refuses_test_mode(monkeypatch):
    """Coded identities are HMAC(secret, name). A published secret makes them reversible."""
    from shared.secrets import require_real_data_ingest_secret

    monkeypatch.setenv("HERMES_TEST_MODE", "1")
    monkeypatch.setenv("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
    with pytest.raises(RuntimeError, match="Refusing to tokenise real data"):
        require_real_data_ingest_secret()


def test_real_data_ingest_refuses_denylisted_secret(monkeypatch):
    from shared.secrets import require_real_data_ingest_secret

    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("IDENTITY_MAP_SECRET", "local-dev-secret")
    with pytest.raises(RuntimeError):
        require_real_data_ingest_secret()


def test_real_data_ingest_accepts_a_strong_secret(monkeypatch):
    from shared.secrets import require_real_data_ingest_secret

    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("IDENTITY_MAP_SECRET", "a-genuinely-strong-operator-secret-2026")
    assert require_real_data_ingest_secret() == "a-genuinely-strong-operator-secret-2026"


def test_phase8_entrypoints_do_not_force_test_mode():
    """Regression: every Phase 8 real-data script used to set HERMES_TEST_MODE=1."""
    root = Path(__file__).resolve().parents[2]
    for name in ("ingest_baseline.py", "ingest_certificates.py"):
        text = (root / "scripts" / "phase8" / name).read_text(encoding="utf-8")
        assert 'setdefault("HERMES_TEST_MODE"' not in text, (
            f"{name} forces test mode, which would tokenise real people with the "
            "published fixture secret (C-2)"
        )
        assert "require_real_data_ingest_secret" in text
