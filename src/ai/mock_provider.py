"""Deterministic, network-free LLM provider for tests.

Core CI must pass with zero running Ollama instance (Phase 32). Every test in
this repo that exercises the LLM-assist layer uses this provider, never the
real one, unless explicitly marked as a live-Ollama integration test.
"""

from __future__ import annotations

from typing import Mapping, Optional

from ai.provider import LLMUnavailableError


class MockLLMProvider:
    """Returns a fixed response, or looks one up by a substring match on the
    prompt. Raises LLMUnavailableError if ``fail`` is set, so callers' offline
    fallback paths are exercisable without touching a network."""

    def __init__(
        self,
        fixed_response: Optional[str] = None,
        responses_by_prompt_substring: Optional[Mapping[str, str]] = None,
        fail: bool = False,
    ) -> None:
        self._fixed = fixed_response
        self._by_substring = dict(responses_by_prompt_substring or {})
        self._fail = fail
        self.calls: list = []  # test introspection: every (prompt, system) pair received

    def generate(self, prompt: str, *, system: Optional[str] = None, timeout: float = 30.0) -> str:
        self.calls.append((prompt, system))
        if self._fail:
            raise LLMUnavailableError("mock provider configured to simulate unavailability")
        if self._fixed is not None:
            return self._fixed
        for needle, response in self._by_substring.items():
            if needle in prompt:
                return response
        raise LLMUnavailableError(f"MockLLMProvider has no configured response for prompt: {prompt!r}")
