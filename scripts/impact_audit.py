#!/usr/bin/env python3
"""HR-held impact / bias audit — NEVER joined into the ops scoring path.

Computes Gini-like concentration of shortlist appearances and never-shortlisted cohort
from staffing_requests history only. Tenure bands require an HR export (not in Hermes DB).
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# No secret needed: this script only reads the database; it never tokenises people.

from shared.db import HermesDB


def gini(counts):
    vals = sorted(float(v) for v in counts)
    if not vals:
        return 0.0
    n = len(vals)
    total = sum(vals)
    if total == 0:
        return 0.0
    cum = 0.0
    for i, v in enumerate(vals, start=1):
        cum += i * v
    return (2 * cum) / (n * total) - (n + 1) / n


def main() -> int:
    db_path = Path(os.getenv("HERMES_DB_PATH", "data/hermes.db"))
    if not db_path.exists():
        print("No DB — write methodology stub only")
        return 0
    db = HermesDB(db_path)
    with db.session() as conn:
        rows = conn.execute("SELECT shortlist_json FROM staffing_requests").fetchall()
        population = [
            r["coded_identity"]
            for r in conn.execute("SELECT coded_identity FROM identity_map").fetchall()
        ]
    appearances = Counter()
    for row in rows:
        for tok in json.loads(row["shortlist_json"] or "[]"):
            appearances[tok] += 1
    never = [p for p in population if appearances[p] == 0]
    report = {
        "population": len(population),
        "shortlist_events": sum(appearances.values()),
        "gini_shortlist_appearances": round(gini(appearances.values() or [0]), 4),
        "never_shortlisted_count": len(never),
        "never_shortlisted_sample": never[:20],
        "note": "Tenure-band accrual requires HR export — not stored in Hermes ops DB.",
    }
    Path("docs/validation").mkdir(parents=True, exist_ok=True)
    Path("docs/validation/impact-audit-latest.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
