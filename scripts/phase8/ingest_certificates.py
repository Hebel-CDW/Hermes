#!/usr/bin/env python3
"""Ingest Certificates sheet into cert_staging with earned_at=NULL (no invented dates)."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from collections import Counter
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path = [str(ROOT / "src"), str(ROOT)] + [
    p for p in sys.path if Path(p).resolve() != (ROOT / "scripts" / "phase8").resolve()
]
from phase8.workbook import cell_str, open_workbook, sheet_rows  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.secrets import require_real_data_ingest_secret  # noqa: E402
from shared.service import HermesService  # noqa: E402


def staging_id(person: str, cert: str) -> str:
    material = f"{person.strip().lower()}|{cert.strip().lower()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


CERT_COLUMNS = range(3, 12)  # certificate cells sit in columns D..L of the Certificates sheet


def ingest_certs(
    src: Path,
    db_path: Path,
    request_csv: Optional[Path] = None,
    include_names: bool = False,
    svc: Optional[HermesService] = None,
    quiet: bool = False,
) -> dict:
    """Stage certificates with earned_at=NULL; classify each label by exact cert code only.

    * Dates are never invented: ``earned_at`` stays NULL until a human supplies it.
    * Classification uses ``resolve_cert_label`` (human alias or whole-token cert code);
      no fuzzy or substring matching. Nothing is promoted to evidence here.
    * The date-request worksheet carries coded identities; the person-name column is
      opt-in (``include_names``) for an authorised reviewer and is gitignored.
    """
    # C-2 guardrail: real people are tokenised from the Certificates sheet here.
    secret = require_real_data_ingest_secret()
    if svc is None:
        svc = HermesService(db=HermesDB(db_path), mapping_secret=secret)
    db = svc.db
    svc.mark_database("real")  # refuses to relabel a synthetic DB or switch secrets
    from shared.taxonomy import load_taxonomy

    code_to_skill = {code.lower(): skill.skill_id for skill in load_taxonomy().all_skills() for code in skill.cert_codes}
    wb = open_workbook(src)
    rows = sheet_rows(wb["Certificates"])
    coded_for: Dict[str, str] = {}
    outcome_for: Dict[str, tuple] = {}
    outcomes: Counter = Counter()
    staged: Dict[str, tuple] = {}
    request_rows = []
    for row in rows[2:]:
        name = cell_str(row[0] if row else None)
        if not name:
            continue
        key = name.lower()
        if key not in coded_for:
            coded_for[key] = db.resolve_coded_for_source(key) or svc.abstract(
                {"employee_id": key, "name": name}
            )["coded_identity"]
        coded = coded_for[key]
        for col in CERT_COLUMNS:
            if col >= len(row):
                break
            cert = cell_str(row[col])
            if not cert:
                continue
            if cert not in outcome_for:
                outcome_for[cert] = resolve_cert_label(cert, code_to_skill, db)
            _skill, cert_code, outcome = outcome_for[cert]
            outcomes[outcome] += 1
            sid = staging_id(name, cert)
            staged[sid] = (sid, coded, cert, cert_code)
            entry = {"staging_id": sid, "coded_identity": coded, "cert_label": cert, "earned_at": ""}
            if include_names:
                entry["person_name"] = name
            request_rows.append(entry)
    db.insert_cert_stagings(list(staged.values()))  # one transaction

    out = request_csv or (ROOT / "data" / "phase8" / "cert_date_request.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["staging_id", "coded_identity", "cert_label", "earned_at"] + (["person_name"] if include_names else [])
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(request_rows)
    report = {
        "certs_staged": len(request_rows),
        "staging_rows": len(staged),
        "people_with_certificates": len(coded_for),
        "distinct_cert_labels": len(outcome_for),
        "classification": {
            "exact_cert_code": outcomes.get("exact_cert_code", 0),
            "human_alias": outcomes.get("human_alias", 0),
            "ambiguous_label": outcomes.get("ambiguous_label", 0),
            "unmapped_label": outcomes.get("unmapped_label", 0),
        },
        "date_request": str(out),
        "date_request_includes_names": include_names,
        "note": "earned_at left empty — do not invent",
    }
    if not quiet:
        print(json.dumps(report, indent=2))
    return report


def _token_list(text: str) -> list:
    import re

    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _contains_token_sequence(haystack: list, needle: list) -> bool:
    """True when `needle` occurs as consecutive whole tokens in `haystack`."""
    n = len(needle)
    return n > 0 and any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def resolve_cert_label(label: str, code_to_skill: dict, db: HermesDB) -> tuple:
    """Governed cert label -> (skill_id, cert_code, outcome).

    Order of precedence — no fuzzy or substring matching anywhere:
      1. a human-approved alias in skill_aliases (mapped_by='human')
      2. ontology cert codes appearing as consecutive whole tokens in the label
         ("CKA - Certified Kubernetes Administrator" -> CKA; "AZ-104: ..." -> AZ-104)
    Anything else is left unpromoted: `unmapped_label` when nothing matches,
    `ambiguous_label` when codes for more than one skill match.

    G-3: this replaces a bidirectional substring test (`code in label or label in
    code`) that could silently credit a certificate to the wrong skill.
    """
    from phase8.workbook import normalize_label

    with db.session() as conn:
        row = conn.execute(
            "SELECT skill_id FROM skill_aliases WHERE alias_label = ? AND mapped_by = 'human'",
            (normalize_label(label),),
        ).fetchone()
    if row and row["skill_id"]:
        return row["skill_id"], None, "human_alias"

    label_tokens = _token_list(label)
    hits = {
        code: sid
        for code, sid in code_to_skill.items()
        if _contains_token_sequence(label_tokens, _token_list(code))
    }
    skills = set(hits.values())
    if len(skills) == 1:
        code = sorted(hits)[0]
        return skills.pop(), code.upper(), "exact_cert_code"
    if len(skills) > 1:
        return None, None, "ambiguous_label"
    return None, None, "unmapped_label"


def promote_dated_certs(csv_path: Path, db_path: Path, mapping_secret: Optional[str] = None) -> dict:
    """Promote rows with a human-supplied earned_at and a governed skill mapping.

    Callers choose the secret explicitly; the CLI (`promote_certs.py --mode`) never
    silently falls back to test mode.
    """
    from datetime import datetime

    from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel
    from shared.taxonomy import load_taxonomy

    db = HermesDB(db_path)
    svc = HermesService(db=db, mapping_secret=mapping_secret)
    tax = load_taxonomy()
    code_to_skill = {}
    for skill in tax.all_skills():
        for code in skill.cert_codes:
            code_to_skill[code.lower()] = skill.skill_id

    promoted = 0
    skipped_null = 0
    skipped_unmapped = 0
    skipped_ambiguous = 0
    evidence = []
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            earned = (row.get("earned_at") or "").strip()
            if not earned:
                skipped_null += 1
                continue
            coded = row["coded_identity"]
            label = row["cert_label"]
            skill_id, cert_code, outcome = resolve_cert_label(label, code_to_skill, db)
            if outcome == "ambiguous_label":
                skipped_ambiguous += 1
                continue
            if skill_id is None:
                skipped_unmapped += 1
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
                    source_ref=cert_code or label,
                    metadata={"source_ref": cert_code or label},
                )
            )
            with db.session() as conn:
                conn.execute(
                    "UPDATE cert_staging SET earned_at=?, promoted=1, cert_code=? WHERE staging_id=?",
                    (earned, cert_code, row["staging_id"]),
                )
            promoted += 1
    if evidence:
        svc.stage_and_merge(evidence)
    return {
        "promoted": promoted,
        "skipped_null_or_blank_date": skipped_null,
        "skipped_unmapped_label": skipped_unmapped,
        "skipped_ambiguous_label": skipped_ambiguous,
    }


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    src = Path(argv[0]) if argv else ROOT / "data" / "source" / "Skill_Matrix_2025.xlsx"
    db_path = Path(argv[1]) if len(argv) > 1 else Path(os.getenv("HERMES_DB_PATH", "data/hermes.db"))
    ingest_certs(src, db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
