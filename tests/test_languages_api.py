#!/usr/bin/env python3
"""
Tests for the language catalog / preference endpoints and the Ollama model
proxy: GET /api/languages, GET /api/languages/translation-support,
GET+PUT /api/settings/languages, GET /api/ollama/models. Reuses the stubbed
app from test_capabilities_api.py.
"""

import json

import pytest
import requests
from test_capabilities_api import app, app_module


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "sub" / "settings.json"
    monkeypatch.setenv("SETTINGS_PATH", str(path))
    return path


@pytest.fixture
def client():
    with app.test_client() as c:
        yield c


# --- GET /api/languages ------------------------------------------------------


def test_languages_returns_catalog_and_default_prefs(client, settings_file):
    body = client.get("/api/languages").get_json()
    codes = {e["code"] for e in body["languages"]}
    assert {"en", "auto", "multi", "pt-BR", "cy"} <= codes
    assert body["prefs"] == {"transcription": None, "translation": None}


# --- settings round trip ------------------------------------------------------


def test_put_then_get_round_trips_and_persists(client, settings_file):
    resp = client.put(
        "/api/settings/languages",
        json={"transcription": ["en", "auto", "fr", "en"], "translation": ["es"]},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"transcription": ["en", "auto", "fr"], "translation": ["es"]}
    assert client.get("/api/settings/languages").get_json()["translation"] == ["es"]
    on_disk = json.loads(settings_file.read_text())
    assert on_disk["languages"]["transcription"] == ["en", "auto", "fr"]


def test_put_partial_keeps_other_list(client, settings_file):
    client.put("/api/settings/languages", json={"transcription": ["en"], "translation": ["de"]})
    client.put("/api/settings/languages", json={"translation": None})
    assert client.get("/api/settings/languages").get_json() == {
        "transcription": ["en"],
        "translation": None,
    }


def test_put_preserves_unrelated_settings_keys(client, settings_file):
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text(json.dumps({"other": 1}))
    client.put("/api/settings/languages", json={"translation": ["fr"]})
    assert json.loads(settings_file.read_text())["other"] == 1


@pytest.mark.parametrize(
    "payload,needle",
    [
        ({"transcription": []}, "at least one"),
        ({"transcription": ["xx"]}, "Unknown transcription"),
        ({"translation": ["en"]}, "Unknown translation"),  # English is not a target
        ({"translation": "es"}, "list of language codes"),
        ({"translation": ["auto"]}, "Unknown translation"),
    ],
)
def test_put_rejects_invalid_lists(client, settings_file, payload, needle):
    resp = client.put("/api/settings/languages", json=payload)
    assert resp.status_code == 400
    assert needle in resp.get_json()["error"]
    assert not settings_file.exists()


def test_put_requires_json_object(client, settings_file):
    resp = client.put("/api/settings/languages", data="[]", content_type="application/json")
    assert resp.status_code == 400


def test_corrupt_settings_file_reads_as_defaults(client, settings_file):
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text("{not json")
    assert client.get("/api/settings/languages").get_json() == {
        "transcription": None,
        "translation": None,
    }


def test_unwritable_settings_path_is_500(client, tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("SETTINGS_PATH", str(blocker / "settings.json"))
    resp = client.put("/api/settings/languages", json={"translation": ["es"]})
    assert resp.status_code == 500
    assert "Could not save settings" in resp.get_json()["error"]


# --- GET /api/languages/translation-support -----------------------------------


def test_translation_support_cloud_and_ollama(client):
    cloud = client.get("/api/languages/translation-support?provider=anthropic&model=x").get_json()
    assert cloud["supported"] is None and cloud["verified"] is True
    llama = client.get(
        "/api/languages/translation-support?provider=ollama&model=llama3.1:8b"
    ).get_json()
    assert "es" in llama["supported"] and "ja" not in llama["supported"]
    unknown = client.get("/api/languages/translation-support?provider=ollama&model=foo").get_json()
    assert unknown == {"supported": None, "verified": False, "label": "foo", "source": ""}


# --- GET /api/ollama/models ----------------------------------------------------


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _patch_get(monkeypatch, result):
    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(app_module.requests, "get", fake_get)
    return calls


def test_ollama_models_lists_and_sorts(client, monkeypatch):
    calls = _patch_get(
        monkeypatch,
        _FakeResp(
            {
                "models": [
                    {
                        "name": "qwen2.5:7b",
                        "details": {"family": "qwen2", "parameter_size": "7.6B"},
                    },
                    {"name": "Gemma3:4b", "details": {"family": "gemma3"}},
                    {"bogus": True},
                ]
            }
        ),
    )
    resp = client.get("/api/ollama/models?host=mac:11434/v1")
    body = resp.get_json()
    assert resp.status_code == 200
    assert calls == [("http://mac:11434/api/tags", 3)]
    assert body["host"] == "http://mac:11434"
    assert [m["name"] for m in body["models"]] == ["Gemma3:4b", "qwen2.5:7b"]
    assert body["models"][1] == {"name": "qwen2.5:7b", "family": "qwen2", "parameter_size": "7.6B"}


def test_ollama_models_falls_back_to_env_host(client, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama:11434")
    calls = _patch_get(monkeypatch, _FakeResp({"models": []}))
    assert client.get("/api/ollama/models").status_code == 200
    assert calls[0][0] == "http://ollama:11434/api/tags"


def test_ollama_models_requires_host(client, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    resp = client.get("/api/ollama/models")
    assert resp.status_code == 400
    assert "OLLAMA_HOST" in resp.get_json()["error"]


@pytest.mark.parametrize("host", ["http://a b", "file:///etc/passwd", "host/../x", "x?y=1"])
def test_ollama_models_rejects_malformed_host(client, monkeypatch, host):
    calls = _patch_get(monkeypatch, _FakeResp({"models": []}))
    resp = client.get("/api/ollama/models", query_string={"host": host})
    assert resp.status_code == 400
    assert calls == []


@pytest.mark.parametrize(
    "result",
    [
        requests.ConnectionError("refused"),
        requests.Timeout("slow"),
        _FakeResp({}, status=500),
        _FakeResp(ValueError("not json")),
    ],
)
def test_ollama_models_unreachable_is_502(client, monkeypatch, result):
    _patch_get(monkeypatch, result)
    resp = client.get("/api/ollama/models?host=localhost:11434")
    assert resp.status_code == 502
    assert "Could not reach Ollama" in resp.get_json()["error"]
