import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _install_task_dependency_stubs():
    if "deepgram" not in sys.modules:
        deepgram = types.ModuleType("deepgram")

        class DeepgramClient:
            pass

        class PrerecordedOptions:
            pass

        deepgram.DeepgramClient = DeepgramClient
        deepgram.PrerecordedOptions = PrerecordedOptions
        sys.modules["deepgram"] = deepgram

    if "deepgram_captions" not in sys.modules:
        deepgram_captions = types.ModuleType("deepgram_captions")
        deepgram_captions.DeepgramConverter = object
        deepgram_captions.srt = object()
        sys.modules["deepgram_captions"] = deepgram_captions

    if "redis" not in sys.modules:
        redis_module = types.ModuleType("redis")

        class DummyRedis:
            def get(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return True

            def setex(self, *args, **kwargs):
                return True

            def exists(self, *args, **kwargs):
                return False

            def delete(self, *args, **kwargs):
                return 0

        redis_module.from_url = lambda *args, **kwargs: DummyRedis()
        sys.modules["redis"] = redis_module

    if "celery" not in sys.modules:
        celery_module = types.ModuleType("celery")

        class DummyCelery:
            def __init__(self, *args, **kwargs):
                self.conf = SimpleNamespace(task_routes={})

            def task(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

        celery_module.Celery = DummyCelery
        celery_module.group = lambda *args, **kwargs: None
        celery_module.chord = lambda *args, **kwargs: None
        sys.modules["celery"] = celery_module


_install_task_dependency_stubs()
sys.modules.pop("web.tasks", None)
tasks_module = importlib.import_module("web.tasks")


class FakeTaskContext:
    def update_state(self, *args, **kwargs):
        return None


def _make_detected_language_response():
    return SimpleNamespace(
        results=SimpleNamespace(
            channels=[SimpleNamespace(detected_language="es")]
        )
    )


def test_transcribe_task_skips_existing_language_tagged_sidecar_in_auto_detect(monkeypatch, tmp_path):
    media_file = tmp_path / "episode.mkv"
    media_file.write_text("video")
    (tmp_path / "episode.spa.srt").write_text("subtitle")

    monkeypatch.setattr(tasks_module, "DG_KEY", "test-key")
    monkeypatch.setattr(tasks_module, "_save_job_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        tasks_module,
        "extract_audio",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("extract_audio should not run")),
    )
    monkeypatch.setattr(
        tasks_module,
        "transcribe_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("transcribe_file should not run")),
    )

    result = tasks_module.transcribe_task(
        FakeTaskContext(),
        str(media_file),
        language="en",
        detect_language=True,
    )

    assert result["status"] == "skipped"
    assert result["srt"].endswith("episode.spa.srt")


def test_transcribe_task_keeps_generating_transcript_when_resolved_subtitle_exists(monkeypatch, tmp_path):
    media_file = tmp_path / "episode.mkv"
    media_file.write_text("video")
    (tmp_path / "episode.spa.srt").write_text("subtitle")

    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"audio")

    transcript_path = tmp_path / "Transcripts" / "episode.transcript.speakers.txt"
    response = _make_detected_language_response()
    write_srt = Mock()

    monkeypatch.setattr(tasks_module, "DG_KEY", "test-key")
    monkeypatch.setattr(tasks_module, "_save_job_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks_module, "get_video_duration", lambda *args, **kwargs: 60.0)
    monkeypatch.setattr(tasks_module, "extract_audio", lambda *args, **kwargs: audio_file)
    monkeypatch.setattr(tasks_module, "transcribe_file", lambda *args, **kwargs: response)
    monkeypatch.setattr(tasks_module, "write_srt", write_srt)
    monkeypatch.setattr(tasks_module, "find_speaker_map", lambda *args, **kwargs: None)

    def fake_write_transcript(resp, dest, speaker_map_path=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("Speaker 0: hola", encoding="utf-8")

    monkeypatch.setattr(tasks_module, "write_transcript", fake_write_transcript)

    result = tasks_module.transcribe_task(
        FakeTaskContext(),
        str(media_file),
        language="en",
        detect_language=True,
        enable_transcript=True,
    )

    assert result["status"] == "ok"
    assert transcript_path.exists()
    write_srt.assert_not_called()


def test_save_job_log_does_not_raise_when_log_root_is_unwritable(monkeypatch, tmp_path, capsys):
    blocked_path = tmp_path / "logs"
    blocked_path.write_text("not a directory", encoding="utf-8")

    monkeypatch.setattr(tasks_module, "LOG_ROOT", blocked_path)

    tasks_module._save_job_log({"status": "ok"})

    captured = capsys.readouterr()
    assert "Failed to write job log" in captured.err
