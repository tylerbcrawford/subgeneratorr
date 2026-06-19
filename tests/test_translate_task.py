#!/usr/bin/env python3
"""
Tests for the translate_subtitles_task Celery task (web/tasks.py).

The core translation logic is covered in test_translate.py; here we test the
task *glue*: credential/host resolution, per-target iteration, keyterm glossary
passthrough, Ollama base-url normalization, and the error-to-RuntimeError
conversion. SubtitleTranslator is patched with a fake so no LLM runs.
"""

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _install_task_dependency_stubs():
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
    if "redis" not in sys.modules:
        redis_module = types.ModuleType("redis")

        class DummyRedis:
            def get(self, *a, **k):
                return None

            def set(self, *a, **k):
                return True

            def setex(self, *a, **k):
                return True

            def exists(self, *a, **k):
                return False

            def delete(self, *a, **k):
                return 0

        redis_module.from_url = lambda *a, **k: DummyRedis()
        sys.modules["redis"] = redis_module
    if "celery" not in sys.modules:
        celery_module = types.ModuleType("celery")

        class DummyCelery:
            def __init__(self, *a, **k):
                self.conf = SimpleNamespace(task_routes={})

            def task(self, *a, **k):
                def decorator(func):
                    return func

                return decorator

        celery_module.Celery = DummyCelery
        celery_module.group = lambda *a, **k: None
        celery_module.chord = lambda *a, **k: None
        sys.modules["celery"] = celery_module


_install_task_dependency_stubs()
tasks_module = importlib.import_module("web.tasks")


class FakeTaskContext:
    def update_state(self, *a, **k):
        return None


def _make_fake_translator():
    """A SubtitleTranslator stand-in that records construction + per-target calls."""
    record = {"instances": [], "calls": []}

    class FT:
        def __init__(self, provider, model, api_key, *, ollama_base_url=None, **kw):
            record["instances"].append(
                {
                    "provider": provider,
                    "model": model,
                    "api_key": api_key,
                    "ollama_base_url": ollama_base_url,
                }
            )

        def translate_file(self, srt_path, target_language, keyterms=None, overwrite=False):
            record["calls"].append(
                {
                    "srt": str(srt_path),
                    "target": target_language,
                    "keyterms": keyterms,
                    "overwrite": overwrite,
                }
            )
            tag = {"es": "spa", "fr": "fre", "de": "ger"}.get(target_language, target_language)
            return SimpleNamespace(
                target_tag=tag,
                output_path=str(srt_path),
                skipped=False,
                cost=0.02,
                input_tokens=100,
                output_tokens=200,
            )

    return FT, record


def _make_media(tmp_path):
    src = tmp_path / "Movie.eng.srt"
    src.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n")
    return tmp_path / "Movie.mkv", src


def test_translate_task_translates_each_target_and_summarizes(monkeypatch, tmp_path):
    FT, record = _make_fake_translator()
    monkeypatch.setattr("core.translate.SubtitleTranslator", FT)
    monkeypatch.setattr(tasks_module, "load_keyterms_from_csv", lambda vp: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    video, src = _make_media(tmp_path)

    result = tasks_module.translate_subtitles_task(
        FakeTaskContext(),
        str(video),
        str(src),
        ["es", "fr"],
        "anthropic",
        "claude-sonnet-4-6",
    )

    assert result["target_count"] == 2
    assert {r["tag"] for r in result["results"]} == {"spa", "fre"}
    assert result["total_cost"] == pytest.approx(0.04)
    assert [c["target"] for c in record["calls"]] == ["es", "fr"]


def test_translate_task_ollama_normalizes_base_url_and_passes_overwrite(monkeypatch, tmp_path):
    FT, record = _make_fake_translator()
    monkeypatch.setattr("core.translate.SubtitleTranslator", FT)
    monkeypatch.setattr(tasks_module, "load_keyterms_from_csv", lambda vp: None)
    video, src = _make_media(tmp_path)

    tasks_module.translate_subtitles_task(
        FakeTaskContext(),
        str(video),
        str(src),
        ["es"],
        "ollama",
        "llama3.1",
        overwrite=True,
        ollama_host="http://ollama:11434",
    )

    assert record["instances"][0]["ollama_base_url"] == "http://ollama:11434/v1"
    assert record["calls"][0]["overwrite"] is True


def test_translate_task_passes_keyterms_as_glossary(monkeypatch, tmp_path):
    FT, record = _make_fake_translator()
    monkeypatch.setattr("core.translate.SubtitleTranslator", FT)
    monkeypatch.setattr(tasks_module, "load_keyterms_from_csv", lambda vp: ["Heisenberg", "Pollos"])
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    video, src = _make_media(tmp_path)

    tasks_module.translate_subtitles_task(
        FakeTaskContext(), str(video), str(src), ["fr"], "openai", "gpt-4.1"
    )

    assert record["calls"][0]["keyterms"] == ["Heisenberg", "Pollos"]


def test_translate_task_missing_api_key_raises_runtimeerror(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    video, src = _make_media(tmp_path)

    with pytest.raises(RuntimeError):
        tasks_module.translate_subtitles_task(
            FakeTaskContext(), str(video), str(src), ["es"], "anthropic", "claude-sonnet-4-6"
        )
