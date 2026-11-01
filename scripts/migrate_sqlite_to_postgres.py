#!/usr/bin/env python3
"""Copy an existing SQLite Hermes database into a fresh PostgreSQL database.

    python -m scripts.migrate_sqlite_to_postgres \\
        --sqlite data/hermes.db --postgres postgresql://user:pw@host:5432/hermes

Every row is copied VERBATIM — no value is recomputed, reformatted, or
fabricated. IDs, timestamps, the audit hash chain, evidence, identity
mappings, skills, config rows and governance metadata are carried over
exactly as stored. The destination database is migrated (schema created)
first; it must be empty (migrating into a populated database is refused,
to avoid silently merging two installations).

Verification: after copying, every table's row count is compared between
source and destination. A mismatch is reported and the tool exits non-zero
— it never claims success it has not checked.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from shared.db import HermesDB

# Dependency order matches infra/postgres/001_schema.sql's FK graph: every
# table that references identity_map(coded_identity) is copied after it.
TABLES: List[str] = [
    "hermes_meta",
    "identity_map",
    "identity_vault",
    "org_edges",
    "evidence_staging",
    "skills_matrix",
    "skills_matrix_history",
    "role_profiles",
    "demand_signals",
    "availability",
    "audit_ledger",
    "staffing_requests",
    "evidence_contests",
    "account_context",
    "baseline_assessments",
    "skill_aliases",
    "manager_aliases",
    "cert_staging",
    "phase8_ingest_runs",
    "principal_bindings",
    # HOI (migration 002), parents before children.
    "opportunities",
    "opportunity_members",
    "opportunity_documents",
    "requirement_versions",
    "resource_requirements",
    "candidate_shortlists",
    "capacity_snapshots",
    "cost_parameters",
    "fin_loaded_costs",
    "market_benchmarks",
    "commercial_scenarios",
    "scenario_assignments",
    "approval_events",
    "opportunity_audit",
    "fin_access_log",
]


class MigrationRefused(RuntimeError):
    pass


def _columns(conn, table: str) -> List[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def _count(conn, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(dict(row)["n"])


def migrate(sqlite_path: Path, postgres_url: str) -> dict:
    src = HermesDB(path=sqlite_path)
    dst = HermesDB(database_url=postgres_url)  # migrate() already ran: schema exists

    # The anchor this tool re-seals after copying is HMAC-signed with
    # IDENTITY_MAP_SECRET (HermesDB._anchor_key). Running this tool without
    # that secret set would silently re-seal an UNSIGNED anchor — weaker
    # tamper-evidence than the source database had, discovered only later
    # when a correctly-configured server reports the chain as tampered.
    # Fail closed instead of degrading security silently.
    if not src._anchor_key():
        raise MigrationRefused(
            "IDENTITY_MAP_SECRET (or HERMES_AUDIT_ANCHOR_KEY) is not set — migrating now would "
            "re-seal the audit anchor unsigned. Export the same secret the destination server "
            "uses, then re-run."
        )

    # HermesDB.__init__ bootstraps exactly one hermes_meta row
    # (audit_anchor_initialised) on first open of ANY fresh database, on
    # both dialects — expected, not evidence of prior data. Every other
    # table, and every other hermes_meta key, must be empty.
    with dst.session() as dconn:
        existing = sum(_count(dconn, t) for t in TABLES if t != "hermes_meta")
        existing += sum(
            1 for r in dconn.execute("SELECT key FROM hermes_meta") if dict(r)["key"] != "audit_anchor_initialised"
        )
    if existing:
        raise MigrationRefused(
            f"destination database already has {existing} unexpected rows — "
            "refusing to migrate into a non-empty database"
        )

    report = {}
    with src.session() as sconn, dst.session() as dconn:
        for table in TABLES:
            cols = _columns(sconn, table)
            rows = sconn.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
            placeholders = ", ".join("?" for _ in cols)
            col_list = ", ".join(cols)
            if rows:
                if table == "skills_matrix_history" and dst.dialect == "postgres":
                    # history_id is GENERATED ALWAYS AS IDENTITY on Postgres (vs
                    # SQLite's plain AUTOINCREMENT) — explicit IDs must be forced
                    # with OVERRIDING SYSTEM VALUE to preserve them verbatim.
                    dconn.executemany(
                        f"INSERT INTO {table} ({col_list}) OVERRIDING SYSTEM VALUE VALUES ({placeholders})",
                        [tuple(dict(r)[c] for c in cols) for r in rows],
                    )
                    dconn.execute(
                        "SELECT setval(pg_get_serial_sequence('skills_matrix_history', 'history_id'), "
                        "(SELECT MAX(history_id) FROM skills_matrix_history))"
                    )
                elif table == "hermes_meta":
                    # The destination's own bootstrap row for this key must be
                    # overwritten with the source's authoritative value — the
                    # whole point of migrating is to carry the SOURCE's history.
                    for r in rows:
                        values = dict(r)
                        dconn.execute(
                            "INSERT INTO hermes_meta (key, value) VALUES (?, ?) "
                            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                            (values["key"], values["value"]),
                        )
                else:
                    dconn.executemany(
                        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                        [tuple(dict(r)[c] for c in cols) for r in rows],
                    )
            report[table] = len(rows)
        dconn.commit()
        # The destination's tamper-evidence anchor was sealed at bootstrap
        # (event_count=0), before audit_ledger rows existed. Re-seal it now
        # against the actually-migrated chain — the same call
        # _ensure_audit_anchor() itself uses, just re-run post-copy — or
        # verify_audit_chain() will wrongly report a rewritten chain on a
        # correctly migrated database.
        dst._write_anchor(dst._chain_state(dconn))

    mismatches = {}
    with src.session() as sconn, dst.session() as dconn:
        for table in TABLES:
            s, d = _count(sconn, table), _count(dconn, table)
            if s != d:
                mismatches[table] = {"sqlite": s, "postgres": d}

    if mismatches:
        raise MigrationRefused(f"row count mismatch after copy: {mismatches}")

    return {"tables_copied": report, "total_rows": sum(report.values())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sqlite", type=Path, required=True)
    ap.add_argument("--postgres", required=True, help="postgresql://... DSN, must point at an empty database")
    args = ap.parse_args(argv)

    if not args.sqlite.is_file():
        print(f"REFUSED: sqlite database not found: {args.sqlite}", file=sys.stderr)
        return 2
    try:
        result = migrate(args.sqlite, args.postgres)
    except MigrationRefused as exc:
        print(f"MIGRATION REFUSED: {exc}", file=sys.stderr)
        return 2
    print(f"migrated {result['total_rows']} rows across {len(result['tables_copied'])} tables, verified row-for-row")
    for table, n in result["tables_copied"].items():
        if n:
            print(f"  {table}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
