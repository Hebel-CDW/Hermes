#!/usr/bin/env python3
"""Seed the SYNTHETIC demo organisation (data/fixtures/demo_org.json) into a fresh database.

36 invented people across all 8 skill domains, 10 role templates (one per manager scenario in
docs/DEMO_RUNBOOK.md), demand signals, two reporting lines and one open evidence dispute.
Evidence dates are stored as "days ago" and resolved at seed time, so freshness is the same
every time the demo is started.
"""

from __future__ import annotations

import argparse
import json
import os
import zlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path = [str(ROOT / "src"), str(ROOT)] + sys.path

from shared.db import HermesDB  # noqa: E402
from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel  # noqa: E402
from shared.service import HermesService  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "demo_org.json"
TICKET_GAP_DAYS = 21


def _records(fixture: Dict[str, Any], coded: Dict[str, str], now: datetime) -> List[EvidenceRecord]:
    out: List[EvidenceRecord] = []
    for row in fixture["evidence"]:
        emp, skill, level = row["employee_id"], row["skill_id"], ProficiencyLevel(row["proficiency"])
        when = now - timedelta(days=row["days_ago"])
        if row["kind"] == "D":
            for i in range(int(row["detail"])):
                key = "{}:{}:{}".format(emp, skill, i)
                ref = "INC-{}".format(zlib.crc32(key.encode()) % 90000 + 10000)
                out.append(
                    EvidenceRecord(
                        evidence_id=f"{ref}:{skill}",
                        coded_identity=coded[emp],
                        skill_id=skill,
                        evidence_type=EvidenceType.DEMONSTRATED,
                        proficiency=level,
                        occurred_at=when - timedelta(days=TICKET_GAP_DAYS * i),
                        source_ref=ref,
                        metadata={"source_ref": ref},
                    )
                )
        elif row["kind"] == "C":
            out.append(
                EvidenceRecord(
                    evidence_id=f"cert-{row['detail']}-{emp}",
                    coded_identity=coded[emp],
                    skill_id=skill,
                    evidence_type=EvidenceType.CERTIFIED,
                    proficiency=level,
                    occurred_at=when,
                    source_ref=row["detail"],
                )
            )
        else:
            out.append(
                EvidenceRecord(
                    evidence_id=f"decl-{emp}-{skill}",
                    coded_identity=coded[emp],
                    skill_id=skill,
                    evidence_type=EvidenceType.DECLARED,
                    proficiency=level,
                    occurred_at=when,
                    source_ref="declared",
                    metadata={"manager_confirmed": bool(row["detail"])},
                )
            )
    return out


def seed(db_path: Path, fixture_path: Path = FIXTURE) -> Dict[str, Any]:
    os.environ["HERMES_DB_PATH"] = str(db_path)
    os.environ.setdefault("HERMES_TEST_MODE", "1")
    for suffix in ("", "-shm", "-wal", ".audit-anchor.json"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    db = HermesDB(db_path)
    svc = HermesService(db=db, mapping_secret=os.getenv("IDENTITY_MAP_SECRET"))
    svc.mark_database("synthetic")

    coded = {
        p["employee_id"]: svc.abstract({"employee_id": p["employee_id"], "name": p["display_name"]})["coded_identity"]
        for p in fixture["pilot_population"]
    }
    now = datetime.now(timezone.utc)
    merged = svc.stage_and_merge(_records(fixture, coded, now), as_of=now)
    db.set_demand(fixture["demand_weights"])
    for role in fixture["roles"]:
        db.upsert_role(
            role["role_id"],
            role["role_name"],
            role["required_skills"],
            critical_skills=role["critical_skills"],
            min_coverage_ratio=role["min_coverage_ratio"],
        )
    for edge in fixture["org_edges"]:
        db.add_org_edge(coded[edge["manager_employee_id"]], coded[edge["report_employee_id"]])
    for c in fixture.get("contests", []):
        svc.contest(coded[c["employee_id"]], c["reason"], c["skill_id"])
    return {"people": len(coded), "skill_records": len(merged), "roles": len(fixture["roles"])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path(os.getenv("HERMES_DB_PATH", "data/hermes_demo.db")))
    args = parser.parse_args(argv)
    print(json.dumps(seed(args.db), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
