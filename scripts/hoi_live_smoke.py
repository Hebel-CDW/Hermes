#!/usr/bin/env python3
"""Live end-to-end check (and latency report) for Opportunity Intelligence against a RUNNING server.

Walks: upload -> extract -> correct -> approve -> match -> compare -> approvals -> export, then asserts the
security boundaries over real HTTP (no pay leaks, redaction, isolation). Uses the synthetic demo principals and
writes one new opportunity per run, so point it at a demo/scratch database only.

    python -m scripts.hoi_live_smoke --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOW = ROOT / "data" / "fixtures" / "hoi" / "sample_sow.txt"
TIMINGS = []
FAILS = []


def call(base, method, path, token=None, body=None):
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            code, text = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        code, text = e.code, e.read().decode()
    TIMINGS.append((f"{method} {path.split('?')[0]}", (time.perf_counter() - t0) * 1000))
    try:
        return code, json.loads(text), text
    except ValueError:
        return code, {}, text


def check(ok, name, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    base = ap.parse_args().base.rstrip("/")
    tok = {s: call(base, "POST", "/api/auth/token", body={"sub": s})[1]["access_token"]
           for s in ("demo-sales", "demo-sales-2", "demo-manager", "demo-finance", "demo-hr", "demo-admin")}

    c, opp, _ = call(base, "POST", "/api/opportunities", tok["demo-sales"], {
        "client_alias": "Smoke", "name": "Live smoke", "currency": "USD", "contract_type": "time_and_materials",
        "duration_months": 6, "geography": "Remote (EU time zones)", "start_date": "2027-01-11", "is_synthetic": True})
    check(c == 201, "create opportunity", str(opp))
    oid = opp["opportunity_id"]
    for sub, role in (("demo-manager", "manager"), ("demo-finance", "finance"), ("demo-hr", "hr")):
        call(base, "POST", f"/api/opportunities/{oid}/members", tok["demo-sales"], {"sub": sub, "member_role": role})
    check(call(base, "GET", f"/api/opportunities/{oid}", tok["demo-sales-2"])[0] == 404, "other deal team cannot see it")

    c, _, _ = call(base, "POST", f"/api/opportunities/{oid}/documents", tok["demo-sales"], {
        "doc_type": "sow", "filename": "sow.txt", "content_b64": base64.b64encode(SOW.read_bytes()).decode()})
    check(c == 201, "upload SOW")
    check(call(base, "POST", f"/api/opportunities/{oid}/documents", tok["demo-sales"],
               {"doc_type": "sow", "filename": "x.exe", "content_b64": base64.b64encode(b"MZ....").decode()})[0] == 422, "executable refused")
    c, ex, _ = call(base, "POST", f"/api/opportunities/{oid}/extract", tok["demo-sales"], {})
    cur = ex["current"]
    check(c == 200 and len(cur["roles"]) == 2 and cur["status"] == "draft", "extract draft with 2 roles")
    check(call(base, "POST", f"/api/opportunities/{oid}/internal-match", tok["demo-manager"], {})[0] == 409, "unapproved requirements cannot be matched")
    for r in cur["roles"]:
        for s in r["skills"]:
            if s["taxonomy_status"] == "unmapped":
                s["dismissed"] = True
            elif s["level"] is None:
                s["level"] = 3
    check(call(base, "PUT", f"/api/opportunities/{oid}/requirements/{cur['version_id']}", tok["demo-sales"], {"roles": cur["roles"]})[0] == 200, "human correction saved")
    check(call(base, "POST", f"/api/opportunities/{oid}/requirements/approve", tok["demo-sales"], {"version_id": cur["version_id"]})[0] == 200, "requirements approved")

    c, sl, _ = call(base, "POST", f"/api/opportunities/{oid}/internal-match", tok["demo-manager"], {})
    check(c == 200 and any(r["eligible_count"] for r in sl["requirements"]), "internal match returns eligible coded candidates", str(sl)[:200])
    c, red, raw = call(base, "GET", f"/api/opportunities/{oid}/shortlist", tok["demo-sales"])
    check(red.get("redacted") is True and "EMP-" not in raw, "sales shortlist is redacted")

    c, cmpd, _ = call(base, "POST", f"/api/opportunities/{oid}/scenarios/compare", tok["demo-manager"], {"cost_policy_id": "POL-2026", "rate_card_id": "RATE-01"})
    check(c == 200, "compare scenarios", str(cmpd)[:200])
    kinds = [s["kind"] for s in cmpd.get("scenarios", [])]
    print("   scenario kinds:", kinds)
    ext = next((s for s in cmpd["scenarios"] if s["kind"] == "external"), None)
    sid = ext["scenario_id"]
    c, mv, mtxt = call(base, "GET", f"/api/opportunities/{oid}/scenarios/{sid}", tok["demo-manager"])
    check("finance" not in mv and "delivery_cost" not in mtxt and "gross_profit" not in mtxt, "manager view has no cost detail")
    c, fv, _ = call(base, "GET", f"/api/opportunities/{oid}/scenarios/{sid}", tok["demo-finance"])
    check("gross_profit" in fv.get("economics", {}), "finance view has full economics")
    check(call(base, "GET", "/api/finance/loaded-costs", tok["demo-manager"])[0] == 403, "manager cannot read loaded costs")
    check(call(base, "GET", "/api/finance/loaded-costs", tok["demo-admin"])[0] == 403, "admin cannot read loaded costs")

    ap_ = lambda who, role: call(base, "POST", f"/api/opportunities/{oid}/approvals", tok[who], {"scenario_id": sid, "approver_role": role, "outcome": "approved"})
    check(call(base, "POST", f"/api/opportunities/{oid}/export", tok["demo-manager"], {"scenario_id": sid})[0] == 409, "export refused before approval")
    ap_("demo-manager", "delivery")
    c, done, _ = ap_("demo-finance", "finance")
    check(done.get("status") == "approved", "two-lane approval completes", str(done.get("approvals")))
    c, rep, rtxt = call(base, "POST", f"/api/opportunities/{oid}/export", tok["demo-sales"], {"scenario_id": sid})
    check(c == 200 and "monthly_cost" not in rtxt, "sales can export the redacted approved report")
    c, au, _ = call(base, "GET", f"/api/opportunities/{oid}/audit", tok["demo-sales"])
    check(au.get("chain_valid") is True and len(au.get("events", [])) >= 8, "audit chain valid", str(len(au.get("events", []))))

    print("\nlatency (ms):")
    agg = {}
    for k, v in TIMINGS:
        agg.setdefault(k, []).append(v)
    for k, v in sorted(agg.items(), key=lambda kv: -max(kv[1]))[:8]:
        print(f"  {max(v):8.1f}  {k}")
    print(f"\n{'ALL CHECKS PASSED' if not FAILS else str(len(FAILS)) + ' FAILED: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
