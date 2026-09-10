"""Shared Skill Matrix 2025 workbook helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from openpyxl import load_workbook

from shared.exclusions import ExclusionLog, classify_assessment_column
from shared.models import CultureFitForbiddenError, is_client_name_label, is_excluded_assessment_label

DEFAULT_SOURCE = Path("data/source/Skill_Matrix_2025.xlsx")

META_COLUMNS = frozenset(
    {
        "name",
        "first",
        "first name",
        "last name",
        "coworker name",
        "designation",
        "team",
        "manager",
        "soft-skills",
        "soft skills",
        "group",
        "application",
    }
)

GROUP_AVERAGE_RE = re.compile(r"^\s*group\s+average\s*$", re.I)


def open_workbook(path: Optional[Path] = None):
    return load_workbook(str(path or DEFAULT_SOURCE), data_only=True, read_only=True)


def cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip().replace("\xa0", " ").strip()
    return str(value).strip()


def is_group_average_name(name: str) -> bool:
    return bool(GROUP_AVERAGE_RE.match(name or ""))


def is_fractional_assessment(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    if f != f:  # NaN
        return True
    return abs(f - round(f)) > 1e-9


def normalize_label(label: str) -> str:
    s = cell_str(label).lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9+.#/ -]", "", s)
    return s.strip()


def slug_skill_id(label: str) -> str:
    s = normalize_label(label)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return (s or "unknown")[:80]


def detect_header_row(rows: Sequence[Sequence[Any]], max_scan: int = 5) -> int:
    """Return index of header row for people-as-rows sheets."""
    name_tokens = {"name", "first name", "coworker name", "first"}
    for idx, row in enumerate(rows[:max_scan]):
        cells = [normalize_label(cell_str(c)) for c in row if cell_str(c)]
        if any(c in name_tokens for c in cells):
            return idx
    return 0


def person_name_from_row(headers: Sequence[str], row: Sequence[Any]) -> Optional[str]:
    mapping = {normalize_label(h): i for i, h in enumerate(headers) if h}
    # Prefer full name columns
    for key in ("name", "coworker name"):
        if key in mapping:
            val = cell_str(row[mapping[key]] if mapping[key] < len(row) else None)
            if val and not is_group_average_name(val):
                return val
    if "first name" in mapping and "last name" in mapping:
        first = cell_str(row[mapping["first name"]] if mapping["first name"] < len(row) else None)
        last = cell_str(row[mapping["last name"]] if mapping["last name"] < len(row) else None)
        name = f"{first} {last}".strip()
        return name or None
    if "first" in mapping and "name" in mapping:
        # Some sheets use First + Name
        first = cell_str(row[mapping["first"]] if mapping["first"] < len(row) else None)
        last = cell_str(row[mapping["name"]] if mapping["name"] < len(row) else None)
        if first or last:
            return f"{first} {last}".strip()
    return None


def sheet_rows(ws) -> List[Tuple[Any, ...]]:
    return [tuple(r) for r in ws.iter_rows(values_only=True)]


def classify_label_for_extract(label: str) -> str:
    """Return skill | account | excluded | culture_fit for clustering (no raise)."""
    low = label.strip().lower()
    if low == "culture fit":
        return "culture_fit"
    if is_client_name_label(label):
        return "account"
    if is_excluded_assessment_label(label):
        return "excluded"
    return "skill"
