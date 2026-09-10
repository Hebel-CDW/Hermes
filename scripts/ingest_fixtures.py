"""Ingest pilot fixtures through identity gate + inference into SQLite."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from shared.db import HermesDB
from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel
from shared.service import HermesService
from skill_inference.engine import SkillInferenceEngine


def load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ingest(fixture_path: Path, db_path: Path) -> dict:
    os.environ["HERMES_DB_PATH"] = str(db_path)
    if db_path.exists():
        db_path.unlink()
    db = HermesDB(db_path)
    os.environ.setdefault("HERMES_TEST_MODE", "1")
    svc = HermesService(db=db, mapping_secret=os.getenv("IDENTITY_MAP_SECRET"))
    fixture = load_fixture(fixture_path)
    engine = SkillInferenceEngine()

    for person in fixture["pilot_population"]:
        svc.abstract({"employee_id": person["employee_id"], "name": person["display_name"]})

    evidence = []
    for ticket in fixture["tickets"]:
        abstracted = svc.abstract(ticket)
        occurred = datetime.fromisoformat(ticket["resolved_at"].replace("Z", "+00:00"))
        evidence.extend(
            engine.infer_from_ticket(
                abstracted["coded_identity"],
                ticket["short_description"],
                occurred,
                ticket["ticket_number"],
                ticket["ticket_number"],
            )
        )

    for cert in fixture["certifications"]:
        abstracted = svc.abstract(cert)
        evidence.append(
            EvidenceRecord(
                evidence_id=f"cert-{cert['cert_code']}-{cert['employee_id']}",
                coded_identity=abstracted["coded_identity"],
                skill_id=cert["skill_id"],
                evidence_type=EvidenceType.CERTIFIED,
                proficiency=ProficiencyLevel(cert["proficiency"]),
                occurred_at=datetime.fromisoformat(cert["earned_at"].replace("Z", "+00:00")),
                source_ref=cert["cert_code"],
            )
        )

    for dec in fixture["declared"]:
        abstracted = svc.abstract(dec)
        evidence.append(
            EvidenceRecord(
                evidence_id=f"decl-{dec['employee_id']}-{dec['skill_id']}",
                coded_identity=abstracted["coded_identity"],
                skill_id=dec["skill_id"],
                evidence_type=EvidenceType.DECLARED,
                proficiency=ProficiencyLevel(dec["proficiency"]),
                occurred_at=datetime.fromisoformat(dec["declared_at"].replace("Z", "+00:00")),
                source_ref="declared",
                metadata={"manager_confirmed": dec["manager_confirmed"]},
            )
        )

    merged = svc.stage_and_merge(evidence)
    svc.db.set_demand(fixture.get("demand_weights", {}))
    role = fixture.get("role_senior_cloud")
    if role:
        svc.db.upsert_role(
            role["role_id"],
            role["role_name"],
            role["required_skills"],
            critical_skills=role.get("critical_skills") or [],
            min_coverage_ratio=float(role.get("min_coverage_ratio", 0.6)),
        )

    for edge in fixture.get("org_edges", []):
        mgr_id = svc.db.resolve_coded_for_source(edge["manager_employee_id"])
        rep_id = svc.db.resolve_coded_for_source(edge["report_employee_id"])
        if mgr_id and rep_id:
            svc.db.add_org_edge(mgr_id, rep_id)

    # also refresh JSON samples for leakage audit
    matrix = [m.model_dump(mode="json") for m in merged]
    out_dir = Path("data/fixtures")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coded_matrix_sample.json").write_text(
        json.dumps({"records": matrix}, indent=2), encoding="utf-8"
    )
    blocklist = [p["display_name"] for p in fixture["pilot_population"]]
    (out_dir / "identity_blocklist.json").write_text(json.dumps(blocklist, indent=2), encoding="utf-8")

    coverage = svc.db.pilot_coverage()
    report = {
        "db_path": str(db_path),
        "skills_scored": len(merged),
        "coverage": coverage,
    }
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Hermes pilot fixtures into SQLite")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("data/fixtures/pilot_population.json"),
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.getenv("HERMES_DB_PATH", "data/hermes.db")),
    )
    args = parser.parse_args(argv)
    report = ingest(args.fixture, args.db)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
