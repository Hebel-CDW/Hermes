#!/usr/bin/env python3
"""CI verifier for integrity-chained audit ledger."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ensure imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shared.db import HermesDB


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path(os.getenv("HERMES_DB_PATH", "data/hermes.db")))
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"SKIP: no db at {args.db}")
        return 0
    errors = HermesDB(args.db).verify_audit_chain()
    if errors:
        print("FAIL audit chain:")
        for e in errors:
            print(" -", e)
        return 1
    print("OK audit chain verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
