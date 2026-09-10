#!/usr/bin/env python3
"""Keyword precision/recall on held-out anonymised ticket short descriptions."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shared.taxonomy import load_taxonomy


def main() -> int:
    path = Path("data/fixtures/validation/held_out_tickets.json")
    tickets = json.loads(path.read_text())["tickets"]
    tax = load_taxonomy()
    tp = fp = fn = 0
    per_skill = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    for t in tickets:
        predicted = set(tax.match_keywords(t["short_description"]))
        expected = set(t["expected_skills"])
        tp += len(predicted & expected)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        for s in predicted & expected:
            per_skill[s]["tp"] += 1
        for s in predicted - expected:
            per_skill[s]["fp"] += 1
        for s in expected - predicted:
            per_skill[s]["fn"] += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    report = {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "per_skill": dict(per_skill),
    }
    out = Path("docs/validation/keyword-precision-report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = Path("docs/validation/keyword-precision.md")
    md.write_text(
        f"# Keyword precision (held-out)\n\n"
        f"- Precision: **{precision:.2%}**\n"
        f"- Recall: **{recall:.2%}**\n"
        f"- TP/FP/FN: {tp}/{fp}/{fn}\n\n"
        f"Source: `{path}` (anonymised short descriptions only).\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
