"""HOI integration tests: opportunity -> extraction -> approval -> matching -> costing -> scenarios -> approvals -> export.

All data is synthetic. SECRET_COST is a distinctive value used to prove compensation never leaks.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from scripts.seed_demo_org import seed
from shared.db import HermesDB

ROOT = Path(__file__).resolve().parents[2]
SOW = (ROOT / "data" / "fixtures" / "hoi" / "sample_sow.txt").read_bytes()
BENCH = (ROOT / "data" / "fixtures" / "hoi" / "market_benchmarks_synthetic.csv").read_text()
SECRET_COST = "7013.37"
BAND_COST = "6111.11"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db_path = tmp_path / "hoi.db"
    seed(db_path)
    monkeypatch.setenv("HERMES_DB_PATH", str(db_path))
    monkeypatch.setenv("HOI_STORAGE_DIR", str(tmp_path / "store"))
    for k in ("HERMES_API_KEY", "FUNCTION_AUTH_KEY", "HERMES_ENV"):
        monkeypatch.delenv(k, raising=False)
    db = HermesDB(db_path)
    for c in db.load_skills_matrix():  # synthetic capacity: everyone fully available
        db.set_availability(c.coded_identity, True, 1.0)
    api_main.reset_service_for_tests(None)
    with TestClient(api_main.app) as client:
        yield client, db_path
    api_main.reset_service_for_tests(None)


def H(client, sub):
    r = client.post("/api/auth/token", json={"sub": sub})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


OPP = {"client_alias": "Northstar", "name": "Cloud Modernisation", "currency": "USD", "contract_type": "time_and_materials",
       "duration_months": 6, "geography": "Remote (EU time zones)", "start_date": "2027-01-11", "is_synthetic": True}


def new_opp(client, owner="demo-sales", members=("demo-manager", "demo-finance", "demo-hr")):
    h = H(client, owner)
    r = client.post("/api/opportunities", json=OPP, headers=h)
    assert r.status_code == 201, r.text
    oid = r.json()["opportunity_id"]
    roles = {"demo-manager": "manager", "demo-finance": "finance", "demo-hr": "hr", "demo-sales-2": "sales"}
    for m in members:
        assert client.post(f"/api/opportunities/{oid}/members", json={"sub": m, "member_role": roles[m]}, headers=h).status_code == 200
    return oid, h


def upload(client, oid, h, data=SOW, name="sample_sow.txt", dt="sow"):
    return client.post(f"/api/opportunities/{oid}/documents", json={"doc_type": dt, "filename": name, "content_b64": b64(data)}, headers=h)


def extract(client, oid, h):
    r = client.post(f"/api/opportunities/{oid}/extract", json={}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["current"]


def fix_and_approve(client, oid, h, cur=None, mutate=None):
    """Human review: set the level the document never stated, resolve/dismiss the unmapped skill, approve."""
    cur = cur or client.get(f"/api/opportunities/{oid}/requirements", headers=h).json()["current"]
    roles = cur["roles"]
    for r in roles:
        for s in r["skills"]:
            if s["taxonomy_status"] == "unmapped":
                s["dismissed"] = True
            elif s["level"] is None:
                s["level"] = 3
    if mutate:
        mutate(roles)
    u = client.put(f"/api/opportunities/{oid}/requirements/{cur['version_id']}", json={"roles": roles}, headers=h)
    assert u.status_code == 200, u.text
    a = client.post(f"/api/opportunities/{oid}/requirements/approve", json={"version_id": cur["version_id"]}, headers=h)
    assert a.status_code == 200, a.text
    return a.json()["current"]


def finance_setup(client, coded_ids=(), policy=None, role_costs=True):
    f = H(client, "demo-finance")
    pol = policy if policy is not None else {"overhead_pct": "10", "contingency_pct": "5", "training_per_fte": "500",
                                             "internal_lead_weeks": 2}
    assert client.put("/api/finance/cost-policies/POL-2026", json={"payload": pol}, headers=f).status_code == 200
    rates = {"Senior Cloud Engineer": "13000", "Platform SRE Lead": "15000"}
    assert client.put("/api/finance/rate-cards/RATE-01", json={"payload": {"currency": "USD", "unit": "month", "rates": rates}}, headers=f).status_code == 200
    rows = [{"scope": "individual", "subject": c, "monthly_cost": SECRET_COST, "currency": "USD", "effective_from": "2026-01-01", "source": "FIN-CERT-1"}
            for c in coded_ids]
    if role_costs:
        rows += [{"scope": "role_band", "subject": "Senior Cloud Engineer", "monthly_cost": BAND_COST, "currency": "USD", "effective_from": "2026-01-01", "source": "FIN-BAND-1"},
                 {"scope": "role_band", "subject": "Platform SRE Lead", "monthly_cost": "7222.22", "currency": "USD", "effective_from": "2026-01-01", "source": "FIN-BAND-1"}]
    assert client.post("/api/finance/loaded-costs", json={"rows": rows}, headers=f).status_code == 201
    assert client.post("/api/market/benchmarks/import", json={"csv_text": BENCH, "declare_synthetic": True}, headers=f).status_code == 201
    return f


def matched(client, oid, h):
    m = H(client, "demo-manager")
    r = client.post(f"/api/opportunities/{oid}/internal-match", json={}, headers=m)
    assert r.status_code == 200, r.text
    return r.json(), m


SC = {"cost_policy_id": "POL-2026", "rate_card_id": "RATE-01"}


# ============================================================ opportunities and isolation
def test_create_and_isolation(env):
    client, _ = env
    oid, h = new_opp(client)
    assert client.get(f"/api/opportunities/{oid}", headers=h).status_code == 200
    other = H(client, "demo-sales-2")
    assert client.get(f"/api/opportunities/{oid}", headers=other).status_code == 404  # not 403: existence not disclosed
    assert oid not in [o["opportunity_id"] for o in client.get("/api/opportunities", headers=other).json()["opportunities"]]
    assert client.get(f"/api/opportunities/{oid}/audit", headers=other).status_code == 404
    assert client.get(f"/api/opportunities/{oid}/documents", headers=other).status_code == 404
    emp = H(client, "demo-employee")
    assert client.get("/api/opportunities", headers=emp).status_code == 403
    assert client.post("/api/opportunities", json=OPP, headers=emp).status_code == 403
    assert client.post("/api/opportunities", json={**OPP, "duration_months": 0}, headers=h).status_code == 422
    assert client.post("/api/opportunities", json={**OPP, "currency": "US"}, headers=h).status_code == 422
    # only the owner manages the deal team; a member cannot add people
    assert client.post(f"/api/opportunities/{oid}/members", json={"sub": "demo-sales-2", "member_role": "sales"},
                       headers=H(client, "demo-manager")).status_code in (403, 404)


# ============================================================ documents
def docx_bytes(extra=None, body="Role: Cloud Engineer"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<w:document><w:body><w:p><w:r><w:t>{body}</w:t></w:r></w:p></w:body></w:document>')
        for n, c in (extra or {}).items():
            z.writestr(n, c)
    return buf.getvalue()


def test_upload_validation(env, tmp_path):
    client, _ = env
    oid, h = new_opp(client)
    bad = [("evil.exe", b"MZ\x90\x00", "sow"), ("a.txt", b"", "sow"), ("a.csv", b"x", "sow"), ("a.txt", b"hi", "invoice"),
           ("a.pdf", b"not a pdf", "sow"), ("a.pdf", b"%PDF-1.4 /JavaScript (x)", "sow"), ("a.docx", b"PK\x03\x04junk", "sow"),
           ("a.docx", docx_bytes({"word/vbaProject.bin": "x"}), "sow"), ("a.txt", b"abc\x00def", "sow"),
           ("a.txt", b"#!/bin/sh\nrm -rf", "sow")]
    for name, data, dt in bad:
        r = upload(client, oid, h, data, name, dt)
        assert r.status_code == 422, (name, r.text)
    assert client.post(f"/api/opportunities/{oid}/documents", json={"doc_type": "sow", "filename": "a.txt", "content_b64": "!!!notb64"}, headers=h).status_code == 422
    # employees and cross-deal users cannot upload
    assert upload(client, oid, H(client, "demo-sales-2")).status_code == 404
    assert upload(client, oid, H(client, "demo-finance")).status_code == 403


def test_upload_governance_and_encryption(env):
    client, _ = env
    oid, h = new_opp(client)
    d1 = upload(client, oid, h, name="../../etc/sample sow!.txt").json()
    assert "/" not in d1["filename"] and ".." not in d1["filename"]
    assert d1["version"] == 1 and len(d1["checksum"]) == 64 and d1["scan_status"] == "not_scanned" and d1["text_status"] == "ok"
    assert "restricted_uri" not in d1
    d2 = upload(client, oid, h, SOW + b"\nAddendum: revised commercial terms.\n", "../../etc/sample sow!.txt").json()
    assert d2["version"] == 2 and "duplicate" not in d2  # changed content under the same name is a new version
    files = list(Path(client.app.state.__dict__.get("x", "")).parents) if False else None
    store = Path(__import__("os").environ["HOI_STORAGE_DIR"])
    blobs = [p for p in store.rglob("*.enc")]
    assert len(blobs) == 2 and all(b"Senior Cloud Engineer" not in p.read_bytes() for p in blobs)  # encrypted at rest
    assert oct(blobs[0].stat().st_mode & 0o777) == "0o600"


def test_pdf_without_text_is_flagged_needs_ocr_not_invented(env):
    client, _ = env
    oid, h = new_opp(client)
    d = upload(client, oid, h, b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", "scan.pdf").json()
    assert d["text_status"] == "needs_ocr"
    r = client.post(f"/api/opportunities/{oid}/extract", json={}, headers=h)
    assert r.status_code == 422 and "extractable text" in r.json()["detail"]


def test_docx_text_extraction(env):
    client, _ = env
    oid, h = new_opp(client)
    body = "Role: Platform SRE Lead"
    d = upload(client, oid, h, docx_bytes(body=body), "x.docx").json()
    assert d["text_status"] == "ok"


# ============================================================ extraction traceability / unknown stays unknown
def test_extraction_has_verifiable_sources_and_unknowns(env):
    client, _ = env
    oid, h = new_opp(client)
    doc = upload(client, oid, h).json()
    cur = extract(client, oid, h)
    assert cur["status"] == "draft" and len(cur["roles"]) == 2
    text = SOW.decode()
    for role in cur["roles"]:
        for name, f in role["fields"].items():
            s = f["source"]
            assert s["document_id"] == doc["document_id"] and text[s["start"]:s["end"]] == s["quote"], name
            assert 0 < f["confidence"] <= 1
        for s in role["skills"]:
            assert text[s["source"]["start"]:s["source"]["end"]] == s["source"]["quote"]
    cloud = cur["roles"][0]
    assert cloud["headcount"] == 2 and cloud["fte"] == "1" and cloud["constraints"]["mandatory_certifications"] == ["Azure Administrator Associate (AZ-104)"]
    assert cloud["constraints"]["years_experience_min"] == 6
    sre = cur["roles"][1]
    unk = [s for s in sre["skills"] if s["text"] == "Quantum Compliance Mesh"][0]
    assert unk["taxonomy_status"] == "unmapped" and unk["skill_id"] is None and unk["level"] is None
    pref = [s for s in sre["skills"] if s["text"] == "Container Orchestration"][0]
    assert pref["level"] is None and pref["criticality"] == "preferred"  # level not stated -> unknown, never defaulted
    assert any(p.startswith("role[2]:skill_unmapped") for p in cur["blocking_problems"])
    assert any(p.endswith("skill_level_unknown:container_orchestration") for p in cur["blocking_problems"])


def test_missing_fields_stay_unknown_and_bad_dates_rejected(env):
    client, _ = env
    txt = b"Role: Network Engineer\nMust-have skills: Cisco Networking (level 3)\nStart date: 2027-13-45\nFTE: 7\n"
    oid, h = new_opp(client)
    upload(client, oid, h, txt, "jd.txt", "jd")
    cur = extract(client, oid, h)
    r = cur["roles"][0]
    assert r["headcount"] is None and r["fte"] is None and r["start_date"] is None and r["location"] is None
    assert any(n.startswith("rejected_date") for n in cur["notes"]) and any(n.startswith("rejected_fte") for n in cur["notes"])
    ap = client.post(f"/api/opportunities/{oid}/requirements/approve", json={"version_id": cur["version_id"]}, headers=h)
    assert ap.status_code == 422 and "headcount_unknown" in ap.json()["detail"] and "fte_unknown" in ap.json()["detail"]


def test_llm_assist_rejects_unverifiable_output(env):
    client, _ = env
    oid, h = new_opp(client)
    upload(client, oid, h)

    class Fake:
        def generate(self, prompt, *, system=None, timeout=30.0):
            return json.dumps({"roles": [{"role": "Senior Cloud Engineer", "skills": [
                {"skill": "Kubernetes Wizardry", "criticality": "must", "quote": "this sentence is not in the document"},
                {"skill": "Monitoring", "criticality": "must", "quote": "Monitoring (level 3)"}]}]})

    import api.dependencies as deps
    deps.reset_llm_provider_for_tests(Fake())
    try:
        r = client.post(f"/api/opportunities/{oid}/extract", json={"use_llm": True}, headers=h)
    finally:
        deps.reset_llm_provider_for_tests(None)
    cur = r.json()["current"]
    assert cur["extraction_method"] == "rules+llm"
    assert any(n.startswith("llm_rejected_unverifiable_skill:Kubernetes") for n in cur["notes"])
    assert all("Kubernetes Wizardry" != s["text"] for rl in cur["roles"] for s in rl["skills"])


# ============================================================ human approval gate
def test_unapproved_requirements_never_reach_matching_or_scenarios(env):
    client, _ = env
    oid, h = new_opp(client)
    upload(client, oid, h)
    cur = extract(client, oid, h)
    m = H(client, "demo-manager")
    r = client.post(f"/api/opportunities/{oid}/internal-match", json={}, headers=m)
    assert r.status_code == 409 and r.json()["error"] == "requirements_not_approved"
    r = client.post(f"/api/opportunities/{oid}/internal-match", json={"version_id": cur["version_id"]}, headers=m)
    assert r.status_code == 409  # naming the draft explicitly does not bypass the gate
    finance_setup(client)
    r = client.post(f"/api/opportunities/{oid}/scenarios/compare", json=SC, headers=m)
    assert r.status_code == 409 and r.json()["error"] == "requirements_not_approved"
    assert client.post(f"/api/opportunities/{oid}/market-analysis", headers=m).status_code == 409
    ok = client.post(f"/api/opportunities/{oid}/requirements/approve", json={"version_id": cur["version_id"]}, headers=h)
    assert ok.status_code == 422  # unmapped skill + unknown levels block approval
    assert client.get(f"/api/opportunities/{oid}/shortlist", headers=m).json()["requirements"] == []


def test_approved_version_is_immutable_and_revision_creates_new(env):
    client, _ = env
    oid, h = new_opp(client)
    upload(client, oid, h)
    cur = fix_and_approve(client, oid, h, extract(client, oid, h))
    assert cur["status"] == "approved" and len(cur["content_hash"]) == 64 and cur["approved_by"] == "demo-sales"
    r = client.put(f"/api/opportunities/{oid}/requirements/{cur['version_id']}", json={"roles": cur["roles"]}, headers=h)
    assert r.status_code == 409
    rev = client.post(f"/api/opportunities/{oid}/requirements/revise", headers=h).json()["current"]
    assert rev["status"] == "draft" and rev["version_no"] == cur["version_no"] + 1
    assert client.post(f"/api/opportunities/{oid}/requirements/revise", headers=h).status_code == 409
    # matching still uses the approved version, not the draft
    res, _m = matched(client, oid, h)
    assert res["requirement_version_id"] == cur["version_id"]


# ============================================================ internal matching
def test_internal_match_coded_deterministic_and_matches_engine(env):
    client, db_path = env
    oid, h = new_opp(client)
    upload(client, oid, h)
    cur = fix_and_approve(client, oid, h, extract(client, oid, h))
    r1, m = matched(client, oid, h)
    r2, _ = matched(client, oid, h)
    assert r1["match_run_id"] != r2["match_run_id"]
    for a, b in zip(r1["requirements"], r2["requirements"]):
        assert [(c["coded_identity"], c["rank"], c["fitness_score"]) for c in a["candidates"]] == \
               [(c["coded_identity"], c["rank"], c["fitness_score"]) for c in b["candidates"]]
    blob = json.dumps(r1)
    for name in ("Alex Rivera", "Jordan Lee", "Sam Patel"):
        assert name not in blob
    # regression: HOI fitness == the existing engine run directly on the same requirement
    from shared.models import ProficiencyLevel, StaffingRequest
    from shared.service import HermesService
    svc = HermesService(db=HermesDB(db_path), mapping_secret="hermes-test-mode-secret-not-for-prod")
    role = cur["roles"][0]
    live = [s for s in role["skills"] if not s["dismissed"]]
    direct = svc.preview_rank(StaffingRequest(request_id="x", requester_id="t", required_skills={s["skill_id"]: ProficiencyLevel(s["level"]) for s in live}, shortlist_size=10, availability_required=False),
                              critical_skills=[s["skill_id"] for s in live if s["criticality"] == "must"])
    hoi = r1["requirements"][0]["candidates"]
    assert [(c.coded_identity, c.fitness_score) for c in direct.candidates] == [(c["coded_identity"], c["fitness_score"]) for c in hoi]
    assert hoi[0]["explanation"] and hoi[0]["evidence_ids"]


def test_compensation_never_changes_fitness_ranking(env):
    client, _ = env
    oid, h = new_opp(client)
    upload(client, oid, h)
    fix_and_approve(client, oid, h, extract(client, oid, h))
    first, _ = matched(client, oid, h)
    ids = [c["coded_identity"] for c in first["requirements"][0]["candidates"]]
    finance_setup(client, ids, role_costs=True)
    f = H(client, "demo-finance")
    # wildly different pay, reversed against rank
    rows = [{"scope": "individual", "subject": c, "monthly_cost": str(1000 * (i + 1) * 17), "currency": "USD", "effective_from": "2026-06-01", "source": "FIN-2"}
            for i, c in enumerate(ids)]
    assert client.post("/api/finance/loaded-costs", json={"rows": rows}, headers=f).status_code == 201
    second, _ = matched(client, oid, h)
    key = lambda res: [[(c["coded_identity"], c["rank"], c["fitness_score"]) for c in r["candidates"]] for r in res["requirements"]]
    assert key(first) == key(second)


def test_eligibility_constraints_are_separate_pass_fail(env):
    client, db_path = env
    oid, h = new_opp(client)
    upload(client, oid, h)

    def mut(roles):
        roles[0]["constraints"]["location_mandatory"] = True
    fix_and_approve(client, oid, h, extract(client, oid, h), mut)
    res, _ = matched(client, oid, h)
    cloud = res["requirements"][0]
    assert cloud["candidates"] and all(c["eligibility"] in ("ineligible", "unverified") for c in cloud["candidates"])
    # mandatory certificate (AZ-104): a check passes if and only if a CERTIFIED evidence record with that code exists
    con = sqlite3.connect(db_path)
    holders = {r[0] for r in con.execute("SELECT coded_identity FROM evidence_staging WHERE evidence_type='certified' AND source_ref='AZ-104'")}
    con.close()
    seen = set()
    for c in cloud["candidates"]:
        k = next(k for k in c["checks"] if k["check"].startswith("certification"))
        assert (k["status"] == "pass") == (c["coded_identity"] in holders), c["coded_identity"]
        seen.add(k["status"])
    assert "fail" in seen  # some shortlisted candidates genuinely lack it
    # SRE role (no mandatory constraints): with capacity zeroed the top candidate becomes ineligible
    sre = res["requirements"][1]
    top = sre["candidates"][0]["coded_identity"]
    HermesDB(db_path).set_availability(top, False, 0.0)
    res2, _ = matched(client, oid, h)
    t2 = {c["coded_identity"]: c for c in res2["requirements"][1]["candidates"]}[top]
    assert t2["eligibility"] == "ineligible" and any(k["check"] == "capacity" and k["status"] == "fail" for k in t2["checks"])
    # fitness itself still reflects the existing engine (eligibility is separate)
    assert t2["rank"] >= 1


def test_shortlist_redacted_for_non_delivery_and_name_reveal_only_via_gateway(env):
    client, _ = env
    oid, h = new_opp(client)
    upload(client, oid, h)
    fix_and_approve(client, oid, h, extract(client, oid, h))
    res, m = matched(client, oid, h)
    for sub in ("demo-sales", "demo-finance", "demo-hr"):
        s = client.get(f"/api/opportunities/{oid}/shortlist", headers=H(client, sub)).json()
        assert s["redacted"] is True and "candidates" not in json.dumps(s)
    assert client.post(f"/api/opportunities/{oid}/internal-match", json={}, headers=h).status_code == 403  # sales cannot match
    rid = res["requirements"][0]["staffing_request_id"]
    ok = client.post("/api/identity/resolve", json={"request_id": rid}, headers=m)
    assert ok.status_code == 200 and ok.json()["resolved"]
    assert client.post("/api/identity/resolve", json={"request_id": rid}, headers=H(client, "demo-manager-2")).status_code == 403
    assert client.post("/api/identity/resolve", json={"request_id": rid}, headers=h).status_code == 403


# ============================================================ costing
def single_role_opp(client, months=6):
    oid, h = new_opp(client)
    txt = b"Role: Senior Cloud Engineer\nHeadcount: 1\nFTE: 1\nLocation: Remote (EU time zones)\nMust-have skills: Container Orchestration (level 3)\n"
    upload(client, oid, h, txt, "one.txt", "jd")
    fix_and_approve(client, oid, h, extract(client, oid, h))
    return oid, h


def test_illustrative_cost_example_matches_design(env):
    client, _ = env
    oid, h = single_role_opp(client)
    f = H(client, "demo-finance")
    client.put("/api/finance/cost-policies/ZERO", json={"payload": {}}, headers=f)
    client.put("/api/finance/rate-cards/R12", json={"payload": {"currency": "USD", "unit": "month", "rates": {"Senior Cloud Engineer": "12000"}}}, headers=f)
    client.post("/api/finance/loaded-costs", json={"rows": [{"scope": "role_band", "subject": "Senior Cloud Engineer", "monthly_cost": "7000", "currency": "USD", "effective_from": "2026-01-01", "source": "S"}]}, headers=f)
    client.post("/api/market/benchmarks/import", json={"csv_text": BENCH, "declare_synthetic": True}, headers=f)
    res, m = matched(client, oid, h)
    cand = res["requirements"][0]["candidates"][0]["coded_identity"]
    body = {"cost_policy_id": "ZERO", "rate_card_id": "R12", "project_direct_costs": "6000", "months": 6,
            "assignments": [{"requirement_id": res["requirements"][0]["requirement_id"], "resource_type": "internal", "coded_identity": cand, "fte": "1"}]}
    r = client.post(f"/api/opportunities/{oid}/scenarios", json=body, headers=m)
    assert r.status_code == 201, r.text
    # delivery manager sees margin band, never cost figures
    v = r.json()
    assert v["economics"] == {"revenue": "72000.00", "margin_band": "30-40%", "currency": "USD"}
    fin = client.get(f"/api/opportunities/{oid}/scenarios/{v['scenario_id']}", headers=f).json()
    e = fin["economics"]
    assert (e["revenue"], e["delivery_cost"], e["gross_profit"], e["gross_margin_pct"]) == ("72000.00", "48000.00", "24000.00", "33.33")
    assert e["contribution"] == "24000.00" and fin["assumptions"]["cost_basis"] and fin["calc_version"] == "hoi-calc-1.0"
    assert fin["finance"]["currency"] == "USD" and fin["finance"]["months"] == 6


def test_gross_vs_contribution_margin_and_overhead_treatment(env):
    from decimal import Decimal as D
    from hoi.costing import CostPolicy, Line, calculate
    line = [Line("r", "internal", D(1), D(10000), D(20000), "x")]
    below = calculate(line, 10, "USD", CostPolicy.from_payload("p", {"overhead_pct": "20"}))
    incogs = calculate(line, 10, "USD", CostPolicy.from_payload("p", {"overhead_pct": "20", "overhead_treatment": "in_cogs"}))
    assert below["gross_profit"] == below["contribution"] == "100000.00" and below["gross_margin_pct"] == "50.00"
    assert incogs["gross_profit"] == "80000.00" and incogs["contribution"] == "100000.00"
    assert incogs["contribution_margin_pct"] == "50.00" and incogs["gross_margin_pct"] == "40.00"
    assert below["delivery_cost"] == incogs["delivery_cost"] == "120000.00"  # overhead counted in cost-to-deliver either way


def test_currency_units_and_missing_fx(env):
    client, _ = env
    oid, h = single_role_opp(client)
    f = H(client, "demo-finance")
    client.put("/api/finance/rate-cards/RATE-01", json={"payload": {"currency": "USD", "unit": "month", "rates": {"Senior Cloud Engineer": "13000"}}}, headers=f)
    client.put("/api/finance/cost-policies/POL-EUR", json={"payload": {}}, headers=f)
    client.post("/api/finance/loaded-costs", json={"rows": [{"scope": "role_band", "subject": "Senior Cloud Engineer", "monthly_cost": "6000", "currency": "EUR", "effective_from": "2026-01-01", "source": "S"}]}, headers=f)
    res, m = matched(client, oid, h)
    req = res["requirements"][0]
    body = {"cost_policy_id": "POL-EUR", "rate_card_id": "RATE-01", "assignments": [{"requirement_id": req["requirement_id"], "resource_type": "internal", "coded_identity": req["candidates"][0]["coded_identity"], "fte": "1"}]}
    rr = client.post(f"/api/opportunities/{oid}/scenarios", json=body, headers=m)
    assert rr.status_code == 201, rr.text
    s = rr.json()
    assert s["calculable"] is False and "fx_rate_missing:EUR->USD" in s["unresolved_constraints"] and "economics" not in s
    # Finance supplies a dated rate -> converted and recorded
    client.put("/api/finance/cost-policies/POL-EUR", json={"payload": {"fx_rates": {"EUR->USD": {"rate": "1.10", "as_of": "2026-10-01", "source": "FIN-FX"}}}}, headers=f)
    s2 = client.post(f"/api/opportunities/{oid}/scenarios", json=body, headers=m).json()
    fin = client.get(f"/api/opportunities/{oid}/scenarios/{s2['scenario_id']}", headers=f).json()
    assert s2["calculable"] and fin["finance"]["breakdown"]["direct_labor_internal"] == "39600.00"  # 6000*1.10*6
    # external benchmark quoted per year is normalised to a monthly figure
    from hoi.market import monthly
    from decimal import Decimal as D
    assert monthly(D(120000), "year", D(160)) == D(10000) and monthly(D(70), "hour", D(160)) == D(11200)


# ============================================================ finance data segregation
def test_no_salary_leak_anywhere_outside_finance(env, caplog, tmp_path):
    caplog.set_level(logging.DEBUG)
    client, db_path = env
    oid, h = new_opp(client)
    upload(client, oid, h)
    fix_and_approve(client, oid, h, extract(client, oid, h))
    res, m = matched(client, oid, h)
    ids = [c["coded_identity"] for c in res["requirements"][0]["candidates"]]
    f = finance_setup(client, ids)
    cmp_ = client.post(f"/api/opportunities/{oid}/scenarios/compare", json=SC, headers=m)
    assert cmp_.status_code == 200, cmp_.text
    sid = cmp_.json()["scenarios"][0]["scenario_id"]
    surfaces = []
    for sub in ("demo-sales", "demo-manager", "demo-hr", "demo-admin"):
        hh = H(client, sub)
        for path in (f"/api/opportunities/{oid}/scenarios", f"/api/opportunities/{oid}/scenarios/{sid}", f"/api/opportunities/{oid}/audit",
                     f"/api/opportunities/{oid}/shortlist", f"/api/opportunities/{oid}", "/api/finance/summary", "/api/finance/access-log",
                     "/api/finance/cost-policies", "/api/rate-cards"):
            r = client.get(path, headers=hh)
            surfaces.append((sub, path, r.status_code, r.text))
    for sub, path, code, text in surfaces:
        assert SECRET_COST not in text and BAND_COST not in text, (sub, path)
    # raw reads are refused to everyone but Finance
    for sub in ("demo-sales", "demo-manager", "demo-hr", "demo-admin", "demo-employee"):
        assert client.get("/api/finance/loaded-costs", headers=H(client, sub)).status_code == 403
        assert client.post("/api/finance/loaded-costs", json={"rows": []}, headers=H(client, sub)).status_code in (403, 422)
    assert client.get("/api/finance/loaded-costs", headers=f).status_code == 200
    # manager sees no cost/profit/margin-% keys at all
    mv = client.get(f"/api/opportunities/{oid}/scenarios/{sid}", headers=m).json()
    assert not {"finance", "assumptions"} & set(mv) and set(mv["economics"]) == {"revenue", "margin_band", "currency"}
    assert all("monthly_cost" not in a for a in mv["assignments"])
    # global ledger, logs, and the database file never hold plaintext pay
    ledger = json.dumps([e.payload for e in api_main.get_service().audit.all_events()])
    assert SECRET_COST not in ledger and BAND_COST not in ledger
    assert SECRET_COST not in caplog.text
    con = sqlite3.connect(db_path)
    dump = "\n".join(con.iterdump())
    con.close()
    assert SECRET_COST not in dump and BAND_COST not in dump
    # reading raw costs was recorded (actor + action, never values)
    log = client.get("/api/finance/access-log", headers=H(client, "demo-hr")).json()["events"]
    assert any(e["action"] == "list_loaded_costs" and e["actor"] == "demo-finance" for e in log)


def test_audit_rejects_monetary_keys(env):
    client, _ = env
    oid, h = new_opp(client)
    hoi = __import__("api.routers.hoi", fromlist=["x"]).hoi_for(api_main.get_service())
    with pytest.raises(AssertionError):
        hoi.audit(oid, "x", "a", "o", detail={"gross_margin": 1})


# ============================================================ market intelligence
def test_market_import_provenance_and_validation(env):
    client, _ = env
    f = H(client, "demo-finance")
    assert client.post("/api/market/benchmarks/import", json={"csv_text": BENCH, "declare_synthetic": True}, headers=H(client, "demo-sales")).status_code == 403
    assert client.post("/api/market/benchmarks/import", json={"csv_text": BENCH, "declare_synthetic": True}, headers=H(client, "demo-manager")).status_code == 403
    assert client.post("/api/market/benchmarks/import", json={"csv_text": BENCH}, headers=f).status_code == 422  # must declare provenance
    ok = client.post("/api/market/benchmarks/import", json={"csv_text": BENCH, "declare_synthetic": True}, headers=f)
    assert ok.status_code == 201 and ok.json()["synthetic_rows"] == 4
    rows = client.get("/api/market/benchmarks", headers=H(client, "demo-sales")).json()["benchmarks"]
    assert len(rows) == 4
    for r in rows:
        assert r["source"] and r["as_of"] and r["currency"] and r["unit"] and r["is_synthetic"] is True and r["coverage"] == "synthetic"
        assert r["basis"] in ("salary", "contractor_cost", "bill_rate")
    assert {r["basis"] for r in client.get("/api/market/benchmarks?basis=salary", headers=f).json()["benchmarks"]} == {"salary"}
    head = BENCH.splitlines()[0]
    bad_cases = {
        "mismatch": "r,g,s,permanent,contractor_cost,USD,month,1,2,3,10,src,2026-01-01,,",
        "order": "r,g,s,contractor,contractor_cost,USD,month,5,2,3,10,src,2026-01-01,,",
        "future": "r,g,s,contractor,contractor_cost,USD,month,1,2,3,10,src,2999-01-01,,",
        "nosrc": "r,g,s,contractor,contractor_cost,USD,month,1,2,3,10,,2026-01-01,,",
        "unit": "r,g,s,contractor,contractor_cost,USD,week,1,2,3,10,src,2026-01-01,,",
    }
    before = len(client.get("/api/market/benchmarks", headers=f).json()["benchmarks"])
    for name, line in bad_cases.items():
        good = BENCH.splitlines()[1]
        r = client.post("/api/market/benchmarks/import", json={"csv_text": "\n".join([head, good, line]), "declare_synthetic": False}, headers=f)
        assert r.status_code == 422, name
    assert len(client.get("/api/market/benchmarks", headers=f).json()["benchmarks"]) == before  # atomic: good row not kept
    assert client.post("/api/market/benchmarks/import", json={"csv_text": "a,b\n1,2", "declare_synthetic": False}, headers=f).status_code == 422


def test_market_analysis_reports_unavailable_honestly(env):
    client, _ = env
    oid, h = new_opp(client)
    upload(client, oid, h)
    fix_and_approve(client, oid, h, extract(client, oid, h))
    m = H(client, "demo-manager")
    a = client.post(f"/api/opportunities/{oid}/market-analysis", headers=m).json()
    assert all(v["status"] == "unavailable" for r in a["roles"] for v in r["bases"].values())
    finance_setup(client)
    a = client.post(f"/api/opportunities/{oid}/market-analysis", headers=m).json()
    cloud = a["roles"][0]["bases"]
    assert cloud["contractor_cost"][0]["is_synthetic"] and cloud["salary"][0]["basis"] == "salary" and cloud["bill_rate"][0]["basis"] == "bill_rate"
    assert a["roles"][1]["bases"]["salary"]["status"] == "unavailable"  # no salary row for SRE: not invented


# ============================================================ scenarios
def full_flow(client):
    oid, h = new_opp(client)
    upload(client, oid, h)
    fix_and_approve(client, oid, h, extract(client, oid, h))
    res, m = matched(client, oid, h)
    ids = [c["coded_identity"] for r in res["requirements"] for c in r["candidates"][:3]]
    f = finance_setup(client, ids)
    return oid, h, m, f, res


def test_scenarios_internal_external_hybrid_without_assignment(env):
    client, db_path = env
    oid, h, m, f, res = full_flow(client)
    con = sqlite3.connect(db_path)
    before = con.execute("SELECT COUNT(*), COALESCE(SUM(allocation),0) FROM availability").fetchone()
    reqs_before = con.execute("SELECT COUNT(*) FROM staffing_requests WHERE status!='open'").fetchone()
    r = client.post(f"/api/opportunities/{oid}/scenarios/compare", json=SC, headers=m)
    assert r.status_code == 200, r.text
    out = r.json()
    kinds = [s["kind"] for s in out["scenarios"]]
    assert kinds[:2] == ["internal", "external"]
    for s in out["scenarios"]:
        assert s["status"] == "draft" and s["no_automatic_assignment"] is True and s["auto_generated"] is True
        assert s["risk"]["basis"].startswith("rule-based")
    internal = out["scenarios"][0]
    # internal slots follow fitness rank among ELIGIBLE candidates only
    elig = {r_["requirement_id"]: [c for c in r_["candidates"] if c["eligibility"] == "eligible"] for r_ in res["requirements"]}
    for a in internal["assignments"]:
        assert a["coded_identity"] in {c["coded_identity"] for c in elig[a["requirement_id"]]}
    ext = out["scenarios"][1]
    assert ext["risk"]["flags"].count("external_qualification_unverified") == 1 and "benchmark_synthetic" in ext["risk"]["flags"]
    assert "capacity" in internal and ext["lead_time_weeks"]["external_weeks"] == 8  # slowest-to-fill role
    # nothing was assigned or decided anywhere
    assert con.execute("SELECT COUNT(*), COALESCE(SUM(allocation),0) FROM availability").fetchone() == before
    assert con.execute("SELECT COUNT(*) FROM staffing_requests WHERE status!='open'").fetchone() == reqs_before
    con.close()
    assert client.get(f"/api/opportunities/{oid}/scenarios", headers=m).json()["scenarios"]


def test_scenario_rejects_ineligible_candidates_and_flags_skipped_higher_rank(env):
    client, _ = env
    oid, h, m, f, res = full_flow(client)
    req = res["requirements"][1]  # SRE, 1 head
    cands = req["candidates"]
    assert len(cands) >= 2
    base = {**SC, "assignments": []}
    # a coded id that is not on the shortlist is refused
    bad = {**base, "assignments": [{"requirement_id": req["requirement_id"], "resource_type": "internal", "coded_identity": "EMP-00000000", "fte": "0.5"}]}
    r = client.post(f"/api/opportunities/{oid}/scenarios", json=bad, headers=m)
    assert r.status_code == 422 and "candidate_not_eligible" in r.json()["detail"]
    # choosing rank-2 over an eligible rank-1 is allowed but demands an explicit override at delivery approval
    second = [c for c in cands if c["eligibility"] == "eligible"][1]
    ext_slot = [{"requirement_id": res["requirements"][0]["requirement_id"], "resource_type": "external", "fte": "1"}] * 2
    body = {**SC, "assignments": ext_slot + [{"requirement_id": req["requirement_id"], "resource_type": "internal", "coded_identity": second["coded_identity"], "fte": "0.5"}]}
    rr = client.post(f"/api/opportunities/{oid}/scenarios", json=body, headers=m)
    assert rr.status_code == 201, rr.text
    s = rr.json()
    assert s["override_required"] is True and "higher_ranked_eligible_candidate_not_selected" in s["risk"]["flags"]
    r = client.post(f"/api/opportunities/{oid}/approvals", json={"scenario_id": s["scenario_id"], "approver_role": "delivery", "outcome": "approved"}, headers=m)
    assert r.status_code == 422 and "override_reason" in r.json()["detail"]
    r = client.post(f"/api/opportunities/{oid}/approvals", json={"scenario_id": s["scenario_id"], "approver_role": "delivery", "outcome": "approved", "override_reason": "Customer asked for this engineer by role"}, headers=m)
    assert r.status_code == 200
    # over-capacity and over-headcount are refused
    over = {**base, "assignments": [{"requirement_id": req["requirement_id"], "resource_type": "internal", "coded_identity": cands[0]["coded_identity"], "fte": "1"},
                                    {"requirement_id": req["requirement_id"], "resource_type": "external", "fte": "1"}]}
    assert client.post(f"/api/opportunities/{oid}/scenarios", json={**over, **{"cost_policy_id": "POL-2026", "rate_card_id": "RATE-01"}}, headers=m).status_code == 422


def test_scenario_is_deterministic(env):
    client, _ = env
    oid, h, m, f, res = full_flow(client)
    a = client.post(f"/api/opportunities/{oid}/scenarios/compare", json=SC, headers=m).json()["scenarios"]
    b = client.post(f"/api/opportunities/{oid}/scenarios/compare", json=SC, headers=m).json()["scenarios"]
    for x, y in zip(a, b):
        assert x["input_hash"] == y["input_hash"] and x["scenario_id"] != y["scenario_id"]
        fx = client.get(f"/api/opportunities/{oid}/scenarios/{x['scenario_id']}", headers=f).json()["finance"]
        fy = client.get(f"/api/opportunities/{oid}/scenarios/{y['scenario_id']}", headers=f).json()["finance"]
        assert fx == fy


def test_missing_cost_inputs_are_unresolved_not_fabricated(env):
    client, _ = env
    oid, h = single_role_opp(client)
    f = H(client, "demo-finance")
    client.put("/api/finance/cost-policies/POL-X", json={"payload": {}}, headers=f)
    client.put("/api/finance/rate-cards/RATE-X", json={"payload": {"currency": "USD", "unit": "month", "rates": {"Senior Cloud Engineer": "9000"}}}, headers=f)
    res, m = matched(client, oid, h)
    req = res["requirements"][0]
    body = {"cost_policy_id": "POL-X", "rate_card_id": "RATE-X", "assignments": [{"requirement_id": req["requirement_id"], "resource_type": "internal", "coded_identity": req["candidates"][0]["coded_identity"], "fte": "1"}]}
    rr = client.post(f"/api/opportunities/{oid}/scenarios", json=body, headers=m)
    assert rr.status_code == 201, rr.text
    s = rr.json()
    assert s["calculable"] is False and s["unresolved_constraints"] and "economics" not in s
    assert any("Senior Cloud Engineer" in d["message"] and "no approved loaded cost" in d["message"] for d in s["unresolved_detail"])
    assert all(":" not in d["message"].split(" ", 1)[0] and "rr-" not in d["message"] for d in s["unresolved_detail"])  # no raw ids
    r = client.post(f"/api/opportunities/{oid}/approvals", json={"scenario_id": s["scenario_id"], "approver_role": "delivery", "outcome": "approved"}, headers=m)
    assert r.status_code == 409 and r.json()["error"] == "scenario_unresolved"
    ext = {**body, "assignments": [{"requirement_id": req["requirement_id"], "resource_type": "external", "fte": "1"}]}
    s2 = client.post(f"/api/opportunities/{oid}/scenarios", json=ext, headers=m).json()
    assert any(u.startswith("market_benchmark_missing") for u in s2["unresolved_constraints"])
    assert any("no contractor-cost benchmark" in d["message"] and "Senior Cloud Engineer" in d["message"] for d in s2["unresolved_detail"])


# ============================================================ approvals, audit, export
def test_approval_workflow_export_and_sales_view(env):
    client, _ = env
    oid, h, m, f, res = full_flow(client)
    sc = client.post(f"/api/opportunities/{oid}/scenarios/compare", json=SC, headers=m).json()["scenarios"]
    ext = [s for s in sc if s["kind"] == "external"][0]
    full_ok = [s for s in sc if s["kind"] == "internal"][0]
    sid = ext["scenario_id"]
    assert ext["unresolved_constraints"] == []
    ap = lambda sub, role, outcome="approved", **k: client.post(f"/api/opportunities/{oid}/approvals", json={"scenario_id": sid, "approver_role": role, "outcome": outcome, **k}, headers=H(client, sub))
    assert ap("demo-sales", "delivery").status_code == 403           # wrong role
    assert ap("demo-manager", "finance").status_code == 403           # role cannot act for another lane
    assert ap("demo-hr", "hr").status_code == 409                # external-only: no individual pay used, HR lane n/a
    exp = lambda sub, fmt="json": client.post(f"/api/opportunities/{oid}/export", json={"scenario_id": sid, "format": fmt}, headers=H(client, sub))
    assert exp("demo-manager").status_code == 409                     # not approved yet
    r = ap("demo-manager", "delivery"); assert r.json()["status"] == "partially_approved" and r.json()["approvals"]["pending"] == ["finance"]
    assert exp("demo-manager").status_code == 409
    assert client.get(f"/api/opportunities/{oid}/scenarios/{sid}", headers=H(client, "demo-sales")).json().get("approved_totals") is None
    r = ap("demo-finance", "finance"); assert r.json()["status"] == "approved" and r.json()["approvals"]["complete"]
    sales = client.get(f"/api/opportunities/{oid}/scenarios/{sid}", headers=H(client, "demo-sales")).json()
    assert set(sales["approved_totals"]) == {"revenue", "currency", "months"} and "economics" not in sales and "risk" not in sales
    j = exp("demo-sales").json()["report"]
    assert j["scenario"]["status"] == "approved" and j["approvals"] and j["requirements"]["content_hash"]
    txt = json.dumps(j)
    assert SECRET_COST not in txt and BAND_COST not in txt and "monthly_cost" not in txt and "Alex Rivera" not in txt
    assert any("synthetic" in d.lower() for d in j["disclaimers"])
    smd = exp("demo-sales", "markdown").json()["content"]
    assert "coded identities are not shown to this role" in smd and "EMP-" not in smd
    md = exp("demo-finance", "markdown").json()["content"]
    assert "No employee has been assigned" in md and SECRET_COST not in md and "SYNTHETIC" in md
    # re-deciding after the fact is recorded, never silently overwritten
    ap("demo-finance", "finance", "rejected", reason="margin below floor")
    st = client.get(f"/api/opportunities/{oid}/scenarios/{sid}", headers=m).json()
    assert st["status"] == "rejected"
    assert ap("demo-finance", "finance", "rejected").status_code == 422     # reason required


def test_hr_authorization_required_when_individual_pay_used(env):
    client, _ = env
    oid, h, m, f, res = full_flow(client)
    internal = [s for s in client.post(f"/api/opportunities/{oid}/scenarios/compare", json=SC, headers=m).json()["scenarios"] if s["kind"] in ("internal", "hybrid")]
    s = next((x for x in internal if x["calculable"] and not x["unresolved_constraints"]), None)
    if s is None:  # internal cannot fill every position: build a complete custom scenario instead
        ids = {r["requirement_id"]: [c for c in r["candidates"] if c["eligibility"] == "eligible"] for r in res["requirements"]}
        assign = []
        for r in res["requirements"]:
            n = int(r["headcount"])
            pick = ids[r["requirement_id"]][:n]
            assign += [{"requirement_id": r["requirement_id"], "resource_type": "internal", "coded_identity": c["coded_identity"], "fte": r["fte"] or "1"} for c in pick]
            assign += [{"requirement_id": r["requirement_id"], "resource_type": "external", "fte": "1"}] * (n - len(pick))
        s = client.post(f"/api/opportunities/{oid}/scenarios", json={**SC, "assignments": assign}, headers=m).json()
    assert s["uses_individual_cost"] is True and "hr" in s["approvals"]["required"], s["approvals"]
    sid = s["scenario_id"]
    ap = lambda sub, role: client.post(f"/api/opportunities/{oid}/approvals", json={"scenario_id": sid, "approver_role": role, "outcome": "approved"}, headers=H(client, sub))
    assert ap("demo-manager", "delivery").status_code == 200
    assert ap("demo-finance", "finance").json()["status"] == "partially_approved"
    assert client.post(f"/api/opportunities/{oid}/export", json={"scenario_id": sid}, headers=m).status_code == 409
    assert ap("demo-hr", "hr").json()["status"] == "approved"


def test_audit_chain_integrity_and_tamper_detection(env):
    client, db_path = env
    oid, h, m, f, res = full_flow(client)
    client.post(f"/api/opportunities/{oid}/scenarios/compare", json=SC, headers=m)
    a = client.get(f"/api/opportunities/{oid}/audit", headers=h).json()
    types = [e["event_type"] for e in a["events"]]
    for t in ("opportunity_created", "document_uploaded", "requirements_extracted", "requirements_edited", "requirements_approved", "internal_match_run", "scenario_created", "scenarios_compared"):
        assert t in types, t
    assert a["chain_valid"] is True and [e["seq"] for e in a["events"]] == list(range(1, len(types) + 1))
    assert all(e["actor"] for e in a["events"])
    con = sqlite3.connect(db_path)
    con.execute("UPDATE opportunity_audit SET actor='someone-else' WHERE opportunity_id=? AND seq=2", (oid,))
    con.commit(); con.close()
    assert client.get(f"/api/opportunities/{oid}/audit", headers=h).json()["chain_valid"] is False
    # events also reached the platform-wide hash-chained ledger
    assert any(e.event_type.startswith("hoi.") for e in api_main.get_service().audit.all_events())


def test_status_endpoint_is_honest_about_pending_integrations(env):
    client, _ = env
    s = client.get("/api/hoi/status", headers=H(client, "demo-manager")).json()
    assert "malware_scanning" in s["pending_integrations"] and "hris_payroll" in s["pending_integrations"] and "ocr" in s["pending_integrations"]
    assert client.get("/api/hoi/status").status_code == 401


def test_taxonomy_list_available_to_every_deal_role_but_not_employees(env):
    client, _ = env
    for sub in ("demo-sales", "demo-manager", "demo-finance", "demo-hr"):
        r = client.get("/api/hoi/skills", headers=H(client, sub))
        assert r.status_code == 200 and any(s["skill_id"] == "monitoring" for s in r.json()["skills"]), sub
    assert client.get("/api/hoi/skills", headers=H(client, "demo-employee")).status_code == 403


# ============================================================ repeated uploads / duplicate roles
def test_repeated_identical_upload_is_idempotent_and_roles_not_duplicated(env):
    client, _ = env
    oid, h = new_opp(client)
    a = upload(client, oid, h, name="sow_v1.txt")
    b = upload(client, oid, h, name="renamed_copy.txt")  # same bytes, different name
    assert a.status_code == 201 and b.status_code == 201
    assert b.json()["duplicate"] is True and b.json()["document_id"] == a.json()["document_id"]
    assert len(client.get(f"/api/opportunities/{oid}/documents", headers=h).json()["documents"]) == 1
    cur = extract(client, oid, h)
    assert [r["role_name"] for r in cur["roles"]] == ["Senior Cloud Engineer", "Platform SRE Lead"]
    types = [e["event_type"] for e in client.get(f"/api/opportunities/{oid}/audit", headers=h).json()["events"]]
    assert "document_duplicate_ignored" in types


def test_same_role_in_sow_and_jd_is_merged_with_conflicts_flagged_not_hidden(env):
    client, _ = env
    oid, h = new_opp(client)
    upload(client, oid, h, b"Role: Network Engineer\nHeadcount: 2\nFTE: 1\nMust-have skills: Cisco Networking (level 3)\nPreferred skills: Firewall Administration\n", "sow.txt", "sow")
    upload(client, oid, h, b"Role: network engineer\nHeadcount: 3\nMust-have skills: Cisco Networking (level 4), Firewall Administration (level 2)\nCertifications: CCNP\n", "jd.txt", "jd")
    cur = extract(client, oid, h)
    assert len(cur["roles"]) == 1
    r = cur["roles"][0]
    assert r["headcount"] == 2  # first source kept, never silently overwritten
    assert any(n.startswith("conflict:Network Engineer:headcount:2!=3") for n in cur["notes"])
    skills = {s["text"]: s for s in r["skills"]}
    assert len(skills) == 2
    assert skills["Cisco Networking"]["level"] == 4 and any("conflict:Cisco Networking:level" in n for n in cur["notes"])
    assert skills["Firewall Administration"]["criticality"] == "must" and skills["Firewall Administration"]["level"] == 2
    assert r["constraints"]["mandatory_certifications"] == ["CCNP"]
    for s in r["skills"]:  # merged items still point at a verifiable source span
        assert s["source"]["quote"]


def _llm_extract(client, oid, h, reply):
    class Fake:
        def generate(self, prompt, *, system=None, timeout=30.0):
            return reply

    import api.dependencies as deps
    deps.reset_llm_provider_for_tests(Fake())
    try:
        return client.post(f"/api/opportunities/{oid}/extract", json={"use_llm": True}, headers=h).json()["current"]
    finally:
        deps.reset_llm_provider_for_tests(None)


def test_llm_tolerates_small_model_json_glitch_and_does_not_duplicate_rule_findings(env):
    client, _ = env
    oid, h = new_opp(client)
    upload(client, oid, h)
    # the exact malformed shape qwen2.5:7b produced (stray quote before an object), repeating skills the rules already found
    reply = ('{"roles":[{"role":"Senior Cloud Engineer","skills":[{"skill":"Container Orchestration (level 4)","criticality":"must",'
             '"quote":"Container Orchestration (level 4)"},"{"skill":"Azure Networking (level 4)","criticality":"must",'
             '"quote":"Azure Networking (level 4)"}]}]}')
    cur = _llm_extract(client, oid, h, reply)
    assert cur["extraction_method"] == "rules+llm" and not any(n.startswith("llm_unavailable") for n in cur["notes"])
    assert "llm_suggestions:0_new_verified_items" in cur["notes"]
    cloud = [r for r in cur["roles"] if r["role_name"] == "Senior Cloud Engineer"][0]
    texts = [s["text"] for s in cloud["skills"]]
    assert len(texts) == len(set(texts)) == 4


def test_llm_adds_only_verified_new_items_from_prose(env):
    client, _ = env
    oid, h = new_opp(client)
    txt = b"Role: Data Engineer\nHeadcount: 1\nFTE: 1\nMust-have skills: SQL (level 3)\nThe team also needs strong Python scripting day to day.\n"
    upload(client, oid, h, txt, "jd.txt", "jd")
    reply = ('{"roles":[{"role":"Data Engineer","skills":[{"skill":"Python","criticality":"must","quote":"strong Python scripting"},'
             '{"skill":"Spark","criticality":"must","quote":"Spark clusters at petabyte scale"}]}]}')
    cur = _llm_extract(client, oid, h, reply)
    sk = {s["text"]: s for s in cur["roles"][0]["skills"]}
    assert sk["Python"]["origin"] == "llm" and sk["Python"]["skill_id"] == "python" and sk["Python"]["level"] is None
    assert sk["Python"]["confidence"] <= 0.6 and sk["Python"]["source"]["quote"] == "strong Python scripting"
    assert "Spark" not in sk and any(n.startswith("llm_rejected_unverifiable_skill:Spark") for n in cur["notes"])
    assert "llm_suggestions:1_new_verified_items" in cur["notes"]


def test_llm_salvages_missing_brace_glitch_but_still_verifies_quotes(env):
    client, _ = env
    oid, h = new_opp(client)
    txt = b"Role: Data Engineer\nHeadcount: 1\nFTE: 1\nMust-have skills: SQL (level 3)\nThe team relies on strong Python scripting and Ansible playbooks.\n"
    upload(client, oid, h, txt, "jd.txt", "jd")
    # exact shape the real 7B model produced: the object opener is missing; one quote is invented
    reply = ('{"roles":[{"role":"Data Engineer","skills":[{"skill":"SQL (level 3)","criticality":"must","quote":"Must-have skills: SQL (level 3)"},'
             '"skill":"Strong Python scripting","criticality":"must","quote":"strong Python scripting"},'
             '{"skill":"Kafka","criticality":"must","quote":"Kafka streaming platform"}]}]}')
    cur = _llm_extract(client, oid, h, reply)
    texts = {s["text"]: s for s in cur["roles"][0]["skills"]}
    assert not any(n.startswith("llm_unavailable") for n in cur["notes"])
    assert "Strong Python scripting" in texts and texts["Strong Python scripting"]["origin"] == "llm"
    assert "Kafka" not in texts and any(n.startswith("llm_rejected_unverifiable_skill:Kafka") for n in cur["notes"])


# ============================================================ resource limits (hardening)
def test_pdf_decompression_bomb_is_rejected_not_inflated(env):
    import zlib
    client, _ = env
    oid, h = new_opp(client)
    bomb = b"%PDF-1.4\n1 0 obj<<>>stream\n" + zlib.compress(b"A" * 30_000_000, 9) + b"\nendstream\nendobj\n%%EOF"
    assert len(bomb) < 100_000  # tiny upload, 30 MB when inflated
    r = upload(client, oid, h, bomb, "bomb.pdf")
    assert r.status_code == 422 and "expands beyond" in r.json()["detail"]
    assert client.get(f"/api/opportunities/{oid}/documents", headers=h).json()["documents"] == []  # nothing stored


def test_oversized_extracted_text_is_refused(env):
    client, _ = env
    oid, h = new_opp(client)
    r = upload(client, oid, h, b"Role: X\n" + b"filler line of text\n" * 110_000, "huge.txt")  # ~2.2M chars, under the 10 MB cap
    assert r.status_code == 422 and "text exceeds" in r.json()["detail"]


def test_extraction_keeps_drafts_editable_by_capping_roles(env):
    client, _ = env
    oid, h = new_opp(client)
    txt = "".join(f"Role: Engineer {i}\nHeadcount: 1\nFTE: 1\nMust-have skills: SQL (level 3)\n" for i in range(80)).encode()
    upload(client, oid, h, txt, "many.txt", "jd")
    cur = extract(client, oid, h)
    assert len(cur["roles"]) == 50 and any(n.startswith("truncated_roles:80_found") for n in cur["notes"])
    # the capped draft can be saved back through the API (it would 422 if it exceeded the edit limit)
    r = client.put(f"/api/opportunities/{oid}/requirements/{cur['version_id']}", json={"roles": cur["roles"]}, headers=h)
    assert r.status_code == 200


def test_oversized_request_bodies_are_refused_before_they_are_read(env):
    client, _ = env
    oid, h = new_opp(client)
    hj = {**h, "content-type": "application/json"}
    r = client.post(f"/api/opportunities/{oid}/documents", content=b'{"x":"' + b"A" * 16_000_000 + b'"}', headers=hj)
    assert r.status_code == 413 and r.json()["error"] == "payload_too_large"
    f = H(client, "demo-finance")
    r = client.post("/api/market/benchmarks/import", content=b'{"x":"' + b"A" * 2_200_000 + b'"}', headers={**f, "content-type": "application/json"})
    assert r.status_code == 413
    r = client.put("/api/finance/cost-policies/POL-BIG", content=b'{"x":"' + b"A" * 3_100_000 + b'"}', headers={**f, "content-type": "application/json"})
    assert r.status_code == 413
    # a chunked body (no Content-Length) cannot sidestep the limit
    r = client.post(f"/api/opportunities/{oid}/documents", content=iter([b'{"doc_type":"sow"', b"}"]), headers=hj)
    assert r.status_code == 411 and r.json()["error"] == "length_required"
    # normal-sized requests still work
    assert upload(client, oid, h).status_code == 201


# ============================================================ key management boundary (hardening)
def test_encryption_fails_closed_outside_local_mode_and_never_echoes_keys(monkeypatch):
    from cryptography.fernet import Fernet
    from hoi import crypto
    from shared.errors import ConfigurationError

    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("HERMES_ENV", "production")
    for k in ("HOI_DOC_KEY", "HOI_FINANCE_KEY"):
        monkeypatch.delenv(k, raising=False)
    crypto._fernet.cache_clear()
    for purpose in ("doc", "finance"):
        with pytest.raises(ConfigurationError, match="must be set outside local/test mode"):
            crypto.cipher(purpose)
    with pytest.raises(ConfigurationError):
        crypto.encrypt_text("finance", "7013.37")
    monkeypatch.setenv("HOI_FINANCE_KEY", "not-a-valid-key-SECRETVALUE")
    crypto._fernet.cache_clear()
    with pytest.raises(ConfigurationError) as e:
        crypto.cipher("finance")
    assert "SECRETVALUE" not in str(e.value)  # a bad key is never echoed back
    good = Fernet.generate_key().decode()
    monkeypatch.setenv("HOI_FINANCE_KEY", good)
    crypto._fernet.cache_clear()
    assert crypto.decrypt_text("finance", crypto.encrypt_text("finance", "x")) == "x"
    with pytest.raises(ConfigurationError):
        crypto.cipher("doc")
    crypto._fernet.cache_clear()


def test_separate_keys_for_documents_and_finance(monkeypatch):
    from cryptography.fernet import Fernet, InvalidToken
    from hoi import crypto

    monkeypatch.setenv("HOI_DOC_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("HOI_FINANCE_KEY", Fernet.generate_key().decode())
    crypto._fernet.cache_clear()
    token = crypto.encrypt_text("finance", "6111.11")
    with pytest.raises(InvalidToken):
        crypto.decrypt_text("doc", token)  # a document key can never open finance data
    crypto._fernet.cache_clear()


# ============================================================ authorization matrix (hardening)
_BODIES = {
    "documents": {"doc_type": "sow", "filename": "a.txt", "content_b64": "QUJD"},
    "extract": {}, "internal-match": {}, "requirements/approve": {"version_id": "rv-x"}, "members": {"sub": "x", "member_role": "sales"},
    "scenarios": {"cost_policy_id": "POL-2026", "rate_card_id": "RATE-01", "assignments": [{"requirement_id": "rr-x", "resource_type": "external", "fte": "1"}]},
    "scenarios/compare": {"cost_policy_id": "POL-2026", "rate_card_id": "RATE-01"},
    "approvals": {"scenario_id": "sc-x", "approver_role": "delivery", "outcome": "approved"}, "export": {"scenario_id": "sc-x"},
}


def _opportunity_routes():
    from api.routers import hoi as hoi_router
    out = []
    for r in hoi_router.router.routes:
        if "/api/opportunities/{oid}" in r.path:
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                out.append((m, r.path))
    return out


def test_every_opportunity_route_is_scoped_to_the_deal_team(env):
    """No opportunity-scoped route may return data or accept writes for someone outside the deal team."""
    client, _ = env
    routes = _opportunity_routes()
    assert len(routes) >= 17  # guards the enumeration itself: a new route must show up here automatically
    oid, owner = new_opp(client, members=())  # nobody else is on the deal team
    upload(client, oid, owner)
    outsiders = ["demo-sales-2", "demo-manager", "demo-manager-2", "demo-finance", "demo-hr", "demo-employee"]
    for method, path in routes:
        suffix = path.split("/api/opportunities/{oid}", 1)[1].strip("/")
        url = path.replace("{oid}", oid).replace("{vid}", "rv-x").replace("{sid}", "sc-x")
        body = _BODIES.get(suffix.replace("/{vid}", ""))
        if suffix.startswith("requirements/{vid}"):
            body = {"roles": []}
        for sub in outsiders:
            kw = {"json": body} if method in ("POST", "PUT") and body is not None else {}
            r = client.request(method, url, headers=H(client, sub), **kw)
            assert r.status_code in (403, 404), (method, url, sub, r.status_code)
            assert "Northstar" not in r.text and oid not in r.text.replace(url, ""), (method, url, sub)  # nothing about the deal leaks
    # the admin/auditor can read the deal, but cannot write to it
    admin = H(client, "demo-admin")
    assert client.get(f"/api/opportunities/{oid}", headers=admin).status_code == 200
    assert client.post(f"/api/opportunities/{oid}/documents", json=_BODIES["documents"], headers=admin).status_code == 403
    assert client.post(f"/api/opportunities/{oid}/approvals", json=_BODIES["approvals"], headers=admin).status_code == 403
    # sanity: the owner is not locked out by the same enumeration
    assert client.get(f"/api/opportunities/{oid}", headers=owner).status_code == 200
