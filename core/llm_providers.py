#!/usr/bin/env python3
"""
Shared LLM provider layer for subgeneratorr.

A single dispatch point — ``call_llm()`` — that both ``KeytermSearcher``
(keyterm generation) and ``SubtitleTranslator`` (subtitle translation) use to
talk to Anthropic, OpenAI, Google, or a local Ollama server. Centralising the
provider plumbing here keeps the ``(text, input_tokens, output_tokens)``
contract, cost math, and human-readable error mapping in one place.

Ollama is exposed as a fourth provider via OpenAI's wire-compatible
``/v1`` endpoint, so local users get free, offline inference. Because its model
name is free-text (e.g. ``llama3.1``) and carries no ``MODEL_PRICING`` entry,
``calculate_cost()`` naturally returns ``0.0`` for it — no special-casing.
"""

from enum import Enum
from typing import Any, Optional, Tuple

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"


class LLMProvider(Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    OLLAMA = "ollama"


class LLMModel(Enum):
    """Supported LLM models with their API identifiers (cloud providers only)."""

    # Anthropic models (Claude 4.6 series)
    CLAUDE_SONNET_4_6 = "claude-sonnet-4-6"
    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5"

    # OpenAI models (GPT-4.1 series - non-reasoning, low latency)
    GPT_4_1 = "gpt-4.1"
    GPT_4_1_MINI = "gpt-4.1-mini"

    # Google models (Gemini 2.5 series)
    GEMINI_2_5_FLASH = "gemini-2.5-flash"


# Model pricing (per 1M tokens). Ollama models are intentionally absent so the
# cost lookup misses and falls through to $0.00.
MODEL_PRICING = {
    LLMModel.CLAUDE_SONNET_4_6: {"input": 3.00, "output": 15.00},
    LLMModel.CLAUDE_HAIKU_4_5: {"input": 1.00, "output": 5.00},
    LLMModel.GPT_4_1: {"input": 2.00, "output": 8.00},
    LLMModel.GPT_4_1_MINI: {"input": 0.40, "output": 1.60},
    LLMModel.GEMINI_2_5_FLASH: {"input": 0.30, "output": 2.50},
}


def calculate_cost(model: Any, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate USD cost from separate input/output token counts.

    ``model`` may be an ``LLMModel`` (cloud) or a free-text string (Ollama).
    Anything without a ``MODEL_PRICING`` entry — including every Ollama model —
    returns ``0.0``.
    """
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


def call_llm(
    provider: LLMProvider,
    model: str,
    api_key: Optional[str],
    prompt: str,
    *,
    max_tokens: int,
    system_prompt: Optional[str] = None,
    base_url: Optional[str] = None,
    thinking_budget: int = 1024,
    client: Any = None,
) -> Tuple[str, int, int]:
    """
    Dispatch a single completion request to ``provider`` and return
    ``(response_text, input_tokens, output_tokens)``.

    Args:
        provider: Which backend to call.
        model: The provider's model identifier (API string, not the enum).
        api_key: Provider API key (ignored by Ollama; a placeholder is used).
        prompt: The user prompt.
        max_tokens: Response token budget.
        system_prompt: Optional system instruction. Omitted entirely when None
            (this preserves KeytermSearcher's Anthropic call, which sends none).
        base_url: Override the endpoint (used to point Ollama at its server).
        thinking_budget: Google-only cap on "thinking" tokens.
        client: Pre-built SDK client (dependency injection for tests / reuse).

    Raises:
        ValueError: Unknown provider.
        Exception: Provider API failure, mapped to a human-readable message.
    """
    if provider == LLMProvider.ANTHROPIC:
        return _call_anthropic(model, api_key, prompt, max_tokens, system_prompt, client)
    if provider in (LLMProvider.OPENAI, LLMProvider.OLLAMA):
        return _call_openai_compatible(
            provider, model, api_key, prompt, max_tokens, system_prompt, base_url, client
        )
    if provider == LLMProvider.GOOGLE:
        return _call_google(
            model, api_key, prompt, max_tokens, system_prompt, thinking_budget, client
        )
    raise ValueError(f"Unsupported provider: {provider}")


def _call_anthropic(model, api_key, prompt, max_tokens, system_prompt, client):
    if client is None:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Install with: pip install anthropic>=0.30.0"
            )
        client = anthropic.Anthropic(api_key=api_key)

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    try:
        message = client.messages.create(**kwargs)
        if not message.content:
            raise Exception("Anthropic API returned empty response — no content blocks")
        response_text = message.content[0].text
        return response_text, message.usage.input_tokens, message.usage.output_tokens
    except Exception as e:
        error_str = str(e)
        if "rate_limit" in error_str.lower() or "429" in error_str:
            raise Exception("Anthropic API rate limit exceeded — wait a moment and try again")
        elif "401" in error_str or "authentication" in error_str.lower():
            raise Exception("Anthropic API key is invalid or expired")
        else:
            brief = error_str.split("\n")[0][:200]
            raise Exception(f"Anthropic API error: {brief}")


def _call_openai_compatible(
    provider, model, api_key, prompt, max_tokens, system_prompt, base_url, client
):
    """OpenAI and Ollama share the OpenAI Chat Completions wire format."""
    is_ollama = provider == LLMProvider.OLLAMA
    label = "Ollama" if is_ollama else "OpenAI"

    if client is None:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package not installed. Install with: pip install openai>=1.35.0"
            )
        if is_ollama:
            # Ollama ignores the key, but the OpenAI client requires a non-empty one.
            client = openai.OpenAI(
                api_key=api_key or "ollama",
                base_url=base_url or DEFAULT_OLLAMA_BASE_URL,
            )
        else:
            client = openai.OpenAI(api_key=api_key)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
        if not response.choices:
            raise Exception(f"{label} API returned empty response — no choices")
        response_text = response.choices[0].message.content
        return response_text, response.usage.prompt_tokens, response.usage.completion_tokens
    except Exception as e:
        error_str = str(e)
        if is_ollama and (
            "connection" in error_str.lower()
            or "refused" in error_str.lower()
            or "failed to establish" in error_str.lower()
        ):
            raise Exception(
                "Could not reach the Ollama server — check OLLAMA_HOST and that Ollama is running"
            )
        if "rate_limit" in error_str.lower() or "429" in error_str:
            raise Exception(f"{label} API rate limit exceeded — wait a moment and try again")
        elif "401" in error_str or "authentication" in error_str.lower():
            raise Exception(f"{label} API key is invalid or expired")
        elif "insufficient_quota" in error_str.lower():
            raise Exception(f"{label} API quota exceeded — check your billing plan")
        else:
            brief = error_str.split("\n")[0][:200]
            raise Exception(f"{label} API error: {brief}")


def _call_google(model, api_key, prompt, max_tokens, system_prompt, thinking_budget, client):
    if client is None:
        try:
            from google import genai
        except ImportError:
            raise ImportError(
                "google-genai package not installed. Install with: pip install google-genai>=1.0.0"
            )
        client = genai.Client(api_key=api_key)

    # Cap thinking tokens so they don't consume the output budget. Gemini 2.5
    # models spend "thinking" tokens against max_output_tokens; without this cap
    # thinking can swallow the entire budget, leaving nothing for the response.
    config = {
        "max_output_tokens": max_tokens,
        "thinking_config": {"thinking_budget": thinking_budget},
    }
    if system_prompt:
        config["system_instruction"] = system_prompt

    try:
        response = client.models.generate_content(model=model, contents=prompt, config=config)
        response_text = response.text
        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count
        return response_text, input_tokens, output_tokens
    except Exception as e:
        error_str = str(e)
        if "RESOURCE_EXHAUSTED" in error_str:
            raise Exception(
                "Gemini API quota exceeded — try a different model or check your billing plan"
            )
        elif "401" in error_str or "UNAUTHENTICATED" in error_str:
            raise Exception("Gemini API key is invalid or expired")
        elif "403" in error_str or "PERMISSION_DENIED" in error_str:
            raise Exception("Gemini API key lacks permission for this model")
        else:
            brief = error_str.split("\n")[0][:200]
            raise Exception(f"Gemini API error: {brief}")
