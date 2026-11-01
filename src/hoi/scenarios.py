"""Scenario construction (internal / external / hybrid), role-redacted views, approvals and export.

Qualification and operational constraints come first: only candidates whose eligibility is ``eligible``
can be placed in an internal slot, in fitness-rank order. Cost never reorders candidates. Nothing here
assigns anyone: scenarios are drafts until Delivery, Finance (and HR where individual pay was used)
approve; approval records a decision, it does not write to any HR/allocation system.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Sequence

from hoi import costing
from hoi.costing import CALC_VERSION, CostPolicy, Line, dec
from hoi.crypto import decrypt_text, encrypt_text
from hoi.errors import HoiConflict, HoiValidation, OpportunityNotFound
from hoi.finance import norm
from hoi.market import monthly
from hoi.service import HoiService, _id, _json, need_roles
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN, FINANCE, HR, MANAGER, SALES
from shared.errors import AuthorizationError
from shared.models import utc_now

def _seal(value: Optional[str]) -> Optional[str]:
    """Scenario results hold per-person loaded cost and cost totals; they are encrypted at rest with the finance key."""
    return None if value is None else encrypt_text("finance", value)


def _open(blob: str) -> Dict[str, Any]:
    return json.loads(decrypt_text("finance", blob))


APPROVER_ROLE = {"delivery": MANAGER, "finance": FINANCE, "hr": HR}
PERCENTILES = ("p25", "p50", "p75")


class Scenarios:
    def __init__(self, hoi: HoiService) -> None:
        self.h = hoi
        self.db = hoi.db

    # =================================================================== loading helpers
    def _policy(self, name: str, version: Optional[int]) -> tuple:
        row = self.h.vault.get_parameter("policy", name, version)
        if not row:
            raise HoiValidation(f"cost policy '{name}' not found")
        return CostPolicy.from_payload(f"{name}@v{row['version']}", row["payload"]), row

    def _rate_card(self, name: str, version: Optional[int]) -> Mapping[str, Any]:
        row = self.h.vault.get_parameter("rate_card", name, version)
        if not row:
            raise HoiValidation(f"rate card '{name}' not found")
        return row

    def _latest_run(self, opp_id: str, vid: str) -> Optional[str]:
        with self.db.session() as conn:
            r = conn.execute("SELECT match_run_id FROM candidate_shortlists WHERE opportunity_id=? AND version_id=? "
                             "ORDER BY created_at DESC LIMIT 1", (opp_id, vid)).fetchone()
        return r["match_run_id"] if r else None

    def _pool(self, run_id: Optional[str]) -> Dict[str, List[Dict[str, Any]]]:
        """requirement_id -> candidates (rank order) with available_fte, from the stored match run."""
        if not run_id:
            return {}
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM candidate_shortlists WHERE match_run_id=? ORDER BY requirement_id, rank", (run_id,)).fetchall()
            caps = {r["coded_identity"]: r["available_fte"] for r in conn.execute(
                "SELECT coded_identity, available_fte FROM capacity_snapshots WHERE match_run_id=?", (run_id,)).fetchall()}
        pool: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            pool.setdefault(r["requirement_id"], []).append({"coded_identity": r["coded_identity"], "rank": r["rank"],
                                                              "eligibility": r["eligibility"], "available_fte": caps.get(r["coded_identity"])})
        return pool

    # =================================================================== optimizer (drafts only)
    def compare(self, p: AuthPrincipal, opp_id: str, body: Mapping[str, Any]) -> Dict[str, Any]:
        need_roles(p, MANAGER, FINANCE)
        opp = self.h.opportunity(p, opp_id)
        ver = self.h.approved_version(opp_id, body.get("requirement_version_id"))
        vid = ver["version_id"]
        roles = self.h._roles(vid)
        run = self._latest_run(opp_id, vid)
        pool = self._pool(run)
        used: Dict[str, float] = {}
        internal, hybrid_int, notes = [], [], []
        # Greedy, deterministic: requirements in order, candidates in fitness order, eligibility first.
        for r in roles:
            need, fte = int(r["headcount"]), float(r["fte"])
            picked = []
            for c in pool.get(r["requirement_id"], []):
                if len(picked) >= need:
                    break
                avail = c["available_fte"]
                if c["eligibility"] != "eligible" or avail is None:
                    continue
                if used.get(c["coded_identity"], 0.0) + fte > avail + 1e-9:
                    continue
                used[c["coded_identity"]] = used.get(c["coded_identity"], 0.0) + fte
                picked.append({"requirement_id": r["requirement_id"], "resource_type": "internal",
                               "coded_identity": c["coded_identity"], "fte": str(r["fte"])})
            internal += picked
            gap = need - len(picked)
            hybrid_int += picked + [{"requirement_id": r["requirement_id"], "resource_type": "external", "fte": str(r["fte"])}
                                    for _ in range(gap)]
        external = [{"requirement_id": r["requirement_id"], "resource_type": "external", "fte": str(r["fte"])}
                    for r in roles for _ in range(int(r["headcount"]))]
        total_heads = sum(int(r["headcount"]) for r in roles)
        n_int = len(internal)
        specs = [("internal", internal), ("external", external)]
        if 0 < n_int < total_heads:
            specs.append(("hybrid", hybrid_int))
        else:
            notes.append("hybrid_not_applicable: internal staffing " + ("fills every position" if n_int else "fills no position")
                         + ", so a hybrid would duplicate another scenario")
        if not run:
            notes.append("internal_match_not_run: run internal matching first; the internal scenario will show unfilled positions")
        created = []
        for kind, assignments in specs:
            created.append(self.create(p, opp_id, {**body, "requirement_version_id": vid, "kind": kind, "assignments": assignments},
                                       auto_generated=True))
        self.h.audit(opp_id, "scenarios_compared", p.sub, vid, detail={"scenario_ids": [c["scenario_id"] for c in created]})
        return {"scenarios": created, "notes": notes + ["No employee is assigned. Scenarios are drafts for human approval; "
                                                        "internal slots follow fitness rank among eligible candidates only."]}

    # =================================================================== create + calculate
    def create(self, p: AuthPrincipal, opp_id: str, body: Mapping[str, Any], auto_generated: bool = False) -> Dict[str, Any]:
        need_roles(p, MANAGER, FINANCE)
        opp = self.h.opportunity(p, opp_id)
        ver = self.h.approved_version(opp_id, body.get("requirement_version_id"))
        vid = ver["version_id"]
        roles = {r["requirement_id"]: r for r in self.h._roles(vid)}
        currency = str(body.get("currency") or opp["currency"]).upper()
        months = body.get("months") or opp["duration_months"]
        if not isinstance(months, int) or isinstance(months, bool) or not 1 <= months <= 120:
            raise HoiValidation("months must be an integer between 1 and 120")
        if body.get("bill_rate_basis", "per_month") != "per_month":
            raise HoiValidation("only bill_rate_basis=per_month is supported")
        policy_name, rc_name = body.get("cost_policy_id"), body.get("rate_card_id")
        if not policy_name or not rc_name:
            raise HoiValidation("cost_policy_id and rate_card_id are required (Finance-approved inputs)")
        policy, prow = self._policy(policy_name, body.get("cost_policy_version"))
        rcard = self._rate_card(rc_name, body.get("rate_card_version"))
        as_of = body.get("cost_as_of") or opp["start_date"] or date.today().isoformat()
        try:
            date.fromisoformat(as_of)
        except ValueError as exc:
            raise HoiValidation("cost_as_of must be YYYY-MM-DD") from exc
        try:
            direct_extra = dec(body.get("project_direct_costs", "0"), "project_direct_costs")
        except ValueError as exc:
            raise HoiValidation(str(exc)) from exc
        if direct_extra < 0:
            raise HoiValidation("project_direct_costs must not be negative")

        raw = list(body.get("assignments") or [])
        if not raw:
            raise HoiValidation("assignments are required")
        run = self._latest_run(opp_id, vid)
        pool = self._pool(run)
        per_req: Dict[str, int] = {}
        used: Dict[str, Decimal] = {}
        lines: List[Line] = []
        meta: List[Dict[str, Any]] = []
        flags: List[str] = []
        unresolved: List[str] = []
        market_refs: List[str] = []
        fx_used: List[Dict[str, Any]] = []
        ttf: List[Optional[int]] = []
        skipped = False
        uses_individual = False
        cost_refs: List[str] = []
        rc_pay = rcard["payload"]
        rates = {norm(k): v for k, v in rc_pay["rates"].items()}
        self.h.vault.log_access(p.sub, "scenario_costing", opp_id)

        for a in raw:
            rid = a.get("requirement_id")
            if rid not in roles:
                raise HoiValidation(f"requirement_id '{rid}' is not in the approved requirement version")
            role = roles[rid]
            try:
                fte = dec(a.get("fte"), "fte")
            except ValueError as exc:
                raise HoiValidation(str(exc)) from exc
            if not Decimal("0") < fte <= Decimal("1"):
                raise HoiValidation("fte per assignment must be in (0, 1]")
            per_req[rid] = per_req.get(rid, 0) + 1
            if per_req[rid] > int(role["headcount"]):
                raise HoiValidation(f"more assignments than approved headcount for '{role['role_name']}'")
            rtype = a.get("resource_type")
            coded, rank, mcost, csrc, cref = None, None, None, "unresolved", ""
            if rtype == "internal":
                coded = a.get("coded_identity")
                cand = next((c for c in pool.get(rid, []) if c["coded_identity"] == coded), None)
                if cand is None or cand["eligibility"] != "eligible":
                    raise HoiValidation("candidate_not_eligible: only eligible shortlisted candidates can be placed in an internal slot")
                used[coded] = used.get(coded, Decimal("0")) + fte
                if cand["available_fte"] is None or used[coded] > Decimal(str(cand["available_fte"])) + Decimal("0.000001"):
                    raise HoiValidation("candidate_over_capacity: requested FTE exceeds the candidate's available capacity")
                rank = cand["rank"]
                if any(o["eligibility"] == "eligible" and o["rank"] < rank and o["coded_identity"] not in
                       {x.get("coded_identity") for x in raw if x.get("requirement_id") == rid} for o in pool.get(rid, [])):
                    skipped = True
                res = self.h.vault.resolve(coded, role["role_name"], as_of)
                if res is None:
                    unresolved.append(f"cost_unavailable:{rid}:internal")
                else:
                    conv = costing.convert(res["amount"], res["currency"], currency, policy)
                    if conv is None:
                        unresolved.append(f"fx_rate_missing:{res['currency']}->{currency}")
                    else:
                        mcost, cref = conv["amount"], res["cost_ref"]
                        csrc = "individual_loaded_cost" if res["scope"] == "individual" else "role_band_loaded_cost"
                        uses_individual = uses_individual or res["scope"] == "individual"
                        cost_refs.append(cref)
                        if conv.get("rate"):
                            fx_used.append({"pair": f"{res['currency']}->{currency}", "rate": conv["rate"], "as_of": conv.get("as_of"), "source": conv.get("source")})
            elif rtype == "external":
                pct = a.get("percentile") or "p50"
                if pct not in PERCENTILES:
                    raise HoiValidation(f"percentile must be one of {list(PERCENTILES)}")
                geo = role.get("location") or opp.get("geography")
                bm = self.h.market.best(role["role_name"], geo, "contractor_cost")
                if bm is None:
                    unresolved.append(f"market_benchmark_missing:{rid}")
                else:
                    market_refs.append(bm["benchmark_id"])
                    ttf.append(bm["time_to_fill_weeks"])
                    if bm["coverage"] in ("synthetic", "weak"):
                        flags.append(f"benchmark_{bm['coverage']}")
                    base = monthly(Decimal(bm[pct]), bm["unit"], policy.standard_hours_per_month)
                    conv = costing.convert(base, bm["currency"], currency, policy)
                    if conv is None:
                        unresolved.append(f"fx_rate_missing:{bm['currency']}->{currency}")
                    else:
                        mcost, csrc, cref = conv["amount"], f"market_{pct}_contractor_cost", bm["benchmark_id"]
                        if conv.get("rate"):
                            fx_used.append({"pair": f"{bm['currency']}->{currency}", "rate": conv["rate"], "as_of": conv.get("as_of"), "source": conv.get("source")})
                flags.append("external_qualification_unverified")
            else:
                raise HoiValidation("resource_type must be internal or external")
            bill = None
            if norm(role["role_name"]) in rates:
                conv = costing.convert(dec(rates[norm(role["role_name"])]), rc_pay["currency"], currency, policy)
                bill = conv["amount"] if conv else None
                if conv is None:
                    unresolved.append(f"fx_rate_missing:{rc_pay['currency']}->{currency}")
                elif conv.get("rate"):
                    fx_used.append({"pair": f"{rc_pay['currency']}->{currency}", "rate": conv["rate"], "as_of": conv.get("as_of"), "source": conv.get("source")})
            lines.append(Line(rid, rtype, fte, mcost, bill, csrc, cref))
            meta.append({"requirement_id": rid, "resource_type": rtype, "coded_identity": coded, "fte": str(fte), "fitness_rank": rank,
                         "cost_source": csrc, "cost_ref": cref, "percentile": a.get("percentile") if rtype == "external" else None})
        for rid, role in roles.items():
            n = per_req.get(rid, 0)
            if n < int(role["headcount"]):
                unresolved.append(f"headcount_unfilled:{rid}:{int(role['headcount']) - n}")
        calc = costing.calculate(lines, months, currency, policy, direct_extra)
        calc["unresolved"] = sorted(set(calc.get("unresolved", []) + unresolved))
        # capacity impact + lead time + deterministic rule-based risk
        capacity = [{"coded_identity": m["coded_identity"], "requested_fte": str(used[m["coded_identity"]]),
                     "available_fte": next((c["available_fte"] for c in pool.get(m["requirement_id"], []) if c["coded_identity"] == m["coded_identity"]), None)}
                    for m in meta if m["resource_type"] == "internal"]
        has_int, has_ext = any(m["resource_type"] == "internal" for m in meta), any(m["resource_type"] == "external" for m in meta)
        lead = {"internal_weeks": policy.internal_lead_weeks if has_int else None,
                "external_weeks": (max(ttf) if ttf and None not in ttf else None) if has_ext else None}
        known = [v for v in lead.values() if v is not None]
        needed = (1 if has_int else 0) + (1 if has_ext else 0)
        lead["overall_weeks"] = max(known) if known and len(known) == needed else None
        if lead["overall_weeks"] is None:
            flags.append("lead_time_unknown")
        if skipped:
            flags.append("higher_ranked_eligible_candidate_not_selected")
        if any(c["available_fte"] is not None and float(c["available_fte"]) - float(c["requested_fte"]) < 0.2 for c in capacity):
            flags.append("capacity_tight")
        flags = sorted(set(flags))
        risk = ("high" if calc["unresolved"] else "medium" if any(f not in ("lead_time_unknown", "capacity_tight") for f in flags)
                else "low")
        kind = body.get("kind") or ("internal" if not has_ext else "external" if not has_int else "hybrid")
        assumptions = {"policy_ref": policy.policy_ref, "rate_card": f"{rc_name}@v{rcard['version']}", "cost_as_of": as_of,
                       "overhead_treatment": policy.overhead_treatment, "fx_rates_used": sorted({_json(x) for x in fx_used}),
                       "cost_basis": "fully_loaded_monthly (internal) / contractor_cost (external) / bill_rate per month (revenue)"}
        input_hash = costing.input_hash({
            "opp": opp_id, "version": ver["content_hash"], "kind": kind, "months": months, "currency": currency,
            "assignments": sorted(({k: v for k, v in m.items()} for m in meta), key=_json),
            "policy": [policy.policy_ref, prow["payload"]], "rate_card": [assumptions["rate_card"], rc_pay],
            "as_of": as_of, "extra": str(direct_extra), "calc": CALC_VERSION, "cost_refs": sorted(cost_refs),
            "market": sorted(market_refs), "run": run})
        override = skipped
        result = {"finance": calc, "lines": [{**m, "monthly_cost": (str(l.monthly_cost) if l.monthly_cost is not None else None),
                                              "bill_rate_monthly": (str(l.bill_rate_monthly) if l.bill_rate_monthly is not None else None)}
                                             for m, l in zip(meta, lines)],
                  "risk": {"level": risk, "flags": flags, "basis": "rule-based; not a probability"},
                  "lead_time_weeks": lead, "capacity": capacity, "market_refs": sorted(set(market_refs)),
                  "uses_individual_cost": uses_individual, "match_run_id": run, "assumptions": assumptions}
        sid = _id("sc")
        with self.db.session() as conn:
            parent = conn.execute("SELECT scenario_id, version_no FROM commercial_scenarios WHERE opportunity_id=? AND input_hash=? "
                                  "ORDER BY version_no DESC LIMIT 1", (opp_id, input_hash)).fetchone()
            prev_n = conn.execute("SELECT COUNT(*) AS n FROM commercial_scenarios WHERE opportunity_id=? AND kind=?", (opp_id, kind)).fetchone()["n"]
            conn.execute(
                "INSERT INTO commercial_scenarios (scenario_id, opportunity_id, version_id, parent_id, version_no, kind, currency, months, "
                "assumption_json, calc_version, input_hash, calculable, revenue, cogs, profit, margin_pct, result_json, status, "
                "override_required, auto_generated, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sid, opp_id, vid, parent["scenario_id"] if parent else None, int(prev_n) + 1, kind, currency, months,
                 _json(assumptions), CALC_VERSION, input_hash, 1 if calc["calculable"] else 0, calc.get("revenue"), _seal(calc.get("cogs")),
                 _seal(calc.get("gross_profit")), _seal(calc.get("gross_margin_pct")), _seal(_json(result)), "draft", 1 if override else 0,
                 1 if auto_generated else 0, p.sub, utc_now().isoformat()),
            )
            for m in meta:
                conn.execute("INSERT INTO scenario_assignments (assignment_id, scenario_id, requirement_id, resource_type, coded_identity, "
                             "external_slot, fte, fitness_rank, cost_ref) VALUES (?,?,?,?,?,?,?,?,?)",
                             (_id("sa"), sid, m["requirement_id"], m["resource_type"], m["coded_identity"],
                              f"EXT-{uuid.uuid4().hex[:6]}" if m["resource_type"] == "external" else None, m["fte"], m["fitness_rank"], m["cost_ref"]))
            conn.execute("UPDATE opportunities SET stage='scenarios', updated_at=? WHERE opportunity_id=? AND stage!='approved'",
                         (utc_now().isoformat(), opp_id))
        self.h.audit(opp_id, "scenario_created", p.sub, sid, version=str(int(prev_n) + 1), evidence=input_hash,
                     detail={"kind": kind, "calc_version": CALC_VERSION, "calculable": bool(calc["calculable"]),
                             "override_required": override, "auto_generated": auto_generated})
        return self.get(p, opp_id, sid)

    # =================================================================== views
    def _row(self, opp_id: str, sid: str) -> Mapping[str, Any]:
        with self.db.session() as conn:
            r = conn.execute("SELECT * FROM commercial_scenarios WHERE scenario_id=? AND opportunity_id=?", (sid, opp_id)).fetchone()
        if r is None:
            raise OpportunityNotFound("scenario not found")
        return r

    def _approvals(self, sid: str) -> List[Dict[str, Any]]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM approval_events WHERE object_type='scenario' AND object_id=? ORDER BY created_at, approval_id", (sid,)).fetchall()
        return [{"approver_role": r["approver_role"], "outcome": r["outcome"], "reason": r["reason"],
                 "override_reason": r["override_reason"], "actor": r["actor"], "created_at": r["created_at"]} for r in rows]

    @staticmethod
    def required_approvals(uses_individual: bool) -> List[str]:
        return ["delivery", "finance"] + (["hr"] if uses_individual else [])

    def _approval_state(self, r: Mapping[str, Any], res: Mapping[str, Any]) -> Dict[str, Any]:
        latest: Dict[str, str] = {}
        for a in self._approvals(r["scenario_id"]):
            latest[a["approver_role"]] = a["outcome"]
        need = self.required_approvals(res["uses_individual_cost"])
        return {"required": need, "latest": latest, "pending": [x for x in need if latest.get(x) != "approved"],
                "complete": all(latest.get(x) == "approved" for x in need), "rejected": "rejected" in latest.values()}

    def _explain(self, codes: Sequence[str], version_id: str) -> List[Dict[str, str]]:
        """Plain-language form of the machine codes in ``unresolved`` (the codes stay in the API for programs)."""
        names = {r["requirement_id"]: r["role_name"] for r in self.h._roles(version_id)}
        out = []
        for c in codes:
            kind, *rest = c.split(":")
            role = names.get(rest[0], rest[0]) if rest and kind != "fx_rate_missing" else ""
            if kind == "headcount_unfilled":
                msg = f"{role}: {rest[1]} approved position(s) have nobody assigned yet"
            elif kind in ("cost_unavailable", "cost_unresolved"):
                msg = f"{role}: Finance has no approved loaded cost for this person or role, so cost cannot be calculated"
            elif kind == "market_benchmark_missing":
                msg = f"{role}: no contractor-cost benchmark has been imported for this role and geography"
            elif kind == "bill_rate_unresolved":
                msg = f"{role}: the rate card has no customer rate for this role"
            elif kind == "fx_rate_missing":
                msg = f"Finance has not supplied an FX rate for {rest[0]}"
            elif kind == "no_assignments":
                msg = "No positions are assigned in this scenario"
            else:
                msg = c.replace("_", " ")
            out.append({"code": c, "message": msg})
        return out

    def get(self, p: AuthPrincipal, opp_id: str, sid: str) -> Dict[str, Any]:
        self.h.opportunity(p, opp_id)
        return self._view(p, self._row(opp_id, sid))

    def list(self, p: AuthPrincipal, opp_id: str) -> List[Dict[str, Any]]:
        self.h.opportunity(p, opp_id)
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM commercial_scenarios WHERE opportunity_id=? ORDER BY created_at, scenario_id", (opp_id,)).fetchall()
        return [self._view(p, r) for r in rows]

    def _view(self, p: AuthPrincipal, r: Mapping[str, Any]) -> Dict[str, Any]:
        """Explicit whitelist per role. Raw per-person pay is only ever returned to Finance for lines, and only here."""
        res = _open(r["result_json"])
        fin = res["finance"]
        approvals = self._approval_state(r, res)
        approved = r["status"] == "approved"
        assignments = [{k: m[k] for k in ("requirement_id", "resource_type", "coded_identity", "fte", "fitness_rank", "cost_source")}
                       for m in res["lines"]]
        base: Dict[str, Any] = {
            "scenario_id": r["scenario_id"], "opportunity_id": r["opportunity_id"], "kind": r["kind"], "status": r["status"],
            "version_no": r["version_no"], "requirement_version_id": r["version_id"], "currency": r["currency"], "months": r["months"],
            "calc_version": r["calc_version"], "input_hash": r["input_hash"], "calculable": bool(r["calculable"]),
            "auto_generated": bool(r["auto_generated"]), "override_required": bool(r["override_required"]),
            "unresolved_constraints": fin["unresolved"], "unresolved_detail": self._explain(fin["unresolved"], r["version_id"]),
            "approval_required": not approvals["complete"],
            "approvals": approvals, "created_by": r["created_by"], "created_at": r["created_at"],
            "no_automatic_assignment": True,
        }
        if p.has_any_role(SALES) and not p.has_any_role(MANAGER, FINANCE, HR, ADMIN):
            base["assignment_summary"] = {"internal": sum(1 for m in assignments if m["resource_type"] == "internal"),
                                          "external": sum(1 for m in assignments if m["resource_type"] == "external")}
            if approved and r["calculable"]:
                base["approved_totals"] = {"revenue": fin["revenue"], "currency": r["currency"], "months": r["months"]}
            return base
        base.update({"assignments": [{k: v for k, v in m.items() if k != "cost_source"} | {"cost_basis": m["cost_source"]} for m in assignments],
                     "risk": res["risk"], "lead_time_weeks": res["lead_time_weeks"], "capacity": res["capacity"],
                     "uses_individual_cost": res["uses_individual_cost"], "market_refs": res["market_refs"]})
        if r["calculable"]:
            base["economics"] = {"revenue": fin["revenue"], "margin_band": costing.margin_band(fin["gross_margin_pct"]),
                                 "currency": r["currency"]}
        if p.has_any_role(FINANCE):
            base["assignments"] = [{**a, "monthly_cost": l["monthly_cost"], "cost_ref": l["cost_ref"], "bill_rate_monthly": l["bill_rate_monthly"]}
                                   for a, l in zip(base["assignments"], res["lines"])]
            base["finance"] = fin
            base["assumptions"] = res["assumptions"]
            if r["calculable"]:
                base["economics"] = {k: fin[k] for k in ("revenue", "delivery_cost", "cogs", "gross_profit", "gross_margin_pct",
                                                         "contribution", "contribution_margin_pct", "breakdown")} | {"currency": r["currency"]}
        return base

    # =================================================================== approvals
    def approve(self, p: AuthPrincipal, opp_id: str, sid: str, approver_role: str, outcome: str,
                reason: Optional[str], override_reason: Optional[str]) -> Dict[str, Any]:
        if approver_role not in APPROVER_ROLE:
            raise HoiValidation(f"approver_role must be one of {list(APPROVER_ROLE)}")
        if outcome not in ("approved", "rejected"):
            raise HoiValidation("outcome must be approved or rejected")
        if not p.has_any_role(APPROVER_ROLE[approver_role]):
            raise AuthorizationError(f"{approver_role} approval requires the {APPROVER_ROLE[approver_role]} role")
        self.h.opportunity(p, opp_id)
        r = self._row(opp_id, sid)
        res = _open(r["result_json"])
        if outcome == "rejected" and not (reason or "").strip():
            raise HoiValidation("a reason is required when rejecting")
        if outcome == "approved":
            if not r["calculable"] or res["finance"]["unresolved"]:
                raise HoiConflict("scenario has unresolved constraints or inputs and cannot be approved", "scenario_unresolved")
            if r["override_required"] and approver_role == "delivery" and not (override_reason or "").strip():
                raise HoiValidation("override_reason is required: a higher-ranked eligible candidate was not selected")
        if approver_role == "hr" and not res["uses_individual_cost"]:
            raise HoiConflict("HR authorization applies only to scenarios that use individual compensation data")
        with self.db.session() as conn:
            conn.execute("INSERT INTO approval_events (approval_id, opportunity_id, object_type, object_id, approver_role, outcome, "
                         "reason, override_reason, actor, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (_id("ap"), opp_id, "scenario", sid, approver_role, outcome, reason, override_reason, p.sub, utc_now().isoformat()))
        state = self._approval_state(r, res)
        status = "rejected" if state["rejected"] else "approved" if state["complete"] else \
            "partially_approved" if state["latest"] else "draft"
        with self.db.session() as conn:
            conn.execute("UPDATE commercial_scenarios SET status=? WHERE scenario_id=?", (status, sid))
            if status == "approved":
                conn.execute("UPDATE opportunities SET stage='approved', updated_at=? WHERE opportunity_id=?", (utc_now().isoformat(), opp_id))
        self.h.audit(opp_id, f"scenario_{outcome}", p.sub, sid, evidence=r["input_hash"],
                     detail={"approver_role": approver_role, "has_override_reason": bool(override_reason), "scenario_status": status})
        return self.get(p, opp_id, sid)

    # =================================================================== export
    def export(self, p: AuthPrincipal, opp_id: str, sid: str, fmt: str) -> Dict[str, Any]:
        opp = self.h.opportunity(p, opp_id)
        r = self._row(opp_id, sid)
        if r["status"] != "approved":
            raise HoiConflict("only a fully approved scenario can be exported", "scenario_not_approved")
        if fmt not in ("json", "markdown"):
            raise HoiValidation("format must be json or markdown")
        view = self._view(p, r)
        view.pop("finance", None)  # the shareable report never carries per-line or policy internals
        view["assignments"] = [{k: v for k, v in a.items() if k not in ("monthly_cost", "cost_ref", "bill_rate_monthly")} for a in view.get("assignments", [])]
        ver = self.h._version_row(opp_id, r["version_id"])
        report = {
            "report_type": "hermes_opportunity_approved_scenario", "generated_for_role": sorted(p.roles),
            "generated_at": utc_now().isoformat(),
            "opportunity": {k: opp[k] for k in ("opportunity_id", "client_alias", "name", "currency", "contract_type", "duration_months", "geography", "is_synthetic")},
            "requirements": {"version_id": ver["version_id"], "version_no": ver["version_no"], "approved_by": ver["approved_by"],
                             "content_hash": ver["content_hash"],
                             "roles": [{"role_name": x["role_name"], "headcount": x["headcount"], "fte": x["fte"],
                                        "skills": [{"skill": s["skill_name"] or s["text"], "level": s["level"], "criticality": s["criticality"]}
                                                   for s in x["skills"] if not s.get("dismissed")]} for x in self.h._roles(ver["version_id"])]},
            "scenario": view,
            "market": self._market_summary(opp, ver["version_id"], r),
            "approvals": self._approvals(sid),
            "audit": {"head_hash": self.h.audit_trail(p, opp_id)["head_hash"]},
            "disclaimers": ["Hermes ranks and costs; people decide. No employee has been assigned by this report.",
                            "Candidates appear by coded identity only.",
                            "Individual compensation is not included in this report."]
                           + (["Opportunity data is synthetic demonstration data."] if opp["is_synthetic"] else []),
        }
        self.h.audit(opp_id, "report_exported", p.sub, sid, evidence=r["input_hash"], detail={"format": fmt})
        if fmt == "json":
            return {"format": "json", "report": report}
        return {"format": "markdown", "content": self._markdown(report)}

    def _market_summary(self, opp: Mapping[str, Any], vid: str, r: Mapping[str, Any]) -> List[Dict[str, Any]]:
        ids = set(_open(r["result_json"])["market_refs"])
        return [{k: b[k] for k in ("benchmark_id", "role", "geography", "basis", "currency", "unit", "p25", "p50", "p75",
                                   "sample_count", "source", "as_of", "is_synthetic", "coverage")}
                for b in self.h.market.query() if b["benchmark_id"] in ids]

    @staticmethod
    def _markdown(rep: Mapping[str, Any]) -> str:
        o, s = rep["opportunity"], rep["scenario"]
        L = [f"# Approved staffing scenario — {o['name']}", "",
             f"Opportunity `{o['opportunity_id']}` · client alias **{o['client_alias']}** · {o['contract_type']} · "
             f"{o['duration_months']} months · {o['currency']}", "",
             f"Scenario `{s['scenario_id']}` ({s['kind']}) · calc `{s['calc_version']}` · input hash `{s['input_hash'][:16]}…`", "",
             "## Requirements", ""]
        for r in rep["requirements"]["roles"]:
            L.append(f"- **{r['role_name']}** ×{r['headcount']} @ {r['fte']} FTE — " +
                     ", ".join(f"{k['skill']} (L{k['level']}, {k['criticality']})" for k in r["skills"]))
        L += ["", "## Staffing (coded)", ""]
        if not s.get("assignments") and s.get("assignment_summary"):
            L.append(f"- {s['assignment_summary']['internal']} internal and {s['assignment_summary']['external']} external positions "
                     "(coded identities are not shown to this role)")
        for a in s.get("assignments", []):
            who = a.get("coded_identity") or "external slot"
            L.append(f"- {a['resource_type']} · {who} · {a['fte']} FTE" + (f" · fitness rank {a['fitness_rank']}" if a.get("fitness_rank") else ""))
        e = s.get("economics") or s.get("approved_totals")
        if e:
            L += ["", "## Economics", ""] + [f"- {k.replace('_', ' ')}: {v}" for k, v in e.items() if not isinstance(v, dict)]
        L += ["", "## Approvals", ""] + [f"- {a['approver_role']}: {a['outcome']} by {a['actor']}" for a in rep["approvals"]]
        L += ["", "## Market provenance", ""] + [f"- {m['role']} / {m['geography']} / {m['basis']}: P25 {m['p25']} P50 {m['p50']} P75 {m['p75']} {m['currency']}/{m['unit']} "
                                              f"(n={m['sample_count']}, {m['source']}, as of {m['as_of']}{', SYNTHETIC' if m['is_synthetic'] else ''})"
                                              for m in rep["market"]]
        L += ["", "---"] + [f"_{d}_" for d in rep["disclaimers"]]
        return "\n".join(L)

    # =================================================================== market analysis
    def market_analysis(self, p: AuthPrincipal, opp_id: str) -> Dict[str, Any]:
        opp = self.h.opportunity(p, opp_id)
        ver = self.h.approved_version(opp_id)
        out = []
        for role in self.h._roles(ver["version_id"]):
            geo = role.get("location") or opp.get("geography")
            entry = {"requirement_id": role["requirement_id"], "role_name": role["role_name"], "geography": geo, "bases": {}}
            for basis in ("salary", "contractor_cost", "bill_rate"):
                rows = self.h.market.query(role["role_name"], geo, basis)
                entry["bases"][basis] = rows[:3] if rows else {"status": "unavailable", "detail": "no curated benchmark imported for this role/geography/basis"}
            out.append(entry)
        snap = costing.input_hash({"roles": out})
        self.h.audit(opp_id, "market_analysis_generated", p.sub, ver["version_id"], evidence=snap)
        return {"snapshot_hash": snap, "requirement_version_id": ver["version_id"], "roles": out,
                "note": "Salary, contractor cost and customer bill rate are separate bases and are never blended. "
                        "Benchmarks are curated imports, not live feeds."}
