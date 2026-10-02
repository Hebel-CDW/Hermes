"""The LLM provider interface. Every concrete provider (Ollama, mock, any future
enterprise provider) implements this and nothing more.

Deliberately minimal: one method, raw text in, raw text out. Structured output
validation, skill normalization, and every governance check live in
``src/ai/services/*`` — never in a provider. A provider that returns garbage
must never be able to put garbage into application state; that is enforced one
layer up, not here.
"""

from __future__ import annotations

from typing import Optional, Protocol


class LLMProvider(Protocol):
    def generate(self, prompt: str, *, system: Optional[str] = None, timeout: float = 30.0) -> str:
        """Return the model's raw text completion. Raise LLMUnavailableError on
        any failure (connection, timeout, non-2xx, malformed provider response).
        Never returns partial/truncated output silently — callers can trust that
        a returned string is the provider's complete answer or an exception was
        raised instead.
        """
        ...


class LLMUnavailableError(Exception):
    """Raised by any provider when it cannot produce a completion. Callers
    (src/ai/services/*) must catch this and fail safely — Hermes's deterministic
    ranking must keep working with zero LLM assistance available."""
