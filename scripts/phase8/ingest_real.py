#!/usr/bin/env python3
"""Governed REAL-workbook ingestion into the dedicated real-data database.

    set -a; . secrets/hermes_real_data.env; set +a      # strong, unpublished secrets
    python -m scripts.phase8.ingest_real                  # never with HERMES_TEST_MODE

Pipeline (nothing skips a stage):

    XLSX -> Phase 8 parser -> normalisation -> quality validation (coded rejections)
         -> identity abstraction (HMAC coded identities; names only in the vault)
         -> taxonomy / alias resolution (exact governed matches only; everything else pending)
         -> baseline + account-context + certificate staging (never scoring)

Baseline ratings are NEVER turned into skill evidence. Scoring happens only from governed
evidence (e.g. certificates with human-supplied dates via promote_certs), so this command
cannot make real people look scored.

Output is aggregate only: no names, no raw rows, no client labels, no secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
sys.path = [str(ROOT / "src"), str(ROOT), str(ROOT / "scripts" / "phase8")] + [
    p for p in sys.path if Path(p).resolve() != (ROOT / "scripts" / "phase8").resolve()
]

import importlib.util  # noqa: E402


def _load_sibling(name: str):
    """Load a scripts/phase8 module by file path (those scripts rewrite sys.path on import)."""
    spec = importlib.util.spec_from_file_location(f"_phase8_{name}", ROOT / "scripts" / "phase8" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


ingest_baseline = _load_sibling("ingest_baseline").ingest
ingest_certs = _load_sibling("ingest_certificates").ingest_certs
from shared.db import HermesDB  # noqa: E402
from shared.db_trust import ensure_database_trusted  # noqa: E402
from shared.secrets import require_real_data_ingest_secret  # noqa: E402
from shared.service import HermesService  # noqa: E402

DEFAULT_SOURCE = ROOT / "data" / "source" / "Skill_Matrix_2025.xlsx"
DEFAULT_DB = ROOT / "data" / "real" / "hermes_real.db"
DEFAULT_REPORTS = ROOT / "data" / "reports" / "real"

#: Databases that must never receive real people.
FORBIDDEN_DBS = {
    (ROOT / "data" / name).resolve()
    for name in ("hermes.db", "hermes_demo.db", "hermes_validation.db", "hermes_phase8.db")
}


class RealIngestRefused(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def guard_db_path(db_path: Path) -> None:
    resolved = db_path.resolve()
    if resolved in FORBIDDEN_DBS or "fixtures" in resolved.parts or "quarantine" in resolved.parts:
        raise RealIngestRefused(
            f"refusing to write real workforce data into {db_path.name}: use a dedicated real-data database"
        )


def run(
    source: Path = DEFAULT_SOURCE,
    db_path: Path = DEFAULT_DB,
    reports_dir: Path = DEFAULT_REPORTS,
    governance_worksheets: bool = False,
    cert_request_with_names: bool = False,
) -> Dict[str, Any]:
    from shared.excel_sunset import refuse_future_workbook

    refuse_future_workbook(source)
    secret = require_real_data_ingest_secret()  # refuses test mode and published/weak secrets
    guard_db_path(db_path)
    if not source.is_file():
        raise RealIngestRefused(f"source workbook not found: {source.name}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    svc = HermesService(db=HermesDB(db_path), mapping_secret=secret)

    t0 = time.perf_counter()
    base = ingest_baseline(
        source, db_path, reports_dir=reports_dir, governance_worksheets=governance_worksheets, svc=svc, quiet=True
    )
    t1 = time.perf_counter()
    certs = ingest_certs(
        source,
        db_path,
        request_csv=reports_dir / "cert_date_request.csv",
        include_names=cert_request_with_names,
        svc=svc,
        quiet=True,
    )
    t2 = time.perf_counter()

    totals = base["data_quality_totals"]
    with svc.db.session() as conn:
        # dict(row).values() works for both sqlite3.Row (supports row[0] too)
        # and psycopg2 RealDictRow (key-only) — found via a real Postgres
        # test-parity run, same fix as read_models.data_quality's one().
        people = int(next(iter(dict(conn.execute("SELECT COUNT(*) FROM identity_map").fetchone()).values())))
    summary = {
        "sheets": base["data_quality_totals"]["sheets"] + 1,  # + Certificates (certificate workstream)
        "people_detected": people,
        "cells": {
            "processed": totals["rows_processed"],
            "accepted": totals["assessments_accepted"],
            "rejected": totals["rows_rejected"],
            "rejections_by_reason": totals["rejections_by_reason"],
            "accepted_skill_cells": base["baseline_rows"],
            "accepted_account_cells": base["account_rows"],
        },
        "labels": base["label_governance"],
        "excluded_field_occurrences": base["exclusion_column_occurrences"],
        "certificates": {
            "cells": certs["certs_staged"],
            "people": certs["people_with_certificates"],
            "distinct_labels": certs["distinct_cert_labels"],
            "classification": certs["classification"],
        },
        "anomalies": totals["anomaly_count"],
        "timing_seconds": {"baseline": round(t1 - t0, 2), "certificates": round(t2 - t1, 2)},
    }
    digest = _sha256(source)
    with svc.db.session() as conn:
        previous_runs = int(
            next(iter(dict(conn.execute("SELECT COUNT(*) FROM phase8_ingest_runs").fetchone()).values()))
        )
    run_id = f"phase8-{digest[:12]}-{previous_runs + 1:04d}"
    svc.db.record_ingest_run(run_id, source.name, digest, summary)
    svc.audit.append(
        "phase8_workbook_ingest",
        actor="phase8_ingest_real",
        payload={
            "run_id": run_id,
            "source_sha256": digest,
            "people_detected": people,
            "cells_accepted": summary["cells"]["accepted"],
            "cells_rejected": summary["cells"]["rejected"],
            "labels_mapped": summary["labels"]["mapped"],
            "labels_pending": summary["labels"]["pending"],
            "certificate_cells": summary["certificates"]["cells"],
        },
    )
    ensure_database_trusted(svc.db, secret)  # the result must be servable under the real-data policy
    return {"run_id": run_id, "db_path": str(db_path), "summary": summary}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument(
        "--governance-worksheets",
        action="store_true",
        help="also write name-bearing manager/team variant worksheets (gitignored) for human review",
    )
    parser.add_argument(
        "--cert-request-with-names",
        action="store_true",
        help="include person names in the certificate date-request worksheet (gitignored)",
    )
    args = parser.parse_args(argv)
    try:
        result = run(args.source, args.db, args.reports_dir, args.governance_worksheets, args.cert_request_with_names)
    except (RuntimeError, RealIngestRefused) as exc:
        print(f"REAL DATA INGEST REFUSED: {exc}", file=sys.stderr)
        return 2
    _load_sibling("real_data_report").print_report(args.db)  # aggregate-only presentation
    print(f"\nrun_id: {result['run_id']}  timing: {result['summary']['timing_seconds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
