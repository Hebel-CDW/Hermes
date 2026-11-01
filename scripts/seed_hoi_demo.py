#!/usr/bin/env python3
"""Seed SYNTHETIC Opportunity Intelligence demo data on top of the demo organisation.

Everything here is invented: capacity (availability) for the 36 demo people, Finance cost policy, a customer
rate card, loaded costs (a few individual, the rest role bands), curated-style market benchmarks and one
opportunity with the sample SOW uploaded. No real employee or payroll data is read or written.

    python -m scripts.seed_hoi_demo --db data/hermes_demo.db [--stage uploaded|approved|matched] [--ready-copy]

Stages let a demo start at the beginning (default), after requirement approval, or after internal matching.
Run scripts.seed_demo_org first. Storage for encrypted documents follows HOI_STORAGE_DIR.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path = [str(ROOT / "src"), str(ROOT)] + sys.path

from datetime import datetime, timezone  # noqa: E402
import json  # noqa: E402

from hoi.market import parse_csv  # noqa: E402
from hoi.service import HoiService  # noqa: E402
from shared.auth import AuthPrincipal  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.service import HermesService  # noqa: E402

FIX = ROOT / "data" / "fixtures" / "hoi"


def P(sub: str, role: str) -> AuthPrincipal:
    return AuthPrincipal(sub=sub, roles=(role,), coded_identity=None)


def add_extra_people(svc: HermesService, db: HermesDB) -> list:
    """Synthetic Azure-certified engineer: evidence incl. a CERTIFIED AZ-104 record, like the other demo certificates."""
    from scripts.seed_demo_org import _records  # reuse the demo evidence builder

    fx = json.loads((FIX / "demo_extra_people.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    coded = {p["employee_id"]: svc.abstract({"employee_id": p["employee_id"], "name": p["display_name"]})["coded_identity"]
             for p in fx["pilot_population"]}
    svc.stage_and_merge(_records(fx, coded, now), as_of=now)
    return list(coded.values())


def seed(db_path: Path, stage: str = "uploaded", ready_copy: bool = False) -> dict:
    os.environ.setdefault("HERMES_TEST_MODE", "1")
    db = HermesDB(db_path)
    svc = HermesService(db=db, mapping_secret=os.getenv("IDENTITY_MAP_SECRET"))
    hoi = HoiService(svc)
    extra = add_extra_people(svc, db)
    sales, mgr = P("demo-sales", "sales"), P("demo-manager", "manager")

    people = sorted({r.coded_identity for r in db.load_skills_matrix()})
    for i, c in enumerate(people):  # synthetic capacity: one in five people is half-allocated
        db.set_availability(c, True, 0.5 if i % 5 == 4 else 1.0)

    hoi.vault.put_parameter("demo-finance", "policy", "POL-2026", {
        "overhead_pct": "10", "overhead_treatment": "below_gross", "contingency_pct": "5", "training_per_fte": "500",
        "travel_per_fte_month": "100", "internal_lead_weeks": 2}, None, None)
    hoi.vault.put_parameter("demo-finance", "rate_card", "RATE-01", {
        "currency": "USD", "unit": "month", "rates": {"Senior Cloud Engineer": "13000", "Platform SRE Lead": "15000"}}, None, None)
    rows = [{"scope": "role_band", "subject": "Senior Cloud Engineer", "monthly_cost": "7400", "currency": "USD",
             "effective_from": "2026-01-01", "source": "SYNTHETIC-BAND-1"},
            {"scope": "role_band", "subject": "Platform SRE Lead", "monthly_cost": "8300", "currency": "USD",
             "effective_from": "2026-01-01", "source": "SYNTHETIC-BAND-1"}]
    rows += [{"scope": "individual", "subject": c, "monthly_cost": str(6800 + 90 * i), "currency": "USD",
              "effective_from": "2026-01-01", "source": "SYNTHETIC-IND-1"} for i, c in enumerate(people[:8])]
    # The synthetic Azure-certified engineer has an individual loaded cost, so a scenario that staffs them needs HR authorization.
    rows += [{"scope": "individual", "subject": c, "monthly_cost": "7150", "currency": "USD",
              "effective_from": "2026-01-01", "source": "SYNTHETIC-IND-1"} for c in extra]
    hoi.vault.add_costs("demo-finance", rows)
    hoi.market.import_rows("demo-finance", parse_csv((FIX / "market_benchmarks_synthetic.csv").read_text(), True))

    # The finished example is created first so the live-walkthrough opportunity is the newest one, which the
    # app lists (and selects) first.
    ready_id = None
    if ready_copy:
        ready_id = build_opportunity(hoi, sales, mgr, "Cloud Platform Modernisation (completed example)", "matched")["opportunity_id"]
    live_name = "Cloud Platform Modernisation (live walkthrough)" if ready_copy else "Cloud Platform Modernisation"
    out = build_opportunity(hoi, sales, mgr, live_name, stage)
    out.update({"people_with_capacity": len(people), "extra_synthetic_people": len(extra)})
    if ready_id:
        out["ready_opportunity_id"] = ready_id
    return out


def build_opportunity(hoi: HoiService, sales: AuthPrincipal, mgr: AuthPrincipal, name: str, stage: str) -> dict:
    opp = hoi.create_opportunity(sales, {
        "client_alias": "Northstar (fictional)", "name": name, "currency": "USD",
        "contract_type": "time_and_materials", "duration_months": 6, "geography": "Remote (EU time zones)",
        "start_date": "2027-01-11", "bid_deadline": "2026-12-15", "is_synthetic": True})
    oid = opp["opportunity_id"]
    for sub, role in (("demo-manager", "manager"), ("demo-finance", "finance"), ("demo-hr", "hr")):
        hoi.add_member(sales, oid, sub, role)
    hoi.upload_document(sales, oid, "sow", "northstar_sow_synthetic.txt",
                        base64.b64encode((FIX / "sample_sow.txt").read_bytes()).decode())
    out = {"opportunity_id": oid, "stage": "uploaded"}
    if stage in ("approved", "matched"):
        cur = hoi.extract(sales, oid, None)["current"]
        for r in cur["roles"]:
            for s in r["skills"]:
                if s["taxonomy_status"] == "unmapped":
                    s["dismissed"] = True
                elif s["level"] is None:
                    s["level"] = 3  # the reviewer's explicit choice; the document did not state it
        hoi.update_requirements(sales, oid, cur["version_id"], cur["roles"])
        hoi.approve_requirements(mgr, oid, cur["version_id"])
        out["stage"] = "approved"
    if stage == "matched":
        hoi.internal_match(mgr, oid)
        out["stage"] = "matched"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=Path(os.getenv("HERMES_DB_PATH", "data/hermes_demo.db")))
    ap.add_argument("--stage", choices=("uploaded", "approved", "matched"), default="uploaded")
    ap.add_argument("--ready-copy", action="store_true", help="also create a second opportunity already at the matched stage")
    a = ap.parse_args(argv)
    print(seed(a.db, a.stage, a.ready_copy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
