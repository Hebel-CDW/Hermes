#!/usr/bin/env python3
"""Ingest Skill_Matrix_2025 into baseline_assessments + account_context (never scoring)."""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
# Prefer src/phase8 over scripts/phase8 on sys.path
sys.path = [str(ROOT / "src"), str(ROOT)] + [p for p in sys.path if Path(p).resolve() != (ROOT / "scripts" / "phase8").resolve()]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

os.environ.setdefault("HERMES_TEST_MODE", "1")

from phase8.aliases import SkillAliasResolver, ontology_lookup_map  # noqa: E402
from phase8.parsers import ParsedAssessment, _baseline_id, count_raw_person_rows, parse_sheet  # noqa: E402
from phase8.workbook import cell_str, open_workbook, sheet_rows  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.exclusions import ExclusionLog  # noqa: E402
from shared.service import HermesService  # noqa: E402
from shared.taxonomy import load_taxonomy  # noqa: E402

EXPECTED_PERSON_ROWS = {
    "iSeries L2": 12,
    "iSeries L3": 5,
    "ZI Ops": 19,
    "Citrix": 5,
    "CI Ops": 22,
    "Virtualization": 17,
    "Windows": 10,
    "CTS": 20,
    "Collab": 33,
    "Network Security": 35,
    "Backup": 13,
    "Tools": 3,
    "AWS": 19,
    "GCP": 5,
    "Azure": 16,
    "Datacenter": 4,
    "AIX": 4,
    "Endpoint compliance": 6,
    "Storage": 11,
    "MSS": 14,
    "Certificates": 203,
    "ECC-OPS": 33,
}


def propose_variants(values: List[str], out_path: Path, kind: str) -> None:
    """Emit variant CSV with needs_human_review; do not auto-merge."""
    from difflib import SequenceMatcher

    normed = {}
    for v in values:
        key = " ".join(v.lower().split())
        normed.setdefault(key, []).append(v)
    # Cluster near-duplicates
    keys = sorted(normed)
    parent = {k: k for k in keys}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            if SequenceMatcher(None, a, b).ratio() >= 0.87:
                parent[find(b)] = find(a)
    clusters = defaultdict(list)
    for k in keys:
        clusters[find(k)].extend(normed[k])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["canonical_proposal", "variants", "count", "needs_human_review", "mapped_by"],
        )
        w.writeheader()
        for members in clusters.values():
            uniq = sorted(set(members), key=lambda s: (-values.count(s), len(s), s))
            canon = uniq[0]
            needs = "yes" if len(uniq) > 1 else "no"
            w.writerow(
                {
                    "canonical_proposal": canon,
                    "variants": "|".join(uniq),
                    "count": sum(values.count(m) for m in uniq),
                    "needs_human_review": needs,
                    "mapped_by": "pending",  # never human unless confirmed
                }
            )


def ingest(path: Path, db_path: Path, sheet_order: Optional[List[str]] = None) -> dict:
    if db_path.exists():
        # keep identity if rebuilding baseline only — for fresh, caller deletes
        pass
    db = HermesDB(db_path)
    svc = HermesService(db=db)
    tax = load_taxonomy()
    resolver = SkillAliasResolver(db, ontology_lookup_map(tax))
    log = ExclusionLog()
    wb = open_workbook(path)
    order = sheet_order or list(wb.sheetnames)
    dropped_all = []
    managers: List[str] = []
    teams: List[str] = []
    pending = 0
    skill_rows = 0
    account_rows = 0
    per_sheet = {}

    for sheet_name in order:
        if sheet_name not in wb.sheetnames:
            continue
        if sheet_name == "Certificates":
            # Workstream C
            continue
        rows = sheet_rows(wb[sheet_name])
        raw_count = count_raw_person_rows(sheet_name, rows)
        assessments, dropped = parse_sheet(sheet_name, rows, log)
        dropped_all.extend([d.__dict__ for d in dropped])
        people = {a.person_name for a in assessments}
        per_sheet[sheet_name] = {
            "raw_person_rows": raw_count,
            "expected": EXPECTED_PERSON_ROWS.get(sheet_name),
            "unique_people_parsed": len(people),
            "assessments": len(assessments),
            "dropped": len(dropped),
        }
        for a in assessments:
            abstracted = svc.abstract({"employee_id": a.person_name.lower(), "name": a.person_name})
            coded = abstracted["coded_identity"]
            if a.kind == "account":
                db.upsert_account_context(coded, a.raw_label, a.raw_value, a.source_sheet)
                account_rows += 1
                continue
            resolved = resolver.resolve(a.raw_label)
            if resolved.mapped_by == "pending":
                pending += 1
            db.insert_baseline(
                baseline_id=_baseline_id(a.source_sheet, a.person_name, a.raw_label),
                coded_identity=coded,
                raw_label=a.raw_label,
                raw_value=a.raw_value,
                normalised_level=a.normalised_level,
                source_sheet=a.source_sheet,
                source_scale=a.source_scale,
                skill_id=resolved.skill_id,
                assessed_at=None,
            )
            skill_rows += 1

        # Collect manager/team from Certificates later; from skill sheets if present
        # Certificates handled in C; still gather teams from sheet names
        teams.append(sheet_name)

    # Certificates sheet for manager/team variants (not scored here)
    if "Certificates" in wb.sheetnames:
        rows = sheet_rows(wb["Certificates"])
        # header row index 1
        for row in rows[2:]:
            name = cell_str(row[0] if row else None)
            team = cell_str(row[1] if len(row) > 1 else None)
            mgr = cell_str(row[2] if len(row) > 2 else None)
            if name:
                svc.abstract({"employee_id": name.lower(), "name": name})
            if team:
                teams.append(team)
            if mgr:
                managers.append(mgr)

    excl_path = log.write(ROOT / "data" / "reports" / "phase8_exclusions.json")
    propose_variants(managers, ROOT / "data" / "phase8" / "manager_variants.csv", "manager")
    propose_variants(teams, ROOT / "data" / "phase8" / "team_variants.csv", "team")
    dropped_path = ROOT / "data" / "reports" / "phase8_dropped_rows.json"
    dropped_path.parent.mkdir(parents=True, exist_ok=True)
    dropped_path.write_text(json.dumps({"dropped": dropped_all}, indent=2), encoding="utf-8")

    report = {
        "baseline_rows": skill_rows,
        "account_rows": account_rows,
        "pending_aliases": pending,
        "pending_alias_table": db.count_pending_aliases(),
        "per_sheet": per_sheet,
        "exclusions_path": str(excl_path),
        "dropped_path": str(dropped_path),
        "db_path": str(db_path),
    }
    (ROOT / "data" / "reports" / "phase8_ingest_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return report


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    src = Path(argv[0]) if argv else ROOT / "data" / "source" / "Skill_Matrix_2025.xlsx"
    db_path = Path(argv[1]) if len(argv) > 1 else Path(os.getenv("HERMES_DB_PATH", ROOT / "data" / "hermes.db"))
    if not src.exists():
        print(f"missing source {src}", file=sys.stderr)
        return 2
    ingest(src, db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
