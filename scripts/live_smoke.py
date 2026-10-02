#!/usr/bin/env python3
"""Live end-to-end smoke test for a RUNNING Hermes instance (local or hosted).

Exercises the same path a manager walks in the UI, over real HTTP:
sign in -> find people -> why -> gaps -> decide -> team skills -> update a skill
-> employee view / contest -> manager resolves contest, plus the security and
deployment checks a host would care about (RBAC, headers, path traversal,
input validation, readiness, audit chain).

Usage
-----
    python -m scripts.live_smoke                       # http://127.0.0.1:8000
    python -m scripts.live_smoke --base https://hermes.example.com

Runs against the synthetic demo principals, so the target must have demo auth
enabled (``HERMES_TEST_MODE=1`` or ``HERMES_ENV=local``). It creates one staffing
request per run (unique id) and records one decision, one skill update and one
contest on the target database - point it at a scratch/demo DB, never real data.
Exit code 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

ROLE_SKILLS = {"container_orchestration": 3, "azure_networking": 2}


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
    ) -> Tuple[int, Any, Dict[str, str]]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("content-type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                status, raw, headers = resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            status, raw, headers = exc.code, exc.read(), dict(exc.headers)
        text = raw.decode("utf-8", "replace")
        try:
            return status, json.loads(text), headers
        except ValueError:
            return status, text, headers

    def token(self, sub: str) -> str:
        status, body, _ = self.call("POST", "/api/auth/token", {"sub": sub})
        if status != 200:
            raise SystemExit(f"cannot sign in as {sub}: HTTP {status} {body} (is demo auth enabled?)")
        return body["access_token"]


class Report:
    def __init__(self) -> None:
        self.results: List[Tuple[bool, str, str]] = []

    def check(self, ok: bool, name: str, detail: str = "") -> bool:
        self.results.append((bool(ok), name, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
        return bool(ok)

    def section(self, title: str) -> None:
        print(f"\n== {title}")

    @property
    def failed(self) -> int:
        return sum(1 for ok, _, _ in self.results if not ok)


def run(base: str) -> int:
    c, r = Client(base), Report()
    run_id = f"REQ-SMOKE-{int(time.time())}"

    r.section("1. Deployment health")
    s, b, h = c.call("GET", "/health")
    r.check(s == 200 and b.get("status") == "ok", "GET /health is ok", f"{s} {b}")
    s, b, _ = c.call("GET", "/ready")
    r.check(s == 200 and b.get("status") == "ready", "GET /ready (DB trusted, audit chain intact)", f"{s} {b}")
    r.check(b.get("auth_mode") in ("development", "production"), "auth_mode reported", str(b.get("auth_mode")))
    r.check(
        "teams_provider_is_mock" in b,
        "Teams provider configuration reported (mock vs real)",
        str(b.get("teams_provider_is_mock")),
    )
    s, b, h = c.call("GET", "/")
    r.check(s == 200 and isinstance(b, str) and 'id="root"' in b, "SPA shell is served at /", f"{s}")
    r.check("fonts.googleapis.com" not in str(b), "no third-party font/CDN calls in index.html")
    s, b, _ = c.call("GET", "/requests/some-deep-link")
    r.check(s == 200 and isinstance(b, str) and 'id="root"' in b, "deep link falls back to SPA (refresh-safe)")
    low = {k.lower(): v for k, v in h.items()}
    r.check(low.get("x-content-type-options") == "nosniff", "header: X-Content-Type-Options")
    r.check(low.get("x-frame-options") == "DENY", "header: X-Frame-Options")
    r.check("default-src 'self'" in low.get("content-security-policy", ""), "header: Content-Security-Policy")

    r.section("2. Security guardrails")
    s, b, _ = c.call("GET", "/..%2f..%2f..%2f..%2fetc%2fpasswd")
    r.check("root:" not in str(b), "path traversal cannot read host files")
    s, _, _ = c.call("GET", "/api/overview")
    r.check(s in (401, 403), "API refuses requests with no token", str(s))
    s, _, _ = c.call("GET", "/api/overview", token="not-a-real-token")
    r.check(s in (401, 403), "API refuses a forged token", str(s))
    s, _, _ = c.call("POST", "/api/auth/token", {"sub": "nobody-at-all"})
    r.check(s in (400, 401, 403, 404, 422), "unknown user cannot sign in", str(s))
    s, _, _ = c.call("POST", "/api/auth/token", {"sub": "demo-manager", "role": "admin"})
    r.check(s == 422, "token request rejects extra fields (no role smuggling)", str(s))

    mgr, emp = c.token("demo-manager"), c.token("demo-employee")

    r.section("3. Sign in and read models (manager)")
    s, b, _ = c.call("GET", "/api/session", token=mgr)
    r.check(s == 200 and "manager" in b.get("roles", []), "session shows manager role", str(b))
    r.check(b.get("data_classification") == "synthetic", "session labels data as synthetic", str(b))
    if b.get("data_classification") != "synthetic":
        # Hard stop, not a comment: this script writes a scratch staffing request,
        # decision and contest into whatever database it's pointed at. A docstring
        # warning is not a safety control - found during the V3 QA pass that nothing
        # actually stopped someone from running this against a real deployment.
        print("\nABORT: target database is not classified 'synthetic' - refusing to write "
              "a scratch request/decision/contest into it. Point --base at a synthetic "
              "demo instance only.")
        return 1
    mgr_code = b.get("coded_identity")
    s, b, _ = c.call("GET", "/api/overview", token=mgr)
    r.check(s == 200 and b.get("people", 0) > 0, "overview has people", str(s))
    r.check(b.get("audit_chain_verified") is True, "audit chain verified on overview")
    s, b, _ = c.call("GET", "/api/roles", token=mgr)
    roles = b.get("roles", []) if s == 200 else []
    r.check(len(roles) >= 1, "role templates available", str(s))
    s, b, _ = c.call("GET", "/api/skills", token=mgr)
    r.check(s == 200 and len(b.get("skills", [])) > 0, "skills catalogue loads")
    s, b, _ = c.call("GET", "/api/workforce", token=mgr)
    r.check(s == 200 and len(b.get("identities", [])) > 0, "workforce loads")
    s, b, _ = c.call("GET", "/api/identity/directory", token=mgr)
    people = b.get("people", []) if s == 200 else []
    names = {p["coded_identity"]: p["display_name"] for p in people}
    r.check(len(names) >= 3 and all(n for n in names.values()), "directory resolves human names", str(s))
    s, b, _ = c.call("GET", "/api/matrix/runs", token=mgr)
    r.check(s == 200, "matrix runs listed", str(s))
    s, b, _ = c.call("GET", "/api/excel-sunset", token=mgr)
    r.check(s == 200, "Excel retirement gate readable", str(s))
    s, b, _ = c.call("GET", "/api/data-quality", token=mgr)
    r.check(s == 200, "data-quality readable", str(s))

    r.section("4. Find people (rank)")
    s, _, _ = c.call("POST", "/api/fitness/rank", {"request_id": "bad id!", "required_skills": ROLE_SKILLS}, token=mgr)
    r.check(s == 422, "rank rejects malformed request id", str(s))
    s, _, _ = c.call("POST", "/api/fitness/rank", {"request_id": run_id, "required_skills": ROLE_SKILLS}, token=emp)
    r.check(s == 403, "employee cannot rank people (RBAC)", str(s))
    s, rank, _ = c.call(
        "POST", "/api/fitness/rank", {"request_id": run_id, "required_skills": ROLE_SKILLS, "shortlist_size": 5}, token=mgr
    )
    cands = rank.get("candidates", []) if s == 200 else []
    r.check(s == 200 and len(cands) >= 1, "rank returns a shortlist", f"{s}")
    scores = [x["fitness_score"] for x in cands]
    r.check(scores == sorted(scores, reverse=True), "shortlist is best-first")
    r.check([x["rank"] for x in cands] == list(range(1, len(cands) + 1)), "ranks are 1..N with no gaps")
    r.check(all(x.get("per_skill_reasoning") for x in cands), "every candidate carries reasoning (traceable)")
    r.check(all(0.0 <= x <= 1.0 for x in scores), "scores stay within 0..1")
    r.check(all(x["coded_identity"] in names for x in cands), "every ranked person has a display name")
    excluded = rank.get("excluded", []) if s == 200 else []
    r.check(all(e.get("reason") or e.get("exclusion_reason") for e in excluded), "excluded people always say why", str(excluded)[:120])

    r.section("5. Requests and decision")
    s, b, _ = c.call("GET", "/api/staffing/requests", token=mgr)
    listed = b.get("requests", []) if s == 200 else []
    stored = next((x for x in listed if x["request_id"].lower() == run_id.lower()), None)
    r.check(stored is not None, "new request appears in Requests", str([x["request_id"] for x in listed])[:120])
    rid = stored["request_id"] if stored else run_id
    s, b, _ = c.call("GET", f"/api/staffing/requests/{rid}", token=mgr)
    r.check(s == 200 and b.get("result", {}).get("candidates"), "request detail replays the ranking", str(s))
    s, _, _ = c.call("GET", f"/api/staffing/requests/{rid}", token=emp)
    r.check(s == 403, "employee cannot open a staffing request", str(s))
    top = cands[0]["coded_identity"] if cands else None
    s, _, _ = c.call("POST", f"/api/staffing/{rid}/decision", {"status": "accepted"}, token=mgr)
    r.check(s in (400, 422), "accepting without choosing a person is refused", str(s))
    s, b, _ = c.call(
        "POST", f"/api/staffing/{rid}/decision", {"status": "accepted", "chosen_coded_identity": top}, token=mgr
    )
    r.check(s == 200, "manager records the decision", f"{s} {b}")
    s, b, _ = c.call("GET", f"/api/staffing/requests/{rid}", token=mgr)
    dec = (b.get("decision") or {}) if s == 200 else {}
    r.check(dec.get("status") == "accepted" and dec.get("chosen_coded_identity") == top, "decision is stored and shown", str(dec))
    other = c.token("demo-manager-2")
    s, _, _ = c.call("POST", f"/api/staffing/{rid}/decision", {"status": "rejected"}, token=other)
    r.check(s in (403, 404), "a different manager cannot decide someone else's request", str(s))

    r.section("6. Learning gaps")
    if roles and top:
        role = roles[0]
        s, b, _ = c.call(
            "POST",
            "/api/fitness/gaps",
            {
                "coded_identity": top,
                "role_id": role["role_id"],
                "role_name": role["role_name"],
                "required_skills": role["required_skills"],
            },
            token=mgr,
        )
        r.check(s == 200, "gap analysis for the top candidate", f"{s} {str(b)[:100]}")

    r.section("7. Team skills and update a skill")
    s, b, _ = c.call("GET", "/api/identities", token=mgr)
    r.check(s == 200, "team identities visible to manager", str(s))
    declared = False
    denied = False
    for code in names:
        s, b, _ = c.call(
            "POST",
            "/api/team/declare",
            {"coded_identity": code, "skill_id": "azure_networking", "proficiency": 2, "note": "smoke test"},
            token=mgr,
        )
        declared |= s == 200
        denied |= s == 403
    r.check(declared, "manager can update a report's skill")
    r.check(denied, "manager cannot update someone outside their team")
    s, _, _ = c.call(
        "POST",
        "/api/team/declare",
        {"coded_identity": mgr_code or "EMP-00000000", "skill_id": "azure_networking", "proficiency": 99},
        token=mgr,
    )
    r.check(s in (400, 403, 422), "impossible proficiency level is refused", str(s))

    r.section("8. Employee view and contest")
    s, b, _ = c.call("GET", "/api/me", token=emp)
    r.check(s == 200 and "skills" in b, "employee sees their own skills", str(s))
    s, _, _ = c.call("GET", "/api/dashboard", token=emp)
    r.check(s == 403, "employee cannot open the manager dashboard", str(s))
    s, me, _ = c.call("GET", "/api/me", token=emp)
    own_skill = me["skills"][0]["skill_id"] if s == 200 and me.get("skills") else None
    s, b, _ = c.call(
        "POST", "/api/me/contest", {"reason": "smoke test: this rating looks low", "skill_id": own_skill}, token=emp
    )
    r.check(s == 200 and b.get("contest_id"), "employee can contest a rating", f"{s} {b}")
    contest_id = b.get("contest_id") if s == 200 else None
    s, b, _ = c.call("POST", "/api/me/contest", {"reason": "smoke test: general concern"}, token=emp)
    general_id = b.get("contest_id") if s == 200 else None
    if contest_id and general_id:
        path = "/api/team/contests/{}/resolve"
        s, _, _ = c.call("POST", path.format(contest_id), {"status": "confirmed"}, token=emp)
        r.check(s == 403, "employee cannot resolve their own contest", str(s))
        s, _, _ = c.call("POST", path.format(contest_id), {"status": "confirmed"}, token=c.token("demo-manager-2"))
        r.check(s in (403, 404), "a manager outside the team cannot resolve it", str(s))
        s, b, _ = c.call("POST", path.format(contest_id), {"status": "confirmed"}, token=mgr)
        r.check(s == 200, "owning manager confirms a skill-linked contest", f"{s} {b}")
        s, _, _ = c.call("POST", path.format(general_id), {"status": "confirmed"}, token=mgr)
        r.check(s == 422, "a contest with no skill cannot be 'confirmed'", str(s))
        s, _, _ = c.call("POST", path.format(general_id), {"status": "dismissed"}, token=mgr)
        r.check(s == 200, "owning manager can dismiss a general contest", str(s))

    r.section("9. Integrity after all of the above")
    s, b, _ = c.call("GET", "/api/overview", token=mgr)
    r.check(s == 200 and b.get("audit_chain_verified") is True, "audit chain still verified after every write")
    s, b, _ = c.call("GET", "/ready")
    r.check(s == 200, "service still ready")

    r.section("10. LLM assist (requests/parse) - advisory only, never breaks core Hermes")
    s, b, _ = c.call("POST", "/api/requests/parse", {"description": "need someone"}, token=emp)
    r.check(s == 403, "employee cannot use the assist endpoint (manager-only)", str(s))
    s, b, _ = c.call("POST", "/api/requests/parse", {"description": ""}, token=mgr)
    r.check(s == 422, "empty description is rejected", str(s))
    s, b, _ = c.call("POST", "/api/requests/parse", {"description": "need a python person"}, token=mgr)
    r.check(
        s == 200 and isinstance(b.get("available"), bool),
        "assist answers with a well-shaped available/proposal/reason response either way",
        f"{s} {b}",
    )
    if b.get("available") is False:
        r.check(bool(b.get("reason")), "unavailable response explains why, so the manager can continue manually")
        r.check(b.get("proposal") is None, "no partial/fabricated proposal when unavailable")
    else:
        r.check(isinstance(b.get("proposal", {}).get("skills"), list), "available response carries a skills list")

    r.section("11. Real-data governance (this demo DB must never read as real/active)")
    s, b, _ = c.call("GET", "/api/data-quality", token=mgr)
    status = (b.get("activation_status") or {}) if s == 200 else {}
    r.check(s == 200 and "state" in status, "activation_status is present", str(status))
    r.check("real_data_active" in status, "REAL_DATA_ACTIVE is reported", str(status))
    r.check(b.get("data_classification") == "synthetic", "data-quality agrees this is synthetic data", str(s))

    total = len(r.results)
    print(f"\n{total - r.failed}/{total} checks passed")
    return 1 if r.failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="base URL of the running app")
    args = ap.parse_args()
    return run(args.base)


if __name__ == "__main__":
    sys.exit(main())
