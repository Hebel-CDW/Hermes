"""Scan coded matrix records for identity leakage."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

from identity_abstraction.gate import scan_for_identity_leakage


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    path = Path(argv[0]) if argv else Path("data/fixtures/coded_matrix_sample.json")
    if not path.exists():
        print(json.dumps({"status": "pass", "findings": [], "note": "no matrix file"}))
        return 0
    records = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(records, dict):
        records = records.get("records", [])
    blocklist_path = Path("data/fixtures/identity_blocklist.json")
    blocklist = set()
    if blocklist_path.exists():
        blocklist = {x.lower() for x in json.loads(blocklist_path.read_text())}
    findings = scan_for_identity_leakage(records, blocklist=blocklist)
    status = "pass" if not findings else "fail"
    print(json.dumps({"status": status, "findings": findings}, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
