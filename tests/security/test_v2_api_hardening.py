"""V2 SVP hardening — API security regression tests (all data synthetic).

Covers the defects reproduced in the V2 validation:
  * request-id hijack (another manager re-ranking / resolving / deciding a request)
  * decision governance (ownership, shortlist membership, excluded candidates)
  * missing role authorization (employee could rank, enumerate, create identities)
  * token stub accepting arbitrary roles / coded identities
  * unknown skills and malformed inputs returning 200
  * serving an untrusted database
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

import api.main as api_main  # noqa: E402
from scripts.ingest_fixtures import ingest  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.secrets import require_jwt_secret  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "pilot_population.json"
RANK_BODY = {"request_id": "req-A", "required_skills": {"container_orchestration": 3}, "shortlist_size": 3}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Fresh synthetic DB served through the real get_service() trust path."""
    db_path = tmp_path / "hardening.db"
    ingest(FIXTURE, db_path, write_samples=False)
    monkeypatch.setenv("HERMES_DB_PATH", str(db_path))
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.delenv("FUNCTION_AUTH_KEY", raising=False)
    monkeypatch.delenv("HERMES_ENV", raising=False)
    api_main.reset_service_for_tests(None)
    with TestClient(api_main.app) as client:
        yield client, db_path
    api_main.reset_service_for_tests(None)


def token(client, sub):
    r = client.post("/api/auth/token", json={"sub": sub})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def coded(db_path, employee_key):
    return HermesDB(db_path).resolve_coded_for_source(employee_key)


# ---------------------------------------------------------------------------
# Request ownership (hijack)
# ---------------------------------------------------------------------------

def test_request_hijack_is_refused_for_rank_resolve_and_decision(env):
    client, db_path = env
    a, b = token(client, "demo-manager"), token(client, "demo-manager-2")
    ranked = client.post("/api/fitness/rank", headers=a, json=RANK_BODY)
    assert ranked.status_code == 200
    top = ranked.json()["candidates"][0]["coded_identity"]

    assert client.post("/api/fitness/rank", headers=b, json=RANK_BODY).status_code == 403
    assert client.post("/api/identity/resolve", headers=b, json={"request_id": "req-A"}).status_code == 403
    d = client.post(
        "/api/staffing/req-A/decision", headers=b, json={"status": "accepted", "chosen_coded_identity": top}
    )
    assert d.status_code == 403
    assert d.json()["error"] == "request_not_owned"

    # Ownership is unchanged and A keeps working.
    assert HermesDB(db_path).get_staffing_request("req-A")["requester_id"] == "demo-manager"
    assert client.post("/api/fitness/rank", headers=a, json=RANK_BODY).status_code == 200
    assert client.post("/api/identity/resolve", headers=a, json={"request_id": "req-A"}).status_code == 200
    ok = client.post(
        "/api/staffing/req-A/decision", headers=a, json={"status": "accepted", "chosen_coded_identity": top}
    )
    assert ok.status_code == 200
    assert ok.json()["approved_by"] == "demo-manager"


def test_hijacked_rank_leaves_no_audit_or_shortlist_change(env):
    client, db_path = env
    a, b = token(client, "demo-manager"), token(client, "demo-manager-2")
    client.post("/api/fitness/rank", headers=a, json=RANK_BODY)
    before = HermesDB(db_path).get_staffing_request("req-A")
    client.post(
        "/api/fitness/rank",
        headers=b,
        json={**RANK_BODY, "required_skills": {"incident_management": 1}},
    )
    after = HermesDB(db_path).get_staffing_request("req-A")
    assert after == before


def test_db_layer_refuses_ownership_overwrite_even_without_service_check(tmp_path):
    from shared.errors import RequestOwnershipError

    db = HermesDB(tmp_path / "own.db")
    db.save_staffing_request("r1", "owner", ["EMP-00000001"])
    with pytest.raises(RequestOwnershipError):
        db.save_staffing_request("r1", "intruder", ["EMP-00000002"])
    assert db.get_staffing_request("r1")["requester_id"] == "owner"


def test_rerank_after_decision_conflicts(env):
    client, _ = env
    a = token(client, "demo-manager")
    top = client.post("/api/fitness/rank", headers=a, json=RANK_BODY).json()["candidates"][0]["coded_identity"]
    client.post("/api/staffing/req-A/decision", headers=a, json={"status": "accepted", "chosen_coded_identity": top})
    assert client.post("/api/fitness/rank", headers=a, json=RANK_BODY).status_code == 409


# ---------------------------------------------------------------------------
# Decision governance
# ---------------------------------------------------------------------------

def test_decision_on_unknown_request_is_404(env):
    client, _ = env
    r = client.post(
        "/api/staffing/never-ranked/decision", headers=token(client, "demo-manager"), json={"status": "rejected"}
    )
    assert r.status_code == 404


def test_decision_for_non_shortlisted_candidate_is_422(env):
    client, _ = env
    a = token(client, "demo-manager")
    client.post("/api/fitness/rank", headers=a, json=RANK_BODY)
    r = client.post(
        "/api/staffing/req-A/decision",
        headers=a,
        json={"status": "overridden", "chosen_coded_identity": "EMP-00000000"},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "candidate_not_shortlisted"


def test_decision_for_excluded_candidate_is_422(env):
    client, _ = env
    a = token(client, "demo-manager")
    ranked = client.post("/api/fitness/rank", headers=a, json=RANK_BODY).json()
    assert ranked["excluded_candidates"], "fixture must exclude someone for this request"
    excluded = ranked["excluded_candidates"][0]["coded_identity"]
    r = client.post(
        "/api/staffing/req-A/decision",
        headers=a,
        json={"status": "overridden", "chosen_coded_identity": excluded},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "candidate_excluded"


def test_accepted_decision_requires_a_candidate(env):
    client, _ = env
    a = token(client, "demo-manager")
    client.post("/api/fitness/rank", headers=a, json=RANK_BODY)
    r = client.post("/api/staffing/req-A/decision", headers=a, json={"status": "accepted"})
    assert r.status_code == 422
    assert r.json()["error"] == "candidate_required"


def test_forged_approved_by_is_rejected(env):
    client, db_path = env
    a = token(client, "demo-manager")
    top = client.post("/api/fitness/rank", headers=a, json=RANK_BODY).json()["candidates"][0]["coded_identity"]
    r = client.post(
        "/api/staffing/req-A/decision",
        headers=a,
        json={"status": "accepted", "chosen_coded_identity": top, "approved_by": "demo-admin"},
    )
    assert r.status_code == 422
    assert HermesDB(db_path).get_staffing_request("req-A")["status"] == "open"


def test_decision_with_empty_shortlist_is_422(env):
    client, _ = env
    a = token(client, "demo-manager")
    body = {
        "request_id": "req-empty",
        "required_skills": {"infrastructure_as_code": 3},
        "critical_skills": ["incident_management"],
    }
    ranked = client.post("/api/fitness/rank", headers=a, json=body).json()
    assert ranked["candidates"] == []
    r = client.post("/api/staffing/req-empty/decision", headers=a, json={"status": "rejected"})
    assert r.status_code == 422
    assert r.json()["error"] == "no_shortlist"


def test_second_decision_conflicts(env):
    client, _ = env
    a = token(client, "demo-manager")
    top = client.post("/api/fitness/rank", headers=a, json=RANK_BODY).json()["candidates"][0]["coded_identity"]
    first = client.post("/api/staffing/req-A/decision", headers=a, json={"status": "accepted", "chosen_coded_identity": top})
    assert first.status_code == 200
    assert first.json()["engine_rank_of_choice"] == 1
    second = client.post("/api/staffing/req-A/decision", headers=a, json={"status": "rejected"})
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# RBAC — role x endpoint
# ---------------------------------------------------------------------------

def _call(client, headers, method, path, body=None):
    return client.request(method, path, headers=headers, json=body)


def test_rbac_matrix(env):
    client, db_path = env
    heads = {r: token(client, r) for r in ("demo-employee", "demo-manager", "demo-admin")}
    merge_body = {
        "evidence": [
            {
                "evidence_id": "rbac-ev-1",
                "coded_identity": "EMP-12345678",
                "skill_id": "incident_management",
                "evidence_type": "certified",
                "proficiency": 3,
                "occurred_at": "2026-01-01T00:00:00+00:00",
                "source_ref": "SYN-1",
            }
        ]
    }
    matrix = [
        (("GET", "/api/dashboard", None), {"demo-employee": 403, "demo-manager": 200, "demo-admin": 200}),
        (("GET", "/api/identities", None), {"demo-employee": 403, "demo-manager": 200, "demo-admin": 200}),
        (("GET", "/api/identity/directory", None), {"demo-employee": 403, "demo-manager": 200, "demo-admin": 200}),
        (("GET", "/api/matrix/runs", None), {"demo-employee": 403, "demo-manager": 200, "demo-admin": 200}),
        (("GET", "/api/skills", None), {"demo-employee": 200, "demo-manager": 200, "demo-admin": 200}),
        (("GET", "/api/roles", None), {"demo-employee": 200, "demo-manager": 200, "demo-admin": 200}),
        (("GET", "/api/me", None), {"demo-employee": 200, "demo-manager": 200, "demo-admin": 403}),
        (("POST", "/api/identity/abstract", {"employee_id": "SYN-RBAC", "name": "Synthetic"}), {
            "demo-employee": 403, "demo-manager": 403, "demo-admin": 200,
        }),
        (("POST", "/api/inference/merge", merge_body), {"demo-employee": 403, "demo-manager": 403, "demo-admin": 200}),
        (("POST", "/api/fitness/rank", {**RANK_BODY, "request_id": "rbac-rank"}), {
            "demo-employee": 403, "demo-manager": 200, "demo-admin": 403,
        }),
        (("POST", "/api/identity/resolve", {"request_id": "rbac-rank"}), {
            "demo-employee": 403, "demo-manager": 200, "demo-admin": 403,
        }),
        (("POST", "/api/staffing/rbac-rank/decision", {"status": "rejected"}), {
            "demo-employee": 403, "demo-admin": 403, "demo-manager": 200,
        }),
        (("GET", f"/api/team/skill-review/{coded(db_path, 'E1002')}", None), {
            "demo-employee": 403, "demo-manager": 200, "demo-admin": 200,
        }),
        (("POST", "/api/team/declare", {
            "coded_identity": coded(db_path, "E1002"),
            "skill_id": "incident_management",
            "proficiency": 2,
        }), {"demo-employee": 403, "demo-manager": 200, "demo-admin": 200}),
        (("GET", "/api/taxonomy/pending", None), {"demo-employee": 403, "demo-manager": 200, "demo-admin": 200}),
        (("POST", "/api/taxonomy/aliases/k8s/resolve", {"decision": "reject"}), {
            "demo-employee": 403, "demo-manager": 403, "demo-admin": 200,
        }),
        (("GET", "/api/baseline/matrix", None), {"demo-employee": 403, "demo-manager": 200, "demo-admin": 200}),
        (("GET", "/api/excel-sunset", None), {"demo-employee": 403, "demo-manager": 200, "demo-admin": 200}),
        (("POST", "/api/ingest/tickets", {"tickets": [{
            "employee_id": "E1002", "ticket_number": "INC-RBAC",
            "short_description": "kubernetes", "resolved_at": "2026-03-01T00:00:00+00:00",
        }]}), {"demo-employee": 403, "demo-manager": 403, "demo-admin": 200}),
        (("POST", "/api/org/bind-principal", {"sub": "demo-manager", "coded_identity": coded(db_path, "E1001")}), {
            "demo-employee": 403, "demo-manager": 403, "demo-admin": 200,
        }),
        # Added when api/routers/assist.py and the cert-governance queue were built — this
        # matrix is a hand-maintained list, and both were missing from it (found during the
        # V3 QA pass). require_roles(MANAGER) / require_roles(ADMIN) respectively.
        (("POST", "/api/requests/parse", {"description": "need someone"}), {
            "demo-employee": 403, "demo-manager": 200, "demo-admin": 403,
        }),
        (("GET", "/api/certs/pending", None), {
            "demo-employee": 403, "demo-manager": 403, "demo-admin": 200,
        }),
        (("POST", f"/api/team/{coded(db_path, 'E1002')}/capability-check", {"skill_ids": ["container_orchestration"]}), {
            "demo-employee": 403, "demo-manager": 200, "demo-admin": 200,
        }),
        (("POST", "/api/me/capability-check/respond", {"answers": []}), {
            "demo-employee": 200, "demo-manager": 403, "demo-admin": 403,
        }),
    ]
    failures = []
    for (method, path, body), expected in matrix:
        for role, status in expected.items():
            got = _call(client, heads[role], method, path, body).status_code
            if got != status:
                failures.append(f"{role} {method} {path}: expected {status}, got {got}")
    assert not failures, "\n".join(failures)


def test_every_protected_route_requires_a_token(env):
    client, _ = env
    for method, path in [
        ("GET", "/api/dashboard"), ("GET", "/api/skills"), ("GET", "/api/roles"), ("GET", "/api/identities"),
        ("GET", "/api/identity/directory"),
        ("GET", "/api/session"),
        ("GET", "/api/matrix/runs"), ("GET", "/api/me"), ("POST", "/api/identity/abstract"),
        ("POST", "/api/inference/merge"), ("POST", "/api/fitness/rank"), ("POST", "/api/fitness/gaps"),
        ("POST", "/api/identity/resolve"), ("POST", "/api/staffing/x/decision"), ("POST", "/api/me/contest"),
        # assist.py and the cert-governance queue were missing from this list for two
        # commits (found during the V3 QA pass) - a regression on either would have gone
        # uncaught by "every protected route requires a token".
        ("POST", "/api/requests/parse"), ("GET", "/api/certs/pending"),
        ("POST", "/api/certs/x/date"), ("POST", "/api/certs/x/promote"),
        ("POST", "/api/team/EMP-00000000/capability-check"), ("POST", "/api/me/capability-check/respond"),
        ("GET", "/api/team/skill-review/EMP-00000000"), ("POST", "/api/team/declare"),
        ("POST", "/api/team/contests/xxxxxxxx/resolve"),
        ("GET", "/api/taxonomy/pending"), ("GET", "/api/baseline/matrix"), ("GET", "/api/excel-sunset"),
        ("POST", "/api/ingest/tickets"), ("POST", "/api/org/bind-principal"), ("POST", "/api/org/edges"),
    ]:
        assert client.request(method, path, json={}).status_code == 401, f"{method} {path}"


def test_manager_identity_listing_is_limited_to_direct_reports(env):
    client, db_path = env
    listed = client.get("/api/identities", headers=token(client, "demo-manager")).json()["identities"]
    assert sorted(listed) == sorted([coded(db_path, "E1002"), coded(db_path, "E1003")])
    everyone = client.get("/api/identities", headers=token(client, "demo-admin")).json()["identities"]
    assert len(everyone) == 5


def test_gaps_acl_by_role(env):
    client, db_path = env
    body = lambda who: {  # noqa: E731
        "coded_identity": coded(db_path, who),
        "role_id": "senior_cloud_engineer",
        "role_name": "Senior Cloud Engineer",
        "required_skills": {"container_orchestration": 4},
    }
    assert client.post("/api/fitness/gaps", headers=token(client, "demo-employee"), json=body("E1003")).status_code == 200
    assert client.post("/api/fitness/gaps", headers=token(client, "demo-employee"), json=body("E1005")).status_code == 403
    assert client.post("/api/fitness/gaps", headers=token(client, "demo-manager"), json=body("E1003")).status_code == 200
    assert client.post("/api/fitness/gaps", headers=token(client, "demo-manager"), json=body("E1005")).status_code == 403
    assert client.post("/api/fitness/gaps", headers=token(client, "demo-admin"), json=body("E1005")).status_code == 200


# ---------------------------------------------------------------------------
# Identity anti-impersonation
# ---------------------------------------------------------------------------

def _signed(payload, secret=None):
    return {"Authorization": "Bearer " + jwt.encode(payload, secret or require_jwt_secret(), algorithm="HS256")}


def test_token_endpoint_rejects_client_asserted_roles_and_identity(env):
    client, _ = env
    assert client.post("/api/auth/token", json={"sub": "demo-employee", "roles": ["admin"]}).status_code == 422
    assert client.post(
        "/api/auth/token", json={"sub": "demo-employee", "coded_identity": "EMP-deadbeef"}
    ).status_code == 422
    assert client.post("/api/auth/token", json={"sub": "attacker"}).status_code == 401


def test_validly_signed_token_with_forged_role_claim_is_rejected(env):
    client, _ = env
    now = int(time.time())
    forged = _signed({"sub": "demo-employee", "roles": ["admin"], "iat": now, "exp": now + 60})
    r = client.get("/api/identities", headers=forged)
    assert r.status_code == 401
    assert r.json()["error"] == "forged_claims"


def test_validly_signed_token_with_forged_coded_identity_is_rejected(env):
    client, db_path = env
    now = int(time.time())
    forged = _signed(
        {"sub": "demo-employee", "coded_identity": coded(db_path, "E1001"), "iat": now, "exp": now + 60}
    )
    assert client.get("/api/me", headers=forged).status_code == 401


def test_me_is_bound_to_the_server_side_identity(env):
    client, db_path = env
    mine = client.get("/api/me", headers=token(client, "demo-employee")).json()
    assert mine["coded_identity"] == coded(db_path, "E1003")
    other = client.get("/api/me", headers=token(client, "demo-employee-2")).json()
    assert other["coded_identity"] == coded(db_path, "E1005")
    assert mine["coded_identity"] != other["coded_identity"]


def test_employee_cannot_act_as_manager(env):
    client, _ = env
    e = token(client, "demo-employee")
    assert client.post("/api/fitness/rank", headers=e, json=RANK_BODY).status_code == 403


def test_bad_signature_expired_and_malformed_tokens_are_401(env):
    client, _ = env
    now = int(time.time())
    for headers in (
        _signed({"sub": "demo-admin", "iat": now, "exp": now + 60}, secret="x" * 40),
        _signed({"sub": "demo-admin", "iat": now - 100, "exp": now - 50}),
        {"Authorization": "Bearer not.a.jwt"},
        _signed({"sub": "unregistered", "iat": now, "exp": now + 60}),
        _signed({"sub": "demo-admin"}),  # missing exp/iat
    ):
        assert client.get("/api/skills", headers=headers).status_code == 401


def test_production_mode_refuses_the_demo_registry(env, monkeypatch):
    client, _ = env
    valid = token(client, "demo-admin")
    monkeypatch.setenv("HERMES_ENV", "production")
    monkeypatch.delenv("HERMES_TEST_MODE", raising=False)
    monkeypatch.setenv("IDENTITY_MAP_SECRET", "a-strong-validation-identity-secret-987654")
    monkeypatch.setenv("HERMES_JWT_SECRET", "a-strong-validation-jwt-secret-0123456789")
    assert client.post("/api/auth/token", json={"sub": "demo-admin"}).status_code == 403
    now = int(time.time())
    prod_token = _signed({"sub": "demo-admin", "iat": now, "exp": now + 60})
    # 401 = registry disabled (no identity provider); 503 = synthetic DB built with a
    # different secret is refused. Either way nothing is served.
    assert client.get("/api/skills", headers=prod_token).status_code in (401, 503)
    assert valid  # issued before the switch; kept only to show the switch, not reused


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body",
    [
        {"request_id": "v", "required_skills": {"not_a_skill": 3}},
        {"request_id": "v", "required_skills": {"container_orchestration": 0}},
        {"request_id": "v", "required_skills": {"container_orchestration": 6}},
        {"request_id": "v", "required_skills": {"container_orchestration": 3.5}},
        {"request_id": "v", "required_skills": {"container_orchestration": "3"}},
        {"request_id": "v", "required_skills": {"container_orchestration": True}},
        {"request_id": "v", "required_skills": {}},
        {"request_id": "v", "required_skills": ["container_orchestration"]},
        {"request_id": "v", "required_skills": {"container_orchestration": 3}, "min_coverage_ratio": 1.5},
        {"request_id": "v", "required_skills": {"container_orchestration": 3}, "critical_skills": ["nope"]},
        {"request_id": "v", "required_skills": {"container_orchestration": 3}, "availability": {"bob": True}},
        {"request_id": "../etc", "required_skills": {"container_orchestration": 3}},
        {"request_id": "", "required_skills": {"container_orchestration": 3}},
        {"request_id": "x" * 200, "required_skills": {"container_orchestration": 3}},
        {"required_skills": {"container_orchestration": 3}},
    ],
)
def test_invalid_rank_inputs_are_422(env, body):
    client, _ = env
    r = client.post("/api/fitness/rank", headers=token(client, "demo-manager"), json=body)
    assert r.status_code == 422, (body, r.text)


def test_invalid_gap_decision_contest_and_merge_inputs_are_422(env):
    client, db_path = env
    m, adm, emp = token(client, "demo-manager"), token(client, "demo-admin"), token(client, "demo-employee")
    gap = {"role_id": "r", "role_name": "R", "required_skills": {"container_orchestration": 3}}
    assert client.post("/api/fitness/gaps", headers=adm, json={**gap, "coded_identity": "bob"}).status_code == 422
    assert client.post(
        "/api/fitness/gaps", headers=adm, json={**gap, "coded_identity": coded(db_path, "E1003"), "required_skills": {"zzz": 3}}
    ).status_code == 422
    client.post("/api/fitness/rank", headers=m, json=RANK_BODY)
    assert client.post(
        "/api/staffing/req-A/decision", headers=m, json={"status": "accepted", "chosen_coded_identity": "bob"}
    ).status_code == 422
    assert client.post("/api/me/contest", headers=emp, json={"reason": ""}).status_code == 422
    assert client.post("/api/me/contest", headers=emp, json={"reason": "x", "skill_id": "nope"}).status_code == 422
    bad_merge = {"evidence": [{
        "evidence_id": "e", "coded_identity": "EMP-12345678", "skill_id": "made_up_skill",
        "evidence_type": "certified", "proficiency": 3, "occurred_at": "2026-01-01T00:00:00+00:00", "source_ref": "s",
    }]}
    r = client.post("/api/inference/merge", headers=adm, json=bad_merge)
    assert r.status_code == 422 and r.json()["error"] == "unknown_skill"
    assert client.post("/api/inference/merge", headers=adm, json={"evidence": []}).status_code == 422


def test_error_responses_are_structured(env):
    client, _ = env
    a, b = token(client, "demo-manager"), token(client, "demo-manager-2")
    client.post("/api/fitness/rank", headers=a, json=RANK_BODY)
    body = client.post("/api/fitness/rank", headers=b, json=RANK_BODY).json()
    assert set(body) == {"detail", "error"}


# ---------------------------------------------------------------------------
# Untrusted database refusal
# ---------------------------------------------------------------------------

def _legacy_copy(src: Path, dst: Path) -> None:
    """Simulate a pre-V2 database: same data, no trust metadata."""
    dst.write_bytes(src.read_bytes())
    con = sqlite3.connect(dst)
    con.execute("DELETE FROM hermes_meta WHERE key IN ('data_classification','identity_secret_fingerprint')")
    con.commit()
    con.close()


def test_api_refuses_to_serve_a_database_without_trust_metadata(tmp_path, monkeypatch):
    good = tmp_path / "good.db"
    ingest(FIXTURE, good, write_samples=False)
    legacy = tmp_path / "legacy.db"
    _legacy_copy(good, legacy)
    monkeypatch.setenv("HERMES_DB_PATH", str(legacy))
    api_main.reset_service_for_tests(None)
    try:
        with TestClient(api_main.app) as client:
            tok = client.post("/api/auth/token", json={"sub": "demo-admin"}).json()["access_token"]
            r = client.get("/api/skills", headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 503
            assert r.json()["error"] == "missing_trust_metadata"
    finally:
        api_main.reset_service_for_tests(None)


def test_api_serves_trusted_synthetic_database(env):
    client, _ = env
    assert client.get("/api/skills", headers=token(client, "demo-employee")).status_code == 200
