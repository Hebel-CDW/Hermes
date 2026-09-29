"""Phase 8 data-quality reporting with machine-readable rejection reasons.

Every row the workbook parser refuses must carry a **code from `RejectionReason`**,
not a free-text string. That makes rejections countable, assertable in tests, and
reviewable by a human who did not write the parser.

The report deliberately contains **no personal data**: only counts, sheet names,
label counts, and rating distributions. It is safe to commit and to show.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


class RejectionReason:
    """Closed vocabulary of machine-readable rejection codes.

    Adding a code is a deliberate act: `ALL` is asserted against the codes actually
    emitted by the parsers, so an unregistered reason fails the test suite.
    """

    MISSING_NAME = "missing_name"
    GROUP_OR_SECTION_HEADER = "group_or_section_header"
    SECTION_HEADER = "section_header"
    NON_NUMERIC_CELL = "non_numeric_cell"
    FRACTIONAL_AGGREGATE = "fractional_average"
    UNPARSEABLE_VALUE = "unparseable_value"
    OUT_OF_RANGE_VALUE = "out_of_range_value"
    DEFERRED_TO_CERT_WORKSTREAM = "deferred_to_cert_workstream"

    ALL = frozenset(
        {
            MISSING_NAME,
            GROUP_OR_SECTION_HEADER,
            SECTION_HEADER,
            NON_NUMERIC_CELL,
            FRACTIONAL_AGGREGATE,
            UNPARSEABLE_VALUE,
            OUT_OF_RANGE_VALUE,
            DEFERRED_TO_CERT_WORKSTREAM,
        }
    )

    #: Human-facing explanation per code — surfaced directly in the report so a
    #: reviewer never has to open the parser to understand a number.
    DESCRIPTIONS = {
        MISSING_NAME: "Row had no resolvable person name in any name column.",
        GROUP_OR_SECTION_HEADER: "Row is a 'Group Average' or section banner, not a person.",
        SECTION_HEADER: "Row repeats the sheet name or a header label instead of a person.",
        NON_NUMERIC_CELL: "Assessment cell contained text with no digits.",
        FRACTIONAL_AGGREGATE: "Value is fractional — an average, not an individual assessment.",
        UNPARSEABLE_VALUE: "Value could not be coerced to a number.",
        OUT_OF_RANGE_VALUE: "Numeric value fell outside the sheet's declared rating scale.",
        DEFERRED_TO_CERT_WORKSTREAM: "Certificates sheet is handled by the certificate workstream.",
    }

    @classmethod
    def is_valid(cls, reason: str) -> bool:
        return reason in cls.ALL


@dataclass
class SheetQuality:
    """Per-sheet counters. `expected_person_rows` comes from the 2025 brief."""

    sheet: str
    raw_person_rows: int = 0
    people_discovered: int = 0
    people_accepted: int = 0
    rows_processed: int = 0
    rows_rejected: int = 0
    assessments_accepted: int = 0
    labels_discovered: int = 0
    labels_excluded: int = 0
    labels_account: int = 0
    labels_pending: int = 0
    expected_person_rows: Optional[int] = None
    rejections_by_reason: Dict[str, int] = field(default_factory=dict)
    rating_distribution: Dict[str, int] = field(default_factory=dict)
    anomalies: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def person_row_delta(self) -> Optional[int]:
        if self.expected_person_rows is None:
            return None
        return self.people_accepted - self.expected_person_rows


@dataclass
class DataQualityReport:
    """Aggregate workbook ingestion quality."""

    source: str = ""
    sheets: Dict[str, SheetQuality] = field(default_factory=dict)

    def sheet(self, name: str, expected: Optional[int] = None) -> SheetQuality:
        if name not in self.sheets:
            self.sheets[name] = SheetQuality(sheet=name, expected_person_rows=expected)
        return self.sheets[name]

    # -- anomaly detection -------------------------------------------------

    def detect_anomalies(self, row_delta_tolerance: int = 0) -> None:
        """Flag sheet-level conditions a human should look at.

        These are *observations*, not failures — the workbook is what it is. The
        point is that a delta is reported rather than silently absorbed.
        """
        for sq in self.sheets.values():
            sq.anomalies = []
            delta = sq.person_row_delta
            if delta is not None and abs(delta) > row_delta_tolerance:
                sq.anomalies.append(
                    {
                        "code": "person_row_count_delta",
                        "expected": sq.expected_person_rows,
                        "accepted": sq.people_accepted,
                        "delta": delta,
                        "detail": (
                            "Accepted person count differs from the 2025 brief after "
                            "Group Average / section-header filtering."
                        ),
                    }
                )
            if sq.rows_processed and sq.rows_rejected / sq.rows_processed > 0.5:
                sq.anomalies.append(
                    {
                        "code": "high_rejection_rate",
                        "rejected": sq.rows_rejected,
                        "processed": sq.rows_processed,
                        "rate": round(sq.rows_rejected / sq.rows_processed, 4),
                        "detail": "More than half of parsed cells were rejected.",
                    }
                )
            skill_labels = sq.labels_discovered - sq.labels_excluded - sq.labels_account
            if skill_labels > 0 and sq.labels_pending >= skill_labels:
                sq.anomalies.append(
                    {
                        "code": "all_labels_pending",
                        "labels": sq.labels_discovered,
                        "detail": (
                            "No label on this sheet mapped to a canonical skill; all "
                            "await human taxonomy approval."
                        ),
                    }
                )
            if sq.people_accepted == 0 and sq.raw_person_rows > 0:
                sq.anomalies.append(
                    {
                        "code": "no_people_accepted",
                        "raw_person_rows": sq.raw_person_rows,
                        "detail": "Sheet produced candidate rows but no accepted people.",
                    }
                )

    # -- serialisation -----------------------------------------------------

    def totals(self) -> Dict[str, Any]:
        agg: Counter = Counter()
        reasons: Counter = Counter()
        ratings: Counter = Counter()
        for sq in self.sheets.values():
            for key in (
                "raw_person_rows",
                "people_discovered",
                "people_accepted",
                "rows_processed",
                "rows_rejected",
                "assessments_accepted",
                "labels_discovered",
                "labels_excluded",
                "labels_account",
                "labels_pending",
            ):
                agg[key] += getattr(sq, key)
            reasons.update(sq.rejections_by_reason)
            ratings.update(sq.rating_distribution)
        out = dict(agg)
        out["rejections_by_reason"] = dict(sorted(reasons.items()))
        out["rating_distribution"] = dict(sorted(ratings.items()))
        out["sheets"] = len(self.sheets)
        out["anomaly_count"] = sum(len(s.anomalies) for s in self.sheets.values())
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "rejection_reason_vocabulary": dict(sorted(RejectionReason.DESCRIPTIONS.items())),
            "totals": self.totals(),
            "per_sheet": {
                name: {
                    "raw_person_rows": sq.raw_person_rows,
                    "people_discovered": sq.people_discovered,
                    "people_accepted": sq.people_accepted,
                    "expected_person_rows": sq.expected_person_rows,
                    "person_row_delta": sq.person_row_delta,
                    "rows_processed": sq.rows_processed,
                    "rows_rejected": sq.rows_rejected,
                    "assessments_accepted": sq.assessments_accepted,
                    "labels_discovered": sq.labels_discovered,
                    "labels_excluded": sq.labels_excluded,
                    "labels_account": sq.labels_account,
                    "labels_pending": sq.labels_pending,
                    "rejections_by_reason": dict(sorted(sq.rejections_by_reason.items())),
                    "rating_distribution": dict(sorted(sq.rating_distribution.items())),
                    "anomalies": sq.anomalies,
                }
                for name, sq in sorted(self.sheets.items())
            },
        }

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


def build_report(
    source: str,
    per_sheet_inputs: Dict[str, Dict[str, Any]],
    expected_person_rows: Optional[Dict[str, int]] = None,
) -> DataQualityReport:
    """Assemble a report from per-sheet parse results.

    ``per_sheet_inputs[sheet]`` accepts:
        raw_person_rows, people (iterable of names), accepted_people (iterable),
        assessments (iterable of ParsedAssessment-likes), dropped (iterable of
        DroppedRow-likes), labels_discovered/excluded/account/pending (ints).

    Person names are consumed only to *count* distinct people; they are never
    written into the report.
    """
    expected = expected_person_rows or {}
    report = DataQualityReport(source=source)
    for sheet_name, data in per_sheet_inputs.items():
        sq = report.sheet(sheet_name, expected.get(sheet_name))
        sq.raw_person_rows = int(data.get("raw_person_rows", 0))
        if "people_discovered" in data:
            sq.people_discovered = int(data["people_discovered"])
        else:
            sq.people_discovered = len(set(data.get("people", ()) or ()))
        sq.people_accepted = len(set(data.get("accepted_people", ()) or ()))
        sq.labels_discovered = int(data.get("labels_discovered", 0))
        sq.labels_excluded = int(data.get("labels_excluded", 0))
        sq.labels_account = int(data.get("labels_account", 0))
        sq.labels_pending = int(data.get("labels_pending", 0))

        assessments = list(data.get("assessments", ()) or ())
        sq.assessments_accepted = len(assessments)
        ratings: Counter = Counter()
        for a in assessments:
            level = getattr(a, "normalised_level", None)
            ratings["not_assessed" if level is None else f"level_{int(level)}"] += 1
        sq.rating_distribution = dict(ratings)

        reasons: Counter = Counter()
        for d in data.get("dropped", ()) or ():
            reason = getattr(d, "reason", None) or "unknown"
            reasons[reason] += 1
        sq.rejections_by_reason = dict(reasons)
        sq.rows_rejected = sum(reasons.values())
        sq.rows_processed = sq.assessments_accepted + sq.rows_rejected

    report.detect_anomalies()
    return report


def unknown_rejection_reasons(report: DataQualityReport) -> List[str]:
    """Return any rejection codes outside the closed vocabulary."""
    seen: set = set()
    for sq in report.sheets.values():
        seen |= set(sq.rejections_by_reason)
    return sorted(r for r in seen if not RejectionReason.is_valid(r))
