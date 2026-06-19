#!/usr/bin/env python3
"""
Tests for the translation web API: /api/config Ollama status and the
POST /api/translate endpoint (validation + task dispatch).

Mirrors the Flask test setup used by test_library_scan_api.py: auth disabled,
heavy deps (deepgram / redis / tasks) stubbed, web.app imported once.
"""

import importlib
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

os.environ["DISABLE_AUTH"] = "true"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _install_app_dependency_stubs():
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
    if "tasks" not in sys.modules:
        tasks_module = types.ModuleType("tasks")

        class DummyControl:
            def revoke(self, *a, **k):
                return None

        class DummyCeleryApp:
            def __init__(self):
                self.control = DummyControl()

            def AsyncResult(self, task_id):
                return SimpleNamespace(state="PENDING", info=None)

        class DummyTask:
            def delay(self, **kwargs):
                return SimpleNamespace(id="00000000-0000-0000-0000-000000000000")

        tasks_module.celery_app = DummyCeleryApp()
        tasks_module.make_batch = lambda *a, **k: None
        tasks_module.generate_keyterms_task = DummyTask()
        tasks_module.library_scan_task = DummyTask()
        tasks_module.translate_subtitles_task = DummyTask()
        sys.modules["tasks"] = tasks_module


_install_app_dependency_stubs()

app_module = importlib.import_module("web.app")
app = app_module.app
app.config.update(TESTING=True)


def _make_media_with_srt(tmp_path, srt_name="Movie.eng.srt"):
    video = tmp_path / "Movie.mkv"
    video.write_text("video")
    srt = tmp_path / srt_name
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nHello\n\n2\n00:00:03,000 --> 00:00:05,000\nWorld\n"
    )
    return video, srt


# --- /api/config Ollama status ----------------------------------------------


def test_api_config_reports_ollama_configured_when_host_set():
    with app.test_client() as client:
        os.environ["OLLAMA_HOST"] = "http://ollama:11434"
        try:
            resp = client.get("/api/config")
        finally:
            del os.environ["OLLAMA_HOST"]
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["providers"]["ollama"] is True


def test_api_config_reports_ollama_unconfigured_when_host_absent():
    with app.test_client() as client:
        os.environ.pop("OLLAMA_HOST", None)
        resp = client.get("/api/config")
    assert resp.get_json()["providers"]["ollama"] is False


# --- POST /api/translate validation -----------------------------------------


def test_translate_requires_video_path():
    with app.test_client() as client:
        resp = client.post("/api/translate", json={"targets": ["es"]})
    assert resp.status_code == 400


def test_translate_rejects_unknown_target_language(tmp_path):
    video, _ = _make_media_with_srt(tmp_path)
    with app.test_client() as client, _patched_env(app_module, tmp_path):
        resp = client.post(
            "/api/translate",
            json={"video_path": str(video), "targets": ["xx"], "provider": "anthropic"},
        )
    assert resp.status_code == 400
    assert "xx" in resp.get_json()["error"]


def test_translate_requires_at_least_one_target(tmp_path):
    video, _ = _make_media_with_srt(tmp_path)
    with app.test_client() as client, _patched_env(app_module, tmp_path):
        resp = client.post(
            "/api/translate",
            json={"video_path": str(video), "targets": [], "provider": "anthropic"},
        )
    assert resp.status_code == 400


def test_translate_404_when_no_source_subtitle(tmp_path):
    video = tmp_path / "Movie.mkv"
    video.write_text("video")  # no sidecar SRT
    with app.test_client() as client, _patched_env(app_module, tmp_path):
        resp = client.post(
            "/api/translate",
            json={"video_path": str(video), "targets": ["es"], "provider": "anthropic"},
        )
    assert resp.status_code == 400
    assert "subtitle" in resp.get_json()["error"].lower()


def test_translate_ollama_requires_host(tmp_path):
    video, _ = _make_media_with_srt(tmp_path)
    with app.test_client() as client, _patched_env(app_module, tmp_path):
        os.environ.pop("OLLAMA_HOST", None)
        resp = client.post(
            "/api/translate",
            json={"video_path": str(video), "targets": ["es"], "provider": "ollama"},
        )
    assert resp.status_code == 400
    assert "ollama" in resp.get_json()["error"].lower()


def test_translate_dispatches_task_and_returns_task_id(tmp_path):
    video, srt = _make_media_with_srt(tmp_path)
    captured = {}

    class CapturingTask:
        def delay(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id="task-xyz")

    with (
        app.test_client() as client,
        _patched_env(app_module, tmp_path),
        _patch(app_module, "translate_subtitles_task", CapturingTask()),
        _patch_env_var("ANTHROPIC_API_KEY", "sk-test"),
    ):
        resp = client.post(
            "/api/translate",
            json={
                "video_path": str(video),
                "targets": ["es", "fr"],
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
            },
        )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["task_id"] == "task-xyz"
    assert captured["targets"] == ["es", "fr"]
    assert captured["source_srt"] == str(srt)
    assert captured["provider"] == "anthropic"


def test_translate_estimate_ollama_is_zero(tmp_path):
    video, _ = _make_media_with_srt(tmp_path)
    with (
        app.test_client() as client,
        _patched_env(app_module, tmp_path),
        _patch_env_var("OLLAMA_HOST", "http://ollama:11434"),
    ):
        resp = client.post(
            "/api/translate",
            json={
                "video_path": str(video),
                "targets": ["es", "fr"],
                "provider": "ollama",
                "model": "llama3.1",
                "estimate_only": True,
            },
        )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["estimated_cost"] == 0.0


def test_translate_estimate_cloud_scales_with_targets(tmp_path):
    video, _ = _make_media_with_srt(tmp_path)
    with (
        app.test_client() as client,
        _patched_env(app_module, tmp_path),
        _patch_env_var("ANTHROPIC_API_KEY", "sk-test"),
    ):
        resp = client.post(
            "/api/translate",
            json={
                "video_path": str(video),
                "targets": ["es", "fr", "de"],
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "estimate_only": True,
            },
        )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["estimated_cost"] > 0
    assert body["target_count"] == 3


# --- Small context-manager helpers ------------------------------------------


class _patch:
    """Minimal attribute patcher (avoids importing unittest.mock everywhere)."""

    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self._old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)
        return self.value

    def __exit__(self, *exc):
        setattr(self.obj, self.name, self._old)


class _patch_env_var:
    def __init__(self, key, value):
        self.key, self.value = key, value

    def __enter__(self):
        self._old = os.environ.get(self.key)
        os.environ[self.key] = self.value
        return self

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop(self.key, None)
        else:
            os.environ[self.key] = self._old


def _patched_env(app_module, media_root):
    return _patch(app_module, "MEDIA_ROOT", media_root)
