"""Excel sunset: freeze 2025 survey, refuse the next workbook, never seed scores."""

from __future__ import annotations

from pathlib import Path

import pytest

from shared.errors import WorkbookFrozenError
from shared.excel_sunset import (
    FORBIDDEN_NEXT_YEAR,
    FROZEN_SURVEY_YEAR,
    freeze_database,
    kill_gate,
    refuse_future_workbook,
)


def test_frozen_year_is_2025_and_next_workbook_is_2026():
    assert FROZEN_SURVEY_YEAR == 2025
    assert FORBIDDEN_NEXT_YEAR == 2026


@pytest.mark.parametrize(
    "name",
    [
        "Skill_Matrix_2026.xlsx",
        "skill_matrix_2027.xlsx",
        "Skill Matrix 2026.xlsx",
    ],
)
def test_refuses_workbooks_after_the_frozen_survey(name, tmp_path):
    path = tmp_path / name
    path.write_bytes(b"xlsx")
    with pytest.raises(WorkbookFrozenError) as exc:
        refuse_future_workbook(path)
    assert exc.value.code == "workbook_frozen"
    assert "2026" in str(exc.value) or str(FORBIDDEN_NEXT_YEAR) in str(exc.value)


@pytest.mark.parametrize("name", ["Skill_Matrix_2025.xlsx", "Skill_matrix_Data.xlsx"])
def test_allows_the_frozen_2025_workbook(name, tmp_path):
    path = tmp_path / name
    path.write_bytes(b"xlsx")
    refuse_future_workbook(path)  # does not raise


def test_freeze_database_records_policy_metadata(tmp_path):
    from shared.db import HermesDB

    db = HermesDB(tmp_path / "freeze.db")
    freeze_database(db)
    assert db.get_meta("survey_frozen_year") == "2025"
    assert db.get_meta("next_workbook_forbidden") == "2026"


def test_kill_gate_starts_closed_on_an_empty_database(tmp_path):
    from shared.db import HermesDB

    db = HermesDB(tmp_path / "gate.db")
    freeze_database(db)
    gate = kill_gate(db)
    assert gate["survey_year_frozen"] == 2025
    assert gate["next_workbook_allowed"] is False
    assert gate["ready_to_retire_excel"] is False
    assert gate["criteria"]["survey_frozen"] is True
    assert gate["criteria"]["pilot_coverage_met"] is False
    assert gate["criteria"]["baseline_agreement_met"] is False
    assert gate["criteria"]["staffing_decision_met"] is False


def test_ingest_baseline_refuses_a_2026_workbook_before_opening(tmp_path):
    from scripts.phase8.ingest_baseline import ingest

    path = tmp_path / "Skill_Matrix_2026.xlsx"
    path.write_bytes(b"xlsx")
    with pytest.raises(WorkbookFrozenError):
        ingest(path, tmp_path / "no.db")
