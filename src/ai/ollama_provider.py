"""Ollama LLM provider. Local-only today; the LLMProvider boundary (provider.py)
is what lets this be swapped for an Azure-hosted model later without touching
any calling code (src/ai/services/*, api/routers/assist.py).

Configuration is fail-closed, matching the rest of this codebase's secrets
policy (shared/secrets.py): OLLAMA_MODEL has no hardcoded fallback. An
unconfigured model name is a deployment mistake, not a default to paper over.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

from ai.provider import LLMUnavailableError
from shared.errors import ConfigurationError

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL")
        if not self.model:
            raise ConfigurationError(
                "OLLAMA_MODEL is not set. Hermes will not guess a model name — "
                "set it explicitly (e.g. OLLAMA_MODEL=qwen2.5:7b-instruct)."
            )

    def generate(self, prompt: str, *, system: Optional[str] = None, timeout: float = 30.0) -> str:
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        try:
            resp = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama request failed: {exc}") from exc
        except ValueError as exc:  # non-JSON body
            raise LLMUnavailableError(f"Ollama returned a non-JSON response: {exc}") from exc
        text = data.get("response")
        if text is None:
            raise LLMUnavailableError(f"Ollama response missing 'response' field: {data!r}")
        return text
