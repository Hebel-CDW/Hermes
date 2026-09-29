"""Sheet-shape parsers for Skill_Matrix_2025 (dispatch table, not 22 copies)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase8.normalize import classify_scale, normalize_level
from phase8.quality import RejectionReason
from phase8.workbook import (
    META_COLUMNS,
    cell_str,
    detect_header_row,
    is_fractional_assessment,
    is_group_average_name,
    normalize_label,
    person_name_from_row,
)
from shared.exclusions import ExclusionLog, classify_assessment_column
from shared.models import is_culture_fit_label


@dataclass(frozen=True)
class ParsedAssessment:
    person_name: str
    raw_label: str
    raw_value: Optional[float]
    normalised_level: Optional[int]
    source_sheet: str
    source_scale: str
    kind: str  # skill | account


@dataclass(frozen=True)
class DroppedRow:
    sheet: str
    reason: str
    detail: str


def _baseline_id(sheet: str, person: str, label: str) -> str:
    material = f"{sheet}|{person.strip().lower()}|{label.strip().lower()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


#: Inclusive upper bound of raw values per scale. 0 is always legal — it means
#: "not assessed" and normalises to NULL (never level 0 or 1).
SCALE_MAX = {"collab_four_point": 4.0, "five_point_undefined": 5.0}


def _row_is_group_average(headers: Sequence[str], row: Sequence[Any]) -> bool:
    """True when any name-ish cell on the row reads 'Group Average'.

    `person_name_from_row` deliberately returns None for these rows, which meant they
    were rejected as `missing_name` — hiding genuine group-average rows behind a
    misleading code in the data-quality report. Detect them explicitly first.
    """
    mapping = {normalize_label(h): i for i, h in enumerate(headers) if h}
    for key in ("name", "coworker name", "first name", "first"):
        idx = mapping.get(key)
        if idx is None or idx >= len(row):
            continue
        if is_group_average_name(cell_str(row[idx])):
            return True
    return False


def _out_of_range(value: float, scale: str) -> bool:
    """True when a numeric value falls outside the sheet's declared rating scale.

    Previously such values were stored with ``normalised_level=NULL`` and **no
    rejection record**, so bad data was silently indistinguishable from
    "not assessed". Now it is rejected with a reason.
    """
    return value < 0.0 or value > SCALE_MAX.get(scale, 5.0)


def parse_standard_people_rows(
    sheet_name: str, rows: Sequence[Sequence[Any]], log: ExclusionLog
) -> Tuple[List[ParsedAssessment], List[DroppedRow]]:
    assessments: List[ParsedAssessment] = []
    dropped: List[DroppedRow] = []
    if not rows:
        return assessments, dropped
    header_idx = detect_header_row(rows)
    headers = [cell_str(c) for c in rows[header_idx]]
    scale = classify_scale(sheet_name)

    # Map skill/account columns
    col_kinds: Dict[int, Tuple[str, str]] = {}
    for i, h in enumerate(headers):
        if not h or normalize_label(h) in META_COLUMNS:
            continue
        if is_culture_fit_label(h):
            # Workbook contains culture-fit columns widely; strip with explicit log.
            # classify_assessment_column still raises for direct callers (guardrail test).
            log.record(sheet_name, h, "culture_fit_forbidden_column", h)
            continue
        kind = classify_assessment_column(h, sheet_name, log)
        if kind == "excluded":
            continue
        col_kinds[i] = (kind, h)

    for row in rows[header_idx + 1 :]:
        name = person_name_from_row(headers, row)
        if _row_is_group_average(headers, row):
            dropped.append(
                DroppedRow(sheet_name, RejectionReason.GROUP_OR_SECTION_HEADER, "Group Average")
            )
            continue
        if not name:
            dropped.append(DroppedRow(sheet_name, RejectionReason.MISSING_NAME, repr(row[:3])))
            continue
        if is_group_average_name(name) or normalize_label(name).startswith("ibm i"):
            dropped.append(
                DroppedRow(sheet_name, RejectionReason.GROUP_OR_SECTION_HEADER, name)
            )
            continue
        # Skip blank-ish designation-only section headers
        if name.lower() in {sheet_name.lower(), "name"}:
            dropped.append(DroppedRow(sheet_name, RejectionReason.SECTION_HEADER, name))
            continue
        for idx, (kind, label) in col_kinds.items():
            raw = row[idx] if idx < len(row) else None
            if raw is None or cell_str(raw) == "":
                continue
            if isinstance(raw, str) and not any(ch.isdigit() for ch in raw):
                dropped.append(
                    DroppedRow(sheet_name, RejectionReason.NON_NUMERIC_CELL, f"{name}/{label}")
                )
                continue
            if is_fractional_assessment(raw):
                dropped.append(
                    DroppedRow(
                        sheet_name, RejectionReason.FRACTIONAL_AGGREGATE, f"{name}/{label}={raw}"
                    )
                )
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                dropped.append(
                    DroppedRow(
                        sheet_name, RejectionReason.UNPARSEABLE_VALUE, f"{name}/{label}={raw}"
                    )
                )
                continue
            if _out_of_range(value, scale):
                dropped.append(
                    DroppedRow(
                        sheet_name,
                        RejectionReason.OUT_OF_RANGE_VALUE,
                        f"{name}/{label}={value} outside {scale}",
                    )
                )
                continue
            assessments.append(
                ParsedAssessment(
                    person_name=name,
                    raw_label=label,
                    raw_value=value,
                    normalised_level=normalize_level(value, scale),
                    source_sheet=sheet_name,
                    source_scale=scale,
                    kind=kind,
                )
            )
    return assessments, dropped


def parse_collab_transposed(
    sheet_name: str, rows: Sequence[Sequence[Any]], log: ExclusionLog
) -> Tuple[List[ParsedAssessment], List[DroppedRow]]:
    assessments: List[ParsedAssessment] = []
    dropped: List[DroppedRow] = []
    if not rows:
        return assessments, dropped
    scale = classify_scale(sheet_name)
    # Row 0: people names from column E (index 4) onward
    header = rows[0]
    people: Dict[int, str] = {}
    for i, cell in enumerate(header):
        if i < 4:
            continue
        name = cell_str(cell)
        if name and not is_group_average_name(name):
            people[i] = name
    for row in rows[1:]:
        app = cell_str(row[1] if len(row) > 1 else None)
        if not app or normalize_label(app) in {"application", "group"}:
            continue
        if is_culture_fit_label(app):
            log.record(sheet_name, app, "culture_fit_forbidden_column", app)
            continue
        kind = classify_assessment_column(app, sheet_name, log)
        if kind == "excluded":
            continue
        for col_idx, person in people.items():
            raw = row[col_idx] if col_idx < len(row) else None
            if raw is None or cell_str(raw) == "":
                continue
            if is_fractional_assessment(raw):
                dropped.append(
                    DroppedRow(sheet_name, RejectionReason.FRACTIONAL_AGGREGATE, f"{person}/{app}")
                )
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                dropped.append(
                    DroppedRow(sheet_name, RejectionReason.UNPARSEABLE_VALUE, f"{person}/{app}")
                )
                continue
            if _out_of_range(value, scale):
                dropped.append(
                    DroppedRow(
                        sheet_name,
                        RejectionReason.OUT_OF_RANGE_VALUE,
                        f"{person}/{app}={value} outside {scale}",
                    )
                )
                continue
            assessments.append(
                ParsedAssessment(
                    person_name=person,
                    raw_label=app,
                    raw_value=value,
                    normalised_level=normalize_level(value, scale),
                    source_sheet=sheet_name,
                    source_scale=scale,
                    kind=kind,
                )
            )
    # NOTE: the discovered-people count is a *metric*, not a rejection. It used to be
    # prepended here as a synthetic DroppedRow, which inflated the rejection count and
    # polluted phase8_dropped_rows.json with a non-reason. Counts now belong to the
    # data-quality report (phase8.quality), reachable via count_raw_person_rows().
    return assessments, dropped


PARSERS = {
    "Collab": parse_collab_transposed,
    # All other skill sheets share people-as-rows shape
}


def parse_sheet(
    sheet_name: str, rows: Sequence[Sequence[Any]], log: ExclusionLog
) -> Tuple[List[ParsedAssessment], List[DroppedRow]]:
    if sheet_name == "Certificates":
        return [], [
            DroppedRow(sheet_name, RejectionReason.DEFERRED_TO_CERT_WORKSTREAM, "not baseline")
        ]
    parser = PARSERS.get(sheet_name, parse_standard_people_rows)
    return parser(sheet_name, rows, log)


def count_raw_person_rows(sheet_name: str, rows: Sequence[Sequence[Any]]) -> int:
    """Approximate raw person-row count including Group Average (for reporting)."""
    if sheet_name == "Collab":
        if not rows:
            return 0
        return sum(1 for i, c in enumerate(rows[0]) if i >= 4 and cell_str(c))
    if sheet_name == "Certificates":
        # header at row index 1
        return max(0, len(rows) - 2)
    header_idx = detect_header_row(rows)
    count = 0
    headers = [cell_str(c) for c in rows[header_idx]] if rows else []
    for row in rows[header_idx + 1 :]:
        name = person_name_from_row(headers, row)
        if name:
            count += 1
    return count
