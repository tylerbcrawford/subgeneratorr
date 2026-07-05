#!/usr/bin/env python3
"""
Tests for the engine-selection web API surface: GET /api/capabilities,
engine/whisper_model validation on POST /api/submit, and the engine-aware
POST /api/estimate ($0 for local). Mirrors the test_translate_api.py setup.
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
        tasks_module.make_batch = lambda *a, **k: SimpleNamespace(id="batch-id")
        tasks_module.generate_keyterms_task = DummyTask()
        tasks_module.library_scan_task = DummyTask()
        tasks_module.translate_subtitles_task = DummyTask()
        sys.modules["tasks"] = tasks_module


_install_app_dependency_stubs()

app_module = importlib.import_module("web.app")
app = app_module.app
app.config.update(TESTING=True)


# --- GET /api/capabilities ---------------------------------------------------


def test_capabilities_lists_both_engines():
    with app.test_client() as client:
        resp = client.get("/api/capabilities")
    body = resp.get_json()
    assert resp.status_code == 200
    assert set(body["engines"].keys()) == {"deepgram", "whisper"}
    assert "audio_intelligence" in body["engines"]["deepgram"]["capabilities"]
    assert "audio_intelligence" not in body["engines"]["whisper"]["capabilities"]
    assert "keyterm" in body["engines"]["whisper"]["capabilities"]


def test_capabilities_reports_default_engine_and_models():
    with app.test_client() as client:
        resp = client.get("/api/capabilities")
    body = resp.get_json()
    assert body["default_engine"] == "deepgram"
    assert "small" in body["whisper_models"]
    assert body["default_whisper_model"] == "small"


# --- POST /api/submit validation ----------------------------------------------


def _submit(client, **extra):
    payload = {"files": [], "language": "en", **extra}
    return client.post("/api/submit", json=payload)


def test_submit_rejects_unknown_engine():
    with app.test_client() as client:
        resp = _submit(client, engine="siri")
    assert resp.status_code == 400


def test_submit_rejects_unknown_whisper_model():
    with app.test_client() as client:
        resp = _submit(client, engine="whisper", whisper_model="enormous-v9")
    assert resp.status_code == 400


def test_submit_passes_engine_to_batch(monkeypatch):
    captured = {}

    def fake_make_batch(files, model, language, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="batch-id")

    monkeypatch.setattr(app_module, "make_batch", fake_make_batch)
    with app.test_client() as client:
        resp = _submit(client, engine="whisper", whisper_model="base")
    assert resp.status_code == 200
    assert captured["engine"] == "whisper"
    assert captured["whisper_model"] == "base"


def test_submit_defaults_to_deepgram(monkeypatch):
    captured = {}

    def fake_make_batch(files, model, language, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="batch-id")

    monkeypatch.setattr(app_module, "make_batch", fake_make_batch)
    with app.test_client() as client:
        resp = _submit(client)
    assert resp.status_code == 200
    assert captured["engine"] == "deepgram"
    assert captured["whisper_model"] is None


# --- POST /api/estimate engine awareness --------------------------------------


def test_estimate_whisper_is_free():
    with app.test_client() as client:
        resp = client.post("/api/estimate", json={"files": [], "engine": "whisper"})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["estimated_cost_usd"] == 0.0
    assert body["price_per_minute"] == 0.0
    assert body["engine"] == "whisper"


def test_estimate_deepgram_keeps_pricing():
    with app.test_client() as client:
        resp = client.post("/api/estimate", json={"files": []})
    body = resp.get_json()
    assert body["price_per_minute"] == 0.0057
    assert body["engine"] == "deepgram"
