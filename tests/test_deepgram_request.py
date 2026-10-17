#!/usr/bin/env python3
"""
Tests for the Deepgram request contract (core/transcribe.py transcribe_file)
and response normalization (response_to_dict) against deepgram-sdk 7.x.

The SDK client is patched, so no network call is made; the tests pin what the
app sends: options as keyword arguments, list values passed through as lists
(the SDK sends them as repeated query parameters), diarization via
diarize_model only, and an explicit timeout.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _install_core_dependency_stubs():
    if "deepgram" not in sys.modules:
        deepgram = types.ModuleType("deepgram")
        deepgram.DeepgramClient = type("DeepgramClient", (), {})
        sys.modules["deepgram"] = deepgram
    if "deepgram_captions" not in sys.modules:
        deepgram_captions = types.ModuleType("deepgram_captions")
        deepgram_captions.DeepgramConverter = object
        deepgram_captions.srt = object()
        sys.modules["deepgram_captions"] = deepgram_captions


_install_core_dependency_stubs()

from core import transcribe  # noqa: E402
from core.transcribe import DIARIZE_MODEL, response_to_dict, transcribe_file  # noqa: E402


def _call(**kwargs):
    """Run transcribe_file against a mocked client; return (client ctor kwargs, request kwargs)."""
    with patch("core.transcribe.DeepgramClient") as mock_client:
        instance = MagicMock()
        mock_client.return_value = instance
        transcribe_file(b"audio", "dg-key", kwargs.pop("model", "nova-3"), "en", **kwargs)
        media = instance.listen.v1.media
        assert media.transcribe_file.call_count == 1
        return mock_client.call_args.kwargs, media.transcribe_file.call_args.kwargs


def test_baseline_request_shape():
    client_kwargs, req = _call()
    assert client_kwargs["api_key"] == "dg-key"
    assert client_kwargs["timeout"] == transcribe.DEEPGRAM_TIMEOUT
    assert req["request"] == b"audio"
    assert req["model"] == "nova-3"
    assert req["language"] == "en"
    assert req["smart_format"] is True
    assert req["punctuate"] is True
    assert req["utterances"] is True
    assert req["profanity_filter"] is False
    # Disabled features are omitted entirely rather than sent as false.
    for absent in ("numerals", "detect_language", "keyterm", "diarize", "diarize_model", "redact"):
        assert absent not in req


def test_default_timeout_exceeds_sdk_60s_default():
    # deepgram-sdk 7.x defaults to 60 s, too short for feature-length audio.
    assert transcribe.DEEPGRAM_TIMEOUT > 60


def test_diarization_sends_only_diarize_model():
    _, req = _call(diarize=True)
    assert req["diarize_model"] == DIARIZE_MODEL == "v2"
    # Sending the legacy boolean alongside diarize_model is an HTTP 400.
    assert "diarize" not in req


def test_keyterms_pass_as_list_for_nova3_variants_only():
    terms = ["Dom Cobb", "Ariadne"]
    _, req = _call(keyterms=terms)
    assert req["keyterm"] == terms
    _, req = _call(model="nova-3-medical", keyterms=terms)
    assert req["keyterm"] == terms
    _, req = _call(model="nova-2", keyterms=terms)
    assert "keyterm" not in req


def test_list_options_and_flags():
    _, req = _call(
        profanity_filter="on",
        numerals=True,
        detect_language=True,
        redact=["pci", "pii"],
        replace=["colour:color"],
        search=["totem"],
        tag="batch-1",
        utt_split=1.2,
        summarize=True,
        sentiment=True,
    )
    assert req["profanity_filter"] is True
    assert req["numerals"] is True
    assert req["detect_language"] is True
    assert req["redact"] == ["pci", "pii"]
    assert req["replace"] == ["colour:color"]
    assert req["search"] == ["totem"]
    assert req["tag"] == ["batch-1"]
    assert req["utt_split"] == 1.2
    assert req["summarize"] == "v2"
    assert req["sentiment"] is True


def test_response_to_dict_handles_sdk_models_and_dicts():
    class FakeModel:
        def model_dump(self, **kwargs):
            # Mirror pydantic: the helper must ask for JSON-shaped output
            # without None fields (no `speaker: null` on undiarized words).
            assert kwargs == {"mode": "json", "by_alias": True, "exclude_none": True}
            return {"results": {"channels": []}}

    assert response_to_dict(FakeModel()) == {"results": {"channels": []}}
    raw = {"results": {}}
    assert response_to_dict(raw) is raw
    with pytest.raises(TypeError):
        response_to_dict(object())


def test_speaker_transcript_uses_punctuated_words(tmp_path):
    from types import SimpleNamespace as NS

    words = [
        NS(word="my", punctuated_word="My", speaker=0),
        NS(word="name's", punctuated_word="name's", speaker=0),
        NS(word="abed", punctuated_word="Abed.", speaker=0),
        NS(word="hi", punctuated_word=None, speaker=1),
    ]
    alt = NS(words=words, transcript="my name's abed hi")
    resp = NS(results=NS(channels=[NS(alternatives=[alt])]))
    dest = tmp_path / "out.txt"
    transcribe.write_transcript(resp, dest)
    text = dest.read_text()
    assert "Speaker 0: My name's Abed." in text
    # Falls back to the raw token when Deepgram omits the punctuated form.
    assert "Speaker 1: hi" in text
