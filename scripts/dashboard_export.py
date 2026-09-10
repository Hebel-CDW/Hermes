"""Export coded-only coverage/freshness dashboard (Power BI replacement)."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from shared.db import HermesDB


def export(db_path: Path, out_dir: Path) -> Path:
    db = HermesDB(db_path)
    matrix = db.matrix_records_as_dicts()
    coverage = db.pilot_coverage()

    by_skill = defaultdict(list)
    for row in matrix:
        by_skill[row["skill_id"]].append(float(row["freshness"]))

    freshness = {
        skill: round(sum(vals) / len(vals), 4) if vals else 0.0
        for skill, vals in sorted(by_skill.items())
    }

    # Explicitly never include display names
    for row in matrix:
        assert "name" not in row
        assert "display_name" not in row

    report = {
        "coverage": coverage,
        "avg_freshness_by_skill": freshness,
        "skill_distribution": [
            {
                "coded_identity": r["coded_identity"],
                "skill_id": r["skill_id"],
                "proficiency": r["proficiency"],
                "confidence": r["confidence"],
                "freshness": r["freshness"],
            }
            for r in matrix
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "dashboard.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    rows_html = "".join(
        f"<tr><td>{r['coded_identity']}</td><td>{r['skill_id']}</td>"
        f"<td>{r['proficiency']}</td><td>{r['confidence']}</td><td>{r['freshness']}</td></tr>"
        for r in report["skill_distribution"]
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Hermes Local Dashboard</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 2rem; background: #f7f4ef; color: #1c1c1c; }}
    h1 {{ font-size: 1.6rem; }}
    .meta {{ margin-bottom: 1.5rem; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }}
    th {{ background: #ebe4d8; }}
    .note {{ margin-top: 1rem; font-size: 0.9rem; color: #444; }}
  </style>
</head>
<body>
  <h1>Hermes — Skills Matrix (coded identities only)</h1>
  <div class="meta">
    <div>Pilot size: {coverage['pilot_size']}</div>
    <div>With demonstrated evidence: {coverage['with_demonstrated']}</div>
    <div>Coverage: {coverage['coverage_pct']}%</div>
  </div>
  <table>
    <thead>
      <tr><th>Coded ID</th><th>Skill</th><th>Proficiency</th><th>Confidence</th><th>Freshness</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
  <p class="note">Real names are never shown on this dashboard. Resolution is logged and shortlist-only.</p>
</body>
</html>
"""
    html_path = out_dir / "dashboard.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path(os.getenv("HERMES_DB_PATH", "data/hermes.db")))
    parser.add_argument("--out", type=Path, default=Path("data/reports"))
    args = parser.parse_args(argv)
    path = export(args.db, args.out)
    print(json.dumps({"dashboard": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
