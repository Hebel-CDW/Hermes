"""POST /api/copilot/ask: grounded, advisory, role-scoped, and never dependent on the LLM.

Runs against the seeded demo organisation with a mock LLM, so no Ollama is needed.
"""

from __future__ import annotations

import os

os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

import api.main as api_main  # noqa: E402
import pytest  # noqa: E402
from ai.mock_provider import MockLLMProvider  # noqa: E402
from api.dependencies import reset_llm_provider_for_tests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from scripts.seed_demo_org import seed  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.service import HermesService  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    path = tmp_path / "org.db"
    seed(path)
    api_main.reset_service_for_tests(HermesService(db=HermesDB(path)))
    with TestClient(api_main.app) as c:
        yield c
    api_main.reset_service_for_tests(None)
    reset_llm_provider_for_tests(None)


def _auth(client: TestClient, sub: str) -> dict:
    token = client.post("/api/auth/token", json={"sub": sub}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_manager_question_is_grounded_in_workforce_facts(client):
    llm = MockLLMProvider(fixed_response="Priya Nair is the clear first choice.")
    reset_llm_provider_for_tests(llm)
    r = client.post("/api/copilot/ask", json={"question": "Who has only one backup?"}, headers=_auth(client, "demo-manager"))
    assert r.status_code == 200
    assert r.json()["source"] == "model"
    prompt, system = llm.calls[-1]
    assert "SKILLS WITH EXACTLY ONE HOLDER" in prompt and "Gregory Baptiste" in prompt
    assert "ALREADY WORKED OUT" in system and "Never invent" in system


def test_employee_prompt_contains_only_their_own_data(client):
    llm = MockLLMProvider(fixed_response="ok")
    reset_llm_provider_for_tests(llm)
    r = client.post("/api/copilot/ask", json={"question": "What should I learn?"}, headers=_auth(client, "demo-employee"))
    assert r.status_code == 200
    prompt, _ = llm.calls[-1]
    assert "YOUR CLOSEST ROLE" in prompt
    # Nobody else's name or record may reach an employee's prompt.
    assert "Priya Nair" not in prompt and "Walter Okafor" not in prompt
    assert "Contoso" not in prompt  # the dispute text itself is theirs, but only the status is summarised


def test_closest_role_uses_level_shortfall_and_critical_skills(client):
    llm = MockLLMProvider(fixed_response="ok")
    reset_llm_provider_for_tests(llm)
    client.post("/api/copilot/ask", json={"question": "closest role?"}, headers=_auth(client, "demo-employee"))
    prompt, _ = llm.calls[-1]
    line = next(l for l in prompt.splitlines() if l.startswith("YOUR CLOSEST ROLE"))
    # Sam Patel is one level short on two skills of Azure Platform Engineer, which has no critical skill.
    assert "Azure Platform Engineer" in line


def test_offline_fallback_when_model_is_down(client):
    reset_llm_provider_for_tests(MockLLMProvider(fail=True))
    r = client.post("/api/copilot/ask", json={"question": "anything"}, headers=_auth(client, "demo-manager"))
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "offline" and body["model"] is None
    assert "not reachable" in body["answer"]


def test_offline_fallback_never_shows_internal_model_directives(client):
    """Facts contain instructions for the model ("already worked out, state it as the answer"); a person must never see them."""
    reset_llm_provider_for_tests(MockLLMProvider(fail=True))
    for sub, q in (("demo-manager", "Who should I pick for the Senior Cloud Engineer role?"), ("demo-employee", "What should I learn next?")):
        body = client.post("/api/copilot/ask", json={"question": q}, headers=_auth(client, sub)).json()
        text = body["answer"].lower()
        assert body["source"] == "offline"
        assert "already worked out" not in text and "state it as the answer" not in text and "state exactly this" not in text
        assert "not an answer to your exact question" in text
    manager = client.post("/api/copilot/ask", json={"question": "Who should I pick for the Senior Cloud Engineer role?"},
                          headers=_auth(client, "demo-manager")).json()["answer"]
    assert "Priya Nair" in manager  # the focus line for the named role leads the summary


def test_offline_fallback_when_no_model_configured(client, monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    reset_llm_provider_for_tests(None)
    r = client.post("/api/copilot/ask", json={"question": "anything"}, headers=_auth(client, "demo-employee"))
    assert r.status_code == 200 and r.json()["source"] == "offline"


def test_copilot_requires_a_signed_in_employee_or_manager(client):
    assert client.post("/api/copilot/ask", json={"question": "hi"}).status_code == 401
    assert client.post("/api/copilot/ask", json={"question": "hi"}, headers=_auth(client, "demo-admin")).status_code == 403
    assert client.post("/api/copilot/ask", json={"question": ""}, headers=_auth(client, "demo-manager")).status_code == 422


def _prompt_for(client, question, sub="demo-manager", request_id=None):
    llm = MockLLMProvider(fixed_response="ok")
    reset_llm_provider_for_tests(llm)
    body = {"question": question}
    if request_id:
        body["request_id"] = request_id
    assert client.post("/api/copilot/ask", json=body, headers=_auth(client, sub)).status_code == 200
    return llm.calls[-1]


def test_skill_question_is_answered_from_a_worked_out_holder_list(client):
    prompt, _ = _prompt_for(client, "Who is the best person for Kubernetes on my team?")
    assert "FOCUS SKILL Container Orchestration (ALREADY WORKED OUT)" in prompt
    block = prompt.split("FOCUS SKILL Container Orchestration")[1].split("\n\n")[0]
    assert "Priya Nair" in block
    # Not a request question, so request fit scores must not be offered as distractors.
    assert "The manager's recent staffing requests" not in prompt


def test_person_question_lists_what_breaks_if_they_leave(client):
    prompt, _ = _prompt_for(client, "If Gregory Baptiste leaves, what breaks?")
    line = next(l for l in prompt.splitlines() if "IF Gregory Baptiste LEFT" in l)
    assert "RPGLE" in line and "HMC" in line and "High Availability" in line


def test_head_to_head_uses_the_engines_own_ranking(client):
    role = next(r for r in client.get("/api/roles", headers=_auth(client, "demo-manager")).json()["roles"] if r["role_name"] == "Data Protection Engineer")
    r = client.post("/api/fitness/rank", headers=_auth(client, "demo-manager"), json={
        "request_id": "h2h-1", "required_skills": role["required_skills"], "critical_skills": role["critical_skills"], "role_id": role["role_id"], "shortlist_size": 5})
    assert r.status_code == 200
    prompt, _ = _prompt_for(client, "Compare Walter Okafor and Hannah Kim. Who should I pick?", request_id="h2h-1")
    h2h = next(l for l in prompt.splitlines() if l.startswith("HEAD TO HEAD"))
    assert "Hannah Kim ranks #1" in h2h and "Walter Okafor ranks #2" in h2h
    assert "COMPARISON" in prompt and "[NEEDED by the open request" in prompt


def test_growth_question_separates_already_qualified_from_next_closest(client):
    prompt, _ = _prompt_for(client, "Who could grow into a Senior Cloud Engineer with the least training?")
    block = prompt.split("FOCUS ROLE Senior Cloud Engineer")[1]
    assert "ALREADY fully meet it: Priya Nair" in block
    assert "Mei Tanaka" in block.split("GROW into it")[1][:900]


def test_weakest_area_is_computed_not_guessed(client):
    prompt, _ = _prompt_for(client, "Which area is our weakest?")
    line = next(l for l in prompt.splitlines() if l.startswith("WEAKEST AREA"))
    assert "IBM i" in line


def test_question_specific_facts_come_last_so_the_model_cache_is_reused(client):
    prompt, _ = _prompt_for(client, "Who is the best person for Kubernetes on my team?")
    assert prompt.index("FOCUS SKILL") > prompt.index("People and their strongest skills")


def test_off_topic_and_pay_questions_are_declined_by_rule(client):
    _, system = _prompt_for(client, "Write me a poem about clouds.")
    assert "ONE sentence" in system and "poems" in system and "pay" in system
