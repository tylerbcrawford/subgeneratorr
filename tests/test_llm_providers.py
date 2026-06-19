#!/usr/bin/env python3
"""
Tests for the shared LLM provider layer (core/llm_providers.py).

This module is the single dispatch point both KeytermSearcher and
SubtitleTranslator use to talk to Anthropic / OpenAI / Google / Ollama.
Tests inject fake clients (dependency injection) so no real SDK or network
call is needed, and assert the (text, input_tokens, output_tokens) contract
plus provider-specific wiring (Ollama base_url + $0 cost, Anthropic system
omission, Google thinking budget).
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.llm_providers import (  # noqa: E402
    LLMModel,
    LLMProvider,
    calculate_cost,
    call_llm,
)

# --- Fake SDK responses / clients (no network, no real SDK) -----------------


class _Recorder:
    """Callable that records the kwargs it was called with and returns a canned response."""

    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _fake_anthropic_response(text, in_tok, out_tok):
    return types.SimpleNamespace(
        content=[types.SimpleNamespace(text=text)],
        usage=types.SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
    )


def _fake_openai_response(text, in_tok, out_tok):
    choice = types.SimpleNamespace(message=types.SimpleNamespace(content=text))
    return types.SimpleNamespace(
        choices=[choice],
        usage=types.SimpleNamespace(prompt_tokens=in_tok, completion_tokens=out_tok),
    )


def _fake_google_response(text, in_tok, out_tok):
    return types.SimpleNamespace(
        text=text,
        usage_metadata=types.SimpleNamespace(
            prompt_token_count=in_tok, candidates_token_count=out_tok
        ),
    )


class FakeAnthropicClient:
    def __init__(self, response):
        self.messages = types.SimpleNamespace(create=_Recorder(response))


class FakeOpenAIClient:
    def __init__(self, response):
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=_Recorder(response))
        )


class FakeGoogleClient:
    def __init__(self, response):
        self.models = types.SimpleNamespace(generate_content=_Recorder(response))


# --- Provider enum ----------------------------------------------------------


def test_ollama_provider_enum_value():
    assert LLMProvider.OLLAMA.value == "ollama"


# --- Cost calculation -------------------------------------------------------


def test_calculate_cost_uses_per_million_pricing():
    # GPT-4.1 priced at $2.00/1M in, $8.00/1M out.
    cost = calculate_cost(LLMModel.GPT_4_1, 1_000_000, 1_000_000)
    assert cost == pytest.approx(10.00)


def test_calculate_cost_returns_zero_for_free_text_ollama_model():
    # A free-text Ollama model name has no MODEL_PRICING entry -> $0.00.
    assert calculate_cost("llama3.1", 5000, 5000) == 0.0


# --- call_llm: contract + per-provider wiring -------------------------------


def test_call_llm_openai_returns_text_and_token_contract():
    client = FakeOpenAIClient(_fake_openai_response("Hola", 12, 34))
    result = call_llm(
        LLMProvider.OPENAI,
        "gpt-4.1",
        "key",
        "Translate this",
        max_tokens=500,
        system_prompt="sys",
        client=client,
    )
    assert result == ("Hola", 12, 34)
    kw = client.chat.completions.create.kwargs
    assert kw["model"] == "gpt-4.1"
    assert kw["max_tokens"] == 500
    assert kw["messages"][0] == {"role": "system", "content": "sys"}
    assert kw["messages"][-1] == {"role": "user", "content": "Translate this"}


def test_call_llm_anthropic_omits_system_when_not_provided():
    # KeytermSearcher's Anthropic path passes no system prompt; preserve that.
    client = FakeAnthropicClient(_fake_anthropic_response("Bonjour", 7, 9))
    result = call_llm(
        LLMProvider.ANTHROPIC,
        "claude-sonnet-4-6",
        "key",
        "Translate this",
        max_tokens=500,
        client=client,
    )
    assert result == ("Bonjour", 7, 9)
    assert "system" not in client.messages.create.kwargs


def test_call_llm_anthropic_includes_system_when_provided():
    client = FakeAnthropicClient(_fake_anthropic_response("x", 1, 1))
    call_llm(
        LLMProvider.ANTHROPIC,
        "claude-sonnet-4-6",
        "key",
        "p",
        max_tokens=10,
        system_prompt="be terse",
        client=client,
    )
    assert client.messages.create.kwargs["system"] == "be terse"


def test_call_llm_google_returns_contract_and_sets_thinking_budget():
    client = FakeGoogleClient(_fake_google_response("Hallo", 20, 30))
    result = call_llm(
        LLMProvider.GOOGLE,
        "gemini-2.5-flash",
        "key",
        "Translate this",
        max_tokens=2048,
        system_prompt="sys",
        thinking_budget=1024,
        client=client,
    )
    assert result == ("Hallo", 20, 30)
    cfg = client.models.generate_content.kwargs["config"]
    assert cfg["max_output_tokens"] == 2048
    assert cfg["thinking_config"]["thinking_budget"] == 1024
    assert cfg["system_instruction"] == "sys"


def test_call_llm_ollama_builds_openai_client_with_base_url_and_key_fallback(monkeypatch):
    constructed = {}
    fake_response = _fake_openai_response("Ciao", 3, 4)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            constructed.update(kwargs)
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=_Recorder(fake_response))
            )

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    result = call_llm(
        LLMProvider.OLLAMA,
        "llama3.1",
        None,
        "Translate this",
        max_tokens=4096,
        base_url="http://ollama:11434/v1",
    )
    assert result == ("Ciao", 3, 4)
    assert constructed["base_url"] == "http://ollama:11434/v1"
    # Ollama ignores the key but the OpenAI client requires a non-empty placeholder.
    assert constructed["api_key"]


def test_call_llm_rejects_unknown_provider():
    with pytest.raises(ValueError):
        call_llm("not-a-provider", "m", "k", "p", max_tokens=10, client=object())
