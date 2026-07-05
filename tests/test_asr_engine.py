"""Tests for the pluggable ASR engine layer (core/asr_engine.py)."""

import sys
import types
from unittest.mock import MagicMock

import pytest

from core.asr_engine import (
    CAP_AUDIO_INTELLIGENCE,
    CAP_DIARIZATION,
    CAP_FIND_REPLACE,
    CAP_KEYTERM,
    CAP_LANGUAGE_DETECT,
    CAP_REDACTION,
    DEFAULT_WHISPER_MODEL,
    VALID_ENGINES,
    WHISPER_MAX_HOTWORD_CHARS,
    WHISPER_MAX_KEYTERMS,
    DeepgramEngine,
    NormalizedResult,
    NormalizedSegment,
    NormalizedWord,
    TranscribeOptions,
    WhisperEngine,
    cap_keyterms,
    engine_capabilities,
    get_engine,
)

# ---------------------------------------------------------------------------
# Fake faster_whisper module (the lean image doesn't ship the real one, and
# neither does CI — the engine must lazy-import it).
# ---------------------------------------------------------------------------


class _FakeWord:
    def __init__(self, start, end, word):
        self.start = start
        self.end = end
        self.word = word


class _FakeSegment:
    def __init__(self, start, end, text, words):
        self.start = start
        self.end = end
        self.text = text
        self.words = words


class _FakeInfo:
    def __init__(self, language="en", duration=10.0):
        self.language = language
        self.language_probability = 0.99
        self.duration = duration


class _FakeWhisperModel:
    """Captures constructor + transcribe kwargs; yields canned segments."""

    init_calls = []

    def __init__(self, model_size_or_path, **kwargs):
        self.model = model_size_or_path
        self.kwargs = kwargs
        _FakeWhisperModel.init_calls.append((model_size_or_path, kwargs))
        self.transcribe_kwargs = None
        self.segments = [
            _FakeSegment(
                0.0,
                2.0,
                " Hello there.",
                [_FakeWord(0.0, 1.0, " Hello"), _FakeWord(1.2, 2.0, " there.")],
            ),
            _FakeSegment(
                3.0,
                5.0,
                " General Kenobi.",
                [_FakeWord(3.0, 4.0, " General"), _FakeWord(4.1, 5.0, " Kenobi.")],
            ),
        ]
        self.info = _FakeInfo()

    def transcribe(self, audio, **kwargs):
        self.transcribe_kwargs = kwargs
        return iter(self.segments), self.info


@pytest.fixture()
def fake_faster_whisper(monkeypatch):
    """Install a fake faster_whisper module and reset the engine's model cache."""
    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = _FakeWhisperModel
    _FakeWhisperModel.init_calls = []
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    import core.asr_engine as ae

    monkeypatch.setattr(ae, "_MODEL_CACHE", {})
    return mod


def _last_model():
    assert _FakeWhisperModel.init_calls, "WhisperModel was never constructed"
    return _FakeWhisperModel.init_calls


# ---------------------------------------------------------------------------
# Registry / capabilities
# ---------------------------------------------------------------------------


def test_valid_engines_registry():
    assert VALID_ENGINES == {"deepgram", "whisper"}
    assert set(engine_capabilities().keys()) == VALID_ENGINES


def test_whisper_declares_reduced_capability_set():
    caps = WhisperEngine.capabilities()
    assert CAP_KEYTERM in caps
    assert CAP_FIND_REPLACE in caps
    assert CAP_LANGUAGE_DETECT in caps
    assert CAP_AUDIO_INTELLIGENCE not in caps
    assert CAP_REDACTION not in caps
    assert CAP_DIARIZATION not in caps


def test_deepgram_declares_full_capability_set():
    caps = DeepgramEngine.capabilities()
    assert CAP_AUDIO_INTELLIGENCE in caps
    assert CAP_REDACTION in caps
    assert CAP_DIARIZATION in caps
    assert caps > WhisperEngine.capabilities() - {CAP_KEYTERM}


def test_engine_capabilities_is_json_friendly():
    caps = engine_capabilities()
    for name, entry in caps.items():
        assert isinstance(entry["capabilities"], list)
        assert entry["capabilities"] == sorted(entry["capabilities"])


def test_get_engine_unknown_raises():
    with pytest.raises(ValueError, match="Unknown ASR engine"):
        get_engine("siri")


def test_get_engine_returns_instances():
    assert isinstance(get_engine("whisper"), WhisperEngine)
    assert isinstance(get_engine("deepgram", api_key="dg-test"), DeepgramEngine)


# ---------------------------------------------------------------------------
# Keyterm capping
# ---------------------------------------------------------------------------


def test_cap_keyterms_none_and_empty():
    assert cap_keyterms(None) is None
    assert cap_keyterms([]) is None


def test_cap_keyterms_count_cap():
    terms = [f"term{i}" for i in range(WHISPER_MAX_KEYTERMS + 20)]
    capped = cap_keyterms(terms)
    assert capped.count(",") == WHISPER_MAX_KEYTERMS - 1


def test_cap_keyterms_char_cap():
    terms = ["x" * 100 for _ in range(20)]
    capped = cap_keyterms(terms)
    assert len(capped) <= WHISPER_MAX_HOTWORD_CHARS


# ---------------------------------------------------------------------------
# WhisperEngine
# ---------------------------------------------------------------------------


def test_whisper_rejects_unknown_model():
    with pytest.raises(ValueError, match="whisper model"):
        WhisperEngine(model="enormous-v9")


def test_whisper_default_model_is_small():
    assert DEFAULT_WHISPER_MODEL == "small"
    assert WhisperEngine().model == "small"


def test_whisper_transcribe_normalizes(fake_faster_whisper):
    eng = WhisperEngine(model="tiny")
    result = eng.transcribe(b"fake-audio", TranscribeOptions(language="en"))

    assert isinstance(result, NormalizedResult)
    assert result.detected_language == "en"
    assert [s.text for s in result.segments] == ["Hello there.", "General Kenobi."]
    seg = result.segments[0]
    assert seg.start == 0.0 and seg.end == 2.0
    assert [w.word for w in seg.words] == ["Hello", "there."]
    assert seg.words[1].start == 1.2


def test_whisper_transcribe_anti_hallucination_settings(fake_faster_whisper):
    eng = WhisperEngine(model="tiny")
    eng.transcribe(b"fake-audio", TranscribeOptions(language="en"))
    _, kwargs = _last_model()[-1]
    model = _find_fake_model()
    assert model.transcribe_kwargs["vad_filter"] is True
    assert model.transcribe_kwargs["condition_on_previous_text"] is False
    assert model.transcribe_kwargs["word_timestamps"] is True


def _find_fake_model():
    import core.asr_engine as ae

    models = list(ae._MODEL_CACHE.values())
    assert models, "model cache is empty"
    return models[-1]


def test_whisper_language_mapping(fake_faster_whisper):
    eng = WhisperEngine(model="tiny")

    eng.transcribe(b"a", TranscribeOptions(language="es"))
    assert _find_fake_model().transcribe_kwargs["language"] == "es"

    eng.transcribe(b"a", TranscribeOptions(language="multi"))
    assert _find_fake_model().transcribe_kwargs["language"] is None

    eng.transcribe(b"a", TranscribeOptions(language="es", detect_language=True))
    assert _find_fake_model().transcribe_kwargs["language"] is None

    # Regional variants normalize to base codes (whisper rejects "pt-BR")
    eng.transcribe(b"a", TranscribeOptions(language="pt-BR"))
    assert _find_fake_model().transcribe_kwargs["language"] == "pt"


def test_whisper_hotwords_from_keyterms(fake_faster_whisper):
    eng = WhisperEngine(model="tiny")
    eng.transcribe(b"a", TranscribeOptions(language="en", keyterms=["Kenobi", "Tatooine"]))
    assert _find_fake_model().transcribe_kwargs["hotwords"] == "Kenobi, Tatooine"

    eng.transcribe(b"a", TranscribeOptions(language="en"))
    assert _find_fake_model().transcribe_kwargs["hotwords"] is None


def test_whisper_model_cache_reuses_instance(fake_faster_whisper):
    eng = WhisperEngine(model="tiny")
    eng.transcribe(b"a", TranscribeOptions())
    eng2 = WhisperEngine(model="tiny")
    eng2.transcribe(b"b", TranscribeOptions())
    assert len(_FakeWhisperModel.init_calls) == 1


def test_whisper_progress_callback(fake_faster_whisper):
    eng = WhisperEngine(model="tiny")
    calls = []
    eng.transcribe(
        b"a",
        TranscribeOptions(language="en"),
        progress_callback=lambda done, total: calls.append((done, total)),
    )
    assert calls == [(2.0, 10.0), (5.0, 10.0)]


def test_whisper_find_replace(fake_faster_whisper):
    eng = WhisperEngine(model="tiny")
    result = eng.transcribe(
        b"a", TranscribeOptions(language="en", replace=["Kenobi:Skywalker"])
    )
    assert result.segments[1].text == "General Skywalker."
    assert result.segments[1].words[1].word == "Skywalker."


def test_whisper_empty_result_has_no_segments(fake_faster_whisper):
    eng = WhisperEngine(model="tiny")
    model_holder = {}

    class _EmptyModel(_FakeWhisperModel):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.segments = []
            model_holder["m"] = self

    fake_faster_whisper.WhisperModel = _EmptyModel
    result = eng.transcribe(b"a", TranscribeOptions())
    assert result.segments == []


# ---------------------------------------------------------------------------
# DeepgramEngine adapter
# ---------------------------------------------------------------------------


def _fake_dg_response():
    word1 = MagicMock(word="hello", start=0.0, end=0.5, punctuated_word="Hello")
    word2 = MagicMock(word="world", start=0.6, end=1.0, punctuated_word="world.")
    utt = MagicMock(start=0.0, end=1.0, transcript="Hello world.", words=[word1, word2])
    resp = MagicMock()
    resp.results.utterances = [utt]
    resp.results.channels[0].detected_language = "en"
    return resp


def test_deepgram_normalize_from_utterances():
    resp = _fake_dg_response()
    result = DeepgramEngine.normalize_response(resp)
    assert len(result.segments) == 1
    seg = result.segments[0]
    assert seg.text == "Hello world."
    assert [w.word for w in seg.words] == ["Hello", "world."]
    assert result.detected_language == "en"
    assert result.raw is resp


def test_deepgram_requires_api_key_to_transcribe():
    eng = DeepgramEngine(api_key="")
    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        eng.transcribe(b"a", TranscribeOptions())


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


def test_transcribe_options_defaults():
    opts = TranscribeOptions()
    assert opts.language == "en"
    assert opts.detect_language is False
    assert opts.keyterms is None
    assert opts.replace is None
    assert opts.model is None


def test_normalized_dataclasses():
    w = NormalizedWord(word="hi", start=0.0, end=0.4)
    s = NormalizedSegment(start=0.0, end=0.4, text="hi", words=[w])
    r = NormalizedResult(segments=[s], detected_language="en")
    assert r.segments[0].words[0].speaker is None
    assert r.raw is None
