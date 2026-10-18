"""
Which translation targets a given LLM officially supports.

Cloud frontier models (Claude, GPT, Gemini) handle every target. Local Ollama
models vary widely, so this curated table maps Ollama model families to the
languages their model cards list. The web UI greys out unsupported targets
(advisory only: the backend never refuses a translation on this basis).

Unknown families fall back to "all targets, unverified" so a brand-new model is
never blocked, just flagged.
"""

import re
from dataclasses import dataclass
from typing import FrozenSet, List, Optional, Pattern, Tuple

from core.languages import TRANSLATION_CODES

_CLOUD_PROVIDERS = {"anthropic", "openai", "google"}


def _codes(spec: str) -> FrozenSet[str]:
    return frozenset(spec.split()) & TRANSLATION_CODES


# (pattern on the normalized model name, display label, supported targets or
# None for "all", source). First match wins, so specific patterns come first.
# An empty set means the card claims English only.
_FAMILIES: List[Tuple[Pattern, str, Optional[FrozenSet[str]], str]] = [
    # Qwen3 = 119 languages, Qwen3.5+ = 201 (huggingface.co/Qwen/Qwen3.5-9B).
    (re.compile(r"qwen3"), "Qwen 3", None, "qwenlm.github.io/blog/qwen3"),
    # Qwen2 / 2.5: English, Chinese + 27 languages (qwenlm.github.io/blog/qwen2).
    (
        re.compile(r"qwen2"),
        "Qwen 2.5",
        _codes(
            "en zh de fr es pt it nl ru cs pl ar fa he tr ja ko vi th id ms lo my km tl hi bn ur"
        ),
        "qwenlm.github.io/blog/qwen2",
    ),
    # Gemma 3 / 4: 140+ languages (ai.google.dev/gemma/docs/core/model_card_3).
    (re.compile(r"gemma[3-9]"), "Gemma 3+", None, "ai.google.dev/gemma/docs"),
    (re.compile(r"gemma"), "Gemma", _codes(""), "ai.google.dev/gemma/docs/core/model_card_2"),
    # Llama 4: 12 languages (llama.com/docs/model-cards-and-prompt-formats/llama4).
    (
        re.compile(r"llama4"),
        "Llama 4",
        _codes("ar en fr de hi id it pt es tl th vi"),
        "llama.com/docs/model-cards-and-prompt-formats/llama4",
    ),
    # Llama 3.1 / 3.2 / 3.3: 8 languages (github.com/meta-llama/llama-models).
    (
        re.compile(r"llama3"),
        "Llama 3",
        _codes("en de fr it pt hi es th"),
        "github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md",
    ),
    (
        re.compile(r"mistral-nemo"),
        "Mistral NeMo",
        _codes("en fr de es it pt zh ja ko ar hi"),
        "mistral.ai/news/mistral-nemo",
    ),
    (
        re.compile(r"mistral-small"),
        "Mistral Small",
        _codes("en fr de es it zh ja ko pt nl pl"),
        "mistral.ai/news/mistral-small-3",
    ),
    (
        re.compile(r"mistral(?:$|:)"),
        "Mistral 7B",
        _codes(""),
        "mistral.ai/news/announcing-mistral-7b",
    ),
    # Aya 23 / Aya Expanse: 23 languages (huggingface.co/CohereForAI/aya-expanse-8b).
    (
        re.compile(r"aya"),
        "Aya",
        _codes("ar zh cs nl en fr de el he hi id it ja ko fa pl pt ro ru es tr uk vi"),
        "huggingface.co/CohereForAI/aya-expanse-8b",
    ),
    (
        re.compile(r"command-r"),
        "Command R",
        _codes("en fr es it de pt ja ko zh ar"),
        "huggingface.co/CohereForAI/c4ai-command-r-08-2024",
    ),
    # Phi-3.5-mini / Phi-4-mini: 23 languages (huggingface.co/microsoft/Phi-3.5-mini-instruct).
    (
        re.compile(r"phi3\.5|phi4-mini"),
        "Phi mini",
        _codes("ar zh cs da nl en fi fr de he hu it ja ko no pl pt ru es sv th tr uk"),
        "huggingface.co/microsoft/Phi-3.5-mini-instruct",
    ),
    (re.compile(r"phi[34]"), "Phi", _codes(""), "huggingface.co/microsoft/phi-4"),
    # gpt-oss: mostly-English training; card evaluates 14 MMMLU languages (arxiv.org/abs/2508.10925).
    (
        re.compile(r"gpt-oss"),
        "gpt-oss",
        _codes("ar bn zh fr de hi id it ja ko pt es sw yo"),
        "arxiv.org/abs/2508.10925",
    ),
]


@dataclass(frozen=True)
class SupportInfo:
    supported: Optional[FrozenSet[str]]  # None = every translation target
    verified: bool  # False = unknown model family, nothing to check against
    label: str
    source: str = ""

    def to_json(self) -> dict:
        return {
            "supported": sorted(self.supported) if self.supported is not None else None,
            "verified": self.verified,
            "label": self.label,
            "source": self.source,
        }


def normalize_ollama_model(name: str) -> str:
    """``hf.co/org/Qwen2.5-7B:Q4_K_M`` -> ``qwen2.5-7b`` (lowercase, no tag/registry)."""
    base = (name or "").strip().lower().rsplit("/", 1)[-1]
    return base.split(":", 1)[0]


def translation_support(provider: str, model: Optional[str]) -> SupportInfo:
    """Translation targets ``model`` on ``provider`` officially supports."""
    provider = (provider or "").lower()
    if provider in _CLOUD_PROVIDERS:
        return SupportInfo(None, True, model or provider)
    if provider != "ollama":
        return SupportInfo(None, False, model or provider)
    normalized = normalize_ollama_model(model or "")
    for pattern, label, supported, source in _FAMILIES:
        if pattern.match(normalized):
            return SupportInfo(supported, True, label, source)
    return SupportInfo(None, False, model or "this model")
