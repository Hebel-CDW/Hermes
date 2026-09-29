#!/usr/bin/env python3
"""Compare baseline_assessments vs skills_matrix — never feeds scoring."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path = [str(ROOT / "src"), str(ROOT)] + sys.path
# No secret needed: this script only reads the database; it never tokenises people.

from shared.db import HermesDB  # noqa: E402


def run(db_path: Path) -> dict:
    if not db_path.exists():
        report = {
            "overlaps": 0,
            "note": "No database at path — nothing to compare.",
            "exact_agreement_rate": None,
            "within_one_rate": None,
        }
        _write(report)
        print(json.dumps(report, indent=2))
        return report

    db = HermesDB(db_path)
    with db.session() as conn:
        baseline = conn.execute(
            """
            SELECT coded_identity, skill_id, normalised_level, source_sheet, raw_label
            FROM baseline_assessments
            WHERE skill_id IS NOT NULL AND normalised_level IS NOT NULL
            """
        ).fetchall()
        matrix = conn.execute(
            "SELECT coded_identity, skill_id, proficiency FROM skills_matrix"
        ).fetchall()

    matrix_map = {(r["coded_identity"], r["skill_id"]): int(r["proficiency"]) for r in matrix}
    overlaps = []
    for b in baseline:
        key = (b["coded_identity"], b["skill_id"])
        if key not in matrix_map:
            continue
        overlaps.append(
            {
                "coded_identity": b["coded_identity"],
                "skill_id": b["skill_id"],
                "baseline_level": int(b["normalised_level"]),
                "engine_level": matrix_map[key],
                "source_sheet": b["source_sheet"],
                "delta": matrix_map[key] - int(b["normalised_level"]),
            }
        )

    n = len(overlaps)
    if n == 0:
        report = {
            "overlaps": 0,
            "exact_agreement_rate": None,
            "within_one_rate": None,
            "note": (
                "No overlapping (identity, skill) pairs between baseline and skills_matrix yet. "
                "This is expected until demonstrated/certified evidence exists for the same people."
            ),
            "engine_higher": [],
            "baseline_higher": [],
            "by_sheet": {},
        }
        _write(report)
        _write_md(report)
        print(json.dumps(report, indent=2))
        return report

    exact = sum(1 for o in overlaps if o["delta"] == 0)
    within = sum(1 for o in overlaps if abs(o["delta"]) <= 1)
    engine_higher = [o for o in overlaps if o["delta"] > 0]
    baseline_higher = [o for o in overlaps if o["delta"] < 0]
    by_sheet = defaultdict(list)
    for o in overlaps:
        by_sheet[o["source_sheet"]].append(o["delta"])

    report = {
        "overlaps": n,
        "exact_agreement_rate": round(exact / n, 4),
        "within_one_rate": round(within / n, 4),
        "mean_delta_engine_minus_baseline": round(sum(o["delta"] for o in overlaps) / n, 4),
        "engine_higher_count": len(engine_higher),
        "baseline_higher_count": len(baseline_higher),
        "engine_higher_sample": engine_higher[:20],
        "baseline_higher_sample": baseline_higher[:20],
        "by_sheet_mean_delta": {
            s: round(sum(v) / len(v), 4) for s, v in sorted(by_sheet.items())
        },
        "note": (
            "engine_higher may indicate expertise invisible to manager baseline; "
            "baseline_higher may indicate keyword/scoring gaps."
        ),
    }
    _write(report)
    _write_md(report)
    print(json.dumps(report, indent=2))
    return report


def _write(report: dict) -> None:
    out = ROOT / "data" / "reports" / "baseline_agreement.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _write_md(report: dict) -> None:
    out = ROOT / "data" / "reports" / "baseline_agreement.md"
    lines = ["# Baseline vs engine agreement\n"]
    if report["overlaps"] == 0:
        lines.append(report.get("note", "No overlaps.\n"))
    else:
        lines.append(f"- Overlaps: **{report['overlaps']}**\n")
        lines.append(f"- Exact agreement: **{report['exact_agreement_rate']:.1%}**\n")
        lines.append(f"- Within one level: **{report['within_one_rate']:.1%}**\n")
        lines.append(f"- Engine higher (possible invisible expertise): {report['engine_higher_count']}\n")
        lines.append(f"- Baseline higher (possible scoring gap): {report['baseline_higher_count']}\n")
        lines.append("\n" + report.get("note", "") + "\n")
    out.write_text("".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    db_path = Path(argv[0]) if argv else Path(os.getenv("HERMES_DB_PATH", "data/hermes.db"))
    run(db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
