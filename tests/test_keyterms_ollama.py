#!/usr/bin/env python3
"""
Keyterm generation through a local Ollama model: endpoint validation and $0
estimate (POST /api/keyterms/generate), the Celery task's Ollama wiring, and
KeytermSearcher passing the Ollama endpoint down to call_llm.
"""

from types import SimpleNamespace

import pytest
from test_translate_api import _patched_env, app, app_module
from test_translate_task import FakeTaskContext, tasks_module

import core.keyterm_search as keyterm_search
from core.keyterm_search import KeytermSearcher
from core.llm_providers import LLMModel, LLMProvider


def _video(tmp_path):
    video = tmp_path / "Inception (2010)" / "Inception (2010).mkv"
    video.parent.mkdir()
    video.write_text("video")
    return video


def _post(tmp_path, monkeypatch, **body):
    video = _video(tmp_path)
    with app.test_client() as client, _patched_env(app_module, tmp_path):
        return client.post(
            "/api/keyterms/generate", json={"video_path": str(video), "provider": "ollama", **body}
        )


# --- endpoint -----------------------------------------------------------------


def test_ollama_requires_model_name(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama:11434")
    resp = _post(tmp_path, monkeypatch)
    assert resp.status_code == 400
    assert "Ollama model name required" in resp.get_json()["error"]


def test_ollama_requires_host(tmp_path, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    resp = _post(tmp_path, monkeypatch, model="qwen3:8b")
    assert resp.status_code == 400
    assert "Ollama host not configured" in resp.get_json()["error"]


def test_ollama_estimate_is_free(tmp_path, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    resp = _post(
        tmp_path, monkeypatch, model="qwen3:8b", ollama_host="mac:11434", estimate_only=True
    )
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert body["estimated_cost"] == 0
    assert body["model"] == "qwen3:8b"


def test_cloud_estimate_works_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = _post(tmp_path, monkeypatch, provider="anthropic", estimate_only=True)
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert body["estimated_cost"] > 0


def test_cloud_generation_still_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = _post(tmp_path, monkeypatch, provider="anthropic")
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "ANTHROPIC_API_KEY not configured"


def test_ollama_generation_queues_task_with_host(tmp_path, monkeypatch):
    calls = []

    class RecordingTask:
        def delay(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id="00000000-0000-0000-0000-000000000001")

    monkeypatch.setattr(app_module, "generate_keyterms_task", RecordingTask())
    resp = _post(tmp_path, monkeypatch, model="qwen3:8b", ollama_host="http://mac:11434")
    assert resp.status_code == 200
    assert calls[0]["provider"] == "ollama"
    assert calls[0]["model"] == "qwen3:8b"
    assert calls[0]["ollama_host"] == "http://mac:11434"


def test_cloud_generation_does_not_forward_ollama_host(tmp_path, monkeypatch):
    calls = []

    class RecordingTask:
        def delay(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id="00000000-0000-0000-0000-000000000002")

    monkeypatch.setattr(app_module, "generate_keyterms_task", RecordingTask())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama:11434")
    resp = _post(tmp_path, monkeypatch, provider="anthropic")
    assert resp.status_code == 200
    assert calls[0]["ollama_host"] is None


# --- Celery task --------------------------------------------------------------


def test_task_builds_ollama_searcher_with_normalized_base_url(tmp_path, monkeypatch):
    record = {}

    class FakeSearcher:
        def __init__(self, provider, model, api_key, base_url=None):
            record.update(provider=provider, model=model, api_key=api_key, base_url=base_url)

        def generate_from_metadata(self, **kw):
            return {"keyterms": ["Cobb"], "token_count": 10, "estimated_cost": 0.0, "model": "q"}

    monkeypatch.setattr(keyterm_search, "KeytermSearcher", FakeSearcher)
    monkeypatch.setattr(tasks_module, "load_keyterms_from_csv", lambda vp: None)
    monkeypatch.setattr(tasks_module, "save_keyterms_to_csv", lambda vp, k: True)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    result = tasks_module.generate_keyterms_task(
        FakeTaskContext(),
        video_path=str(_video(tmp_path)),
        provider="ollama",
        model="qwen3:8b",
        ollama_host="mac:11434",
    )
    assert record == {
        "provider": LLMProvider.OLLAMA,
        "model": "qwen3:8b",
        "api_key": None,
        "base_url": "http://mac:11434/v1",
    }
    assert result["actual_cost"] == 0.0 and result["keyterms"] == ["Cobb"]


def test_task_ollama_without_host_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks_module, "load_keyterms_from_csv", lambda vp: None)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    with pytest.raises(RuntimeError, match="Ollama host not configured"):
        tasks_module.generate_keyterms_task(
            FakeTaskContext(), video_path=str(_video(tmp_path)), provider="ollama", model="m"
        )


# --- KeytermSearcher ----------------------------------------------------------


def test_searcher_passes_base_url_and_model_name_to_call_llm(monkeypatch):
    seen = {}

    def fake_call_llm(provider, model, api_key, prompt, **kw):
        seen.update(provider=provider, model=model, api_key=api_key, **kw)
        return "Cobb, Ariadne", 100, 20

    monkeypatch.setattr(keyterm_search, "call_llm", fake_call_llm)
    searcher = KeytermSearcher(LLMProvider.OLLAMA, "qwen3:8b", None, base_url="http://mac:11434/v1")
    metadata = SimpleNamespace(media_type="movie")
    monkeypatch.setattr(searcher, "_build_prompt", lambda *a, **k: "prompt")
    result = searcher.generate_from_metadata(metadata)

    assert seen["model"] == "qwen3:8b" and seen["base_url"] == "http://mac:11434/v1"
    assert result["keyterms"] == ["Cobb", "Ariadne"]
    assert result["estimated_cost"] == 0 and result["model"] == "qwen3:8b"


def test_searcher_rejects_blank_ollama_model():
    with pytest.raises(ValueError, match="Ollama model name required"):
        KeytermSearcher(LLMProvider.OLLAMA, "  ", None)


def test_searcher_still_validates_cloud_models():
    with pytest.raises(ValueError):
        KeytermSearcher(LLMProvider.OPENAI, LLMModel.CLAUDE_SONNET_5_5, "k")
