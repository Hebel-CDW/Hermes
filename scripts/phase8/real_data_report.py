#!/usr/bin/env python3
"""Aggregate-only REAL data validation report, read from the governed real-data database.

    set -a; . secrets/hermes_real_data.env; set +a
    python -m scripts.phase8.real_data_report            # human summary
    python -m scripts.phase8.real_data_report --json     # machine-readable
    python -m scripts.phase8.real_data_report --verify   # exit 1 on any consistency failure

Prints counts only — no names, tokens, raw rows or client labels. Refuses to open a database
that fails the trust policy (wrong secret, test mode, reversible identities).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path = [str(ROOT / "src"), str(ROOT)] + [p for p in sys.path if p not in (str(ROOT / "src"), str(ROOT))]

from shared.db import HermesDB  # noqa: E402
from shared.db_trust import ensure_database_trusted  # noqa: E402
from shared.read_models import data_quality  # noqa: E402
from shared.secrets import require_real_data_ingest_secret  # noqa: E402
from shared.taxonomy import load_taxonomy  # noqa: E402

DEFAULT_DB = ROOT / "data" / "real" / "hermes_real.db"


def load(db_path: Path) -> Dict[str, Any]:
    secret = require_real_data_ingest_secret()
    if not db_path.is_file():
        raise RuntimeError(f"real-data database not found: {db_path.name}")
    db = HermesDB(db_path)
    ensure_database_trusted(db, secret)
    if db.get_meta("data_classification") != "real":
        raise RuntimeError("database is not classified as real data")
    return data_quality(db, load_taxonomy())


def consistency_failures(dq: Dict[str, Any]) -> List[str]:
    """Stored ingestion summary vs live database rows. Every check is a count equality."""
    failures: List[str] = []
    ing = dq["ingestion"]
    db = dq["database"]
    if ing is None:
        return ["no ingestion run recorded"]

    def eq(name: str, a: Any, b: Any) -> None:
        if a != b:
            failures.append(f"{name}: {a} != {b}")

    eq("people detected == identity_map", ing["people_detected"], db["people_imported"])
    eq("pending labels == pending alias rows", ing["labels"]["pending"], db["pending_aliases"])
    eq("certificate cells == cert_staging rows", ing["certificates"]["cells"], dq["certificates"]["staged"])
    eq(
        "exact cert-code classifications == staged cert_code rows",
        ing["certificates"]["classification"]["exact_cert_code"],
        dq["certificates"]["exact_mapped"],
    )
    eq(
        "accepted == skill cells + account cells",
        ing["cells_accepted"],
        (ing["accepted_skill_cells"] or 0) + (ing["accepted_account_cells"] or 0),
    )
    eq("processed == accepted + rejected", ing["cells_processed"], ing["cells_accepted"] + ing["cells_rejected"])
    eq("mapped labels == approved alias trace", ing["labels"]["mapped"], len(ing["labels"]["mapped_trace"]))
    eq("certificates with earned_at (never invented)", dq["certificates"]["with_earned_at"], dq["certificates"]["promoted"])
    if db["baseline_rows_mapped"] and not ing["labels"]["mapped"]:
        failures.append("baseline rows carry skill ids but no label is mapped")
    if db["baseline_rows"] > ing["accepted_skill_cells"]:
        failures.append("more baseline rows than accepted skill cells")
    if db["baseline_rows_mapped"] != 0 and ing["labels"]["mapped"] == 0:
        failures.append("mapped baseline rows without a governed label mapping")
    if dq["pipeline"]["scored"] > 0 and db["evidence_records"] == 0:
        failures.append("scored people without evidence")
    return failures


def _fmt(n: Any) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n)


def render(dq: Dict[str, Any]) -> str:
    ing = dq["ingestion"] or {}
    labels = ing.get("labels", {})
    rej = labels.get("rejected", {})
    certs = dq["certificates"]
    lines = [
        "HERMES REAL DATA VALIDATION",
        "",
        f"Classification:        {dq['data_classification']}",
        f"Sheets:                {_fmt(ing.get('sheets'))}",
        f"People imported:       {_fmt(dq['database']['people_imported'])}",
        f"Cells processed:       {_fmt(ing.get('cells_processed'))}",
        f"Accepted:              {_fmt(ing.get('cells_accepted'))}",
        f"Rejected:              {_fmt(ing.get('cells_rejected'))}",
    ]
    for reason, n in sorted((ing.get("rejections_by_reason") or {}).items(), key=lambda kv: -kv[1]):
        lines.append(f"  {reason:<30} {_fmt(n)}")
    lines += [
        f"Canonical skills:      {_fmt(dq['canonical_skills'])}",
        f"Workbook skill labels: {_fmt(labels.get('skill_labels'))}",
        f"Mapped:                {_fmt(labels.get('mapped'))}",
        f"Pending:               {_fmt(labels.get('pending'))}",
        f"Rejected labels:       client/account {_fmt(rej.get('client_account'))} · soft skill {_fmt(rej.get('soft_skill'))} · culture fit {_fmt(rej.get('culture_fit'))}",
        f"Certificates:          {_fmt(certs['staged'])} staged · {_fmt(certs['exact_mapped'])} exact code · {_fmt(certs['pending'])} pending · {_fmt(certs['with_earned_at'])} dated",
        f"Scored population:     {_fmt(dq['pipeline']['scored'])}",
    ]
    return "\n".join(lines)


def print_report(db_path: Path = DEFAULT_DB) -> Dict[str, Any]:
    dq = load(db_path)
    print(render(dq))
    return dq


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    try:
        dq = load(args.db)
    except RuntimeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(dq, indent=2, sort_keys=True) if args.json else render(dq))
    if args.verify:
        failures = consistency_failures(dq)
        if failures:
            print("\nCONSISTENCY FAILED:\n  " + "\n  ".join(failures))
            return 1
        print("\nCONSISTENCY OK - ingestion summary matches database rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
