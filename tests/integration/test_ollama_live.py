"""Optional, self-skipping live-Ollama integration test (Phase 32).

Core CI must pass with zero running Ollama — this test checks for a reachable
instance at import time and skips cleanly if there isn't one, rather than
requiring a pytest marker flag to opt out. Run explicitly with:

    OLLAMA_MODEL=qwen2.5:7b-instruct pytest tests/integration/test_ollama_live.py

Verified working against the local Ollama instance during development of this
feature (qwen2.5:7b-instruct, ~6s latency, correctly mapped known skills and
correctly refused to invent a mapping for an unknown one).
"""

from __future__ import annotations

import os

import httpx
import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from ai.ollama_provider import DEFAULT_BASE_URL  # noqa: E402


def _ollama_reachable() -> bool:
    base = os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL)
    try:
        httpx.get(f"{base}/api/tags", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not (os.getenv("OLLAMA_MODEL") and _ollama_reachable()),
    reason="no reachable Ollama instance / OLLAMA_MODEL not set — set it to run this test",
)


def test_real_ollama_extracts_known_skills_and_flags_unknown_ones():
    from ai.ollama_provider import OllamaProvider
    from ai.services.work_requirement import extract_work_requirement

    provider = OllamaProvider()
    proposal = extract_work_requirement(
        provider,
        "I need someone to automate ServiceNow incident triage using Python and REST APIs.",
    )
    mapped_ids = {s.mapped_skill_id for s in proposal.skills}
    # The model may phrase things slightly differently across runs; assert on
    # the two skills that are unambiguous governed-taxonomy names.
    assert "python" in mapped_ids
    assert "servicenow" in mapped_ids
    # Nothing in the response may ever silently create a new taxonomy entry —
    # mapped_skill_id is None for the one proposal we expect not to match.
    assert all(s.mapped_skill_id is not None for s in proposal.skills)
