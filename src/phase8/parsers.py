"""Sheet-shape parsers for Skill_Matrix_2025 (dispatch table, not 22 copies)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from phase8.normalize import classify_scale, normalize_level
from phase8.workbook import (
    META_COLUMNS,
    cell_str,
    detect_header_row,
    is_fractional_assessment,
    is_group_average_name,
    normalize_label,
    person_name_from_row,
    sheet_rows,
)
from shared.exclusions import ExclusionLog, classify_assessment_column
from shared.models import CultureFitForbiddenError, is_culture_fit_label


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
        if not name:
            dropped.append(DroppedRow(sheet_name, "missing_name", repr(row[:3])))
            continue
        if is_group_average_name(name) or normalize_label(name).startswith("ibm i"):
            dropped.append(DroppedRow(sheet_name, "group_or_section_header", name))
            continue
        # Skip blank-ish designation-only section headers
        if name.lower() in {sheet_name.lower(), "name"}:
            dropped.append(DroppedRow(sheet_name, "section_header", name))
            continue
        for idx, (kind, label) in col_kinds.items():
            raw = row[idx] if idx < len(row) else None
            if raw is None or cell_str(raw) == "":
                continue
            if isinstance(raw, str) and not any(ch.isdigit() for ch in raw):
                dropped.append(DroppedRow(sheet_name, "non_numeric_cell", f"{name}/{label}"))
                continue
            if is_fractional_assessment(raw):
                dropped.append(DroppedRow(sheet_name, "fractional_average", f"{name}/{label}={raw}"))
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                dropped.append(DroppedRow(sheet_name, "unparseable_value", f"{name}/{label}={raw}"))
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
                dropped.append(DroppedRow(sheet_name, "fractional_average", f"{person}/{app}"))
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                dropped.append(DroppedRow(sheet_name, "unparseable_value", f"{person}/{app}"))
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
    return assessments, [DroppedRow(sheet_name, "people_columns", str(len(people)))] + dropped


PARSERS = {
    "Collab": parse_collab_transposed,
    # All other skill sheets share people-as-rows shape
}


def parse_sheet(
    sheet_name: str, rows: Sequence[Sequence[Any]], log: ExclusionLog
) -> Tuple[List[ParsedAssessment], List[DroppedRow]]:
    if sheet_name == "Certificates":
        return [], [DroppedRow(sheet_name, "deferred_to_cert_workstream", "not baseline")]
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
