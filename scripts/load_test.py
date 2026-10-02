#!/usr/bin/env python3
"""Real load test against a running Hermes instance. Not a simulation — fires
actual concurrent HTTP requests and measures what actually happens.

    python -m scripts.load_test --base http://127.0.0.1:8013 --levels 10,50,100,310,1000

Reports p50/p95/p99 latency, throughput, and error rate per level. Stops
escalating once the error rate crosses 5% at a level — reporting that as the
measured bottleneck rather than continuing to claim higher levels "work."
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple


def _token(base: str, sub: str) -> str:
    req = urllib.request.Request(
        f"{base}/api/auth/token", data=json.dumps({"sub": sub}).encode(),
        headers={"content-type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["access_token"]


def _one_rank_call(base: str, token: str, idx: int) -> Tuple[float, int]:
    body = json.dumps({
        "request_id": f"load-{idx}-{int(time.time() * 1000)}",
        "required_skills": {"container_orchestration": 3, "azure_networking": 2},
        "shortlist_size": 5,
    }).encode()
    req = urllib.request.Request(
        f"{base}/api/fitness/rank", data=body,
        headers={"content-type": "application/json", "Authorization": f"Bearer {token}"}, method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception:
        status = 0
    return (time.perf_counter() - start, status)


def run_level(base: str, token: str, n: int) -> Dict:
    results: List[Tuple[float, int]] = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(n, 200)) as pool:
        futures = [pool.submit(_one_rank_call, base, token, i) for i in range(n)]
        for f in as_completed(futures):
            results.append(f.result())
    wall = time.perf_counter() - t0
    latencies = sorted(r[0] for r in results)
    errors = sum(1 for _, status in results if status != 200)
    return {
        "n": n,
        "wall_seconds": round(wall, 2),
        "throughput_req_s": round(n / wall, 2) if wall > 0 else 0,
        "p50_ms": round(statistics.median(latencies) * 1000, 1),
        "p95_ms": round(latencies[int(len(latencies) * 0.95) - 1] * 1000, 1),
        "p99_ms": round(latencies[int(len(latencies) * 0.99) - 1] * 1000, 1),
        "max_ms": round(latencies[-1] * 1000, 1),
        "error_count": errors,
        "error_rate": round(errors / n, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--levels", default="10,50,100,310,1000")
    ap.add_argument("--sub", default="demo-manager")
    args = ap.parse_args()

    token = _token(args.base, args.sub)
    print(f"{'level':>8} {'wall_s':>8} {'req/s':>8} {'p50_ms':>8} {'p95_ms':>8} {'p99_ms':>8} {'max_ms':>8} {'errors':>8}")
    for level in (int(x) for x in args.levels.split(",")):
        stats = run_level(args.base, token, level)
        print(
            f"{stats['n']:>8} {stats['wall_seconds']:>8} {stats['throughput_req_s']:>8} "
            f"{stats['p50_ms']:>8} {stats['p95_ms']:>8} {stats['p99_ms']:>8} {stats['max_ms']:>8} "
            f"{stats['error_count']:>8}"
        )
        if stats["error_rate"] > 0.05:
            print(f"\nSTOPPING: error rate {stats['error_rate']:.1%} at level {level} exceeds 5% — "
                  "this is the measured bottleneck, not a level to push past.")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
