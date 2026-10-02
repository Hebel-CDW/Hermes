"""POST /api/team/{coded_identity}/capability-check and
POST /api/me/capability-check/respond — the Teams golden-path HTTP surface,
backed by MockTeamsProvider via get_teams_provider/reset_teams_provider_for_tests.
"""

from __future__ import annotations

import os

os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

import api.main as api_main  # noqa: E402
from api.dependencies import reset_teams_provider_for_tests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from integrations.teams.mock_provider import MockTeamsProvider  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.service import HermesService  # noqa: E402


def _token_for(client, sub: str) -> str:
    return client.post("/api/auth/token", json={"sub": sub}).json()["access_token"]


def test_manager_sends_capability_check_to_direct_report(tmp_path):
    db = HermesDB(tmp_path / "t1.db")
    svc = HermesService(db=db)
    coded = svc.abstract({"employee_id": "api-emp-1", "name": "API Employee"})["coded_identity"]
    api_main.reset_service_for_tests(svc)
    reset_teams_provider_for_tests(MockTeamsProvider())
    try:
        with TestClient(api_main.app) as client:
            token = _token_for(client, "demo-admin")
            resp = client.post(
                f"/api/team/{coded}/capability-check",
                json={"skill_ids": ["python"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["sent_to"] == coded
            assert body["mock"] is True
    finally:
        api_main.reset_service_for_tests(None)
        reset_teams_provider_for_tests(None)


def test_unknown_skill_in_capability_check_is_rejected(tmp_path):
    db = HermesDB(tmp_path / "t2.db")
    svc = HermesService(db=db)
    coded = svc.abstract({"employee_id": "api-emp-2", "name": "API Employee 2"})["coded_identity"]
    api_main.reset_service_for_tests(svc)
    reset_teams_provider_for_tests(MockTeamsProvider())
    try:
        with TestClient(api_main.app) as client:
            token = _token_for(client, "demo-admin")
            resp = client.post(
                f"/api/team/{coded}/capability-check",
                json={"skill_ids": ["not_a_real_skill"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 422
    finally:
        api_main.reset_service_for_tests(None)
        reset_teams_provider_for_tests(None)


def test_employee_responds_to_own_capability_check_creates_declared_evidence(tmp_path):
    db = HermesDB(tmp_path / "t3.db")
    svc = HermesService(db=db)
    svc.abstract({"employee_id": "E1003", "name": "Demo Employee"})  # demo-employee's registry employee_key
    api_main.reset_service_for_tests(svc)
    reset_teams_provider_for_tests(MockTeamsProvider())
    try:
        with TestClient(api_main.app) as client:
            token = _token_for(client, "demo-employee")
            resp = client.post(
                "/api/me/capability-check/respond",
                json={"answers": [{
                    "skill_id": "python", "actively_used": True, "experience": "working",
                    "recency": "under_30_days", "delivered_in_real_work": True,
                }]},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["declared_skill_count"] == 1
    finally:
        api_main.reset_service_for_tests(None)
        reset_teams_provider_for_tests(None)


def test_employee_response_body_cannot_carry_an_identity_field(tmp_path):
    """Pins that CapabilityCheckResponseBody has no coded_identity field at
    all — there is nothing to spoof in the first place, the strongest
    possible version of "never client-asserted identity"."""
    db = HermesDB(tmp_path / "t4.db")
    svc = HermesService(db=db)
    svc.abstract({"employee_id": "E1003", "name": "Demo Employee"})
    api_main.reset_service_for_tests(svc)
    reset_teams_provider_for_tests(MockTeamsProvider())
    try:
        with TestClient(api_main.app) as client:
            token = _token_for(client, "demo-employee")
            resp = client.post(
                "/api/me/capability-check/respond",
                json={
                    "coded_identity": "EMP-ffffffff",
                    "answers": [{
                        "skill_id": "python", "actively_used": True, "experience": "working",
                        "recency": "under_30_days", "delivered_in_real_work": True,
                    }],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 422  # extra="forbid" rejects the unexpected field outright
    finally:
        api_main.reset_service_for_tests(None)
        reset_teams_provider_for_tests(None)


def test_manager_cannot_send_capability_check_outside_their_team(tmp_path):
    db = HermesDB(tmp_path / "t5.db")
    svc = HermesService(db=db)
    coded = svc.abstract({"employee_id": "api-emp-5", "name": "API Employee 5"})["coded_identity"]
    api_main.reset_service_for_tests(svc)
    reset_teams_provider_for_tests(MockTeamsProvider())
    try:
        with TestClient(api_main.app) as client:
            token = _token_for(client, "demo-manager")  # not this person's manager
            resp = client.post(
                f"/api/team/{coded}/capability-check",
                json={"skill_ids": ["python"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code in (403, 404)
    finally:
        api_main.reset_service_for_tests(None)
        reset_teams_provider_for_tests(None)
