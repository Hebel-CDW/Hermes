"""Curated market benchmarks (CSV/manual import only). No live feed exists; none is implied.

Salary, contractor cost and customer bill rate are separate ``basis`` values and are never merged.
Imports are atomic: any invalid row rejects the whole file with per-row errors.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from hoi.costing import dec
from hoi.errors import HoiValidation
from hoi.finance import norm
from shared.models import utc_now

BASES = ("salary", "contractor_cost", "bill_rate")
ENGAGEMENTS = ("permanent", "contractor", "vendor")
UNITS = ("month", "year", "hour")
REQUIRED = ("role", "geography", "seniority", "engagement_type", "basis", "currency", "unit",
            "p25", "p50", "p75", "sample_count", "source", "as_of")
MIN_SAMPLE = 5
MAX_ROWS = 5000


def parse_csv(text: str, declare_synthetic: bool) -> List[Dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    cols = [c.strip().lower() for c in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED if c not in cols]
    if missing:
        raise HoiValidation(f"CSV is missing required columns: {missing}")
    rows, errors = [], []
    for i, raw in enumerate(reader, start=2):
        if i - 1 > MAX_ROWS:
            raise HoiValidation(f"CSV exceeds {MAX_ROWS} rows")
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        try:
            rows.append(_row(r, declare_synthetic))
        except (ValueError, HoiValidation) as exc:
            errors.append(f"line {i}: {exc}")
    if errors:
        raise HoiValidation("; ".join(errors[:20]) + (f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""))
    if not rows:
        raise HoiValidation("CSV has no data rows")
    return rows


def _row(r: Dict[str, str], declare_synthetic: bool) -> Dict[str, Any]:
    for k in ("role", "geography", "seniority", "source"):
        if not r.get(k):
            raise ValueError(f"{k} is required")
    if r["basis"] not in BASES:
        raise ValueError(f"basis must be one of {list(BASES)}")
    if r["engagement_type"] not in ENGAGEMENTS:
        raise ValueError(f"engagement_type must be one of {list(ENGAGEMENTS)}")
    if (r["basis"] == "salary") != (r["engagement_type"] == "permanent"):
        raise ValueError("salary basis requires engagement_type=permanent; contractor_cost/bill_rate require contractor or vendor")
    if r["unit"] not in UNITS:
        raise ValueError(f"unit must be one of {list(UNITS)}")
    if not re.match(r"^[A-Z]{3}$", r["currency"]):
        raise ValueError("currency must be a 3-letter upper-case code")
    p = [dec(r[k], k) for k in ("p25", "p50", "p75")]
    if any(v < 0 for v in p) or not p[0] <= p[1] <= p[2]:
        raise ValueError("percentiles must satisfy 0 <= p25 <= p50 <= p75")
    try:
        n = int(r["sample_count"])
    except ValueError as exc:
        raise ValueError("sample_count must be an integer") from exc
    if n < 0:
        raise ValueError("sample_count must not be negative")
    try:
        as_of = date.fromisoformat(r["as_of"])
    except ValueError as exc:
        raise ValueError("as_of must be YYYY-MM-DD") from exc
    if as_of > date.today():
        raise ValueError("as_of is in the future")
    ttf: Optional[int] = None
    if r.get("time_to_fill_weeks"):
        ttf = int(r["time_to_fill_weeks"])
        if ttf < 0:
            raise ValueError("time_to_fill_weeks must not be negative")
    synthetic = declare_synthetic or r.get("synthetic", "").lower() in ("1", "true", "yes")
    return {**{k: r[k] for k in ("role", "geography", "seniority", "engagement_type", "basis", "currency", "unit", "source")},
            "p25": str(p[0]), "p50": str(p[1]), "p75": str(p[2]), "sample_count": n, "as_of": as_of.isoformat(),
            "time_to_fill_weeks": ttf, "is_synthetic": synthetic}


class MarketStore:
    def __init__(self, db: Any) -> None:
        self.db = db

    def import_rows(self, actor: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        batch = f"mb-{uuid.uuid4().hex[:10]}"
        with self.db.session() as conn:
            for r in rows:
                conn.execute(
                    "INSERT INTO market_benchmarks (benchmark_id, role, geography, seniority, engagement_type, basis, "
                    "currency, unit, p25, p50, p75, sample_count, source, as_of, time_to_fill_weeks, is_synthetic, "
                    "import_batch, imported_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"bm-{uuid.uuid4().hex[:12]}", r["role"], r["geography"], r["seniority"], r["engagement_type"],
                     r["basis"], r["currency"], r["unit"], r["p25"], r["p50"], r["p75"], r["sample_count"], r["source"],
                     r["as_of"], r["time_to_fill_weeks"], 1 if r["is_synthetic"] else 0, batch, actor,
                     utc_now().isoformat()),
                )
        return {"import_batch": batch, "rows": len(rows), "synthetic_rows": sum(1 for r in rows if r["is_synthetic"])}

    def query(self, role: Optional[str] = None, geography: Optional[str] = None,
              basis: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM market_benchmarks ORDER BY role, geography, basis, as_of DESC, benchmark_id").fetchall()
        out = []
        for r in rows:
            if role and norm(r["role"]) != norm(role):
                continue
            if geography and norm(r["geography"]) != norm(geography):
                continue
            if basis and r["basis"] != basis:
                continue
            d = {k: r[k] for k in r.keys() if k not in ("created_at",)}
            d["is_synthetic"] = bool(d["is_synthetic"])
            d["coverage"] = coverage(d)
            out.append(d)
        return out

    def best(self, role: str, geography: Optional[str], basis: str) -> Optional[Dict[str, Any]]:
        """Most recent matching row for role (+geography when given); None when absent (never invented)."""
        rows = self.query(role, geography, basis)
        return rows[0] if rows else None


def coverage(b: Dict[str, Any]) -> str:
    if b["is_synthetic"]:
        return "synthetic"
    if (b["sample_count"] or 0) < MIN_SAMPLE:
        return "weak"
    return "ok"


def monthly(amount: Decimal, unit: str, hours_per_month: Decimal) -> Decimal:
    if unit == "month":
        return amount
    if unit == "year":
        return amount / Decimal(12)
    return amount * hours_per_month
