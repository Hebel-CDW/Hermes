"""OllamaProvider config and error-mapping — no real network calls (httpx is
monkeypatched). The one live-network test is tests/integration/test_ollama_live.py,
which self-skips unless Ollama is actually reachable.
"""

from __future__ import annotations

import os

import httpx
import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from ai.ollama_provider import OllamaProvider  # noqa: E402
from ai.provider import LLMUnavailableError  # noqa: E402
from shared.errors import ConfigurationError  # noqa: E402


def test_missing_model_raises_configuration_error(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(ConfigurationError):
        OllamaProvider()


def test_explicit_model_argument_does_not_need_env_var(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    provider = OllamaProvider(model="qwen2.5:3b-instruct")
    assert provider.model == "qwen2.5:3b-instruct"


def test_base_url_defaults_and_strips_trailing_slash(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    provider = OllamaProvider(model="x", base_url="http://example.test:11434/")
    assert provider.base_url == "http://example.test:11434"


def test_successful_generate_returns_response_text(monkeypatch):
    provider = OllamaProvider(model="x")

    def fake_post(url, json, timeout):
        assert json["model"] == "x"
        assert json["stream"] is False
        return httpx.Response(200, json={"response": "hello", "done": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr("ai.ollama_provider.httpx.post", fake_post)
    assert provider.generate("prompt") == "hello"


def test_system_prompt_is_included_when_given(monkeypatch):
    provider = OllamaProvider(model="x")
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(json)
        return httpx.Response(200, json={"response": "ok"}, request=httpx.Request("POST", url))

    monkeypatch.setattr("ai.ollama_provider.httpx.post", fake_post)
    provider.generate("prompt", system="be terse")
    assert captured["system"] == "be terse"


def test_connection_error_raises_unavailable(monkeypatch):
    provider = OllamaProvider(model="x")

    def fake_post(url, json, timeout):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr("ai.ollama_provider.httpx.post", fake_post)
    with pytest.raises(LLMUnavailableError):
        provider.generate("prompt")


def test_non_2xx_status_raises_unavailable(monkeypatch):
    provider = OllamaProvider(model="x")

    def fake_post(url, json, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(500, json={"error": "boom"}, request=request)

    monkeypatch.setattr("ai.ollama_provider.httpx.post", fake_post)
    with pytest.raises(LLMUnavailableError):
        provider.generate("prompt")


def test_response_missing_response_field_raises_unavailable(monkeypatch):
    provider = OllamaProvider(model="x")

    def fake_post(url, json, timeout):
        return httpx.Response(200, json={"done": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr("ai.ollama_provider.httpx.post", fake_post)
    with pytest.raises(LLMUnavailableError):
        provider.generate("prompt")
