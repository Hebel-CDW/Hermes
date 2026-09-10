"""Phase 8 assessment-field exclusion logging and filters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.models import (
    CultureFitForbiddenError,
    is_client_name_label,
    is_culture_fit_label,
    is_excluded_assessment_label,
)


def default_exclusions_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "reports" / "phase8_exclusions.json"


class ExclusionLog:
    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []

    def record(self, sheet: str, column: str, reason: str, label: Optional[str] = None) -> None:
        self.entries.append(
            {
                "sheet": sheet,
                "column": column,
                "reason": reason,
                "label": label or column,
            }
        )

    def write(self, path: Optional[Path] = None) -> Path:
        out = path or default_exclusions_path()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"exclusions": self.entries}, indent=2), encoding="utf-8")
        return out


def classify_assessment_column(label: str, sheet: str, log: ExclusionLog) -> str:
    """Return 'skill' | 'account' | 'excluded'. Raises on culture fit.

    'account' columns go to account_context (never scoring).
    'excluded' soft-skills are dropped and logged.
    """
    if is_culture_fit_label(label):
        raise CultureFitForbiddenError(f"culture fit column forbidden: sheet={sheet!r} column={label!r}")
    if is_client_name_label(label):
        log.record(sheet, label, "client_account_context", label)
        return "account"
    if is_excluded_assessment_label(label):
        log.record(sheet, label, "soft_skill_excluded", label)
        return "excluded"
    return "skill"
