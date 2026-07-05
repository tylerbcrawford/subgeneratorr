#!/usr/bin/env python3
"""
Tests for engine selection in transcribe_task (web/tasks.py).

Engine logic itself is covered in test_asr_engine.py / test_srt_writer.py;
here we test the task glue: the conditional DEEPGRAM_API_KEY gate, the whisper
branch (normalized SRT written, detected-language sidecar naming, per-segment
progress updates), and that the deepgram path is untouched. WhisperEngine is
patched with a fake so no model loads.
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

from core.asr_engine import NormalizedResult, NormalizedSegment, NormalizedWord  # noqa: E402


class RecordingTaskContext:
    def __init__(self):
        self.states = []

    def update_state(self, state=None, meta=None):
        self.states.append({"state": state, "meta": meta or {}})


def _normalized_result(language="en"):
    return NormalizedResult(
        segments=[
            NormalizedSegment(
                start=0.0,
                end=2.0,
                text="Hello there.",
                words=[
                    NormalizedWord(word="Hello", start=0.0, end=1.0),
                    NormalizedWord(word="there.", start=1.2, end=2.0),
                ],
            )
        ],
        detected_language=language,
    )


def _make_fake_whisper_engine(result=None, fail=False):
    record = {"instances": [], "calls": []}

    class FakeWhisperEngine:
        def __init__(self, model=None, **kwargs):
            self.model = model
            record["instances"].append({"model": model, **kwargs})

        def transcribe(self, buf, opts, progress_callback=None):
            record["calls"].append({"buf_len": len(buf), "opts": opts})
            if fail:
                raise RuntimeError("boom")
            if progress_callback is not None:
                progress_callback(2.0, 10.0)
            return result or _normalized_result()

    return FakeWhisperEngine, record


def _common_patches(monkeypatch, tmp_path, dg_key=""):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio")
    monkeypatch.setattr(tasks_module, "DG_KEY", dg_key)
    monkeypatch.setattr(tasks_module, "_save_job_log", lambda *a, **k: None)
    monkeypatch.setattr(tasks_module, "get_video_duration", lambda *a, **k: 60.0)
    monkeypatch.setattr(tasks_module, "extract_audio", lambda *a, **k: audio_file)
    monkeypatch.setattr(tasks_module, "load_keyterms_from_csv", lambda *a, **k: None)


def test_whisper_task_runs_without_deepgram_key(monkeypatch, tmp_path):
    """The zero-cloud path: no DEEPGRAM_API_KEY, engine=whisper — must succeed."""
    media = tmp_path / "episode.mkv"
    media.write_text("video")
    fake_engine, record = _make_fake_whisper_engine()
    _common_patches(monkeypatch, tmp_path, dg_key="")
    monkeypatch.setattr(tasks_module, "WhisperEngine", fake_engine)
    monkeypatch.setattr(
        tasks_module,
        "transcribe_file",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cloud path must not run")),
    )

    result = tasks_module.transcribe_task(
        RecordingTaskContext(), str(media), language="en", engine="whisper"
    )

    assert result["status"] == "ok"
    assert result["engine"] == "whisper"
    srt_path = tmp_path / "episode.eng.srt"
    assert srt_path.exists()
    assert "Hello there." in srt_path.read_text(encoding="utf-8")
    assert record["calls"], "whisper engine was never invoked"


def test_deepgram_task_still_requires_key(monkeypatch, tmp_path):
    media = tmp_path / "episode.mkv"
    media.write_text("video")
    _common_patches(monkeypatch, tmp_path, dg_key="")

    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        tasks_module.transcribe_task(RecordingTaskContext(), str(media), language="en")


def test_unknown_engine_rejected(monkeypatch, tmp_path):
    media = tmp_path / "episode.mkv"
    media.write_text("video")
    _common_patches(monkeypatch, tmp_path, dg_key="key")

    with pytest.raises(ValueError, match="engine"):
        tasks_module.transcribe_task(
            RecordingTaskContext(), str(media), language="en", engine="siri"
        )


def test_whisper_model_passed_to_engine(monkeypatch, tmp_path):
    media = tmp_path / "episode.mkv"
    media.write_text("video")
    fake_engine, record = _make_fake_whisper_engine()
    _common_patches(monkeypatch, tmp_path)
    monkeypatch.setattr(tasks_module, "WhisperEngine", fake_engine)

    tasks_module.transcribe_task(
        RecordingTaskContext(),
        str(media),
        language="en",
        engine="whisper",
        whisper_model="base",
    )

    assert record["instances"][0]["model"] == "base"


def test_whisper_detected_language_names_sidecar(monkeypatch, tmp_path):
    media = tmp_path / "episode.mkv"
    media.write_text("video")
    fake_engine, _ = _make_fake_whisper_engine(result=_normalized_result(language="es"))
    _common_patches(monkeypatch, tmp_path)
    monkeypatch.setattr(tasks_module, "WhisperEngine", fake_engine)

    result = tasks_module.transcribe_task(
        RecordingTaskContext(),
        str(media),
        language="en",
        detect_language=True,
        engine="whisper",
    )

    assert result["srt"].endswith("episode.spa.srt")
    assert (tmp_path / "episode.spa.srt").exists()


def test_whisper_progress_reaches_celery_state(monkeypatch, tmp_path):
    media = tmp_path / "episode.mkv"
    media.write_text("video")
    fake_engine, _ = _make_fake_whisper_engine()
    _common_patches(monkeypatch, tmp_path)
    monkeypatch.setattr(tasks_module, "WhisperEngine", fake_engine)
    ctx = RecordingTaskContext()

    tasks_module.transcribe_task(ctx, str(media), language="en", engine="whisper")

    progress = [
        s["meta"]
        for s in ctx.states
        if s["state"] == "PROGRESS" and "progress_seconds" in s["meta"]
    ]
    assert progress and progress[0]["progress_seconds"] == 2.0
    assert progress[0]["total_seconds"] == 10.0


def test_whisper_transcript_written_from_segments(monkeypatch, tmp_path):
    media = tmp_path / "episode.mkv"
    media.write_text("video")
    fake_engine, _ = _make_fake_whisper_engine()
    _common_patches(monkeypatch, tmp_path)
    monkeypatch.setattr(tasks_module, "WhisperEngine", fake_engine)

    result = tasks_module.transcribe_task(
        RecordingTaskContext(),
        str(media),
        language="en",
        engine="whisper",
        enable_transcript=True,
    )

    transcript = tmp_path / "Transcripts" / "episode.transcript.speakers.txt"
    assert transcript.exists()
    assert "Hello there." in transcript.read_text(encoding="utf-8")
    assert result["status"] == "ok"


def test_whisper_skip_logic_still_applies(monkeypatch, tmp_path):
    media = tmp_path / "episode.mkv"
    media.write_text("video")
    (tmp_path / "episode.eng.srt").write_text("existing")
    fake_engine, record = _make_fake_whisper_engine()
    _common_patches(monkeypatch, tmp_path)
    monkeypatch.setattr(tasks_module, "WhisperEngine", fake_engine)

    result = tasks_module.transcribe_task(
        RecordingTaskContext(), str(media), language="en", engine="whisper"
    )

    assert result["status"] == "skipped"
    assert not record["calls"]
