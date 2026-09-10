#!/usr/bin/env python3
"""Ingest Certificates sheet into cert_staging with earned_at=NULL (no invented dates)."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path = [str(ROOT / "src"), str(ROOT)] + [
    p for p in sys.path if Path(p).resolve() != (ROOT / "scripts" / "phase8").resolve()
]
os.environ.setdefault("HERMES_TEST_MODE", "1")

from phase8.workbook import cell_str, open_workbook, sheet_rows  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.service import HermesService  # noqa: E402


def staging_id(person: str, cert: str) -> str:
    material = f"{person.strip().lower()}|{cert.strip().lower()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def ingest_certs(src: Path, db_path: Path) -> dict:
    db = HermesDB(db_path)
    svc = HermesService(db=db)
    wb = open_workbook(src)
    rows = sheet_rows(wb["Certificates"])
    request_rows = []
    count = 0
    for row in rows[2:]:
        name = cell_str(row[0] if row else None)
        if not name:
            continue
        coded = svc.abstract({"employee_id": name.lower(), "name": name})["coded_identity"]
        for col in range(3, min(len(row), 12)):
            cert = cell_str(row[col])
            if not cert:
                continue
            sid = staging_id(name, cert)
            with db.session() as conn:
                conn.execute(
                    """
                    INSERT INTO cert_staging (
                      staging_id, coded_identity, cert_label, cert_code, earned_at, source_sheet, promoted
                    ) VALUES (?, ?, ?, NULL, NULL, 'Certificates', 0)
                    ON CONFLICT(staging_id) DO NOTHING
                    """,
                    (sid, coded, cert),
                )
            request_rows.append(
                {
                    "staging_id": sid,
                    "person_name": name,
                    "coded_identity": coded,
                    "cert_label": cert,
                    "earned_at": "",
                }
            )
            count += 1
    out = ROOT / "data" / "phase8" / "cert_date_request.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["staging_id", "person_name", "coded_identity", "cert_label", "earned_at"]
        )
        w.writeheader()
        w.writerows(request_rows)
    report = {"certs_staged": count, "date_request": str(out), "note": "earned_at left empty — do not invent"}
    print(json.dumps(report, indent=2))
    return report


def promote_dated_certs(csv_path: Path, db_path: Path) -> dict:
    """Promote rows with non-empty earned_at into CertifiedEvidence → skills_matrix."""
    from datetime import datetime

    from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel
    from shared.taxonomy import load_taxonomy

    db = HermesDB(db_path)
    svc = HermesService(db=db)
    tax = load_taxonomy()
    # cert_code lookup from ontology
    code_to_skill = {}
    for skill in tax.all_skills():
        for code in skill.cert_codes:
            code_to_skill[code.lower()] = skill.skill_id

    promoted = 0
    skipped_null = 0
    evidence = []
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            earned = (row.get("earned_at") or "").strip()
            if not earned:
                skipped_null += 1
                continue
            coded = row["coded_identity"]
            label = row["cert_label"]
            # Map label → skill via cert_codes containment or pending skip
            skill_id = None
            low = label.lower()
            for code, sid in code_to_skill.items():
                if code in low or low in code:
                    skill_id = sid
                    break
            if not skill_id:
                # leave unpromoted if unknown — do not guess into matrix
                continue
            occurred = datetime.fromisoformat(earned.replace("Z", "+00:00"))
            evidence.append(
                EvidenceRecord(
                    evidence_id=f"cert-{row['staging_id']}",
                    coded_identity=coded,
                    skill_id=skill_id,
                    evidence_type=EvidenceType.CERTIFIED,
                    proficiency=ProficiencyLevel.PROFICIENT,
                    occurred_at=occurred,
                    source_ref=label,
                )
            )
            with db.session() as conn:
                conn.execute(
                    "UPDATE cert_staging SET earned_at=?, promoted=1, cert_code=? WHERE staging_id=?",
                    (earned, skill_id, row["staging_id"]),
                )
            promoted += 1
    if evidence:
        svc.stage_and_merge(evidence)
    return {"promoted": promoted, "skipped_null_or_blank_date": skipped_null}


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    src = Path(argv[0]) if argv else ROOT / "data" / "source" / "Skill_Matrix_2025.xlsx"
    db_path = Path(argv[1]) if len(argv) > 1 else Path(os.getenv("HERMES_DB_PATH", "data/hermes.db"))
    ingest_certs(src, db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
