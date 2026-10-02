#!/usr/bin/env python3
"""Phase 6 — real-data leakage gate.

Scans the actual real-classified database (default ``data/real/hermes_real.db``)
for real names, emails, or client/account labels that reached a scoring-adjacent
table (``skills_matrix``, ``evidence_staging``, ``audit_ledger`` payloads).

Exit code 0 and ``{"status": "pass", "findings": []}`` means clean. Any finding is
exit code 1 — run this before enabling any real-backed demo mode, and wire it into
CI/ops as a hard gate, not an advisory check.

Never prints a real name or value; findings are redacted before output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from identity_abstraction.gate import scan_real_database_for_leakage  # noqa: E402
from shared.db import HermesDB  # noqa: E402


def _redact(finding: dict) -> dict:
    """Never echo the leaked value itself back to a log or terminal."""
    out = dict(finding)
    if "value" in out:
        out["value"] = "__REDACTED__"
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    db_path = Path(argv[0]) if argv else Path("data/real/hermes_real.db")
    if not db_path.exists():
        print(json.dumps({"status": "pass", "findings": [], "note": "no real database present"}))
        return 0
    db = HermesDB(db_path)
    findings = [_redact(f) for f in scan_real_database_for_leakage(db)]
    status = "pass" if not findings else "fail"
    print(
        json.dumps(
            {"status": status, "database": str(db_path), "finding_count": len(findings), "findings": findings},
            indent=2,
        )
    )
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
