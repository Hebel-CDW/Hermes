"""Policy and helpers to retire the annual Skill Matrix workbook.

The 2025 workbook is a labelled survey (Track B). Fitness never reads it.
A 2026 Skill Matrix must not be ingested. Living scores come from tickets,
dated certificates, and manager-confirmed declared skills.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from shared.db import HermesDB
from shared.errors import WorkbookFrozenError

FROZEN_SURVEY_YEAR = 2025
FORBIDDEN_NEXT_YEAR = 2026
_YEAR_IN_NAME = re.compile(r"(?:skill[\s_-]*matrix[\s_-]*)?(20\d{2})", re.I)

ROOT = Path(__file__).resolve().parents[2]
PROPOSALS_PATH = ROOT / "taxonomy" / "pilot_aliases.yaml"


def refuse_future_workbook(path: Path) -> None:
    """Allow the frozen 2025 survey (and year-less copies). Refuse later years."""
    name = Path(path).name
    match = _YEAR_IN_NAME.search(name.replace(" ", "_"))
    if not match:
        return
    year = int(match.group(1))
    if year > FROZEN_SURVEY_YEAR:
        raise WorkbookFrozenError(
            f"Skill Matrix {year} is forbidden. The {FROZEN_SURVEY_YEAR} workbook is frozen "
            f"as a labelled survey. Updates go through Hermes evidence, not a {FORBIDDEN_NEXT_YEAR} spreadsheet."
        )


def freeze_database(db: HermesDB) -> None:
    db.set_meta("survey_frozen_year", str(FROZEN_SURVEY_YEAR))
    db.set_meta("next_workbook_forbidden", str(FORBIDDEN_NEXT_YEAR))


def load_alias_proposals(path: Optional[Path] = None) -> Dict[str, str]:
    """Normalised alias label -> governed skill_id. Proposals only until a human approves."""
    from phase8.workbook import normalize_label

    src = path or PROPOSALS_PATH
    if not src.is_file():
        return {}
    raw = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    out: Dict[str, str] = {}
    for row in raw.get("proposals") or []:
        alias = normalize_label(str(row["alias"]))
        skill_id = str(row["skill_id"]).strip()
        if alias and skill_id:
            out[alias] = skill_id
    return out


def _coverage_pct(db: HermesDB) -> float:
    stats = db.pilot_coverage()
    return float(stats.get("coverage_pct") or 0.0)


def _agreement_overlaps(db: HermesDB) -> int:
    with db.session() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM baseline_assessments b
            JOIN skills_matrix s
              ON s.coded_identity = b.coded_identity AND s.skill_id = b.skill_id
            WHERE b.skill_id IS NOT NULL AND b.skill_id != ''
            """
        ).fetchone()
    return int(row["n"])


def _decision_count(db: HermesDB) -> int:
    with db.session() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM staffing_requests WHERE status IN ('accepted','rejected') AND decided_at IS NOT NULL"
        ).fetchone()
    return int(row["n"])


def kill_gate(db: HermesDB) -> Dict[str, Any]:
    freeze_database(db)
    coverage = _coverage_pct(db)
    overlaps = _agreement_overlaps(db)
    decisions = _decision_count(db)
    survey_frozen = db.get_meta("survey_frozen_year") == str(FROZEN_SURVEY_YEAR)
    coverage_met = coverage >= 80.0
    agreement_met = overlaps > 0
    decision_met = decisions >= 1
    ready = survey_frozen and coverage_met and agreement_met and decision_met
    return {
        "survey_year_frozen": FROZEN_SURVEY_YEAR,
        "next_workbook_year_forbidden": FORBIDDEN_NEXT_YEAR,
        "next_workbook_allowed": False,
        "ready_to_retire_excel": ready,
        "criteria": {
            "survey_frozen": survey_frozen,
            "pilot_coverage_pct": coverage,
            "pilot_coverage_met": coverage_met,
            "baseline_agreement_overlaps": overlaps,
            "baseline_agreement_met": agreement_met,
            "staffing_decisions": decisions,
            "staffing_decision_met": decision_met,
        },
    }


def map_cert_label(db: HermesDB, label: str, code_to_skill: Dict[str, str]) -> tuple:
    """Human alias first, then whole-token cert codes. No fuzzy match."""
    import re

    from phase8.workbook import normalize_label

    with db.session() as conn:
        row = conn.execute(
            "SELECT skill_id FROM skill_aliases WHERE alias_label = ? "
            "AND mapped_by = 'human' AND skill_id IS NOT NULL AND skill_id != ''",
            (normalize_label(label),),
        ).fetchone()
    if row:
        return row["skill_id"], None

    def tokens(text: str) -> list:
        return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]

    label_tokens = tokens(label)
    hits: Dict[str, str] = {}
    for code, skill_id in code_to_skill.items():
        needle = tokens(code)
        n = len(needle)
        if n and any(label_tokens[i : i + n] == needle for i in range(len(label_tokens) - n + 1)):
            hits[code] = skill_id
    skills = set(hits.values())
    if len(skills) == 1:
        return skills.pop(), sorted(hits)[0].upper()
    return None, None


def pending_alias_inbox(db: HermesDB) -> Dict[str, Any]:
    from phase8.workbook import normalize_label

    proposals = load_alias_proposals()
    pending = []
    for row in db.list_pending_aliases():
        key = normalize_label(row["alias_label"])
        pending.append(
            {
                "alias_label": row["alias_label"],
                "skill_id": row.get("skill_id") or "",
                "mapped_by": row["mapped_by"],
                "proposed_skill_id": proposals.get(key, ""),
            }
        )
    return {"pending": pending}


def survey_matrix(db: HermesDB) -> Dict[str, Any]:
    """Read-only 2025 survey cells. Never written to skills_matrix."""
    from phase8.workbook import normalize_label

    proposals = load_alias_proposals()
    with db.session() as conn:
        aliases = {
            r["alias_label"]: r["skill_id"]
            for r in conn.execute(
                "SELECT alias_label, skill_id FROM skill_aliases "
                "WHERE mapped_by IN ('human','auto') AND skill_id IS NOT NULL AND skill_id != ''"
            )
        }
        rows = conn.execute(
            """
            SELECT coded_identity, skill_id, raw_label, normalised_level, source_sheet
            FROM baseline_assessments
            WHERE normalised_level IS NOT NULL
            ORDER BY coded_identity, raw_label
            """
        ).fetchall()
    cells = []
    for row in rows:
        skill_id = (row["skill_id"] or "").strip()
        if not skill_id:
            key = normalize_label(row["raw_label"])
            skill_id = aliases.get(key, "") or proposals.get(key, "")
        if not skill_id:
            continue
        cells.append(
            {
                "coded_identity": row["coded_identity"],
                "skill_id": skill_id,
                "raw_label": row["raw_label"],
                "level": int(row["normalised_level"]),
                "source_sheet": row["source_sheet"],
            }
        )
    return {
        "kind": "survey_2025",
        "used_for_fitness": False,
        "label": "2025 manager survey — not used for Find people",
        "cells": cells,
    }
