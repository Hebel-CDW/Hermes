"""V2 SVP hardening — audit anchor, database trust, secret policy, config-hash fidelity.

All data is synthetic.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from fitness_gap.engine import FitnessGapEngine  # noqa: E402
from shared.audit import AuditLedger  # noqa: E402
from shared.config import DEFAULT_SCORING, load_scoring_config  # noqa: E402
from shared.db import HermesDB, hash_audit_row  # noqa: E402
from shared.db_trust import (  # noqa: E402
    assess_database_trust,
    identity_secret_fingerprint,
    mark_database,
)
from shared.errors import ConfigurationError, UnknownSkillError, UntrustedDatabaseError  # noqa: E402
from shared.models import (  # noqa: E402
    EvidenceRecord,
    EvidenceType,
    ProficiencyLevel,
    StaffingRequest,
)
from shared.secrets import (  # noqa: E402
    PUBLISHED_SECRETS,
    require_identity_map_secret,
    require_jwt_secret,
    require_real_data_ingest_secret,
    validate_real_data_secret,
)
from skill_inference.engine import SkillInferenceEngine  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SECRET = "hermes-test-mode-secret-not-for-prod"
STRONG = "q7Rz-Kp2!vX9mW4tLb8Nc3Hs6Jd1Fg5Ye0Ua"


# ===========================================================================
# Audit integrity with external anchor
# ===========================================================================

@pytest.fixture()
def ledger(tmp_path):
    db = HermesDB(tmp_path / "ledger.db")
    for i in range(6):
        db.append_audit(f"ev-{i}", "evt", "actor", {"i": i})
    assert db.verify_audit_chain() == []
    return db


def _rewrite_chain(db, mutate_seq):
    with db.session() as conn:
        rows = conn.execute("SELECT * FROM audit_ledger ORDER BY seq").fetchall()
        prev = ""
        for r in rows:
            actor = "attacker" if r["seq"] == mutate_seq else r["actor"]
            h = hash_audit_row(prev, r["event_id"], r["event_type"], actor, json.loads(r["payload_json"]), r["created_at"])
            conn.execute("UPDATE audit_ledger SET actor=?, prev_hash=?, row_hash=? WHERE seq=?", (actor, prev, h, r["seq"]))
            prev = h


def test_anchor_detects_event_modification(ledger):
    with ledger.session() as c:
        c.execute("UPDATE audit_ledger SET actor='attacker' WHERE seq=3")
    assert ledger.verify_audit_chain()


def test_anchor_detects_middle_deletion(ledger):
    with ledger.session() as c:
        c.execute("DELETE FROM audit_ledger WHERE seq=3")
    assert ledger.verify_audit_chain()


def test_anchor_detects_latest_event_deletion(ledger):
    with ledger.session() as c:
        c.execute("DELETE FROM audit_ledger WHERE seq=(SELECT MAX(seq) FROM audit_ledger)")
    errors = ledger.verify_audit_chain()
    assert any("most recent events deleted" in e for e in errors)


def test_anchor_detects_deletion_of_all_events(ledger):
    with ledger.session() as c:
        c.execute("DELETE FROM audit_ledger")
    errors = ledger.verify_audit_chain()
    assert any("event count 0" in e for e in errors)


def test_anchor_detects_recomputed_forged_chain(ledger):
    _rewrite_chain(ledger, mutate_seq=2)
    errors = ledger.verify_audit_chain()
    assert any("chain rewritten" in e for e in errors)
    # The chain itself is internally consistent — only the anchor catches it.
    assert not any("prev_hash" in e or "row_hash" in e for e in errors)


def test_anchor_detects_arbitrary_deletion_even_when_chain_is_relinked(ledger):
    with ledger.session() as c:
        c.execute("DELETE FROM audit_ledger WHERE seq=2")
    _rewrite_chain(ledger, mutate_seq=-1)  # re-link remaining events consistently
    assert ledger.verify_audit_chain()


def test_missing_anchor_after_initialisation_is_reported(ledger):
    ledger.anchor_path().unlink()
    assert any("missing" in e for e in ledger.verify_audit_chain())


def test_forged_anchor_without_key_is_reported(ledger):
    path = ledger.anchor_path()
    doc = json.loads(path.read_text())
    with ledger.session() as c:
        c.execute("DELETE FROM audit_ledger WHERE seq=(SELECT MAX(seq) FROM audit_ledger)")
        head = c.execute("SELECT seq, row_hash FROM audit_ledger ORDER BY seq DESC LIMIT 1").fetchone()
    doc.update(seq=head["seq"], chain_head=head["row_hash"], event_count=doc["event_count"] - 1)
    path.write_text(json.dumps(doc))  # attacker updates body but cannot re-sign
    assert any("signature invalid" in e for e in ledger.verify_audit_chain())


def test_anchor_can_live_in_a_separate_directory(tmp_path, monkeypatch):
    anchors = tmp_path / "anchors"
    monkeypatch.setenv("HERMES_AUDIT_ANCHOR_DIR", str(anchors))
    db = HermesDB(tmp_path / "sep.db")
    db.append_audit("e", "t", "a", {})
    assert db.anchor_path().parent == anchors and db.anchor_path().is_file()
    assert db.verify_audit_chain() == []


def test_untampered_ledger_verifies_and_anchor_never_moves_backwards(ledger):
    anchor_before = json.loads(ledger.anchor_path().read_text())
    ledger._write_anchor({"seq": 1, "chain_head": "old", "event_count": 1})
    assert json.loads(ledger.anchor_path().read_text()) == anchor_before
    assert ledger.verify_audit_chain() == []


# ===========================================================================
# Database trust
# ===========================================================================

def _db_with_identity(path, secret, key="SYN-1"):
    db = HermesDB(path)
    token = "EMP-" + hmac.new(secret.encode(), key.lower().encode(), hashlib.sha256).hexdigest()[:8]
    db.upsert_identity(token, key, display_name="Synthetic Person")
    return db


def test_empty_database_is_trusted(tmp_path):
    assert assess_database_trust(HermesDB(tmp_path / "e.db"), STRONG).trusted


def test_database_without_metadata_is_refused(tmp_path):
    db = _db_with_identity(tmp_path / "legacy.db", FIXTURE_SECRET)
    result = assess_database_trust(db, FIXTURE_SECRET)
    assert not result.trusted and result.reason == "missing_trust_metadata"


def test_synthetic_database_is_trusted_in_test_mode(tmp_path):
    db = _db_with_identity(tmp_path / "syn.db", FIXTURE_SECRET)
    mark_database(db, "synthetic", FIXTURE_SECRET)
    assert assess_database_trust(db, FIXTURE_SECRET).trusted


def test_synthetic_database_with_real_data_tables_is_refused(tmp_path):
    db = _db_with_identity(tmp_path / "mixed.db", FIXTURE_SECRET)
    mark_database(db, "synthetic", FIXTURE_SECRET)
    token = db.resolve_coded_for_source("SYN-1")
    db.insert_baseline("b1", token, "k8s", 3.0, 3, "AWS", "five_point_undefined")
    assert assess_database_trust(db, FIXTURE_SECRET).reason == "synthetic_database_contains_real_data_tables"


def test_real_database_with_reversible_identities_is_refused(tmp_path, monkeypatch):
    """The exact condition of the pre-V2 Phase 8 database."""
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    db = _db_with_identity(tmp_path / "rev.db", FIXTURE_SECRET)
    # Even if someone labels it "real" under a strong running secret...
    db.set_meta("data_classification", "real")
    db.set_meta("identity_secret_fingerprint", identity_secret_fingerprint(STRONG))
    result = assess_database_trust(db, STRONG)
    assert not result.trusted
    assert result.reason == "reversible_identity_mapping"
    assert result.reversible_identities == 1


def test_real_database_built_with_strong_secret_is_trusted(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    db = _db_with_identity(tmp_path / "real.db", STRONG)
    mark_database(db, "real", STRONG)
    assert assess_database_trust(db, STRONG).trusted


def test_real_database_is_refused_in_test_mode(tmp_path, monkeypatch):
    db = _db_with_identity(tmp_path / "realtm.db", STRONG)
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    mark_database(db, "real", STRONG)
    monkeypatch.setenv("HERMES_TEST_MODE", "1")
    assert assess_database_trust(db, STRONG).reason == "real_database_in_test_mode"


def test_secret_mismatch_is_refused(tmp_path):
    db = _db_with_identity(tmp_path / "mm.db", FIXTURE_SECRET)
    mark_database(db, "synthetic", FIXTURE_SECRET)
    assert assess_database_trust(db, STRONG).reason == "identity_secret_mismatch"


def test_classification_cannot_be_relabelled(tmp_path):
    db = _db_with_identity(tmp_path / "rl.db", FIXTURE_SECRET)
    mark_database(db, "synthetic", FIXTURE_SECRET)
    with pytest.raises(UntrustedDatabaseError):
        mark_database(db, "real", FIXTURE_SECRET)


def test_quarantined_phase8_database_is_refused_if_present(tmp_path, monkeypatch):
    """Operates on a COPY; the quarantined original is never opened for writing."""
    candidates = [ROOT / "data" / "quarantine" / "hermes_phase8.UNTRUSTED.db", ROOT / "data" / "hermes_phase8.db"]
    source = next((p for p in candidates if p.is_file()), None)
    if source is None:
        pytest.skip("no local Phase 8 database present (expected in a clean clone)")
    copy = tmp_path / "p8copy.db"
    copy.write_bytes(source.read_bytes())
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    result = assess_database_trust(HermesDB(copy), STRONG)
    assert not result.trusted


# ===========================================================================
# Secret policy
# ===========================================================================

def test_published_fixture_secret_is_rejected_without_test_mode_flag(monkeypatch):
    """The bypass found in validation: fixture secret supplied, flag not set."""
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("IDENTITY_MAP_SECRET", FIXTURE_SECRET)
    with pytest.raises(RuntimeError):
        require_real_data_ingest_secret()
    with pytest.raises(RuntimeError):
        require_identity_map_secret()


def test_published_jwt_secret_is_rejected_outside_test_mode(monkeypatch):
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")
    with pytest.raises(RuntimeError):
        require_jwt_secret()


@pytest.mark.parametrize(
    "secret",
    ["", "short-but-unique-16", "a" * 40, "abababababababababababababababab", *sorted(PUBLISHED_SECRETS)],
)
def test_weak_or_published_secrets_rejected_for_real_data(secret):
    with pytest.raises(RuntimeError):
        validate_real_data_secret(secret)


def test_strong_secret_accepted_for_real_data(monkeypatch):
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("IDENTITY_MAP_SECRET", STRONG)
    assert require_real_data_ingest_secret() == STRONG


def _run_promote(args, env_overrides):
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERMES_") and k != "IDENTITY_MAP_SECRET"}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "phase8" / "promote_certs.py"), *args],
        env=env, capture_output=True, text=True, cwd=str(ROOT), timeout=120,
    )


@pytest.fixture()
def synthetic_csv(tmp_path):
    path = tmp_path / "req.csv"
    path.write_text("staging_id,person_name,coded_identity,cert_label,earned_at\nsyn-1,Synthetic,EMP-00000001,CKA,\n")
    return path


def test_promote_certs_requires_explicit_mode(synthetic_csv, tmp_path):
    r = _run_promote([str(synthetic_csv), str(tmp_path / "p.db")], {})
    assert r.returncode == 2 and "--mode" in r.stderr


def test_promote_certs_synthetic_mode_does_not_force_test_mode(synthetic_csv, tmp_path):
    r = _run_promote(["--mode", "synthetic", str(synthetic_csv), str(tmp_path / "p.db")], {})
    assert r.returncode == 2 and "HERMES_TEST_MODE=1" in r.stderr
    ok = _run_promote(["--mode", "synthetic", str(synthetic_csv), str(tmp_path / "p2.db")], {"HERMES_TEST_MODE": "1"})
    assert ok.returncode == 0, ok.stderr


def test_promote_certs_real_mode_refuses_test_mode_and_fixture_secret(synthetic_csv, tmp_path):
    r1 = _run_promote(["--mode", "real", str(synthetic_csv), str(tmp_path / "p.db")], {"HERMES_TEST_MODE": "1"})
    assert r1.returncode != 0 and "Refusing" in r1.stderr
    r2 = _run_promote(["--mode", "real", str(synthetic_csv), str(tmp_path / "p.db")], {"IDENTITY_MAP_SECRET": FIXTURE_SECRET})
    assert r2.returncode != 0 and "Refusing" in r2.stderr


def test_no_real_data_script_forces_test_mode():
    for rel in ("phase8/ingest_baseline.py", "phase8/ingest_certificates.py", "phase8/promote_certs.py",
                "phase8/baseline_agreement.py", "impact_audit.py"):
        text = (ROOT / "scripts" / rel).read_text(encoding="utf-8")
        assert 'setdefault("HERMES_TEST_MODE"' not in text, rel


def test_ci_uses_fixture_secrets_only_with_test_mode():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    if FIXTURE_SECRET in ci:
        assert 'HERMES_TEST_MODE: "1"' in ci


# ===========================================================================
# Config-hash fidelity: version changes  <=>  a score can change
# ===========================================================================

AS_OF = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _ev(i, typ, lvl, skill="container_orchestration", days=200, coded="EMP-0000000a"):
    return EvidenceRecord(
        evidence_id=f"{coded}-{i}", coded_identity=coded, skill_id=skill, evidence_type=typ,
        proficiency=ProficiencyLevel(lvl), occurred_at=datetime.fromordinal(AS_OF.toordinal() - days).replace(tzinfo=timezone.utc),
        source_ref=f"SYN-{i}", metadata={"manager_confirmed": True},
    )


def _pipeline_scores(cfg):
    """A deliberately sensitive synthetic scenario that exercises every parameter."""
    evidence = [
        # Conflicting levels, so each type weight can flip the merged level:
        #   default   cert 2x0.30=0.60@L5 beats demo 0.55@L2 and decl 0.15@L4  -> L5
        #   W_DEMO=.9 demo 0.90@L2 wins                                        -> L2
        #   W_CERT=.05 cert 0.10@L5 loses to demo 0.55@L2                      -> L2
        #   W_DECL=.9 decl 0.90@L4 wins                                        -> L4
        _ev(1, EvidenceType.DEMONSTRATED, 2), _ev(2, EvidenceType.CERTIFIED, 5),
        _ev(3, EvidenceType.CERTIFIED, 5, days=150), _ev(7, EvidenceType.DECLARED, 4),
        # medium-class skill without override -> medium half-life matters
        _ev(4, EvidenceType.DEMONSTRATED, 4, skill="azure_compute", coded="EMP-0000000b"),
        _ev(5, EvidenceType.DEMONSTRATED, 4, skill="azure_compute", coded="EMP-0000000b", days=10),
        _ev(6, EvidenceType.DEMONSTRATED, 3, skill="infrastructure_as_code", coded="EMP-0000000c"),
        # slow-class skill without override -> slow half-life matters
        _ev(8, EvidenceType.DEMONSTRATED, 4, skill="itil", coded="EMP-0000000c", days=400),
    ]
    engine = SkillInferenceEngine(config=cfg)
    matrix = engine.merge_evidence(evidence, as_of=AS_OF)
    fitness = FitnessGapEngine(config=cfg, audit=AuditLedger(),
                               adjacency={"container_orchestration": ["azure_compute"]})
    out = {}
    for req, cov in (({"container_orchestration": 5}, 0.0), ({"container_orchestration": 3, "azure_networking": 3}, None), ({"itil": 3}, 0.0)):
        r = fitness.rank_candidates(
            StaffingRequest(request_id="f", requester_id="m",
                            required_skills={k: ProficiencyLevel(v) for k, v in req.items()}, shortlist_size=10),
            matrix, allocation={"EMP-0000000a": 0.5, "EMP-0000000b": 0.5, "EMP-0000000c": 0.5},
            min_coverage_ratio=cov,
        )
        out[str(req)] = [(c.coded_identity, c.fitness_score) for c in r.candidates]
    return out


BASE_SCORES = None


@pytest.mark.parametrize(
    "var,value,expect_change",
    [
        ("HERMES_W_DEMO", "0.9", True),
        ("HERMES_W_CERT", "0.05", True),
        ("HERMES_W_DECL", "0.9", True),
        ("HERMES_VOLUME_K", "0.9", True),
        ("HERMES_ALLOC_W", "0.5", True),
        ("HERMES_ADJACENCY_DISCOUNT", "0.9", True),
        ("HERMES_MIN_COVERAGE", "0.4", True),
        ("HERMES_MAX_SHORTLIST", "1", True),
        ("HERMES_HALF_LIFE_MEDIUM", "30", True),
        ("HERMES_HALF_LIFE_SLOW", "30", True),
        # No ontology skill uses this class without an explicit override:
        ("HERMES_HALF_LIFE_FAST", "30", False),
    ],
)
def test_version_changes_if_and_only_if_scores_change(var, value, expect_change):
    base_cfg = load_scoring_config(env={})
    tuned_cfg = load_scoring_config(env={var: value})
    version_changed = tuned_cfg.version != base_cfg.version
    scores_changed = _pipeline_scores(tuned_cfg) != _pipeline_scores(base_cfg)
    assert version_changed == expect_change, f"{var}: version_changed={version_changed}"
    assert scores_changed == expect_change, f"{var}: scores_changed={scores_changed}"


def test_removed_global_half_life_env_var_is_refused():
    with pytest.raises(ConfigurationError):
        load_scoring_config(env={"HERMES_HALF_LIFE": "30"})


@pytest.mark.parametrize(
    "env",
    [{"HERMES_W_DEMO": "2"}, {"HERMES_ALLOC_W": "-0.1"}, {"HERMES_MAX_SHORTLIST": "11"},
     {"HERMES_HALF_LIFE_MEDIUM": "0"}, {"HERMES_VOLUME_K": "abc"}],
)
def test_invalid_config_values_fail_loudly(env):
    with pytest.raises(ConfigurationError):
        load_scoring_config(env=env)


def test_default_scores_unchanged_by_config_restructure():
    """The effective half-lives equal the pre-hardening values, so scores are preserved."""
    lives = dict(DEFAULT_SCORING.effective_half_lives)
    assert lives["azure_compute"] == 365.0
    assert lives["azure_networking"] == 120.0
    assert lives["container_orchestration"] == 120.0
    assert lives["incident_management"] == 365.0
    assert lives["infrastructure_as_code"] == 365.0
    assert len(lives) >= 40
    assert DEFAULT_SCORING.adjacency_discount == 0.5


def test_unknown_skill_evidence_is_rejected_not_scored():
    with pytest.raises(UnknownSkillError):
        SkillInferenceEngine().merge_evidence([_ev(1, EvidenceType.CERTIFIED, 3, skill="made_up_skill")])
