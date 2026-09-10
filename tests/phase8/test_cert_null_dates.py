import csv
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from shared.db import HermesDB
from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel
from shared.service import HermesService


def test_null_dated_cert_never_in_skills_matrix(tmp_path):
    db = HermesDB(tmp_path / "cert.db")
    svc = HermesService(db=db)
    coded = svc.abstract({"employee_id": "cert-person", "name": "Cert Person"})["coded_identity"]
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO cert_staging (
              staging_id, coded_identity, cert_label, cert_code, earned_at, promoted
            ) VALUES ('s1', ?, 'CKA', 'CKA', NULL, 0)
            """,
            (coded,),
        )
    # Staging alone must not create matrix rows
    assert svc.db.load_skills_matrix() == []

    # With a real date, certified evidence does create a matrix row
    svc.stage_and_merge(
        [
            EvidenceRecord(
                evidence_id="c-dated",
                coded_identity=coded,
                skill_id="container_orchestration",
                evidence_type=EvidenceType.CERTIFIED,
                proficiency=ProficiencyLevel.PROFICIENT,
                occurred_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
                source_ref="CKA",
            )
        ]
    )
    matrix = svc.db.load_skills_matrix()
    assert any(r.skill_id == "container_orchestration" for r in matrix)


def test_promote_skips_blank_earned_at(tmp_path):
    sys_path_fix()
    from ingest_certificates import promote_dated_certs

    db_path = tmp_path / "p.db"
    db = HermesDB(db_path)
    svc = HermesService(db=db)
    coded = svc.abstract({"employee_id": "p2", "name": "P Two"})["coded_identity"]
    csv_path = tmp_path / "req.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["staging_id", "person_name", "coded_identity", "cert_label", "earned_at"]
        )
        w.writeheader()
        w.writerow(
            {
                "staging_id": "x1",
                "person_name": "P Two",
                "coded_identity": coded,
                "cert_label": "Certified Kubernetes Administrator",
                "earned_at": "",
            }
        )
    report = promote_dated_certs(csv_path, db_path)
    assert report["promoted"] == 0
    assert svc.db.load_skills_matrix() == []


def sys_path_fix():
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "scripts" / "phase8"))
    sys.path.insert(0, str(root / "src"))
