from __future__ import annotations

import os

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from ai.mock_provider import MockLLMProvider  # noqa: E402
from ai.provider import LLMUnavailableError  # noqa: E402


def test_fixed_response_is_returned_verbatim():
    provider = MockLLMProvider(fixed_response='{"skills": []}')
    assert provider.generate("anything") == '{"skills": []}'


def test_substring_lookup_matches_prompt():
    provider = MockLLMProvider(responses_by_prompt_substring={"ServiceNow": '{"skills": [{"skill": "ServiceNow"}]}'})
    out = provider.generate("Work description: ServiceNow stuff")
    assert "ServiceNow" in out


def test_unmatched_prompt_raises_unavailable():
    provider = MockLLMProvider(responses_by_prompt_substring={"foo": "bar"})
    with pytest.raises(LLMUnavailableError):
        provider.generate("no match here")


def test_fail_flag_simulates_offline_provider():
    provider = MockLLMProvider(fail=True)
    with pytest.raises(LLMUnavailableError):
        provider.generate("anything")


def test_calls_are_recorded_for_test_introspection():
    provider = MockLLMProvider(fixed_response="{}")
    provider.generate("prompt one", system="sys")
    assert provider.calls == [("prompt one", "sys")]
