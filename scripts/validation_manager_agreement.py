#!/usr/bin/env python3
"""Blind manager-agreement baseline vs Hermes top-1/top-3 (fixture-backed)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HERMES_TEST_MODE", "1")

from shared.db import HermesDB
from shared.models import ProficiencyLevel, StaffingRequest
from shared.service import HermesService
from ingest_fixtures import ingest


def main() -> int:
    db_path = Path("data/hermes_validation.db")
    ingest(Path("data/fixtures/pilot_population.json"), db_path)
    svc = HermesService(db=HermesDB(db_path))
    decisions = json.loads(Path("data/fixtures/validation/manager_decisions.json").read_text())[
        "decisions"
    ]
    top1 = top3 = 0
    disagreements = []
    for d in decisions:
        mgr_key = d["manager_top1"].strip().lower()
        mgr_coded = svc.db.resolve_coded_for_source(mgr_key)
        req = StaffingRequest(
            request_id=f"val-{d['id']}",
            requester_id="validation",
            required_skills={d["required_skill"]: ProficiencyLevel.PROFICIENT},
            shortlist_size=3,
        )
        result = svc.rank(req)
        codes = [c.coded_identity for c in result.candidates]
        if mgr_coded and codes and codes[0] == mgr_coded:
            top1 += 1
        if mgr_coded and mgr_coded in codes:
            top3 += 1
        else:
            disagreements.append(
                {
                    "id": d["id"],
                    "skill": d["required_skill"],
                    "manager": mgr_coded,
                    "hermes_top": codes,
                    "notes": d.get("hermes_notes"),
                }
            )
    n = len(decisions)
    report = {
        "n": n,
        "top1_agreement": round(top1 / n, 4) if n else 0,
        "top3_agreement": round(top3 / n, 4) if n else 0,
        "disagreement_count": len(disagreements),
        "disagreements_sample": disagreements[:10],
    }
    Path("docs/validation").mkdir(parents=True, exist_ok=True)
    Path("docs/validation/manager-agreement-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    Path("docs/validation/manager-agreement.md").write_text(
        f"# Manager agreement baseline (n={n})\n\n"
        f"- Top-1 agreement: **{report['top1_agreement']:.1%}**\n"
        f"- Top-3 agreement: **{report['top3_agreement']:.1%}**\n"
        f"- Disagreements characterised: {report['disagreement_count']}\n\n"
        "Disagreements are expected when managers use informal knowledge Hermes cannot see.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
