"""Pure-Python governance tests for ai.services.work_requirement — no network,
no Ollama. Proves the exact-match-only skill mapping and the fail-safe
behavior on malformed model output.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from ai.mock_provider import MockLLMProvider  # noqa: E402
from ai.provider import LLMUnavailableError  # noqa: E402
from ai.services.work_requirement import LLMExtractionError, extract_work_requirement  # noqa: E402


def test_known_skills_map_to_governed_skill_ids():
    provider = MockLLMProvider(
        fixed_response='{"skills": [{"skill": "Python", "importance": "required"}]}'
    )
    proposal = extract_work_requirement(provider, "need a python person")
    assert proposal.ambiguities == []
    assert len(proposal.skills) == 1
    assert proposal.skills[0].mapped_skill_id == "python"
    assert proposal.skills[0].importance == "required"


def test_unknown_skill_label_becomes_an_ambiguity_not_a_taxonomy_write():
    """Core governance invariant (Phase 17): an LLM-proposed label that doesn't
    exactly match a governed skill name/id must never become a mapped skill_id."""
    provider = MockLLMProvider(
        fixed_response='{"skills": [{"skill": "Some Totally Unknown Thing", "importance": "required"}]}'
    )
    proposal = extract_work_requirement(provider, "need someone")
    assert proposal.skills == []
    assert proposal.ambiguities == ["Some Totally Unknown Thing"]


def test_markdown_fenced_json_is_still_parsed():
    provider = MockLLMProvider(
        fixed_response='Sure! Here you go:\n```json\n{"skills": [{"skill": "Python", "importance": "preferred"}]}\n```'
    )
    proposal = extract_work_requirement(provider, "need a python person")
    assert proposal.skills[0].mapped_skill_id == "python"
    assert proposal.skills[0].importance == "preferred"


def test_malformed_json_raises_extraction_error_not_a_crash():
    provider = MockLLMProvider(fixed_response="this is not json at all")
    with pytest.raises(LLMExtractionError):
        extract_work_requirement(provider, "need someone")


def test_missing_skills_key_raises_extraction_error():
    provider = MockLLMProvider(fixed_response='{"not_skills": []}')
    with pytest.raises(LLMExtractionError):
        extract_work_requirement(provider, "need someone")


def test_provider_failure_propagates_as_unavailable():
    provider = MockLLMProvider(fail=True)
    with pytest.raises(LLMUnavailableError):
        extract_work_requirement(provider, "need someone")


def test_duplicate_skill_ids_are_deduplicated():
    provider = MockLLMProvider(
        fixed_response=(
            '{"skills": ['
            '{"skill": "Python", "importance": "required"},'
            '{"skill": "python", "importance": "preferred"}'
            "]}"
        )
    )
    proposal = extract_work_requirement(provider, "need a python person, strongly")
    assert len(proposal.skills) == 1
