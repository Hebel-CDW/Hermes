#!/usr/bin/env python3
"""Generate Hermes_Skills_Collection_Template_v2.xlsx from ontology + 2025 teams."""

from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from shared.taxonomy import load_taxonomy  # noqa: E402

OUT = ROOT / "data" / "phase8" / "Hermes_Skills_Collection_Template_v2.xlsx"

# Reconciled against 22 workbook sheets (Certificates excluded as a team)
TEAMS_2025 = [
    "iSeries L2",
    "iSeries L3",
    "ZI Ops",
    "Citrix",
    "CI Ops",
    "Virtualization",
    "Windows",
    "CTS",
    "Collab",
    "Network Security",
    "Backup",
    "Tools",
    "AWS",
    "GCP",
    "Azure",
    "Datacenter",
    "AIX",
    "Endpoint compliance",
    "Storage",
    "MSS",
    "ECC-OPS",
]

TOWERS = ["Compute", "Cloud", "Network", "Storage", "Endpoint", "Collaboration", "Mainframe", "Security", "Ops"]
SKILL_TYPES = ["Technical", "Platform", "Process"]
CRITICALITY = ["Y", "N"]
PROFICIENCY = ["1", "2", "3", "4", "5"]
DECAY = ["fast", "medium", "slow"]


def main() -> int:
    tax = load_taxonomy()
    skills = tax.all_skills()
    wb = Workbook()

    # Instructions — ontology level definitions win
    ws = wb.active
    ws.title = "Instructions"
    ws.append(["Hermes Skills Collection Template v2"])
    ws.append([])
    ws.append(["Proficiency levels (from Hermes ontology — not v1 template wording):"])
    # Use first skill's definitions as canonical text
    for p in skills[0].proficiency_levels:
        ws.append([int(p.level), p.label, p.behavioural_definition])
    ws.append([])
    ws.append(["Notes:"])
    ws.append(["- Skill ID must match the ontology / candidate_skills canonical_id."])
    ws.append(["- Decay Class: fast=<1y, medium=1-3y, slow=>3y half-life."])
    ws.append(["- As-of Date is required for certified evidence promotion."])
    ws.append(["- Do not enter client/account names as skills."])

    # Skills Collection
    sc = wb.create_sheet("Skills Collection")
    sc_headers = [
        "Employee Name",
        "Tower",
        "Team",
        "Skill ID",
        "Skill Name",
        "Skill Type",
        "Required Proficiency",
        "Ticket Keywords",
        "Parent / Related Skills",
        "Decay Class",
        "As-of Date",
        "Confirmed By",
        "Criticality",
    ]
    sc.append(sc_headers)

    # Role Profiles
    rp = wb.create_sheet("Role Profiles")
    rp.append(["role_id", "role_name", "skill_id", "required_level", "critical"])

    # Team Reference
    tr = wb.create_sheet("Team Reference")
    tr.append(["team_name", "tower_hint", "notes"])
    for team in TEAMS_2025:
        tower = "Cloud" if team in {"AWS", "GCP", "Azure"} else ""
        note = "Separate cloud platform team" if team in {"AWS", "GCP", "Azure"} else ""
        tr.append([team, tower, note])

    # Hidden lists for dropdowns
    lists = wb.create_sheet("_lists")
    lists.append(["skill_id"])
    for s in skills:
        lists.append([s.skill_id])
    lists["B1"] = "team"
    for i, team in enumerate(TEAMS_2025, start=2):
        lists[f"B{i}"] = team
    lists["C1"] = "decay"
    for i, d in enumerate(DECAY, start=2):
        lists[f"C{i}"] = d
    lists["D1"] = "tower"
    for i, t in enumerate(TOWERS, start=2):
        lists[f"D{i}"] = t
    lists["E1"] = "skill_type"
    for i, t in enumerate(SKILL_TYPES, start=2):
        lists[f"E{i}"] = t
    lists["F1"] = "criticality"
    for i, t in enumerate(CRITICALITY, start=2):
        lists[f"F{i}"] = t
    lists["G1"] = "proficiency"
    for i, t in enumerate(PROFICIENCY, start=2):
        lists[f"G{i}"] = t

    n_skills = len(skills)
    n_teams = len(TEAMS_2025)

    def add_dv(ws, formula: str, cells: str) -> None:
        dv = DataValidation(type="list", formula1=formula, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(cells)

    add_dv(sc, f"'_lists'!$D$2:$D${1+len(TOWERS)}", "B2:B500")
    add_dv(sc, f"'_lists'!$B$2:$B${1+n_teams}", "C2:C500")
    add_dv(sc, f"'_lists'!$A$2:$A${1+n_skills}", "D2:D500")
    add_dv(sc, f"'_lists'!$E$2:$E${1+len(SKILL_TYPES)}", "F2:F500")
    add_dv(sc, f"'_lists'!$G$2:$G${1+len(PROFICIENCY)}", "G2:G500")
    add_dv(sc, f"'_lists'!$C$2:$C${1+len(DECAY)}", "J2:J500")
    add_dv(sc, f"'_lists'!$F$2:$F${1+len(CRITICALITY)}", "M2:M500")

    add_dv(rp, f"'_lists'!$A$2:$A${1+n_skills}", "C2:C200")
    add_dv(rp, f"'_lists'!$G$2:$G${1+len(PROFICIENCY)}", "D2:D200")
    add_dv(rp, f"'_lists'!$F$2:$F${1+len(CRITICALITY)}", "E2:E200")

    lists.sheet_state = "hidden"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
