"""Phase 5/7 — workbook parser tests against SYNTHETIC fixtures.

`src/phase8/parsers.py` previously had **0% coverage**: every real-workbook shape
was untested, and the whole `phase8` package was excluded from the coverage gate.

These fixtures are built in-memory with openpyxl and contain **invented** people and
labels. No confidential workbook is read, so the tests run identically in CI, on a
laptop, and in a clean clone.

Shapes covered:
  * people-as-rows (the 20 standard sheets)
  * Collab transposed (people across the header, applications down column B)
  * 1–5 and Collab 1–4 scales
  * zero / blank / fractional / non-numeric / out-of-range cells
  * Group Average and section-header rows
  * soft-skill, culture-fit, and client/account columns
"""

from __future__ import annotations

import os

import pytest
from openpyxl import Workbook

os.environ.setdefault("HERMES_TEST_MODE", "1")

from phase8.parsers import (  # noqa: E402
    count_raw_person_rows,
    parse_collab_transposed,
    parse_sheet,
    parse_standard_people_rows,
)
from phase8.quality import RejectionReason, build_report, unknown_rejection_reasons  # noqa: E402
from phase8.workbook import sheet_rows  # noqa: E402
from shared.exclusions import ExclusionLog  # noqa: E402


# --------------------------------------------------------------------------
# Synthetic fixtures
# --------------------------------------------------------------------------

def _rows_from(matrix):
    """Round-trip through a real worksheet so we exercise openpyxl typing."""
    wb = Workbook()
    ws = wb.active
    for row in matrix:
        ws.append(row)
    return sheet_rows(ws)


@pytest.fixture()
def standard_rows():
    """People-as-rows, 1–5 scale, with every rejection case represented."""
    return _rows_from(
        [
            ["Name", "Team", "Culture fit", "Kubernetes", "Cottage Health", "Customer service", "Backup"],
            ["Ada Lovelace", "AWS", 5, 4, 3, 5, 2],
            ["Grace Hopper", "AWS", 4, 5, 0, 4, ""],          # 0 -> not assessed; blank skipped
            ["Group Average", "AWS", 4.5, 4.5, 1.5, 4.5, 2],  # group row -> rejected
            ["Alan Turing", "AWS", 3, "n/a", 2, 3, 3.5],      # non-numeric + fractional
            ["Edsger Dijkstra", "AWS", 2, 9, 1, 2, 4],        # 9 is out of range for 1-5
            [None, "AWS", 1, 1, 1, 1, 1],                     # missing name
        ]
    )


@pytest.fixture()
def collab_rows():
    """Collab transposed: people across the header from column E (index 4)."""
    return _rows_from(
        [
            ["", "Application", "", "", "Ada Lovelace", "Grace Hopper", "Group Average"],
            ["", "Microsoft Teams", "", "", 4, 3, 3.5],
            ["", "Culture fit", "", "", 4, 4, 4],
            ["", "Zoom Admin", "", "", 1, 0, 0.5],
            ["", "Customer service", "", "", 4, 4, 4],
            ["", "Cottage Health", "", "", 2, 2, 2],
        ]
    )


# --------------------------------------------------------------------------
# People-as-rows shape
# --------------------------------------------------------------------------

def test_standard_sheet_accepts_only_real_people(standard_rows):
    log = ExclusionLog()
    assessments, _dropped = parse_standard_people_rows("AWS", standard_rows, log)
    people = {a.person_name for a in assessments}
    assert people == {"Ada Lovelace", "Grace Hopper", "Alan Turing", "Edsger Dijkstra"}
    assert "Group Average" not in people


def test_group_average_and_missing_name_are_rejected_with_reasons(standard_rows):
    log = ExclusionLog()
    _, dropped = parse_standard_people_rows("AWS", standard_rows, log)
    reasons = {d.reason for d in dropped}
    assert RejectionReason.GROUP_OR_SECTION_HEADER in reasons
    assert RejectionReason.MISSING_NAME in reasons


def test_every_rejection_uses_the_closed_vocabulary(standard_rows, collab_rows):
    log = ExclusionLog()
    _, dropped_a = parse_standard_people_rows("AWS", standard_rows, log)
    _, dropped_b = parse_collab_transposed("Collab", collab_rows, log)
    for d in list(dropped_a) + list(dropped_b):
        assert RejectionReason.is_valid(d.reason), f"unregistered rejection reason: {d.reason!r}"


def test_non_numeric_and_fractional_cells_are_rejected(standard_rows):
    log = ExclusionLog()
    _, dropped = parse_standard_people_rows("AWS", standard_rows, log)
    reasons = {d.reason for d in dropped}
    assert RejectionReason.NON_NUMERIC_CELL in reasons
    assert RejectionReason.FRACTIONAL_AGGREGATE in reasons


def test_out_of_range_value_is_rejected_not_silently_nulled(standard_rows):
    """Regression: 9 on a 1-5 sheet used to be stored with normalised_level=NULL."""
    log = ExclusionLog()
    assessments, dropped = parse_standard_people_rows("AWS", standard_rows, log)
    assert RejectionReason.OUT_OF_RANGE_VALUE in {d.reason for d in dropped}
    offending = [
        a for a in assessments if a.person_name == "Edsger Dijkstra" and a.raw_label == "Kubernetes"
    ]
    assert offending == [], "out-of-range value must not become an assessment"


def test_zero_becomes_not_assessed_never_level_one(standard_rows):
    log = ExclusionLog()
    assessments, _ = parse_standard_people_rows("AWS", standard_rows, log)
    zeros = [
        a
        for a in assessments
        if a.person_name == "Grace Hopper" and a.raw_label == "Cottage Health"
    ]
    assert len(zeros) == 1
    assert zeros[0].raw_value == 0.0
    assert zeros[0].normalised_level is None


def test_blank_cells_are_skipped_without_a_rejection(standard_rows):
    log = ExclusionLog()
    assessments, dropped = parse_standard_people_rows("AWS", standard_rows, log)
    assert not any(
        a.person_name == "Grace Hopper" and a.raw_label == "Backup" for a in assessments
    )
    # A blank cell is an absence of data, not a data-quality failure.
    assert not any("Backup" in d.detail and "Grace" in d.detail for d in dropped)


def test_soft_skill_and_culture_fit_columns_never_become_assessments(standard_rows):
    log = ExclusionLog()
    assessments, _ = parse_standard_people_rows("AWS", standard_rows, log)
    labels = {a.raw_label for a in assessments}
    assert "Customer service" not in labels
    assert "Culture fit" not in labels
    reasons = {e["reason"] for e in log.entries}
    assert "soft_skill_excluded" in reasons
    assert "culture_fit_forbidden_column" in reasons


def test_client_column_is_account_kind_not_skill(standard_rows):
    log = ExclusionLog()
    assessments, _ = parse_standard_people_rows("AWS", standard_rows, log)
    account = [a for a in assessments if a.raw_label == "Cottage Health"]
    assert account, "client column should still be captured as account context"
    assert all(a.kind == "account" for a in account)
    assert all(a.kind == "skill" for a in assessments if a.raw_label == "Kubernetes")


def test_standard_sheet_uses_five_point_scale(standard_rows):
    log = ExclusionLog()
    assessments, _ = parse_standard_people_rows("AWS", standard_rows, log)
    assert {a.source_scale for a in assessments} == {"five_point_undefined"}
    ada = [a for a in assessments if a.person_name == "Ada Lovelace" and a.raw_label == "Kubernetes"]
    assert ada[0].normalised_level == 4  # pass-through


# --------------------------------------------------------------------------
# Collab transposed shape
# --------------------------------------------------------------------------

def test_collab_reads_people_from_header_and_apps_from_column_b(collab_rows):
    log = ExclusionLog()
    assessments, _ = parse_collab_transposed("Collab", collab_rows, log)
    assert {a.person_name for a in assessments} == {"Ada Lovelace", "Grace Hopper"}
    assert "Microsoft Teams" in {a.raw_label for a in assessments}


def test_collab_four_point_scale_stretches_to_five(collab_rows):
    """1->1, 2->2, 3->4, 4->5 — see SCORING_SPECIFICATION.md §7."""
    log = ExclusionLog()
    assessments, _ = parse_collab_transposed("Collab", collab_rows, log)
    assert {a.source_scale for a in assessments} == {"collab_four_point"}
    teams = {
        a.person_name: a.normalised_level
        for a in assessments
        if a.raw_label == "Microsoft Teams"
    }
    assert teams["Ada Lovelace"] == 5   # raw 4 -> 5
    assert teams["Grace Hopper"] == 4   # raw 3 -> 4


def test_collab_zero_is_not_assessed(collab_rows):
    log = ExclusionLog()
    assessments, _ = parse_collab_transposed("Collab", collab_rows, log)
    zoom = {a.person_name: a for a in assessments if a.raw_label == "Zoom Admin"}
    assert zoom["Ada Lovelace"].normalised_level == 1
    assert zoom["Grace Hopper"].normalised_level is None  # raw 0.0


def test_collab_excludes_group_average_column(collab_rows):
    log = ExclusionLog()
    assessments, _ = parse_collab_transposed("Collab", collab_rows, log)
    assert "Group Average" not in {a.person_name for a in assessments}


def test_collab_does_not_emit_a_people_count_as_a_rejection(collab_rows):
    """Regression: the people-column count used to masquerade as a DroppedRow."""
    log = ExclusionLog()
    _, dropped = parse_collab_transposed("Collab", collab_rows, log)
    assert "people_columns" not in {d.reason for d in dropped}


def test_collab_soft_skill_and_client_rows_handled(collab_rows):
    log = ExclusionLog()
    assessments, _ = parse_collab_transposed("Collab", collab_rows, log)
    labels = {a.raw_label for a in assessments}
    assert "Customer service" not in labels
    assert "Culture fit" not in labels
    assert all(a.kind == "account" for a in assessments if a.raw_label == "Cottage Health")


# --------------------------------------------------------------------------
# Dispatch + malformed input
# --------------------------------------------------------------------------

def test_certificates_sheet_is_deferred_not_parsed():
    log = ExclusionLog()
    assessments, dropped = parse_sheet("Certificates", _rows_from([["Name"], ["Ada"]]), log)
    assert assessments == []
    assert [d.reason for d in dropped] == [RejectionReason.DEFERRED_TO_CERT_WORKSTREAM]


def test_parse_sheet_dispatches_collab_to_transposed_parser(collab_rows):
    log = ExclusionLog()
    assessments, _ = parse_sheet("Collab", collab_rows, log)
    assert {a.source_scale for a in assessments} == {"collab_four_point"}


def test_empty_sheet_yields_nothing_and_does_not_raise():
    log = ExclusionLog()
    assert parse_standard_people_rows("AWS", [], log) == ([], [])
    assert parse_collab_transposed("Collab", [], log) == ([], [])


def test_header_only_sheet_yields_no_assessments():
    log = ExclusionLog()
    rows = _rows_from([["Name", "Kubernetes"]])
    assessments, dropped = parse_standard_people_rows("AWS", rows, log)
    assert assessments == []
    assert dropped == []


def test_ragged_rows_shorter_than_header_do_not_raise():
    """Real sheets have short rows; indexing past the end must be tolerated."""
    log = ExclusionLog()
    rows = _rows_from([["Name", "Kubernetes", "Backup"], ["Ada Lovelace"]])
    assessments, _dropped = parse_standard_people_rows("AWS", rows, log)
    assert assessments == []


def test_count_raw_person_rows_matches_shape():
    collab = _rows_from([["", "Application", "", "", "Ada", "Grace"], ["", "Teams", "", "", 1, 2]])
    assert count_raw_person_rows("Collab", collab) == 2
    standard = _rows_from([["Name", "Kubernetes"], ["Ada", 3], ["Grace", 4]])
    assert count_raw_person_rows("AWS", standard) == 2


# --------------------------------------------------------------------------
# Data-quality report
# --------------------------------------------------------------------------

def test_quality_report_counts_and_classifies(standard_rows):
    log = ExclusionLog()
    assessments, dropped = parse_standard_people_rows("AWS", standard_rows, log)
    report = build_report(
        source="synthetic",
        per_sheet_inputs={
            "AWS": {
                "raw_person_rows": count_raw_person_rows("AWS", standard_rows),
                "people": [a.person_name for a in assessments],
                "accepted_people": [a.person_name for a in assessments],
                "assessments": assessments,
                "dropped": dropped,
                "labels_discovered": 5,
                "labels_excluded": 1,
                "labels_account": 1,
                "labels_pending": 3,
            }
        },
        expected_person_rows={"AWS": 4},
    )
    totals = report.totals()
    assert totals["people_accepted"] == 4
    assert totals["rows_processed"] == totals["assessments_accepted"] + totals["rows_rejected"]
    assert totals["rows_rejected"] > 0
    assert unknown_rejection_reasons(report) == []
    # Rating distribution separates "not assessed" from real levels.
    assert "not_assessed" in totals["rating_distribution"]


def test_quality_report_flags_person_row_delta(standard_rows):
    log = ExclusionLog()
    assessments, dropped = parse_standard_people_rows("AWS", standard_rows, log)
    report = build_report(
        source="synthetic",
        per_sheet_inputs={
            "AWS": {
                "raw_person_rows": 6,
                "accepted_people": [a.person_name for a in assessments],
                "assessments": assessments,
                "dropped": dropped,
            }
        },
        expected_person_rows={"AWS": 99},  # deliberately wrong
    )
    codes = {a["code"] for a in report.sheets["AWS"].anomalies}
    assert "person_row_count_delta" in codes


def test_quality_report_flags_all_labels_pending():
    report = build_report(
        source="synthetic",
        per_sheet_inputs={
            "Tools": {
                "labels_discovered": 12,
                "labels_pending": 12,
                "assessments": [],
                "dropped": [],
            }
        },
    )
    codes = {a["code"] for a in report.sheets["Tools"].anomalies}
    assert "all_labels_pending" in codes


def test_quality_report_contains_no_person_names(standard_rows, tmp_path):
    """The report must be safe to commit and show."""
    log = ExclusionLog()
    assessments, dropped = parse_standard_people_rows("AWS", standard_rows, log)
    report = build_report(
        source="synthetic",
        per_sheet_inputs={
            "AWS": {
                "accepted_people": [a.person_name for a in assessments],
                "assessments": assessments,
                "dropped": dropped,
            }
        },
    )
    path = report.write(tmp_path / "dq.json")
    blob = path.read_text(encoding="utf-8")
    for name in ("Ada Lovelace", "Grace Hopper", "Alan Turing", "Edsger Dijkstra"):
        assert name not in blob, f"data-quality report leaked a person name: {name}"


def test_rejection_vocabulary_is_documented():
    """Every code must carry a human-readable explanation."""
    assert set(RejectionReason.DESCRIPTIONS) == set(RejectionReason.ALL)
    assert all(v.strip() for v in RejectionReason.DESCRIPTIONS.values())
