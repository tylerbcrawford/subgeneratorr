"""Tests for per-model translation language support (core/model_languages.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.languages import TRANSLATION_CODES  # noqa: E402
from core.model_languages import (  # noqa: E402
    _FAMILIES,
    normalize_ollama_model,
    translation_support,
)


@pytest.mark.parametrize("provider", ["anthropic", "openai", "google"])
def test_cloud_providers_support_everything(provider):
    info = translation_support(provider, "any-model")
    assert info.supported is None and info.verified


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("qwen2.5:7b", "qwen2.5"),
        ("Llama3.1:8B-Instruct-Q4_K_M", "llama3.1"),
        ("hf.co/bartowski/gemma-3-12b-it-GGUF:Q4_K_M", "gemma-3-12b-it-gguf"),
        ("library/mistral:latest", "mistral"),
        ("", ""),
    ],
)
def test_normalize_ollama_model(raw, expected):
    assert normalize_ollama_model(raw) == expected


@pytest.mark.parametrize(
    "model,label",
    [
        ("qwen3:8b", "Qwen 3"),
        ("qwen3.5:9b", "Qwen 3"),
        ("qwen3-coder:30b", "Qwen 3"),
        ("qwen2.5:1.5b", "Qwen 2.5"),
        ("qwen2.5-coder:7b", "Qwen 2.5"),
        ("gemma3:4b", "Gemma 3+"),
        ("gemma4:e4b", "Gemma 3+"),
        ("gemma2:9b", "Gemma"),
        ("llama3.2:3b", "Llama 3"),
        ("llama4:scout", "Llama 4"),
        ("mistral-nemo:12b", "Mistral NeMo"),
        ("mistral-small:24b", "Mistral Small"),
        ("mistral:7b", "Mistral 7B"),
        ("mistral", "Mistral 7B"),
        ("aya-expanse:8b", "Aya"),
        ("command-r:35b", "Command R"),
        ("phi3.5:3.8b", "Phi mini"),
        ("phi4-mini", "Phi mini"),
        ("phi4:14b", "Phi"),
        ("gpt-oss:20b", "gpt-oss"),
    ],
)
def test_ollama_family_matching(model, label):
    info = translation_support("ollama", model)
    assert info.verified and info.label == label


def test_broad_families_support_everything():
    assert translation_support("ollama", "qwen3:8b").supported is None
    assert translation_support("ollama", "gemma3:4b").supported is None


def test_llama3_supports_its_eight_card_languages():
    assert translation_support("ollama", "llama3.1:8b").supported == {
        "de",
        "fr",
        "it",
        "pt",
        "hi",
        "es",
        "th",
    }  # English is the source, not a target


def test_mistral_large_is_not_mistral_7b():
    info = translation_support("ollama", "mistral-large:123b")
    assert not info.verified and info.supported is None


def test_unknown_family_is_unverified_all():
    info = translation_support("ollama", "deepseek-r1:8b")
    assert info.supported is None and not info.verified
    assert info.label == "deepseek-r1:8b"


def test_every_family_code_is_a_translation_target():
    for _, label, supported, source in _FAMILIES:
        assert source, label
        if supported is not None:
            assert supported <= TRANSLATION_CODES, label


def test_to_json_shape():
    body = translation_support("ollama", "llama3.1").to_json()
    assert body["supported"] == sorted(body["supported"])
    assert set(body) == {"supported", "verified", "label", "source"}
