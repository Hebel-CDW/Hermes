#!/usr/bin/env python3
"""Promote completed cert_date_request.csv rows into certified evidence.

The mode is explicit and required:
  --mode real       real certificate data; requires a strong, non-published
                    IDENTITY_MAP_SECRET and refuses HERMES_TEST_MODE
  --mode synthetic  synthetic fixtures only; requires HERMES_TEST_MODE=1 to be set
                    by the caller (this script never sets it)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path = [str(ROOT / "src"), str(ROOT), str(ROOT / "scripts" / "phase8")] + sys.path

from ingest_certificates import promote_dated_certs  # noqa: E402
from shared.secrets import is_test_mode, require_real_data_ingest_secret  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("real", "synthetic"), required=True)
    parser.add_argument("csv_path", nargs="?", type=Path, default=ROOT / "data" / "phase8" / "cert_date_request.csv")
    parser.add_argument("db_path", nargs="?", type=Path, default=Path(os.getenv("HERMES_DB_PATH", "data/hermes.db")))
    args = parser.parse_args(argv)
    if args.mode == "real":
        secret = require_real_data_ingest_secret()
    else:
        if not is_test_mode():
            print("--mode synthetic requires HERMES_TEST_MODE=1 to be set explicitly", file=sys.stderr)
            return 2
        secret = None
    report = promote_dated_certs(args.csv_path, args.db_path, mapping_secret=secret)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
