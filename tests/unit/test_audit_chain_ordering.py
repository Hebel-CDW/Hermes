"""G-2 regression — audit chain ordering must not depend on timestamps or UUID order.

The Phase 1 audit reproduced a false chain break: two events sharing a
``created_at`` were replayed in ``event_id`` order (random UUIDs), which differed
from write order, so ``verify_audit_chain`` reported ``prev_hash mismatch`` on an
untampered ledger. The fix orders by a monotonic ``seq`` allocated under an
IMMEDIATE transaction.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

os.environ.setdefault("HERMES_TEST_MODE", "1")

import shared.db as sdb  # noqa: E402
from shared.db import HermesDB, hash_audit_row  # noqa: E402


def test_same_timestamp_events_with_unsorted_ids_verify(tmp_path, monkeypatch):
    """The exact reproduction from ARCHITECTURE_REVIEW_V2.md §G-2."""
    db = HermesDB(tmp_path / "chain.db")
    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(sdb, "utc_now", lambda: fixed)
    for event_id in ["zzzz-last", "aaaa-first", "mmmm-middle"]:
        db.append_audit(event_id, "t", "actor", {"n": event_id})
    assert db.verify_audit_chain() == []


def test_seq_is_strictly_monotonic(tmp_path):
    db = HermesDB(tmp_path / "seq.db")
    seqs = [int(db.append_audit(f"e{i}", "t", "a", {"i": i})["seq"]) for i in range(5)]
    assert seqs == [1, 2, 3, 4, 5]


def test_tampered_payload_is_still_detected(tmp_path):
    db = HermesDB(tmp_path / "tamper.db")
    for i in range(3):
        db.append_audit(f"e{i}", "t", "a", {"i": i})
    with db.session() as conn:
        conn.execute(
            "UPDATE audit_ledger SET payload_json = ? WHERE event_id = 'e1'", ('{"i": 99}',)
        )
    errors = db.verify_audit_chain()
    assert any("e1" in e and "row_hash" in e for e in errors)


def test_reordered_seq_is_detected(tmp_path):
    """Moving an event breaks prev_hash linkage even though seq itself is not hashed."""
    db = HermesDB(tmp_path / "reorder.db")
    for i in range(3):
        db.append_audit(f"e{i}", "t", "a", {"i": i})
    with db.session() as conn:
        conn.execute("DROP INDEX UX_audit_seq")
        conn.execute("UPDATE audit_ledger SET seq = 99 WHERE event_id = 'e0'")
    assert db.verify_audit_chain() != []


def test_duplicate_seq_is_rejected_by_constraint(tmp_path):
    db = HermesDB(tmp_path / "dup.db")
    db.append_audit("e0", "t", "a", {})
    db.append_audit("e1", "t", "a", {})
    conn = sqlite3.connect(str(tmp_path / "dup.db"))
    try:
        raised = False
        try:
            conn.execute("UPDATE audit_ledger SET seq = 1 WHERE event_id = 'e1'")
            conn.commit()
        except sqlite3.IntegrityError:
            raised = True
        assert raised, "UX_audit_seq must forbid two events at one chain position"
    finally:
        conn.close()


def test_legacy_ledger_without_seq_is_migrated_and_still_verifies(tmp_path):
    """Databases written before V2 have no seq column; migration must keep them valid."""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE audit_ledger (
             event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, actor TEXT NOT NULL,
             payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL DEFAULT '',
             row_hash TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)"""
    )
    prev = ""
    for i, event_id in enumerate(["b-second-sorts-first", "a-first-written"]):
        created = f"2026-01-01T00:00:0{i}+00:00"
        payload = {"i": i}
        row_hash = hash_audit_row(prev, event_id, "t", "a", payload, created)
        conn.execute(
            "INSERT INTO audit_ledger VALUES (?, 't', 'a', ?, ?, ?, ?)",
            (event_id, '{"i": %d}' % i, prev, row_hash, created),
        )
        prev = row_hash
    conn.commit()
    conn.close()

    db = HermesDB(path)  # runs migrate()
    with db.session() as c:
        rows = c.execute("SELECT event_id, seq FROM audit_ledger ORDER BY seq").fetchall()
    assert [r["event_id"] for r in rows] == ["b-second-sorts-first", "a-first-written"]
    assert db.verify_audit_chain() == []
    # Appends continue the migrated chain.
    db.append_audit("c-new", "t", "a", {"i": 2})
    assert db.verify_audit_chain() == []
