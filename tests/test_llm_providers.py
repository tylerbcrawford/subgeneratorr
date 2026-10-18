#!/usr/bin/env python3
"""
Tests for the shared LLM provider layer (core/llm_providers.py).

This module is the single dispatch point both KeytermSearcher and
SubtitleTranslator use to talk to Anthropic / OpenAI / Google / Ollama.
Tests inject fake clients (dependency injection) so no real SDK or network
call is needed, and assert the (text, input_tokens, output_tokens) contract
plus provider-specific wiring (Ollama base_url + $0 cost, Anthropic system
omission, per-model thinking controls), refusal/truncation handling, and the
model catalog / retired-id aliases.
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import llm_providers  # noqa: E402
from core.llm_providers import (  # noqa: E402
    LEGACY_MODEL_ALIASES,
    MODEL_SPECS,
    LLMError,
    LLMModel,
    LLMProvider,
    calculate_cost,
    call_llm,
    default_model,
    model_catalog,
    resolve_model,
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


def _fake_anthropic_response(text, in_tok, out_tok, stop_reason="end_turn", blocks=None):
    return types.SimpleNamespace(
        content=blocks if blocks is not None else [types.SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=types.SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
    )


def _fake_openai_response(text, in_tok, out_tok, finish_reason="stop", refusal=None):
    choice = types.SimpleNamespace(
        message=types.SimpleNamespace(content=text, refusal=refusal),
        finish_reason=finish_reason,
    )
    return types.SimpleNamespace(
        choices=[choice],
        usage=types.SimpleNamespace(prompt_tokens=in_tok, completion_tokens=out_tok),
    )


def _fake_google_response(text, in_tok, out_tok, thoughts=None, finish_reason="STOP"):
    return types.SimpleNamespace(
        text=text,
        candidates=[types.SimpleNamespace(finish_reason=finish_reason)],
        usage_metadata=types.SimpleNamespace(
            prompt_token_count=in_tok,
            candidates_token_count=out_tok,
            thoughts_token_count=thoughts,
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
    # GPT-6.1 Sol priced at $2.00/1M in, $10.00/1M out.
    cost = calculate_cost(LLMModel.GPT_6_1_SOL, 1_000_000, 1_000_000)
    assert cost == pytest.approx(12.00)


def test_calculate_cost_returns_zero_for_free_text_ollama_model():
    # A free-text Ollama model name has no MODEL_PRICING entry -> $0.00.
    assert calculate_cost("llama3.1", 5000, 5000) == 0.0


# --- call_llm: contract + per-provider wiring -------------------------------


def test_call_llm_openai_returns_text_and_token_contract():
    client = FakeOpenAIClient(_fake_openai_response("Hola", 12, 34))
    result = call_llm(
        LLMProvider.OPENAI,
        "gpt-6-luna",
        "key",
        "Translate this",
        max_tokens=500,
        system_prompt="sys",
        client=client,
    )
    assert result == ("Hola", 12, 34)
    kw = client.chat.completions.create.kwargs
    assert kw["model"] == "gpt-6-luna"
    # GPT-6 reasoning models 400 on max_tokens; reasoning is switched off.
    assert kw["max_completion_tokens"] == 500
    assert "max_tokens" not in kw
    assert kw["reasoning_effort"] == "none"
    assert kw["messages"][0] == {"role": "system", "content": "sys"}
    assert kw["messages"][-1] == {"role": "user", "content": "Translate this"}


def test_call_llm_anthropic_omits_system_when_not_provided():
    # KeytermSearcher's Anthropic path passes no system prompt; preserve that.
    client = FakeAnthropicClient(_fake_anthropic_response("Bonjour", 7, 9))
    result = call_llm(
        LLMProvider.ANTHROPIC,
        "claude-sonnet-5-5",
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
        "claude-sonnet-5-5",
        "key",
        "p",
        max_tokens=10,
        system_prompt="be terse",
        client=client,
    )
    assert client.messages.create.kwargs["system"] == "be terse"


def test_call_llm_google_returns_contract_and_sets_thinking_level():
    client = FakeGoogleClient(_fake_google_response("Hallo", 20, 30, thoughts=5))
    result = call_llm(
        LLMProvider.GOOGLE,
        "gemini-3.5-flash-lite",
        "key",
        "Translate this",
        max_tokens=2048,
        system_prompt="sys",
        client=client,
    )
    # Thinking tokens bill as output, so they're folded into output_tokens.
    assert result == ("Hallo", 20, 35)
    cfg = client.models.generate_content.kwargs["config"]
    headroom = MODEL_SPECS[LLMModel.GEMINI_3_5_FLASH_LITE].thinking_headroom
    assert cfg["max_output_tokens"] == 2048 + headroom
    assert cfg["thinking_config"] == {"thinking_level": "minimal"}
    assert cfg["system_instruction"] == "sys"


def test_call_llm_ollama_builds_openai_client_with_base_url_and_key_fallback(monkeypatch):
    constructed = {}
    fake_response = _fake_openai_response("Ciao", 3, 4)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            constructed.update(kwargs)
            constructed["instance"] = self
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
    # Ollama's compatibility layer reads max_tokens and gets no reasoning knobs;
    # thinking headroom is added so reasoning models still reach an answer.
    kw = constructed["instance"].chat.completions.create.kwargs
    assert kw["max_tokens"] == 4096 + llm_providers.OLLAMA_THINKING_HEADROOM
    assert "reasoning_effort" not in kw
    # Ollama ignores the key but the OpenAI client requires a non-empty placeholder.
    assert constructed["api_key"]
    # Local generation is CPU-bound: explicit timeout, no SDK retries.
    assert constructed["timeout"] == llm_providers.OLLAMA_TIMEOUT
    assert constructed["max_retries"] == 0


def _ollama_client_returning(text, finish_reason="stop"):
    message = types.SimpleNamespace(content=text, refusal=None)
    response = types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=types.SimpleNamespace(prompt_tokens=5, completion_tokens=7),
    )
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda **kw: response))
    )


def test_ollama_strips_inline_think_blocks():
    client = _ollama_client_returning("<think>\nLet me recall the cast.\n</think>\nCobb, Ariadne")
    text, _, _ = call_llm(LLMProvider.OLLAMA, "qwen3:4b", None, "p", max_tokens=10, client=client)
    assert text == "Cobb, Ariadne"


def test_ollama_reasoning_only_reply_is_an_error():
    client = _ollama_client_returning("<think>hmm</think>")
    with pytest.raises(LLMError, match="only reasoning"):
        call_llm(LLMProvider.OLLAMA, "qwen3:4b", None, "p", max_tokens=10, client=client)


def test_ollama_timeout_maps_to_actionable_error():
    class APITimeoutError(Exception):
        pass

    def boom(**kwargs):
        raise APITimeoutError("Request timed out.")

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=boom))
    )
    with pytest.raises(LLMError, match="OLLAMA_TIMEOUT"):
        call_llm(LLMProvider.OLLAMA, "qwen2.5:3b", None, "p", max_tokens=10, client=client)


def test_call_llm_rejects_unknown_provider():
    with pytest.raises(ValueError):
        call_llm("not-a-provider", "m", "k", "p", max_tokens=10, client=object())


# --- Per-model thinking controls --------------------------------------------


def test_anthropic_models_send_their_thinking_off_config():
    # Sonnet 5.5 rejects {"type": "disabled"} (400) — between_tools is its off switch.
    expected = {
        "claude-sonnet-5-5": {"type": "between_tools"},
        "claude-haiku-5-5": {"type": "disabled"},
    }
    for model_id, thinking in expected.items():
        client = FakeAnthropicClient(_fake_anthropic_response("ok", 1, 1))
        call_llm(LLMProvider.ANTHROPIC, model_id, "key", "p", max_tokens=500, client=client)
        assert client.messages.create.kwargs["thinking"] == thinking


def test_gpt_sol_uses_low_reasoning_with_headroom():
    # gpt-6.1-sol rejects reasoning_effort "none"; "low" is its floor.
    client = FakeOpenAIClient(_fake_openai_response("ok", 1, 1))
    call_llm(LLMProvider.OPENAI, "gpt-6.1-sol", "key", "p", max_tokens=500, client=client)
    kw = client.chat.completions.create.kwargs
    assert kw["reasoning_effort"] == "low"
    assert kw["max_completion_tokens"] == 500 + MODEL_SPECS[LLMModel.GPT_6_1_SOL].thinking_headroom


def test_retired_model_id_gets_its_replacements_request_options():
    client = FakeOpenAIClient(_fake_openai_response("ok", 1, 1))
    call_llm(LLMProvider.OPENAI, "gpt-4.1-mini", "key", "p", max_tokens=100, client=client)
    assert client.chat.completions.create.kwargs["reasoning_effort"] == "none"


# --- Response robustness ----------------------------------------------------


def test_anthropic_skips_leading_thinking_blocks():
    blocks = [
        types.SimpleNamespace(type="thinking", thinking=""),
        types.SimpleNamespace(type="text", text="Bonjour"),
    ]
    client = FakeAnthropicClient(_fake_anthropic_response(None, 5, 6, blocks=blocks))
    result = call_llm(
        LLMProvider.ANTHROPIC, "claude-haiku-5-5", "key", "p", max_tokens=10, client=client
    )
    assert result == ("Bonjour", 5, 6)


def test_anthropic_refusal_raises_readable_error():
    client = FakeAnthropicClient(
        _fake_anthropic_response(None, 5, 0, stop_reason="refusal", blocks=[])
    )
    with pytest.raises(LLMError, match="declined"):
        call_llm(
            LLMProvider.ANTHROPIC, "claude-sonnet-5-5", "key", "p", max_tokens=10, client=client
        )


def test_anthropic_truncated_before_text_raises():
    blocks = [types.SimpleNamespace(type="thinking", thinking="")]
    client = FakeAnthropicClient(
        _fake_anthropic_response(None, 5, 10, stop_reason="max_tokens", blocks=blocks)
    )
    with pytest.raises(LLMError, match="token limit"):
        call_llm(
            LLMProvider.ANTHROPIC, "claude-sonnet-5-5", "key", "p", max_tokens=10, client=client
        )


def test_openai_empty_content_with_length_finish_raises():
    client = FakeOpenAIClient(_fake_openai_response(None, 5, 10, finish_reason="length"))
    with pytest.raises(LLMError, match="token limit"):
        call_llm(LLMProvider.OPENAI, "gpt-6-luna", "key", "p", max_tokens=10, client=client)


def test_openai_refusal_raises_readable_error():
    client = FakeOpenAIClient(_fake_openai_response(None, 5, 3, refusal="I can't help with that"))
    with pytest.raises(LLMError, match="declined"):
        call_llm(LLMProvider.OPENAI, "gpt-6-luna", "key", "p", max_tokens=10, client=client)


def test_google_max_tokens_with_no_text_raises():
    client = FakeGoogleClient(_fake_google_response(None, 5, 0, finish_reason="MAX_TOKENS"))
    with pytest.raises(LLMError, match="token limit"):
        call_llm(LLMProvider.GOOGLE, "gemini-3.8-flash", "key", "p", max_tokens=10, client=client)


def test_api_errors_map_by_status_code():
    class FakeStatusError(Exception):
        status_code = 429

    def _raise(**_):
        raise FakeStatusError("slow down")

    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=_raise))
    with pytest.raises(LLMError, match="rate limit"):
        call_llm(
            LLMProvider.ANTHROPIC, "claude-sonnet-5-5", "key", "p", max_tokens=10, client=client
        )


# --- Catalog / aliases ------------------------------------------------------


def test_every_model_has_a_spec_and_catalog_entry():
    assert set(MODEL_SPECS) == set(LLMModel)
    listed = {m["id"] for models in model_catalog().values() for m in models}
    assert listed == {m.value for m in LLMModel}


def test_catalog_lists_best_quality_first_per_provider():
    catalog = model_catalog()
    for provider in (LLMProvider.ANTHROPIC, LLMProvider.OPENAI, LLMProvider.GOOGLE):
        assert catalog[provider.value][0]["id"] == default_model(provider).value
        assert "Best Quality" in catalog[provider.value][0]["hint"]


def test_resolve_model_accepts_current_and_retired_ids():
    assert resolve_model("claude-haiku-5-5") is LLMModel.CLAUDE_HAIKU_5_5
    for retired, replacement in LEGACY_MODEL_ALIASES.items():
        assert resolve_model(retired) is replacement
    with pytest.raises(ValueError):
        resolve_model("not-a-model")


def test_retired_aliases_stay_within_provider():
    families = {"claude": "anthropic", "gpt": "openai", "gemini": "google"}
    for retired, replacement in LEGACY_MODEL_ALIASES.items():
        assert MODEL_SPECS[replacement].provider.value == families[retired.split("-")[0]]
