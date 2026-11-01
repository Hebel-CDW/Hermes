"""Deterministic scenario costing. Pure functions over Decimal; no I/O, no randomness, no clock.

Definitions (also in docs/HOI_ARCHITECTURE.md; Finance must certify before production):

* revenue            = sum(bill_rate_monthly * fte * months)            [customer bill rate, scenario currency]
* direct_labor       = sum(internal loaded_monthly_cost * fte * months)  [fully loaded internal cost]
* contractor_cost    = sum(external monthly_cost * fte * months)         [benchmark contractor_cost basis]
* other direct costs = recruiting/onboarding per external slot + training/fte + travel/fte-month
                       + tools/fte-month + transition (lump) + project_direct_costs (lump)
* contingency        = contingency_pct * (direct_labor + contractor + other direct costs)
* allocated_overhead = overhead_pct * direct_labor
* COGS (gross)       = direct + contingency (+ allocated_overhead only when overhead_treatment == "in_cogs")
* gross margin %     = (revenue - COGS) / revenue * 100
* contribution       = revenue - (direct + contingency)   — never includes allocated overhead
* delivery_cost      = direct + contingency + allocated_overhead  (the full cost-to-deliver)

Salary, contractor cost, loaded cost and bill rate are different bases and are labelled separately.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional

CALC_VERSION = "hoi-calc-1.0"
_CENT = Decimal("0.01")
_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


def dec(value: Any, field_name: str = "value") -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field_name} must be a number")
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if not d.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return d


def money(d: Decimal) -> str:
    return str(d.quantize(_CENT, rounding=ROUND_HALF_EVEN))


def pct(d: Decimal) -> str:
    return str(d.quantize(_CENT, rounding=ROUND_HALF_EVEN))


@dataclass(frozen=True)
class CostPolicy:
    policy_ref: str
    overhead_pct: Decimal = _ZERO
    overhead_treatment: str = "below_gross"  # or "in_cogs"
    contingency_pct: Decimal = _ZERO
    training_per_fte: Decimal = _ZERO
    travel_per_fte_month: Decimal = _ZERO
    tools_per_fte_month: Decimal = _ZERO
    recruiting_onboarding_per_external_slot: Decimal = _ZERO
    transition_total: Decimal = _ZERO
    standard_hours_per_month: Decimal = Decimal("160")
    utilization: Decimal = Decimal("1")
    internal_lead_weeks: Optional[int] = None
    fx_rates: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # "EUR->USD": {rate, as_of, source}

    @staticmethod
    def from_payload(policy_ref: str, p: Mapping[str, Any]) -> "CostPolicy":
        treatment = str(p.get("overhead_treatment", "below_gross"))
        if treatment not in ("in_cogs", "below_gross"):
            raise ValueError("overhead_treatment must be in_cogs or below_gross")
        util = dec(p.get("utilization", "1"), "utilization")
        if not _ZERO < util <= Decimal("1"):
            raise ValueError("utilization must be in (0, 1]")
        out = {}
        for k in ("overhead_pct", "contingency_pct"):
            v = dec(p.get(k, "0"), k)
            if v < 0 or v > _HUNDRED:
                raise ValueError(f"{k} must be between 0 and 100")
            out[k] = v
        for k in ("training_per_fte", "travel_per_fte_month", "tools_per_fte_month",
                  "recruiting_onboarding_per_external_slot", "transition_total"):
            v = dec(p.get(k, "0"), k)
            if v < 0:
                raise ValueError(f"{k} must not be negative")
            out[k] = v
        hours = dec(p.get("standard_hours_per_month", "160"), "standard_hours_per_month")
        if hours <= 0:
            raise ValueError("standard_hours_per_month must be positive")
        lead = p.get("internal_lead_weeks")
        return CostPolicy(
            policy_ref=policy_ref, overhead_treatment=treatment, utilization=util,
            standard_hours_per_month=hours,
            internal_lead_weeks=int(lead) if lead is not None else None,
            fx_rates=dict(p.get("fx_rates") or {}), **out,
        )


@dataclass(frozen=True)
class Line:
    requirement_id: str
    resource_type: str  # internal | external
    fte: Decimal
    monthly_cost: Optional[Decimal]  # scenario currency; None = unresolved
    bill_rate_monthly: Optional[Decimal]  # scenario currency; None = unresolved
    cost_source: str  # e.g. individual_loaded_cost | role_band | market_p50_contractor_cost | unresolved
    ref: str = ""


def convert(amount: Decimal, src: str, dst: str, policy: CostPolicy) -> Optional[Dict[str, Any]]:
    """Convert using only a Finance-supplied rate; no rate means unresolved (never a guess)."""
    if src == dst:
        return {"amount": amount, "rate": None}
    fx = policy.fx_rates.get(f"{src}->{dst}")
    if not fx:
        return None
    rate = dec(fx["rate"], "fx rate")
    if rate <= 0:
        return None
    return {"amount": amount * rate, "rate": str(rate), "as_of": fx.get("as_of"), "source": fx.get("source")}


def calculate(lines: List[Line], months: int, currency: str, policy: CostPolicy,
              project_direct_costs: Decimal = _ZERO) -> Dict[str, Any]:
    """Return the full (finance-view) calculation. Unresolved inputs yield calculable=False and no figures."""
    m = Decimal(months)
    total_fte = sum((ln.fte for ln in lines), _ZERO)
    unresolved: List[str] = []
    for ln in lines:
        if ln.monthly_cost is None:
            unresolved.append(f"cost_unresolved:{ln.requirement_id}:{ln.resource_type}")
        if ln.bill_rate_monthly is None:
            unresolved.append(f"bill_rate_unresolved:{ln.requirement_id}")
    base: Dict[str, Any] = {
        "calc_version": CALC_VERSION, "currency": currency, "months": months,
        "total_fte": str(total_fte), "policy_ref": policy.policy_ref,
        "productive_hours": str((total_fte * policy.standard_hours_per_month * m * policy.utilization).quantize(_CENT)),
        "unresolved": sorted(set(unresolved)),
    }
    if not lines:
        base["unresolved"] = ["no_assignments"]
    if base["unresolved"]:
        return {**base, "calculable": False}

    internal = sum((ln.monthly_cost * ln.fte * m for ln in lines if ln.resource_type == "internal"), _ZERO)
    external = sum((ln.monthly_cost * ln.fte * m for ln in lines if ln.resource_type == "external"), _ZERO)
    ext_slots = sum(1 for ln in lines if ln.resource_type == "external")
    revenue = sum((ln.bill_rate_monthly * ln.fte * m for ln in lines), _ZERO)
    recruiting = policy.recruiting_onboarding_per_external_slot * ext_slots
    training = policy.training_per_fte * total_fte
    travel = policy.travel_per_fte_month * total_fte * m
    tools = policy.tools_per_fte_month * total_fte * m
    transition = policy.transition_total
    direct = internal + external + recruiting + training + travel + tools + transition + project_direct_costs
    contingency = direct * policy.contingency_pct / _HUNDRED
    overhead = internal * policy.overhead_pct / _HUNDRED
    cogs = direct + contingency + (overhead if policy.overhead_treatment == "in_cogs" else _ZERO)
    profit = revenue - cogs
    contribution = revenue - (direct + contingency)
    gm = (profit / revenue * _HUNDRED) if revenue else None
    cm = (contribution / revenue * _HUNDRED) if revenue else None
    return {
        **base, "calculable": True, "overhead_treatment": policy.overhead_treatment,
        "revenue": money(revenue), "delivery_cost": money(direct + contingency + overhead), "cogs": money(cogs),
        "gross_profit": money(profit), "gross_margin_pct": pct(gm) if gm is not None else None,
        "contribution": money(contribution), "contribution_margin_pct": pct(cm) if cm is not None else None,
        "breakdown": {
            "direct_labor_internal": money(internal), "contractor_cost_external": money(external),
            "recruiting_onboarding": money(recruiting), "training": money(training), "travel": money(travel),
            "tools": money(tools), "transition": money(transition), "project_direct_costs": money(project_direct_costs),
            "contingency": money(contingency), "allocated_overhead": money(overhead),
        },
    }


def margin_band(gross_margin_pct: Optional[str]) -> str:
    """Coarse band shown to roles that may not see cost figures."""
    if gross_margin_pct is None:
        return "unknown"
    v = Decimal(gross_margin_pct)
    if v < 0:
        return "negative"
    for upper, label in ((10, "<10%"), (20, "10-20%"), (30, "20-30%"), (40, "30-40%")):
        if v < upper:
            return label
    return ">=40%"


def input_hash(payload: Mapping[str, Any]) -> str:
    """Stable hash of everything that determines a result (inputs + versions, no secrets)."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
