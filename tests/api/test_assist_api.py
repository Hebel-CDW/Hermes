"""POST /api/requests/parse — manager-only, advisory, never touches ranking.

Uses MockLLMProvider via reset_llm_provider_for_tests so this test (and the
whole default suite) never depends on a running Ollama.
"""

from __future__ import annotations

import os

os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

import api.main as api_main  # noqa: E402
from ai.mock_provider import MockLLMProvider  # noqa: E402
from ai.provider import LLMUnavailableError  # noqa: E402
from api.dependencies import reset_llm_provider_for_tests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.service import HermesService  # noqa: E402


def _token_for(client: TestClient, sub: str) -> str:
    return client.post("/api/auth/token", json={"sub": sub}).json()["access_token"]


def test_manager_gets_a_governed_proposal(tmp_path):
    db = HermesDB(tmp_path / "assist.db")
    svc = HermesService(db=db)
    api_main.reset_service_for_tests(svc)
    reset_llm_provider_for_tests(
        MockLLMProvider(fixed_response='{"skills": [{"skill": "Python", "importance": "required"}]}')
    )
    try:
        with TestClient(api_main.app) as client:
            token = _token_for(client, "demo-manager")
            resp = client.post(
                "/api/requests/parse",
                json={"description": "need a python person"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["available"] is True
            assert body["proposal"]["skills"][0]["mapped_skill_id"] == "python"
            assert body["proposal"]["ambiguities"] == []
    finally:
        api_main.reset_service_for_tests(None)
        reset_llm_provider_for_tests(None)


def test_employee_is_rejected_manager_only(tmp_path):
    db = HermesDB(tmp_path / "assist2.db")
    svc = HermesService(db=db)
    api_main.reset_service_for_tests(svc)
    reset_llm_provider_for_tests(MockLLMProvider(fixed_response='{"skills": []}'))
    try:
        with TestClient(api_main.app) as client:
            token = _token_for(client, "demo-employee")
            resp = client.post(
                "/api/requests/parse",
                json={"description": "need someone"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403
    finally:
        api_main.reset_service_for_tests(None)
        reset_llm_provider_for_tests(None)


def test_llm_unavailable_returns_clean_fallback_not_an_error(tmp_path):
    """Phase 16: Ollama offline must never break the endpoint — it answers
    available: false so the manager can continue manually."""
    db = HermesDB(tmp_path / "assist3.db")
    svc = HermesService(db=db)
    api_main.reset_service_for_tests(svc)

    class _OfflineProvider:
        def generate(self, prompt, *, system=None, timeout=30.0):
            raise LLMUnavailableError("simulated offline")

    reset_llm_provider_for_tests(_OfflineProvider())
    try:
        with TestClient(api_main.app) as client:
            token = _token_for(client, "demo-manager")
            resp = client.post(
                "/api/requests/parse",
                json={"description": "need someone"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["available"] is False
            assert body["proposal"] is None
            assert "offline" in body["reason"]
    finally:
        api_main.reset_service_for_tests(None)
        reset_llm_provider_for_tests(None)


def test_empty_description_is_rejected_with_422(tmp_path):
    db = HermesDB(tmp_path / "assist4.db")
    svc = HermesService(db=db)
    api_main.reset_service_for_tests(svc)
    reset_llm_provider_for_tests(MockLLMProvider(fixed_response="{}"))
    try:
        with TestClient(api_main.app) as client:
            token = _token_for(client, "demo-manager")
            resp = client.post(
                "/api/requests/parse",
                json={"description": ""},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 422
    finally:
        api_main.reset_service_for_tests(None)
        reset_llm_provider_for_tests(None)
