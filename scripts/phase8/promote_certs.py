#!/usr/bin/env python3
"""Promote completed cert_date_request.csv rows into certified evidence."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path = [str(ROOT / "src"), str(ROOT)] + sys.path
os.environ.setdefault("HERMES_TEST_MODE", "1")

from scripts.phase8 import ingest_certificates as ic  # noqa: E402


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    csv_path = Path(argv[0]) if argv else ROOT / "data" / "phase8" / "cert_date_request.csv"
    db_path = Path(argv[1]) if len(argv) > 1 else Path(os.getenv("HERMES_DB_PATH", "data/hermes.db"))
    # import function directly
    sys.path.insert(0, str(ROOT / "scripts" / "phase8"))
    from ingest_certificates import promote_dated_certs

    report = promote_dated_certs(csv_path, db_path)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
