#!/usr/bin/env python3
"""A1: Extract all skill labels from Skill_Matrix_2025 and cluster near-duplicates."""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from phase8.workbook import (  # noqa: E402
    META_COLUMNS,
    cell_str,
    classify_label_for_extract,
    detect_header_row,
    normalize_label,
    open_workbook,
    sheet_rows,
    slug_skill_id,
)

OUT_CSV = ROOT / "data" / "phase8" / "candidate_skills.csv"
OUT_JSON = ROOT / "data" / "phase8" / "label_extraction_report.json"
SIM_THRESHOLD = 0.87


def collect_labels(path: Path) -> Dict[str, Dict]:
    """Map raw_label -> {frequency, sheets: set, kind}."""
    wb = open_workbook(path)
    labels: Dict[str, Dict] = {}

    def add(label: str, sheet: str) -> None:
        lab = cell_str(label)
        if not lab or normalize_label(lab) in META_COLUMNS:
            return
        # Skip cert column headers
        if lab.lower().startswith("cert "):
            return
        kind = classify_label_for_extract(lab)
        entry = labels.setdefault(
            lab, {"frequency": 0, "sheets": set(), "kind": kind, "normalized": normalize_label(lab)}
        )
        entry["frequency"] += 1
        entry["sheets"].add(sheet)
        # Prefer more severe classification if conflict
        if kind in {"culture_fit", "excluded", "account"}:
            entry["kind"] = kind

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = sheet_rows(ws)
        if not rows:
            continue
        if sheet_name == "Certificates":
            # Cert labels are values, not skill columns — skip for skill taxonomy
            continue
        if sheet_name == "Collab":
            # Applications are in column B (index 1) starting after header-ish rows
            for row in rows:
                app = cell_str(row[1] if len(row) > 1 else None)
                if app and normalize_label(app) not in {"application", "group"}:
                    add(app, sheet_name)
            continue
        header_idx = detect_header_row(rows)
        header = [cell_str(c) for c in rows[header_idx]]
        for col in header:
            if col:
                add(col, sheet_name)
    return labels


def cluster_labels(labels: Dict[str, Dict]) -> List[Dict]:
    """Cluster skill-kind labels; excluded/account/culture_fit are singleton excluded clusters."""
    skill_items = [(k, v) for k, v in labels.items() if v["kind"] == "skill"]
    excluded_items = [(k, v) for k, v in labels.items() if v["kind"] != "skill"]

    # Union-find clustering by similarity on normalized form
    parents = {k: k for k, _ in skill_items}

    def find(x: str) -> str:
        while parents[x] != x:
            parents[x] = parents[parents[x]]
            x = parents[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parents[rb] = ra

    norms = {k: v["normalized"] for k, v in skill_items}
    keys = [k for k, _ in skill_items]
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            na, nb = norms[a], norms[b]
            if not na or not nb:
                continue
            if na == nb or SequenceMatcher(None, na, nb).ratio() >= SIM_THRESHOLD:
                union(a, b)

    clusters: Dict[str, List[str]] = defaultdict(list)
    for k in keys:
        clusters[find(k)].append(k)

    rows: List[Dict] = []
    for members in clusters.values():
        # Canonical = highest frequency then shortest label
        members_sorted = sorted(
            members, key=lambda m: (-labels[m]["frequency"], len(m), m.lower())
        )
        canon = members_sorted[0]
        freq = sum(labels[m]["frequency"] for m in members)
        sheets: Set[str] = set()
        for m in members:
            sheets |= labels[m]["sheets"]
        # Flag for human review if multi-member or low-confidence near-dupe
        needs_review = len(members) > 1
        rows.append(
            {
                "canonical_id": slug_skill_id(canon),
                "canonical_name": canon,
                "member_labels": "|".join(sorted(members, key=str.lower)),
                "frequency": freq,
                "source_sheets": "|".join(sorted(sheets)),
                "status": "candidate",
                "needs_human_review": "yes" if needs_review else "no",
                "exclusion_reason": "",
            }
        )

    for lab, meta in excluded_items:
        reason = {
            "culture_fit": "culture_fit_forbidden",
            "excluded": "soft_skill_excluded",
            "account": "client_account_context",
        }.get(meta["kind"], meta["kind"])
        rows.append(
            {
                "canonical_id": "",
                "canonical_name": lab,
                "member_labels": lab,
                "frequency": meta["frequency"],
                "source_sheets": "|".join(sorted(meta["sheets"])),
                "status": "excluded",
                "needs_human_review": "no",
                "exclusion_reason": reason,
            }
        )

    rows.sort(key=lambda r: (0 if r["status"] == "candidate" else 1, -r["frequency"], r["canonical_name"].lower()))
    return rows


def main(argv=None) -> int:
    path = Path(argv[0]) if argv else ROOT / "data" / "source" / "Skill_Matrix_2025.xlsx"
    if not path.exists():
        print(f"MISSING source workbook: {path}", file=sys.stderr)
        return 2
    labels = collect_labels(path)
    clusters = cluster_labels(labels)

    # Acceptance: every label appears exactly once as a member of exactly one cluster
    membership: Dict[str, int] = defaultdict(int)
    for row in clusters:
        for m in row["member_labels"].split("|"):
            if m:
                membership[m] += 1
    missing = set(labels) - set(membership)
    multi = {k: v for k, v in membership.items() if v != 1}
    if missing or multi:
        print(json.dumps({"error": "membership_invariant", "missing": list(missing), "multi": multi}, indent=2))
        return 1

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "canonical_id",
                "canonical_name",
                "member_labels",
                "frequency",
                "source_sheets",
                "status",
                "needs_human_review",
                "exclusion_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(clusters)

    report = {
        "source": str(path),
        "distinct_labels": len(labels),
        "clusters": len(clusters),
        "candidate_clusters": sum(1 for c in clusters if c["status"] == "candidate"),
        "excluded_clusters": sum(1 for c in clusters if c["status"] == "excluded"),
        "needs_human_review": sum(1 for c in clusters if c["needs_human_review"] == "yes"),
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"wrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
