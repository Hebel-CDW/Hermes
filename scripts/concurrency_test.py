#!/usr/bin/env python3
"""Real concurrency test against a running Hermes instance (Phase 7 of the
PostgreSQL migration spike). Fires actual concurrent HTTP requests at the
write endpoints and checks the DATABASE afterward for deadlocks, lost
updates, duplicate rows, or a torn audit chain — it does not just check
HTTP status codes, since a write can return 200 and still have lost data.

    python -m scripts.concurrency_test --base http://127.0.0.1:8031 \\
        --database-url postgresql://postgres:testpass@127.0.0.1:55432/hermes_concurrency

Five categories, mapped onto Hermes's actual write surface (there is no literal
"create employee" endpoint — identities are abstracted, not CRUD-created):
  1. employee creation      -> POST /api/identity/abstract (ADMIN)
  2. assessment submission  -> POST /api/team/declare, same (identity, skill) pair
  3. evidence creation      -> POST /api/ingest/tickets
  4. work request creation  -> POST /api/fitness/rank (writes a staffing_requests row)
  5. decision creation      -> POST /api/staffing/{id}/decision, same request_id
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path = [str(ROOT / "src"), str(ROOT)] + sys.path


def _call(base: str, method: str, path: str, token: str = "", body: Any = None) -> Tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read())
        except Exception:
            payload = {}
        return exc.code, payload


def _token(base: str, sub: str) -> str:
    status, body = _call(base, "POST", "/api/auth/token", body={"sub": sub})
    assert status == 200, f"could not mint token for {sub}: {status} {body}"
    return body["access_token"]


def _concurrent(fn, n: int, max_workers: int = 30) -> List[Tuple[int, Any]]:
    with ThreadPoolExecutor(max_workers=min(n, max_workers)) as pool:
        futures = [pool.submit(fn, i) for i in range(n)]
        return [f.result() for f in as_completed(futures)]


def run(base: str, database_url: str) -> Dict[str, Any]:
    from shared.db import HermesDB

    db = HermesDB(database_url=database_url)
    admin = _token(base, "demo-admin")
    manager = _token(base, "demo-manager")
    stamp = int(time.time())
    report: Dict[str, Any] = {}

    # 1. Employee creation: N concurrent abstractions of brand-new, distinct people.
    with db.session() as conn:
        before = conn.execute("SELECT COUNT(*) AS n FROM identity_map").fetchone()["n"]
    n1 = 20

    def _abstract(i: int):
        return _call(base, "POST", "/api/identity/abstract", admin,
                     {"employee_id": f"CONC-EMP-{stamp}-{i}", "name": f"Concurrency Test {i}"})

    results1 = _concurrent(_abstract, n1)
    with db.session() as conn:
        after = conn.execute("SELECT COUNT(*) AS n FROM identity_map").fetchone()["n"]
        distinct_coded = conn.execute(
            "SELECT COUNT(DISTINCT coded_identity) AS n FROM identity_map"
        ).fetchone()["n"]
    report["employee_creation"] = {
        "attempted": n1, "status_200": sum(1 for s, _ in results1 if s == 200),
        "db_rows_added": after - before, "no_duplicate_coded_identities": distinct_coded == after,
    }

    # 2. Assessment submission: N concurrent declares on the SAME (identity, skill) pair —
    #    the real race: does the last-writer-wins upsert ever duplicate or corrupt the row?
    target_skill = "incident_management"
    with db.session() as conn:
        rows = conn.execute(
            "SELECT report_coded_id FROM org_edges ORDER BY report_coded_id LIMIT 1"
        ).fetchall()
    direct_report = rows[0]["report_coded_id"] if rows else None

    def _declare(i: int):
        return _call(base, "POST", "/api/team/declare", manager,
                     {"coded_identity": direct_report, "skill_id": target_skill,
                      "proficiency": (i % 5) + 1, "note": f"concurrency {i}"})

    n2 = 10  # bounded by DECLARE_LIMITER (10 calls / 60s / principal) — see Phase 10
    results2 = _concurrent(_declare, n2)
    with db.session() as conn:
        matrix_rows = conn.execute(
            "SELECT COUNT(*) AS n FROM skills_matrix WHERE coded_identity=? AND skill_id=?",
            (direct_report, target_skill),
        ).fetchone()["n"]
    report["assessment_submission"] = {
        "attempted": n2, "status_200": sum(1 for s, _ in results2 if s == 200),
        "status_429": sum(1 for s, _ in results2 if s == 429),
        "status_other": [s for s, _ in results2 if s not in (200, 429)],
        "skills_matrix_rows_for_pair": matrix_rows,  # must stay exactly 1 — never duplicated
    }

    # 3. Evidence creation: N concurrent ticket ingests, distinct employees + ticket numbers.
    with db.session() as conn:
        before_ev = conn.execute("SELECT COUNT(*) AS n FROM evidence_staging").fetchone()["n"]
    n3 = 15

    def _ticket(i: int):
        return _call(base, "POST", "/api/ingest/tickets", admin, {"tickets": [{
            "employee_id": f"CONC-EMP-{stamp}-{i}",
            "ticket_number": f"TICK-{stamp}-{i}",
            "short_description": "resolved a container orchestration incident",
            "resolved_at": "2026-09-01T00:00:00Z",
        }]})

    results3 = _concurrent(_ticket, n3)
    with db.session() as conn:
        after_ev = conn.execute("SELECT COUNT(*) AS n FROM evidence_staging").fetchone()["n"]
    report["evidence_creation"] = {
        "attempted": n3, "status_200": sum(1 for s, _ in results3 if s == 200),
        "status_other": [(s, b) for s, b in results3 if s != 200][:3],
        "db_rows_added": after_ev - before_ev,
    }

    # 4. Work request creation: N concurrent /api/fitness/rank calls, each its own staffing_request.
    with db.session() as conn:
        before_req = conn.execute("SELECT COUNT(*) AS n FROM staffing_requests").fetchone()["n"]
    n4 = 20

    def _rank(i: int):
        rid = f"conc-rank-{stamp}-{i}"
        status, body = _call(base, "POST", "/api/fitness/rank", manager, {
            "request_id": rid,
            "required_skills": {"container_orchestration": 3, "azure_networking": 2},
            "shortlist_size": 3, "min_coverage_ratio": 0.0,
        })
        return status, body, rid

    results4: List[Any] = [None] * n4
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_rank, i): i for i in range(n4)}
        for f in as_completed(futures):
            results4[futures[f]] = f.result()
    with db.session() as conn:
        after_req = conn.execute("SELECT COUNT(*) AS n FROM staffing_requests").fetchone()["n"]
        distinct_ids = conn.execute("SELECT COUNT(DISTINCT request_id) AS n FROM staffing_requests").fetchone()["n"]
    report["work_request_creation"] = {
        "attempted": n4, "status_200": sum(1 for s, _, _ in results4 if s == 200),
        "db_rows_added": after_req - before_req, "no_duplicate_request_ids": distinct_ids == after_req,
    }

    # 5. Decision creation: the real race — M concurrent decisions on the SAME request_id.
    #    record_staffing_decision's WHERE status='open' guard must let exactly one win.
    decide_rid = next((rid for s, b, rid in results4 if s == 200 and b.get("candidates")), None)
    decision_summary: Dict[str, Any] = {"skipped_reason": "no ranked request with candidates to decide on"}
    if decide_rid:
        status, body = _call(base, "GET", f"/api/staffing/requests/{decide_rid}", manager)
        shortlist = (body.get("result") or {}).get("shortlist") or []
        chosen = shortlist[0] if shortlist else None
        n5 = 10

        def _decide(i: int):
            return _call(base, "POST", f"/api/staffing/{decide_rid}/decision", manager, {
                "status": "accepted" if chosen else "rejected",
                "chosen_coded_identity": chosen,
                "rejection_reason": None if chosen else "no candidate",
            })

        results5 = _concurrent(_decide, n5)
        with db.session() as conn:
            final = conn.execute(
                "SELECT status, approved_by, decided_at FROM staffing_requests WHERE request_id=?", (decide_rid,)
            ).fetchone()
        decision_summary = {
            "attempted": n5,
            "status_200": sum(1 for s, _ in results5 if s == 200),
            "status_409": sum(1 for s, _ in results5 if s == 409),
            "status_other": [s for s, _ in results5 if s not in (200, 409)],
            "exactly_one_winner": sum(1 for s, _ in results5 if s == 200) == 1,
            "final_request_status": dict(final) if final else None,
        }
    report["decision_creation"] = decision_summary

    # Audit writes: every write above appends audit rows. Verify the chain is intact
    # (no gaps, no duplicate seq, no torn writes) after all this concurrency.
    report["audit_chain_errors"] = db.verify_audit_chain()
    with db.session() as conn:
        total_audit = conn.execute("SELECT COUNT(*) AS n FROM audit_ledger").fetchone()["n"]
        distinct_seq = conn.execute("SELECT COUNT(DISTINCT seq) AS n FROM audit_ledger").fetchone()["n"]
    report["audit_writes"] = {"total_rows": total_audit, "no_duplicate_seq": distinct_seq == total_audit}

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--database-url", required=True)
    args = ap.parse_args()
    report = run(args.base, args.database_url)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
