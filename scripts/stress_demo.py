#!/usr/bin/env python3
"""Stress test for the demo organisation. Real concurrent HTTP, real writes, real integrity checks.

    python -m scripts.stress_demo --base http://127.0.0.1:8051 --db /path/to/demo.db

Phases: baseline latency, read storm at rising concurrency, write storm (rank = request row + audit
row), races on one decision and one dispute, a mixed soak, a rate-limit probe, then database and
audit-chain integrity. Exit code 1 if any integrity or correctness check fails. Use a throwaway database.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

FAILS: List[str] = []


def call(base: str, method: str, path: str, token: Optional[str] = None, body: Any = None, timeout: float = 60) -> Tuple[int, Any, float]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read() or b"null")
            return r.status, payload, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw.decode(errors="replace")
        return e.code, payload, time.perf_counter() - t0
    except Exception as e:  # connection refused, timeout, reset
        return 0, str(e), time.perf_counter() - t0


def pctl(xs: List[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def report(name: str, results: List[Tuple[int, float]], wall: float, ok_codes: Tuple[int, ...] = (200,)) -> Dict[str, float]:
    lat = [d * 1000 for _, d in results]
    errs = sum(1 for c, _ in results if c not in ok_codes)
    out = {
        "n": len(results),
        "rps": len(results) / wall if wall else 0.0,
        "p50": pctl(lat, 0.5),
        "p95": pctl(lat, 0.95),
        "p99": pctl(lat, 0.99),
        "max": max(lat or [0.0]),
        "err": errs / max(len(results), 1),
    }
    codes: Dict[int, int] = {}
    for c, _ in results:
        codes[c] = codes.get(c, 0) + 1
    print(
        f"  {name:34} n={out['n']:5} rps={out['rps']:7.1f} p50={out['p50']:7.1f}ms p95={out['p95']:7.1f}ms "
        f"p99={out['p99']:7.1f}ms max={out['max']:7.1f}ms errors={out['err'] * 100:5.2f}% codes={codes}"
    )
    return out


def check(ok: bool, name: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def storm(workers: int, jobs: List[Callable[[], Tuple[int, float]]]) -> Tuple[List[Tuple[int, float]], float]:
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        out = list(ex.map(lambda j: j(), jobs))
    return out, time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8051")
    ap.add_argument("--db", type=Path, required=True, help="the server's database file, for integrity checks")
    ap.add_argument("--levels", default="10,50,100,200,400")
    ap.add_argument("--soak-seconds", type=int, default=45)
    ap.add_argument("--skip-copilot-limit", action="store_true")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    tok = lambda sub: call(base, "POST", "/api/auth/token", body={"sub": sub})[1]["access_token"]  # noqa: E731
    mgr, emp = tok("demo-manager"), tok("demo-employee")
    roles = call(base, "GET", "/api/roles", mgr)[1]["roles"]
    t = int(time.time())
    seq = iter(range(10**9))
    lock = threading.Lock()

    def nxt() -> int:
        with lock:
            return next(seq)

    reads = [
        ("/api/overview", mgr), ("/api/workforce", mgr), ("/api/dashboard", mgr), ("/api/skills", mgr), ("/api/session", mgr),
        ("/api/me", emp), ("/api/roles", emp), ("/api/staffing/requests", mgr), ("/api/identity/directory", mgr), ("/api/session", emp),
    ]

    def read_job() -> Tuple[int, float]:
        p, tk = random.choice(reads)
        c, _, d = call(base, "GET", p, tk)
        return c, d

    def rank_job() -> Tuple[int, float]:
        role = random.choice(roles)
        c, _, d = call(base, "POST", "/api/fitness/rank", mgr, {
            "request_id": f"st-{t}-{nxt()}", "required_skills": role["required_skills"],
            "critical_skills": role["critical_skills"], "role_id": role["role_id"], "shortlist_size": 5,
        })
        return c, d

    print("\n1 Baseline (single user)")
    for p, tk in reads[:5]:
        res = [(c, d) for c, _, d in (call(base, "GET", p, tk) for _ in range(20))]
        report(p, res, sum(d for _, d in res))
    res = []
    for _ in range(10):
        c, _, d = call(base, "POST", "/api/fitness/rank", mgr, {"request_id": f"st-{t}-b{nxt()}", "required_skills": roles[0]["required_skills"], "shortlist_size": 5})
        res.append((c, d))
    report("POST /api/fitness/rank", res, sum(d for _, d in res))

    print("\n2 Read storm (mixed reads, rising concurrency)")
    worst_err = 0.0
    for lv in [int(x) for x in a.levels.split(",")]:
        res, wall = storm(lv, [read_job] * (lv * 8))
        worst_err = max(worst_err, report(f"{lv} concurrent users x8 calls", res, wall)["err"])
    check(worst_err == 0.0, "no failed read at any concurrency level", f"worst {worst_err * 100:.2f}%")

    print("\n3 Write storm (every call writes a request row and an audit row)")
    for lv in (10, 50, 100):
        res, wall = storm(lv, [rank_job] * (lv * 3))
        rep = report(f"{lv} concurrent rankers x3", res, wall)
        check(rep["err"] == 0.0, f"no failed rank at {lv} concurrent writers", f"{rep['err'] * 100:.2f}%")

    print("\n4 Races")
    senior = next(x for x in roles if x["role_name"] == "Senior Cloud Engineer")
    rid = f"race-{t}"
    d = call(base, "POST", "/api/fitness/rank", mgr, {"request_id": rid, "required_skills": senior["required_skills"], "critical_skills": senior["critical_skills"], "role_id": senior["role_id"], "shortlist_size": 5})[1]
    top = d["candidates"][0]["coded_identity"]

    def decide() -> Tuple[int, float]:
        c, _, dd = call(base, "POST", f"/api/staffing/{rid}/decision", mgr, {"status": "accepted", "chosen_coded_identity": top})
        return c, dd

    res, _ = storm(60, [decide] * 60)
    codes = [c for c, _ in res]
    check(codes.count(200) == 1 and codes.count(409) == 59, "60 simultaneous decisions: exactly 1 accepted, 59 refused",
          f"200={codes.count(200)} 409={codes.count(409)} other={[c for c in codes if c not in (200, 409)]}")

    same_id = f"same-{t}"

    def same_rank() -> Tuple[int, float]:
        c, _, dd = call(base, "POST", "/api/fitness/rank", mgr, {"request_id": same_id, "required_skills": senior["required_skills"], "shortlist_size": 3})
        return c, dd

    res, _ = storm(40, [same_rank] * 40)
    codes = [c for c, _ in res]
    check(all(c in (200, 409) for c in codes), "40 simultaneous ranks of one request id: only 200/409, never a 500", str(sorted(set(codes))))

    people = call(base, "GET", "/api/identity/directory", mgr)[1]["people"]
    sam = next(p["coded_identity"] for p in people if p["display_name"] == "Sam Patel")
    rev = call(base, "GET", f"/api/team/skill-review/{sam}", mgr)[1]
    if rev["contests"]:
        cid = rev["contests"][0]["contest_id"]

        def resolve() -> Tuple[int, float]:
            c, _, dd = call(base, "POST", f"/api/team/contests/{cid}/resolve", mgr, {"status": "confirmed"})
            return c, dd

        res, _ = storm(30, [resolve] * 30)
        codes = [c for c, _ in res]
        check(codes.count(200) == 1 and all(c in (200, 409, 429) for c in codes), "30 simultaneous resolves of one dispute: exactly 1 succeeds",
              f"200={codes.count(200)} others={sorted(set(codes))}")

    print(f"\n5 Mixed soak ({a.soak_seconds}s, 60 workers: 70% reads, 25% ranks, 5% disputes)")
    stop = time.time() + a.soak_seconds
    out: List[Tuple[int, float]] = []
    olock = threading.Lock()

    def worker() -> None:
        while time.time() < stop:
            x = random.random()
            if x < 0.70:
                res_ = read_job()
            elif x < 0.95:
                res_ = rank_job()
            else:
                c, _, dd = call(base, "POST", "/api/me/contest", emp, {"reason": f"soak {nxt()}", "skill_id": "python"})
                res_ = (c, dd)
            with olock:
                out.append(res_)

    t0 = time.perf_counter()
    ths = [threading.Thread(target=worker) for _ in range(60)]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    soak = report("mixed soak", out, time.perf_counter() - t0, ok_codes=(200, 429))
    check(soak["err"] == 0.0, "no 5xx, timeout or dropped connection during the soak", f"{soak['err'] * 100:.2f}%")
    check(soak["p99"] < 15000, "p99 under 15 seconds during the soak", f"{soak['p99']:.0f}ms")

    print("\n6 Rate limits")
    res_codes = [call(base, "POST", "/api/me/contest", emp, {"reason": f"limit {i}"})[0] for i in range(25)]
    check(all(c in (200, 429) for c in res_codes), "dispute endpoint limits or accepts, never errors", str(sorted(set(res_codes))))
    if not a.skip_copilot_limit:
        # Fired together: with a real model each answer takes seconds, and a sequential loop would
        # outlast the 60 s window and never reach the limit.
        with ThreadPoolExecutor(max_workers=24) as pool:
            res_codes = list(pool.map(lambda i: call(base, "POST", "/api/copilot/ask", mgr, {"question": f"hi {i}"}, timeout=180)[0], range(24)))
        check(res_codes.count(429) >= 1 and all(c in (200, 429) for c in res_codes), "copilot is rate limited (20 per minute) and never errors",
              f"200={res_codes.count(200)} 429={res_codes.count(429)}")

    print("\n7 Recovery and integrity")
    time.sleep(1)
    check(call(base, "GET", "/ready")[0] == 200, "server still ready after the storm")
    c, dd, _ = call(base, "POST", "/api/fitness/rank", mgr, {"request_id": f"after-{t}", "required_skills": senior["required_skills"], "critical_skills": senior["critical_skills"], "role_id": senior["role_id"], "shortlist_size": 5})
    check(c == 200 and dd["candidates"] and dd["candidates"][0]["coded_identity"] == top, "ranking still returns the same first choice after the storm", str(c))
    con = sqlite3.connect(str(a.db))
    con.row_factory = sqlite3.Row
    dup = con.execute("SELECT request_id, COUNT(*) AS n FROM staffing_requests GROUP BY request_id HAVING n > 1").fetchall()
    check(not dup, "no duplicate request rows", str(len(dup)))
    acc = con.execute("SELECT COUNT(*) AS n FROM staffing_requests WHERE request_id=? AND status='accepted'", (rid,)).fetchone()["n"]
    check(acc == 1, "the raced request has exactly one accepted decision", str(acc))
    stored = con.execute("SELECT COUNT(*) AS n FROM staffing_requests").fetchone()["n"]
    print(f"      requests stored: {stored}")
    seqs = [row["seq"] for row in con.execute("SELECT seq FROM audit_ledger ORDER BY seq")]
    check(seqs == list(range(1, len(seqs) + 1)), "audit ledger sequence is gap-free", f"{len(seqs)} rows")
    con.close()

    print(f"\n{'ALL STRESS CHECKS PASSED' if not FAILS else str(len(FAILS)) + ' FAILED: ' + '; '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
