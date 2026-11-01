#!/usr/bin/env python3
"""Scenario tests for the demo organisation, through the real HTTP API.

    python -m scripts.scenario_tests --base http://127.0.0.1:8001

Each check asserts an outcome a manager or employee would actually see (who ranks first,
who is excluded and why, what an employee can and cannot see). Run it against a freshly
seeded demo database; it writes real requests, decisions and one dispute resolution.
Exit code 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

PASS, FAIL = [], []


def call(base: str, method: str, path: str, token: Optional[str] = None, body: Any = None) -> Tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw.decode()


def check(ok: bool, name: str, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    tok = lambda sub: call(base, "POST", "/api/auth/token", body={"sub": sub})[1]["access_token"]  # noqa: E731
    mgr, emp, emp2, mgr2, adm = tok("demo-manager"), tok("demo-employee"), tok("demo-employee-2"), tok("demo-manager-2"), tok("demo-admin")

    _, directory = call(base, "GET", "/api/identity/directory", mgr)
    name_of = {p["coded_identity"]: p["display_name"] for p in directory["people"]}
    code_of = {v: k for k, v in name_of.items()}
    _, roles = call(base, "GET", "/api/roles", mgr)
    role = {r["role_name"]: r for r in roles["roles"]}

    def rank(role_name: str, rid: str, size: int = 10, token: str = mgr) -> Dict[str, Any]:
        r = role[role_name]
        s, d = call(base, "POST", "/api/fitness/rank", token, {
            "request_id": rid, "required_skills": r["required_skills"], "critical_skills": r["critical_skills"],
            "role_id": r["role_id"], "shortlist_size": size,
        })
        assert s == 200, (s, d)
        return d

    order = lambda d: [name_of[c["coded_identity"]] for c in d["candidates"]]  # noqa: E731
    excl = lambda d: {name_of[e["coded_identity"]]: e["reason"] for e in d["excluded_candidates"]}  # noqa: E731
    score = lambda d, n: next(c["fitness_score"] for c in d["candidates"] if name_of[c["coded_identity"]] == n)  # noqa: E731
    detail = lambda d, n: next(c for c in d["candidates"] if name_of[c["coded_identity"]] == n)["reasoning_detail"]  # noqa: E731
    t = int(time.time())

    print("\nSetup")
    check(len(name_of) == 36, "36 people in the directory", str(len(name_of)))
    check(len(role) == 10, "10 role templates", str(len(role)))

    print("\n1 Clear winner (Senior Cloud Engineer)")
    d = rank("Senior Cloud Engineer", f"sc-1-{t}")
    check(order(d)[0] == "Priya Nair", "Priya Nair ranks first", str(order(d)[:3]))
    check(score(d, "Priya Nair") > 2 * d["candidates"][1]["fitness_score"], "lead is more than double the runner-up")

    print("\n2 Too close to call (Platform SRE Lead)")
    d = rank("Platform SRE Lead", f"sc-2-{t}")
    check(set(order(d)[:2]) == {"Marcus Webb", "Elena Petrova"}, "Marcus and Elena are the top two", str(order(d)))
    gap = abs(d["candidates"][0]["fitness_score"] - d["candidates"][1]["fitness_score"])
    check(gap < 0.01, "their scores differ by less than 0.01", f"{gap:.4f}")

    print("\n3 Missing critical skill (Firewall and Security Lead)")
    d = rank("Firewall and Security Lead", f"sc-3-{t}")
    check(order(d)[0] == "Callum Reid", "Callum Reid (has the critical skill) ranks first", str(order(d)))
    check(excl(d).get("Tomas Herrera") == "missing_critical_skill", "Tomas Herrera excluded: missing critical skill", str(excl(d).get("Tomas Herrera")))
    check("Tomas Herrera" not in order(d), "Tomas Herrera is not on the shortlist")

    print("\n4 Stale proof (Data Protection Engineer)")
    d = rank("Data Protection Engineer", f"sc-4-{t}")
    check(order(d)[:2] == ["Hannah Kim", "Walter Okafor"], "Hannah Kim beats Walter Okafor", str(order(d)))
    fr = detail(d, "Walter Okafor")["disaster_recovery"]["freshness"]
    check(fr < 0.3, "Walter's disaster-recovery proof is old (freshness < 30%)", f"{fr}")

    print("\n5 Claimed, not proven (Automation Engineer)")
    d = rank("Automation Engineer", f"sc-5-{t}")
    check(order(d)[0] == "Nina Rossi", "Nina Rossi (real tickets) ranks first", str(order(d)))
    check("Dev Malhotra" not in order(d) or score(d, "Dev Malhotra") < score(d, "Nina Rossi") / 5, "Dev Malhotra's claims score far below Nina's")

    print("\n6 Related-skill credit (Azure Platform Engineer)")
    d = rank("Azure Platform Engineer", f"sc-6-{t}")
    statuses = {n: [v["status"] for v in detail(d, n).values()] for n in order(d)}
    check(any("adjacent" in s for s in statuses.values()), "at least one candidate gets labelled partial credit")
    check(order(d)[:3] == ["Priya Nair", "Omar Haddad", "Sam Patel"], "Priya, Omar, Sam lead", str(order(d)[:4]))

    print("\n7 Single point of failure (IBM i Support Engineer)")
    d = rank("IBM i Support Engineer", f"sc-7-{t}")
    check(order(d) == ["Gregory Baptiste"], "only Gregory Baptiste qualifies", str(order(d)))

    print("\n8 Nobody fits (Multi-Cloud Architect)")
    d = rank("Multi-Cloud Architect", f"sc-8-{t}")
    check(order(d) == [], "empty shortlist", str(order(d)))
    check(len(d["excluded_candidates"]) == 36, "all 36 people are accounted for as excluded", str(len(d["excluded_candidates"])))
    s, _ = call(base, "POST", f"/api/staffing/sc-8-{t}/decision", mgr, {"status": "accepted", "chosen_coded_identity": code_of["Alex Rivera"]})
    check(s == 422, "cannot accept someone when there is no shortlist (422)", str(s))

    print("\n9 Grow someone (Mei Tanaka, Senior Cloud Engineer)")
    r = role["Senior Cloud Engineer"]
    s, g = call(base, "POST", "/api/fitness/gaps", mgr, {"coded_identity": code_of["Mei Tanaka"], "role_id": r["role_id"], "role_name": r["role_name"], "required_skills": r["required_skills"]})
    gaps = [x["skill_id"] for x in g["gaps"]]
    check(gaps == ["azure_networking"], "Mei is exactly one skill (Azure Networking) short", str(gaps))

    print("\n10 Employee disputes evidence (Sam Patel)")
    s, me = call(base, "GET", "/api/me", emp)
    check(s == 200 and len(me["contests"]) == 1 and me["contests"][0]["skill_id"] == "infrastructure_as_code", "Sam sees their own open dispute")
    sam = code_of["Sam Patel"]
    s, rev = call(base, "GET", f"/api/team/skill-review/{sam}", mgr)
    check(s == 200 and len(rev["contests"]) == 1, "their manager sees the dispute")
    s, _ = call(base, "GET", f"/api/team/skill-review/{sam}", mgr2)
    check(s == 403, "a different manager cannot see it (403)", str(s))
    before = next(m["confidence"] for m in rev["matrix"] if m["skill_id"] == "infrastructure_as_code")
    s, _ = call(base, "POST", f"/api/team/contests/{rev['contests'][0]['contest_id']}/resolve", mgr, {"status": "confirmed"})
    _, rev2 = call(base, "GET", f"/api/team/skill-review/{sam}", mgr)
    after = next(m["confidence"] for m in rev2["matrix"] if m["skill_id"] == "infrastructure_as_code")
    check(s == 200 and after > before and not rev2["contests"], "confirming raises confidence and closes the dispute", f"{before} -> {after}")
    s, _ = call(base, "POST", f"/api/team/contests/{rev['contests'][0]['contest_id']}/resolve", mgr, {"status": "confirmed"})
    check(s == 409, "resolving the same dispute twice is refused (409)", str(s))

    print("\nDecision flow and ownership")
    d = rank("Senior Cloud Engineer", f"dec-{t}", 5)
    top = d["candidates"][0]["coded_identity"]
    s, _ = call(base, "POST", f"/api/staffing/dec-{t}/decision", mgr2, {"status": "accepted", "chosen_coded_identity": top})
    check(s == 403, "another manager cannot decide my request (403)", str(s))
    s, _ = call(base, "POST", f"/api/staffing/dec-{t}/decision", mgr, {"status": "accepted", "chosen_coded_identity": code_of["Priya Nair"]})
    check(s == 200, "owner accepts the first choice", str(s))
    s, _ = call(base, "POST", f"/api/staffing/dec-{t}/decision", mgr, {"status": "rejected", "rejection_reason": "x"})
    check(s == 409, "second decision on the same request is refused (409)", str(s))
    s, _ = call(base, "POST", "/api/fitness/rank", mgr, {"request_id": f"dec-{t}", "required_skills": {"python": 3}})
    check(s == 409, "re-ranking a decided request is refused (409)", str(s))
    d = rank("Senior Cloud Engineer", f"ovr-{t}", 5)
    s, _ = call(base, "POST", f"/api/staffing/ovr-{t}/decision", mgr, {"status": "overridden", "chosen_coded_identity": d["candidates"][2]["coded_identity"], "override_note": "Mei is closest to growing into this"})
    check(s == 200, "override to a lower-ranked person is recorded", str(s))
    d = rank("Senior Cloud Engineer", f"exc-{t}", 5)
    s, _ = call(base, "POST", f"/api/staffing/exc-{t}/decision", mgr, {"status": "accepted", "chosen_coded_identity": code_of["Jordan Lee"]})
    check(s == 422, "cannot choose someone who was excluded (422)", str(s))

    print("\nEmployee isolation")
    for path in ("/api/identities", "/api/workforce", "/api/dashboard", "/api/overview", "/api/staffing/requests", "/api/identity/directory", "/api/data-quality"):
        s, _ = call(base, "GET", path, emp)
        check(s == 403, f"employee blocked from {path}", str(s))
    s, _ = call(base, "POST", "/api/fitness/rank", emp, {"request_id": "x1", "required_skills": {"python": 3}})
    check(s == 403, "employee cannot rank", str(s))
    r = role["Senior Cloud Engineer"]
    s, _ = call(base, "POST", "/api/fitness/gaps", emp, {"coded_identity": code_of["Priya Nair"], "role_id": r["role_id"], "role_name": r["role_name"], "required_skills": r["required_skills"]})
    check(s == 403, "employee cannot read another person's gaps", str(s))
    s, me2 = call(base, "GET", "/api/me", emp2)
    check(s == 200 and me2["coded_identity"] != me["coded_identity"], "second employee sees only their own record")
    s, _ = call(base, "GET", "/api/me", adm)
    check(s in (400, 403), "admin has no personal profile", str(s))
    s, _ = call(base, "GET", "/api/overview")
    check(s == 401, "no token is refused (401)", str(s))
    s, _ = call(base, "GET", "/api/overview", "not-a-token")
    check(s == 401, "garbage token is refused (401)", str(s))

    print("\nInput hardening")
    for name, body in [
        ("empty required skills", {"request_id": f"bad-1-{t}", "required_skills": {}}),
        ("unknown skill", {"request_id": f"bad-2-{t}", "required_skills": {"not_a_skill": 3}}),
        ("level 9", {"request_id": f"bad-3-{t}", "required_skills": {"python": 9}}),
        ("bad request id", {"request_id": "../../etc/passwd", "required_skills": {"python": 3}}),
    ]:
        s, _ = call(base, "POST", "/api/fitness/rank", mgr, body)
        check(s in (400, 422), f"rejects {name}", str(s))
    s, big = call(base, "POST", "/api/fitness/rank", mgr, {"request_id": f"cap-{t}", "required_skills": {"python": 1}, "shortlist_size": 500})
    check(s == 200 and len(big["candidates"]) <= 10, "an absurd shortlist size is capped by the engine, not honoured", str(len(big["candidates"])) if s == 200 else str(s))
    s, _ = call(base, "POST", "/api/me/contest", emp, {"reason": "x" * 5000})
    check(s == 422, "rejects a 5,000 character dispute", str(s))
    s, _ = call(base, "POST", "/api/copilot/ask", mgr, {"question": ""})
    check(s == 422, "copilot rejects an empty question", str(s))

    print("\nWorkflow: employees propose, managers decide")
    sam = me["coded_identity"]
    _, sess = call(base, "GET", "/api/session", mgr)
    _, ev0 = call(base, "GET", "/api/me", emp)
    s, r1 = call(base, "POST", "/api/me/requests", emp, {"kind": "skill_claim", "skill_id": "python", "proficiency": 4, "note": f"scenario {t}"})
    check(s == 200 and r1["status"] == "pending", "an employee proposal starts as pending", str(s))
    _, ev1 = call(base, "GET", "/api/me", emp)
    check(len(ev1["evidence"]) == len(ev0["evidence"]), "a pending proposal changes nothing on the record")
    s, dup = call(base, "POST", "/api/me/requests", emp, {"kind": "skill_claim", "skill_id": "python", "proficiency": 4})
    check(s == 409, "the same proposal cannot be sent twice", str(s))
    s, inbox = call(base, "GET", "/api/team/inbox", mgr)
    check(s == 200 and any(x["request_id"] == r1["request_id"] for x in inbox["requests"]), "the manager sees it in Approvals")
    s, inbox2 = call(base, "GET", "/api/team/inbox", mgr2)
    check(s == 200 and not any(x["request_id"] == r1["request_id"] for x in inbox2["requests"]), "another manager does not see it")
    s, _ = call(base, "POST", f"/api/team/inbox/{r1['request_id']}/decide", mgr2, {"decision": "approve", "proficiency": 3})
    check(s == 403, "another manager cannot approve it", str(s))
    s, _ = call(base, "GET", "/api/team/inbox", emp)
    check(s == 403, "an employee cannot open Approvals", str(s))
    s, done = call(base, "POST", f"/api/team/inbox/{r1['request_id']}/decide", mgr, {"decision": "approve", "proficiency": 3})
    check(s == 200 and done["status"] == "approved", "the manager approves at the level they confirm", str(s))
    _, ev2 = call(base, "GET", "/api/me", emp)
    check(any(e["skill_id"] == "python" and e["evidence_type"] == "declared" for e in ev2["evidence"]), "approval records a manager-confirmed claim")
    s, _ = call(base, "POST", f"/api/team/inbox/{r1['request_id']}/decide", mgr, {"decision": "approve", "proficiency": 3})
    check(s == 409, "an answered request cannot be answered again", str(s))

    s, c1r = call(base, "POST", "/api/me/requests", emp, {"kind": "certificate", "cert_code": "CKA", "earned_at": "2025-03-01"})
    check(s == 200, "an employee can submit a certificate with its date", str(s))
    s, _ = call(base, "POST", "/api/me/requests", emp, {"kind": "certificate", "cert_code": "CKA", "earned_at": "2999-01-01"})
    check(s in (409, 422), "a certificate dated in the future is refused", str(s))
    s, cd = call(base, "POST", f"/api/team/inbox/{c1r['request_id']}/decide", mgr, {"decision": "approve"})
    check(s == 200, "approving a certificate runs the governed date-and-promote path", str(s))
    _, ev3 = call(base, "GET", "/api/me", emp)
    check(any(e["evidence_type"] == "certified" for e in ev3["evidence"]), "the certificate now counts as proof")

    s, r3 = call(base, "POST", "/api/me/requests", emp, {"kind": "skill_check", "skill_id": "ansible"})
    check(s == 200, "an employee can ask for a skill check", str(s))
    s, wd = call(base, "POST", f"/api/me/requests/{r3['request_id']}/withdraw", emp)
    check(s == 200 and wd["status"] == "withdrawn", "an employee can withdraw a pending request", str(s))
    s, bad = call(base, "POST", "/api/me/requests", emp, {"kind": "skill_claim", "skill_id": "python", "proficiency": 4, "coded_identity": "EMP-00000000"})
    check(s == 422, "a request cannot name someone else (no identity smuggling)", str(s))

    s, goal_roles = call(base, "GET", "/api/roles", emp)
    first_role = goal_roles["roles"][0]["role_id"]
    s, _ = call(base, "PUT", "/api/me/goal", emp, {"role_id": first_role})
    check(s == 200, "an employee can set a growth goal", str(s))
    s, wf = call(base, "GET", "/api/me/workflow", emp)
    check(s == 200 and wf["goal"] and wf["goal"]["role_id"] == first_role, "the goal is remembered")
    s, _ = call(base, "DELETE", "/api/me/goal", emp)
    check(s == 200, "the goal can be cleared", str(s))
    s, tl = call(base, "GET", "/api/me/timeline", emp)
    check(s == 200 and any(e["event_type"] == "employee_request_submitted" for e in tl["events"]), "the employee timeline shows what happened")
    s, tl2 = call(base, "GET", "/api/me/timeline", emp2)
    check(s == 200 and not any(e["event_type"] == "employee_request_submitted" for e in tl2["events"]), "another employee's timeline shows none of it")

    print("\nManager tools: bulk update, what-if, custom roles")
    s, grid = call(base, "GET", "/api/team/grid", mgr)
    check(s == 200 and sam in grid["people"] and sess["coded_identity"] not in grid["people"], "the team grid covers direct reports only")
    s, _ = call(base, "GET", "/api/team/grid", emp)
    check(s == 403, "an employee cannot open the team grid", str(s))
    _, ev_b = call(base, "GET", "/api/me", emp)
    s, _ = call(base, "POST", "/api/team/bulk-declare", mgr, {"items": [
        {"coded_identity": sam, "skill_id": "bash_scripting", "proficiency": 3},
        {"coded_identity": sess["coded_identity"], "skill_id": "bash_scripting", "proficiency": 3}]})
    check(s == 403, "a bulk update with one person off the team is refused whole", str(s))
    _, ev_c = call(base, "GET", "/api/me", emp)
    check(len(ev_c["evidence"]) == len(ev_b["evidence"]), "...and nothing at all was written")
    s, bulk = call(base, "POST", "/api/team/bulk-declare", mgr, {"items": [{"coded_identity": sam, "skill_id": "bash_scripting", "proficiency": 3}]})
    check(s == 200 and bulk["saved"] == 1, "a valid bulk update is saved", str(s))
    s, _ = call(base, "POST", "/api/team/bulk-declare", mgr, {"items": [{"coded_identity": sam, "skill_id": "not_a_skill", "proficiency": 3}]})
    check(s == 422, "a bulk update with an unknown skill is refused", str(s))

    _, reqs_before = call(base, "GET", "/api/staffing/requests", mgr)
    sr = role["Senior Cloud Engineer"]
    body = {"request_id": f"whatif-{t}", "required_skills": sr["required_skills"], "critical_skills": sr["critical_skills"], "shortlist_size": 5}
    s, pv = call(base, "POST", "/api/fitness/preview", mgr, body)
    _, reqs_after = call(base, "GET", "/api/staffing/requests", mgr)
    check(s == 200 and len(reqs_after["requests"]) == len(reqs_before["requests"]), "a what-if preview creates no request")
    real = rank("Senior Cloud Engineer", f"whatif-real-{t}", size=5)
    check(order(pv) == order(real), "the preview ranks exactly like the real thing")
    s, _ = call(base, "POST", "/api/fitness/preview", emp, body)
    check(s == 403, "an employee cannot run a what-if", str(s))

    s, cr = call(base, "POST", "/api/roles/custom", mgr, {"role_name": f"Scenario role {t}", "required_skills": {"python": 3, "ansible": 3}, "critical_skills": ["python"], "min_coverage_ratio": 0.5})
    check(s == 200 and cr["role_id"].startswith("custom_"), "a manager can save a custom role", str(s))
    _, rl = call(base, "GET", "/api/roles", emp)
    check(any(r["role_id"] == cr["role_id"] for r in rl["roles"]), "employees can then aim for it")
    s, _ = call(base, "POST", "/api/roles/custom", mgr, {"role_name": "Bad role", "required_skills": {"python": 3}, "critical_skills": ["ansible"]})
    check(s == 422, "a critical skill the role does not list is refused", str(s))
    s, _ = call(base, "DELETE", "/api/roles/custom/senior_cloud_engineer", mgr)
    check(s == 422, "seeded roles cannot be deleted", str(s))
    s, _ = call(base, "DELETE", f"/api/roles/custom/{cr['role_id']}", mgr)
    check(s == 200, "a custom role can be deleted", str(s))
    s, _ = call(base, "POST", "/api/roles/custom", emp, {"role_name": "Nope", "required_skills": {"python": 3}})
    check(s == 403, "an employee cannot create roles", str(s))

    print("\nCopilot (real model if Ollama is up, otherwise the offline path)")
    s, c1 = call(base, "POST", "/api/copilot/ask", mgr, {"question": "Which skills have only one person who can do them?"})
    check(s == 200 and c1["source"] in ("model", "offline") and c1["answer"].strip() != "", "manager gets an answer", c1.get("source", "") if isinstance(c1, dict) else str(c1))
    if isinstance(c1, dict) and c1.get("source") == "model":
        check("Gregory Baptiste" in c1["answer"], "answer names a real single-holder (Gregory Baptiste)")
    s, c2 = call(base, "POST", "/api/copilot/ask", emp, {"question": "Which role am I closest to?"})
    ans = c2["answer"] if isinstance(c2, dict) else str(c2)
    check(s == 200 and "Azure Platform Engineer" in ans, "employee is told Azure Platform Engineer", ans[:80])
    check(not any(n in ans for n in ("Priya Nair", "Walter Okafor")), "employee answer names nobody else")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
