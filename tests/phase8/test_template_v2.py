import os
from pathlib import Path

import pytest
from openpyxl import load_workbook

os.environ.setdefault("HERMES_TEST_MODE", "1")

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "data" / "phase8" / "Hermes_Skills_Collection_Template_v2.xlsx"


@pytest.mark.skipif(not TEMPLATE.exists(), reason="template not generated")
def test_template_v2_round_trip():
    wb = load_workbook(TEMPLATE)
    assert "Instructions" in wb.sheetnames
    assert "Skills Collection" in wb.sheetnames
    assert "Role Profiles" in wb.sheetnames
    assert "Team Reference" in wb.sheetnames
    instr = [row[2] for row in wb["Instructions"].iter_rows(values_only=True) if row and row[0] == 3]
    # Level 3 label from ontology is Proficient
    assert any(row and row[0] == 3 and row[1] == "Proficient" for row in wb["Instructions"].iter_rows(values_only=True))
    sc = wb["Skills Collection"]
    headers = [c.value for c in next(sc.iter_rows(min_row=1, max_row=1))]
    for required in (
        "Skill ID",
        "Ticket Keywords",
        "Parent / Related Skills",
        "Decay Class",
        "As-of Date",
        "Confirmed By",
    ):
        assert required in headers
    teams = [r[0] for r in wb["Team Reference"].iter_rows(min_row=2, values_only=True) if r and r[0]]
    assert "AWS" in teams and "GCP" in teams and "Azure" in teams
    assert "Managed Cloud" not in teams
    # Dropdowns present on Skills Collection
    assert len(sc.data_validations.dataValidation) >= 5
