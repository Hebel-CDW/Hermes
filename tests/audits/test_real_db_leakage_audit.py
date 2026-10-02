"""Phase 6 — leakage audit extended to the real database, not just synthetic fixtures.

``tests/audits/test_leakage_audit.py`` only ever scans a seeded *synthetic* matrix.
This test runs the same class of check against the actual real-classified database
when one is present on disk, so a leak can be caught before any real-backed demo.

The real database is gitignored (``data/real/``) and never committed, so this test
skips cleanly on any machine that doesn't have it rather than failing CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from identity_abstraction.gate import CODED_ID_PATTERN, scan_real_database_for_leakage
from shared.db import HermesDB

REAL_DB_PATH = Path("data/real/hermes_real.db")


@pytest.mark.skipif(not REAL_DB_PATH.exists(), reason="no real database present on this machine")
def test_real_database_has_zero_identity_leakage():
    db = HermesDB(REAL_DB_PATH)
    findings = scan_real_database_for_leakage(db)
    assert findings == [], f"real-data leakage gate found {len(findings)} finding(s)"


@pytest.mark.skipif(not REAL_DB_PATH.exists(), reason="no real database present on this machine")
def test_real_database_coded_identities_are_properly_shaped():
    """Every identity in scoring-adjacent tables must already be a coded token, not a name."""
    db = HermesDB(REAL_DB_PATH)
    with db.session() as conn:
        for table in ("skills_matrix", "evidence_staging"):
            rows = conn.execute(f"SELECT DISTINCT coded_identity FROM {table}").fetchall()
            for row in rows:
                assert CODED_ID_PATTERN.match(row["coded_identity"]), f"{table} holds a non-coded identity"
