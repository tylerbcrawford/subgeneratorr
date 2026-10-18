#!/usr/bin/env python3
"""
Shared LLM provider layer for subgeneratorr.

A single dispatch point — ``call_llm()`` — that both ``KeytermSearcher``
(keyterm generation) and ``SubtitleTranslator`` (subtitle translation) use to
talk to Anthropic, OpenAI, Google, or a local Ollama server. Centralising the
provider plumbing here keeps the ``(text, input_tokens, output_tokens)``
contract, cost math, and human-readable error mapping in one place.

``MODEL_SPECS`` is the single source of truth for the cloud model roster: API
ids, display labels, pricing, and each model's request quirks. The web UI
renders its model pickers from ``model_catalog()``, so adding or retiring a
model is a one-file change.

Ollama is exposed as a fourth provider via OpenAI's wire-compatible
``/v1`` endpoint, so local users get free, offline inference. Because its model
name is free-text (e.g. ``llama3.1``) and carries no ``MODEL_SPECS`` entry,
``calculate_cost()`` naturally returns ``0.0`` for it — no special-casing.
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
# Seconds to wait for one Ollama completion. Local generation on a slow CPU can
# legitimately take minutes; raise this rather than letting requests time out.
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "600"))
# Extra token budget for local models. Thinking models (qwen3, deepseek-r1,
# gpt-oss...) reason before answering and cannot always be switched off, so a
# visible-answer budget alone ends in an empty, truncated reply. Non-thinking
# models stop at their natural end, so the headroom costs them nothing.
OLLAMA_THINKING_HEADROOM = int(os.environ.get("OLLAMA_THINKING_HEADROOM", "8192"))
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def ollama_api_root(host: str) -> str:
    """``ollama:11434`` / ``http://ollama:11434/v1/`` -> ``http://ollama:11434``."""
    base = host.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = "http://" + base
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base


def ollama_base_url(host: str) -> str:
    """Coerce a user-supplied Ollama host into its OpenAI-compatible ``.../v1`` URL."""
    return ollama_api_root(host) + "/v1"


class LLMProvider(Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    OLLAMA = "ollama"


class LLMModel(Enum):
    """Supported LLM models with their API identifiers (cloud providers only)."""

    # Anthropic models (Claude 5.5 series)
    CLAUDE_SONNET_5_5 = "claude-sonnet-5-5"
    CLAUDE_HAIKU_5_5 = "claude-haiku-5-5"

    # OpenAI models (GPT-6 series — reasoning models, run with reasoning minimized)
    GPT_6_1_SOL = "gpt-6.1-sol"
    GPT_6_LUNA = "gpt-6-luna"

    # Google models (Gemini 3.x series)
    GEMINI_3_8_FLASH = "gemini-3.8-flash"
    GEMINI_3_5_FLASH_LITE = "gemini-3.5-flash-lite"


class LLMError(Exception):
    """A provider call failed; the message is safe to show in the UI."""


@dataclass(frozen=True)
class ModelSpec:
    """Everything the app needs to know about one cloud model.

    ``request_options`` holds provider-specific knobs merged into the request:
    Anthropic ``thinking``, OpenAI ``reasoning_effort``, Google
    ``thinking_level``. Every current model thinks by default; these tasks
    (keyterm lists, cue-by-cue translation) don't benefit, and thinking tokens
    would eat the response budget, so each model is pinned to its lowest
    accepted setting. ``thinking_headroom`` is added to ``max_tokens`` for
    models whose floor still reasons a little.
    """

    provider: LLMProvider
    label: str
    hint: str
    input_price: float  # USD per 1M input tokens
    output_price: float  # USD per 1M output tokens (thinking tokens bill as output)
    request_options: Dict[str, Any] = field(default_factory=dict)
    thinking_headroom: int = 0


# Ordered best-quality first: the first model listed for a provider is its default.
MODEL_SPECS: Dict[LLMModel, ModelSpec] = {
    # "disabled" is a 400 on Sonnet 5.5; between_tools is its thinking-off mode.
    LLMModel.CLAUDE_SONNET_5_5: ModelSpec(
        LLMProvider.ANTHROPIC,
        "Claude Sonnet 5.5",
        "Best Quality",
        2.00,
        10.00,
        {"thinking": {"type": "between_tools"}},
    ),
    # Haiku 5.5 bills $0.50/$2.50 above a 100K-token prompt; our prompts are far smaller.
    LLMModel.CLAUDE_HAIKU_5_5: ModelSpec(
        LLMProvider.ANTHROPIC,
        "Claude Haiku 5.5",
        "Faster, Cheaper",
        0.10,
        0.50,
        {"thinking": {"type": "disabled"}},
    ),
    # Sol rejects reasoning_effort "none"; "low" is its floor.
    LLMModel.GPT_6_1_SOL: ModelSpec(
        LLMProvider.OPENAI,
        "GPT-6.1 Sol",
        "Best Quality",
        2.00,
        10.00,
        {"reasoning_effort": "low"},
        thinking_headroom=1024,
    ),
    LLMModel.GPT_6_LUNA: ModelSpec(
        LLMProvider.OPENAI,
        "GPT-6 Luna",
        "Faster, Cheaper",
        0.10,
        0.50,
        {"reasoning_effort": "none"},
    ),
    # Priced at the list rate effective 2027-01-01 ($0.75/$3.75 promo until then)
    # so estimates err high rather than going stale. 3.8 Flash rejects "minimal".
    LLMModel.GEMINI_3_8_FLASH: ModelSpec(
        LLMProvider.GOOGLE,
        "Gemini 3.8 Flash",
        "Best Quality · Free Tier",
        1.50,
        7.50,
        {"thinking_level": "low"},
        thinking_headroom=1536,
    ),
    LLMModel.GEMINI_3_5_FLASH_LITE: ModelSpec(
        LLMProvider.GOOGLE,
        "Gemini 3.5 Flash-Lite",
        "Faster, Cheaper · Free Tier",
        0.30,
        2.50,
        {"thinking_level": "minimal"},
        thinking_headroom=512,
    ),
}

# Retired model ids still accepted from older clients, saved settings, and
# scripts that call the REST API directly — each maps to its replacement.
LEGACY_MODEL_ALIASES: Dict[str, LLMModel] = {
    "claude-sonnet-4": LLMModel.CLAUDE_SONNET_5_5,
    "claude-sonnet-4-6": LLMModel.CLAUDE_SONNET_5_5,
    "claude-haiku-4-5": LLMModel.CLAUDE_HAIKU_5_5,
    "gpt-4.1": LLMModel.GPT_6_1_SOL,
    "gpt-4.1-mini": LLMModel.GPT_6_LUNA,
    "gemini-2.5-flash": LLMModel.GEMINI_3_5_FLASH_LITE,
}

# Model pricing (per 1M tokens), derived from MODEL_SPECS. Ollama models are
# intentionally absent so the cost lookup misses and falls through to $0.00.
MODEL_PRICING = {
    model: {"input": spec.input_price, "output": spec.output_price}
    for model, spec in MODEL_SPECS.items()
}


def resolve_model(model_id: str) -> LLMModel:
    """Map an API model id (current or retired alias) to its ``LLMModel``.

    Raises:
        ValueError: The id is neither a supported model nor a known alias.
    """
    try:
        return LLMModel(model_id)
    except ValueError:
        pass
    if model_id in LEGACY_MODEL_ALIASES:
        return LEGACY_MODEL_ALIASES[model_id]
    raise ValueError(f"Unsupported model: {model_id}")


def default_model(provider: LLMProvider) -> LLMModel:
    """The provider's best-quality model (first listed in MODEL_SPECS)."""
    return next(m for m, s in MODEL_SPECS.items() if s.provider == provider)


def model_catalog() -> Dict[str, List[Dict[str, str]]]:
    """Cloud model roster for the UI: ``{provider: [{id, label, hint}, ...]}``."""
    catalog: Dict[str, List[Dict[str, str]]] = {}
    for model, spec in MODEL_SPECS.items():
        catalog.setdefault(spec.provider.value, []).append(
            {"id": model.value, "label": spec.label, "hint": spec.hint}
        )
    return catalog


def _spec_for(model: Any) -> Optional[ModelSpec]:
    """Spec for an ``LLMModel`` or API id string; None for Ollama/unknown ids."""
    if isinstance(model, LLMModel):
        return MODEL_SPECS.get(model)
    try:
        return MODEL_SPECS.get(resolve_model(model))
    except (ValueError, TypeError):
        return None


def calculate_cost(model: Any, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate USD cost from separate input/output token counts.

    ``model`` may be an ``LLMModel`` (cloud) or a free-text string (Ollama).
    Anything without a ``MODEL_SPECS`` entry — including every Ollama model —
    returns ``0.0``.
    """
    spec = MODEL_SPECS.get(model) if isinstance(model, LLMModel) else None
    if not spec:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * spec.input_price
    output_cost = (output_tokens / 1_000_000) * spec.output_price
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
        max_tokens: Response token budget (the model's thinking headroom, or
            OLLAMA_THINKING_HEADROOM for Ollama, is added on top, so callers
            size it for the visible answer only).
        system_prompt: Optional system instruction. Omitted entirely when None
            (this preserves KeytermSearcher's Anthropic call, which sends none).
        base_url: Override the endpoint (used to point Ollama at its server).
        client: Pre-built SDK client (dependency injection for tests / reuse).

    Raises:
        ValueError: Unknown provider.
        LLMError: Provider API failure, refusal, or empty/truncated response,
            mapped to a human-readable message.
    """
    spec = _spec_for(model) if provider != LLMProvider.OLLAMA else None
    options = dict(spec.request_options) if spec else {}
    if provider == LLMProvider.OLLAMA:
        budget = max_tokens + OLLAMA_THINKING_HEADROOM
    else:
        budget = max_tokens + (spec.thinking_headroom if spec else 0)

    if provider == LLMProvider.ANTHROPIC:
        return _call_anthropic(model, api_key, prompt, budget, system_prompt, options, client)
    if provider in (LLMProvider.OPENAI, LLMProvider.OLLAMA):
        return _call_openai_compatible(
            provider, model, api_key, prompt, budget, system_prompt, base_url, options, client
        )
    if provider == LLMProvider.GOOGLE:
        return _call_google(model, api_key, prompt, budget, system_prompt, options, client)
    raise ValueError(f"Unsupported provider: {provider}")


def _map_api_error(label: str, e: Exception) -> LLMError:
    """Translate an SDK exception into a short, user-facing ``LLMError``."""
    error_str = str(e)
    lowered = error_str.lower()
    # anthropic/openai expose status_code; google-genai exposes code.
    status = getattr(e, "status_code", None) or getattr(e, "code", None)
    if status == 429 or "rate_limit" in lowered or "429" in error_str:
        if label == "Gemini" or "resource_exhausted" in lowered:
            return LLMError(
                "Gemini API quota exceeded — try a different model or check your billing plan"
            )
        return LLMError(f"{label} API rate limit exceeded — wait a moment and try again")
    if "resource_exhausted" in lowered:
        return LLMError(
            "Gemini API quota exceeded — try a different model or check your billing plan"
        )
    if "insufficient_quota" in lowered:
        return LLMError(f"{label} API quota exceeded — check your billing plan")
    if (
        status == 401
        or "401" in error_str
        or "authentication" in lowered
        or "unauthenticated" in lowered
    ):
        return LLMError(f"{label} API key is invalid or expired")
    if status == 403 or "403" in error_str or "permission_denied" in lowered:
        return LLMError(f"{label} API key lacks permission for this model")
    brief = error_str.split("\n")[0][:200]
    return LLMError(f"{label} API error: {brief}")


def _call_anthropic(model, api_key, prompt, max_tokens, system_prompt, options, client):
    if client is None:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Install with: pip install 'anthropic>=1,<2'"
            )
        client = anthropic.Anthropic(api_key=api_key)

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        **options,
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    try:
        message = client.messages.create(**kwargs)
    except Exception as e:
        raise _map_api_error("Anthropic", e)

    stop_reason = getattr(message, "stop_reason", None)
    if stop_reason == "refusal":
        raise LLMError("Anthropic declined this request (content policy) — try another provider")
    # Responses can open with thinking blocks; only text blocks carry the answer.
    text = "".join(
        block.text for block in message.content if getattr(block, "type", "text") == "text"
    )
    if not text:
        if stop_reason == "max_tokens":
            raise LLMError("Anthropic response hit the token limit before producing any text")
        raise LLMError("Anthropic API returned an empty response")
    return text, message.usage.input_tokens, message.usage.output_tokens


def _call_openai_compatible(
    provider, model, api_key, prompt, max_tokens, system_prompt, base_url, options, client
):
    """OpenAI and Ollama share the OpenAI Chat Completions wire format."""
    is_ollama = provider == LLMProvider.OLLAMA
    label = "Ollama" if is_ollama else "OpenAI"

    if client is None:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package not installed. Install with: pip install 'openai>=3,<4'"
            )
        if is_ollama:
            # Ollama ignores the key, but the OpenAI client requires a non-empty one.
            # No SDK retries: a timed-out local generation is CPU-bound, so a
            # retry repeats the same work (the SDK default would triple it).
            client = openai.OpenAI(
                api_key=api_key or "ollama",
                base_url=base_url or DEFAULT_OLLAMA_BASE_URL,
                timeout=OLLAMA_TIMEOUT,
                max_retries=0,
            )
        else:
            client = openai.OpenAI(api_key=api_key)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # OpenAI reasoning models reject max_tokens outright; max_completion_tokens
    # works on every current model. Ollama's compatibility layer reads max_tokens.
    token_param = "max_tokens" if is_ollama else "max_completion_tokens"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **{token_param: max_tokens},
            **options,
        )
    except Exception as e:
        error_str = str(e).lower()
        if is_ollama and ("timeout" in type(e).__name__.lower() or "timed out" in error_str):
            raise LLMError(
                f"Ollama did not finish within {OLLAMA_TIMEOUT:.0f}s — the model is too slow "
                "on this hardware; try a smaller model or raise OLLAMA_TIMEOUT"
            )
        if is_ollama and (
            "connection" in error_str
            or "refused" in error_str
            or "failed to establish" in error_str
        ):
            raise LLMError(
                "Could not reach the Ollama server — check OLLAMA_HOST and that Ollama is running"
            )
        raise _map_api_error(label, e)

    if not response.choices:
        raise LLMError(f"{label} API returned an empty response — no choices")
    choice = response.choices[0]
    text = choice.message.content
    if not text:
        if getattr(choice.message, "refusal", None):
            raise LLMError(f"{label} declined this request (content policy) — try another provider")
        if getattr(choice, "finish_reason", None) == "length":
            raise LLMError(f"{label} response hit the token limit before producing any text")
        raise LLMError(f"{label} API returned an empty response")
    if is_ollama:
        # Older Ollama builds inline a thinking model's reasoning in the content
        text = _THINK_BLOCK_RE.sub("", text).strip()
        if not text:
            raise LLMError(f"{label} response contained only reasoning, no answer")
    return text, response.usage.prompt_tokens, response.usage.completion_tokens


def _call_google(model, api_key, prompt, max_tokens, system_prompt, options, client):
    if client is None:
        try:
            from google import genai
        except ImportError:
            raise ImportError(
                "google-genai package not installed. Install with: pip install 'google-genai>=2,<3'"
            )
        client = genai.Client(api_key=api_key)

    # Gemini 3.x thinks by default and bills thinking against max_output_tokens;
    # thinking_level pins it to the model's floor (see MODEL_SPECS).
    config = {"max_output_tokens": max_tokens}
    if "thinking_level" in options:
        config["thinking_config"] = {"thinking_level": options["thinking_level"]}
    if system_prompt:
        config["system_instruction"] = system_prompt

    try:
        response = client.models.generate_content(model=model, contents=prompt, config=config)
    except Exception as e:
        raise _map_api_error("Gemini", e)

    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count or 0
    # Thinking tokens are billed as output but reported separately.
    output_tokens = (usage.candidates_token_count or 0) + (
        getattr(usage, "thoughts_token_count", None) or 0
    )
    text = response.text
    if not text:
        candidates = getattr(response, "candidates", None) or []
        reason = str(getattr(candidates[0], "finish_reason", "") if candidates else "")
        if "MAX_TOKENS" in reason:
            raise LLMError("Gemini response hit the token limit before producing any text")
        if "SAFETY" in reason or "PROHIBITED" in reason or "BLOCK" in reason:
            raise LLMError("Gemini declined this request (content policy) — try another provider")
        raise LLMError("Gemini API returned an empty response")
    return text, input_tokens, output_tokens
