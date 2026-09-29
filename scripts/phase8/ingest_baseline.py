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

from phase8.aliases import SkillAliasResolver, ontology_lookup_map  # noqa: E402
from phase8.parsers import ParsedAssessment, _baseline_id, count_raw_person_rows, parse_sheet  # noqa: E402
from phase8.quality import build_report  # noqa: E402
from phase8.workbook import cell_str, normalize_label, open_workbook, sheet_rows  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.excel_sunset import freeze_database, refuse_future_workbook  # noqa: E402
from shared.exclusions import ExclusionLog  # noqa: E402
from shared.secrets import require_real_data_ingest_secret  # noqa: E402
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


def _name_free_dropped(dropped) -> List[dict]:
    """Rejections persisted to disk carry sheet + machine code only.

    The parser's free-text ``detail`` embeds the person's name (``"<name>/<label>"``); it is
    useful in memory for debugging but must never be written to a report or log.
    """
    return [{"sheet": d.sheet, "reason": d.reason} for d in dropped]


def ingest(
    path: Path,
    db_path: Path,
    sheet_order: Optional[List[str]] = None,
    reports_dir: Optional[Path] = None,
    governance_worksheets: bool = False,
    svc: Optional[HermesService] = None,
    quiet: bool = False,
) -> dict:
    """Parse -> validate -> abstract identities -> resolve aliases -> stage baseline (never scoring).

    Performance: each distinct person is abstracted once per run (one audited identity
    event per person, not per cell) and rows are written in one transaction per sheet.
    Validation, rejection codes and alias governance are unchanged.

    Every artefact written here is aggregate or label-level; person names never leave
    memory except through identity abstraction into the vault.
    """
    refuse_future_workbook(path)
    # C-2 guardrail: real people are tokenised here. Refuse the published
    # fixture secret outright — see shared.secrets.require_real_data_ingest_secret.
    secret = require_real_data_ingest_secret()
    if svc is None:
        db = HermesDB(db_path)
        svc = HermesService(db=db, mapping_secret=secret)
    db = svc.db
    freeze_database(db)
    svc.mark_database("real")  # refuses to relabel a synthetic DB or switch secrets
    out_dir = reports_dir or (ROOT / "data" / "reports")
    tax = load_taxonomy()
    resolver = SkillAliasResolver(db, ontology_lookup_map(tax))
    log = ExclusionLog()
    wb = open_workbook(path)
    order = sheet_order or list(wb.sheetnames)
    dropped_all: List[dict] = []
    managers: List[str] = []
    teams: List[str] = []
    coded_for: Dict[str, str] = {}
    pending = 0
    skill_rows = 0
    account_rows = 0
    per_sheet = {}
    quality_inputs: Dict[str, dict] = {}
    skill_label_keys: Dict[str, Optional[str]] = {}
    mapped_trace: Dict[str, dict] = {}
    account_label_keys: set = set()

    def coded(person: str) -> str:
        key = person.strip().lower()
        if key not in coded_for:
            # Known identities are reused (already abstracted and audited); only new people
            # pass through abstraction, once per run — never once per cell.
            coded_for[key] = db.resolve_coded_for_source(key) or svc.abstract(
                {"employee_id": key, "name": person}
            )["coded_identity"]
        return coded_for[key]

    for sheet_name in order:
        if sheet_name not in wb.sheetnames:
            continue
        if sheet_name == "Certificates":
            # Workstream C
            continue
        rows = sheet_rows(wb[sheet_name])
        raw_count = count_raw_person_rows(sheet_name, rows)
        log_mark = len(log.entries)
        assessments, dropped = parse_sheet(sheet_name, rows, log)
        dropped_all.extend(_name_free_dropped(dropped))
        people = {a.person_name for a in assessments}
        sheet_log = log.entries[log_mark:]
        excluded_labels = {
            e["label"] for e in sheet_log if e["reason"] != "client_account_context"
        }
        account_labels = {a.raw_label for a in assessments if a.kind == "account"}
        skill_labels = {a.raw_label for a in assessments if a.kind == "skill"}
        pending_labels = {
            lab for lab in skill_labels if resolver.resolve(lab).mapped_by == "pending"
        }
        quality_inputs[sheet_name] = {
            "raw_person_rows": raw_count,
            "people_discovered": raw_count,
            "accepted_people": people,
            "assessments": assessments,
            "dropped": dropped,
            "labels_discovered": len(skill_labels | account_labels | excluded_labels),
            "labels_excluded": len(excluded_labels),
            "labels_account": len(account_labels),
            "labels_pending": len(pending_labels),
        }
        per_sheet[sheet_name] = {
            "raw_person_rows": raw_count,
            "expected": EXPECTED_PERSON_ROWS.get(sheet_name),
            "unique_people_parsed": len(people),
            "assessments": len(assessments),
            "dropped": len(dropped),
        }
        baseline_batch = []
        account_batch = []
        for a in assessments:
            token = coded(a.person_name)
            if a.kind == "account":
                account_label_keys.add(normalize_label(a.raw_label))
                account_batch.append((token, a.raw_label, a.raw_value, a.source_sheet))
                account_rows += 1
                continue
            resolved = resolver.resolve(a.raw_label)
            label_key = normalize_label(a.raw_label)
            skill_label_keys[label_key] = resolved.skill_id
            if resolved.mapped_by == "pending":
                pending += 1
            else:
                mapped_trace[label_key] = {
                    "label": label_key,
                    "skill_id": resolved.skill_id,
                    "mapped_by": resolved.mapped_by,
                    "match_confidence": resolved.match_confidence,
                }
            baseline_batch.append(
                (
                    _baseline_id(a.source_sheet, a.person_name, a.raw_label),
                    token,
                    resolved.skill_id,
                    a.raw_label,
                    a.raw_value,
                    a.normalised_level,
                    a.source_sheet,
                    a.source_scale,
                    None,  # assessed_at: the workbook carries no assessment dates
                )
            )
            skill_rows += 1
        # One transaction per sheet: a failure rolls the whole sheet back.
        db.insert_baselines(baseline_batch)
        db.upsert_account_contexts(account_batch)
        teams.append(sheet_name)

    # Certificates sheet: abstract the people listed there (certs themselves: ingest_certificates)
    if "Certificates" in wb.sheetnames:
        rows = sheet_rows(wb["Certificates"])
        # header row index 1
        for row in rows[2:]:
            name = cell_str(row[0] if row else None)
            team = cell_str(row[1] if len(row) > 1 else None)
            mgr = cell_str(row[2] if len(row) > 2 else None)
            if name:
                coded(name)
            if team:
                teams.append(team)
            if mgr:
                managers.append(mgr)

    out_dir.mkdir(parents=True, exist_ok=True)
    excl_path = log.write(out_dir / "phase8_exclusions.json")
    if governance_worksheets:
        # Name-bearing human review worksheets: opt-in only, gitignored location only.
        propose_variants(managers, out_dir / "governance" / "manager_variants.csv", "manager")
        propose_variants(teams, out_dir / "governance" / "team_variants.csv", "team")
    dropped_path = out_dir / "phase8_dropped_rows.json"
    dropped_path.write_text(json.dumps({"dropped": dropped_all}, indent=2), encoding="utf-8")

    quality = build_report(str(path.name), quality_inputs, EXPECTED_PERSON_ROWS)
    quality_path = quality.write(out_dir / "phase8_data_quality.json")

    exclusion_reasons = Counter(e["reason"] for e in log.entries)
    excluded_label_keys: Dict[str, set] = defaultdict(set)
    for e in log.entries:
        excluded_label_keys[e["reason"]].add(normalize_label(e["label"]))
    report = {
        "data_quality_path": str(quality_path),
        "data_quality_totals": quality.totals(),
        "baseline_rows": skill_rows,
        "account_rows": account_rows,
        "pending_aliases": pending,
        "pending_alias_table": db.count_pending_aliases(),
        "people_detected": len(coded_for),
        "label_governance": {
            "skill_labels": len(skill_label_keys),
            "mapped": len(mapped_trace),
            "pending": sum(1 for v in skill_label_keys.values() if v is None),
            "mapped_trace": sorted(mapped_trace.values(), key=lambda m: m["label"]),
            "rejected": {
                "client_account": len(account_label_keys),
                "soft_skill": len(excluded_label_keys.get("soft_skill_excluded", set())),
                "culture_fit": len(excluded_label_keys.get("culture_fit_forbidden_column", set())),
            },
        },
        "exclusion_column_occurrences": dict(sorted(exclusion_reasons.items())),
        "per_sheet": per_sheet,
        "exclusions_path": str(excl_path),
        "dropped_path": str(dropped_path),
        "db_path": str(db_path),
    }
    (out_dir / "phase8_ingest_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not quiet:
        print(json.dumps({k: v for k, v in report.items() if k != "per_sheet"}, indent=2))
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
