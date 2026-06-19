#!/usr/bin/env python3
"""
Tests for SubtitleTranslator (core/translate.py).

Translation is an SRT -> SRT post-processing stage: it must preserve cue
indices and timestamps EXACTLY (Nova-3's timing stays authoritative), translate
only the text, and write a language-tagged sidecar. These tests inject a fake
per-window translator (and, in one case, a fake call_llm) so the windowing,
1:1 mapping, retry, and file-naming logic are exercised without any network.
"""

import datetime
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _install_core_dependency_stubs():
    # core.translate imports core.transcribe (for the language-tag helpers),
    # which imports the Deepgram SDK at module load. Stub it like the other
    # core tests so no real SDK install is needed.
    if "deepgram" not in sys.modules:
        deepgram = types.ModuleType("deepgram")
        deepgram.DeepgramClient = type("DeepgramClient", (), {})
        deepgram.PrerecordedOptions = type("PrerecordedOptions", (), {})
        sys.modules["deepgram"] = deepgram
    if "deepgram_captions" not in sys.modules:
        deepgram_captions = types.ModuleType("deepgram_captions")
        deepgram_captions.DeepgramConverter = object
        deepgram_captions.srt = object()
        sys.modules["deepgram_captions"] = deepgram_captions


_install_core_dependency_stubs()

import srt as srt_lib  # noqa: E402

from core.llm_providers import LLMModel, LLMProvider  # noqa: E402
from core.translate import SubtitleTranslator, _parse_translation_response  # noqa: E402

# --- Helpers ----------------------------------------------------------------


def _make_cues(texts, step=3, dur=2):
    cues = []
    t = 0
    for i, text in enumerate(texts, start=1):
        cues.append(
            srt_lib.Subtitle(
                index=i,
                start=datetime.timedelta(seconds=t),
                end=datetime.timedelta(seconds=t + dur),
                content=text,
            )
        )
        t += step
    return cues


def _recording_translator(fn, in_tok=10, out_tok=20, mismatch_when=None):
    """Build a fake per-window translator that records its calls.

    Returns one translation per input text, unless ``mismatch_when(texts)`` is
    truthy, in which case it deliberately returns the wrong count (one item) to
    trigger the per-cue retry path.
    """
    calls = []

    def translator(texts, target_name, keyterms):
        calls.append(list(texts))
        if mismatch_when and mismatch_when(texts):
            return [fn(texts[0])], in_tok, out_tok
        return [fn(t) for t in texts], in_tok, out_tok

    translator.calls = calls
    return translator


def _new_translator(provider=LLMProvider.OPENAI, model=LLMModel.GPT_4_1, **kwargs):
    return SubtitleTranslator(provider, model, "key", **kwargs)


# --- Timing / index preservation -------------------------------------------


def test_translate_cues_preserves_index_and_timing():
    cues = _make_cues(["Hello", "World", "Bye"])
    fake = _recording_translator(lambda t: f"[es] {t}")
    tr = _new_translator(text_translator=fake)

    result = tr.translate_cues(cues, "es")

    assert [c.content for c in result.cues] == ["[es] Hello", "[es] World", "[es] Bye"]
    for orig, new in zip(cues, result.cues):
        assert new.index == orig.index
        assert new.start == orig.start
        assert new.end == orig.end


# --- Windowing --------------------------------------------------------------


def test_translate_cues_batches_into_windows():
    cues = _make_cues([f"line {i}" for i in range(5)])
    fake = _recording_translator(lambda t: t.upper())
    tr = _new_translator(window_size=2, text_translator=fake)

    tr.translate_cues(cues, "fr")

    assert [len(c) for c in fake.calls] == [2, 2, 1]


# --- 1:1 mapping with per-cue retry ----------------------------------------


def test_count_mismatch_falls_back_to_per_cue():
    cues = _make_cues(["a", "b", "c"])
    fake = _recording_translator(lambda t: f"X{t}", mismatch_when=lambda texts: len(texts) > 1)
    tr = _new_translator(window_size=10, text_translator=fake)

    result = tr.translate_cues(cues, "es")

    assert [c.content for c in result.cues] == ["Xa", "Xb", "Xc"]
    # First the full window (count mismatch), then one call per cue.
    assert [len(c) for c in fake.calls] == [3, 1, 1, 1]


def test_per_cue_retry_still_failing_keeps_source_text():
    cues = _make_cues(["a", "b"])

    # A translator that can never return a usable result (always wrong count),
    # even when retried one cue at a time.
    def always_empty(texts, target_name, keyterms):
        return [], 1, 1

    tr = _new_translator(text_translator=always_empty)

    result = tr.translate_cues(cues, "es")

    # Never drop a cue: untranslatable cues fall back to the source text 1:1.
    assert [c.content for c in result.cues] == ["a", "b"]


# --- Target validation + tag resolution ------------------------------------


def test_unknown_target_language_rejected():
    cues = _make_cues(["a"])
    tr = _new_translator(text_translator=_recording_translator(lambda t: t))
    with pytest.raises(ValueError):
        tr.translate_cues(cues, "xx")


@pytest.mark.parametrize("code,tag", [("es", "spa"), ("fr", "fre"), ("zh", "chi"), ("de", "ger")])
def test_target_tag_resolution(code, tag):
    cues = _make_cues(["a"])
    tr = _new_translator(text_translator=_recording_translator(lambda t: t))
    result = tr.translate_cues(cues, code)
    assert result.target_tag == tag


# --- Cost (Ollama is free) --------------------------------------------------


def test_ollama_translation_cost_is_zero():
    cues = _make_cues(["a", "b"])
    fake = _recording_translator(lambda t: t, in_tok=1000, out_tok=2000)
    tr = SubtitleTranslator(LLMProvider.OLLAMA, "llama3.1", None, text_translator=fake)

    result = tr.translate_cues(cues, "es")

    assert result.input_tokens > 0 and result.output_tokens > 0
    assert result.cost == 0.0


def test_cloud_translation_cost_is_nonzero():
    cues = _make_cues(["a"])
    fake = _recording_translator(lambda t: t, in_tok=1_000_000, out_tok=1_000_000)
    tr = _new_translator(model=LLMModel.GPT_4_1, text_translator=fake)
    result = tr.translate_cues(cues, "es")
    assert result.cost == pytest.approx(10.00)


# --- File I/O: tagged sidecar + skip-existing -------------------------------


def test_translate_file_writes_tagged_sidecar(tmp_path):
    src = tmp_path / "Movie.eng.srt"
    src.write_text(srt_lib.compose(_make_cues(["Hello", "World"])), encoding="utf-8")
    fake = _recording_translator(lambda t: f"[es] {t}")
    tr = _new_translator(text_translator=fake)

    result = tr.translate_file(src, "es")

    dest = tmp_path / "Movie.spa.srt"
    assert dest.exists()
    assert result.output_path == dest
    out_cues = list(srt_lib.parse(dest.read_text(encoding="utf-8")))
    src_cues = list(srt_lib.parse(src.read_text(encoding="utf-8")))
    assert len(out_cues) == len(src_cues)
    for o, s in zip(out_cues, src_cues):
        assert o.start == s.start and o.end == s.end
        assert o.content != s.content


def test_translate_file_skips_existing_unless_overwrite(tmp_path):
    src = tmp_path / "Movie.eng.srt"
    src.write_text(srt_lib.compose(_make_cues(["Hello"])), encoding="utf-8")
    dest = tmp_path / "Movie.spa.srt"
    dest.write_text("PRE-EXISTING", encoding="utf-8")
    fake = _recording_translator(lambda t: f"[es] {t}")
    tr = _new_translator(text_translator=fake)

    result = tr.translate_file(src, "es")
    assert result.skipped is True
    assert dest.read_text(encoding="utf-8") == "PRE-EXISTING"

    result2 = tr.translate_file(src, "es", overwrite=True)
    assert result2.skipped is False
    assert dest.read_text(encoding="utf-8") != "PRE-EXISTING"


# --- JSON response parsing --------------------------------------------------


def test_parse_translation_response_extracts_json_from_fenced_block():
    text = '```json\n[{"i": 0, "text": "Hola"}, {"i": 1, "text": "Mundo"}]\n```'
    assert _parse_translation_response(text, 2) == ["Hola", "Mundo"]


def test_parse_translation_response_returns_empty_on_garbage():
    assert _parse_translation_response("not json at all", 2) == []


# --- Real per-window translator wired to call_llm ---------------------------


def test_default_translator_calls_llm_with_json_and_parses():
    captured = {}

    def fake_llm(
        provider, model, api_key, prompt, *, max_tokens, system_prompt=None, base_url=None, **kw
    ):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["max_tokens"] = max_tokens
        return '[{"i":0,"text":"Hola"},{"i":1,"text":"Mundo"}]', 11, 22

    cues = _make_cues(["Hello", "World"])
    tr = _new_translator(llm_call=fake_llm)

    result = tr.translate_cues(cues, "es")

    assert [c.content for c in result.cues] == ["Hola", "Mundo"]
    assert result.input_tokens == 11 and result.output_tokens == 22
    assert captured["model"] == "gpt-4.1"  # LLMModel.value passed through to call_llm
    assert "Spanish" in captured["prompt"]
