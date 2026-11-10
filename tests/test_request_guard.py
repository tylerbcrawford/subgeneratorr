#!/usr/bin/env python3
"""
Cross-site request guard, security headers, and Ollama host validation.

Reuses the stubbed Flask app that test_translate_api.py builds.
"""

import io

import pytest
from test_translate_api import _make_media_with_srt, _patched_env, app, app_module


@pytest.fixture
def client():
    with app.test_client() as c:
        yield c


def test_non_json_write_is_rejected(client):
    # A cross-origin page can send text/plain without a CORS preflight.
    resp = client.post("/api/library-scan", data="{}", headers={"Content-Type": "text/plain"})
    assert resp.status_code == 415


def test_bodyless_form_write_is_rejected(client):
    resp = client.post("/api/library-scan", content_type="application/x-www-form-urlencoded")
    assert resp.status_code == 415


def test_cross_site_write_is_rejected_even_as_json(client):
    resp = client.post("/api/library-scan", json={}, headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 403


def test_cross_site_cancel_is_rejected(client):
    resp = client.post(
        "/api/library-scan/00000000-0000-0000-0000-000000000000/cancel",
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("site", ["same-origin", "same-site", "none", None])
def test_same_site_and_non_browser_json_writes_pass(client, site):
    headers = {"Sec-Fetch-Site": site} if site else {}
    resp = client.post("/api/library-scan", json={"skip_embedded": True}, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "pending"


def test_bodyless_cancel_still_works(client):
    resp = client.post("/api/library-scan/00000000-0000-0000-0000-000000000000/cancel")
    assert resp.status_code == 200


def test_keyterm_upload_accepts_multipart_only(client, tmp_path):
    video, _ = _make_media_with_srt(tmp_path)
    with _patched_env(app_module, tmp_path):
        ok = client.post(
            "/api/keyterms/upload",
            data={"video_path": str(video), "file": (io.BytesIO(b"Heisenberg\n"), "k.csv")},
            content_type="multipart/form-data",
        )
        bad = client.post("/api/keyterms/upload", data="x", content_type="text/plain")
    assert ok.status_code == 200
    assert bad.status_code == 415


def test_reads_are_not_affected_by_the_guard(client):
    resp = client.get("/api/config", headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 200


def test_json_body_must_be_an_object(client):
    resp = client.post("/api/library-scan", json=["not", "an", "object"])
    assert resp.status_code == 400


def test_security_headers_present(client):
    resp = client.get("/healthz")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert resp.headers["Referrer-Policy"] == "same-origin"


def test_frame_options_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(app_module, "FRAME_OPTIONS", "")
    assert "X-Frame-Options" not in client.get("/healthz").headers


@pytest.mark.parametrize(
    "host",
    ["http://ollama:11434/api/../admin", "http://user:pw@ollama:11434", "http://ollama:11434/?x=1"],
)
def test_translate_rejects_malformed_ollama_host(client, tmp_path, host):
    video, _ = _make_media_with_srt(tmp_path)
    with _patched_env(app_module, tmp_path):
        resp = client.post(
            "/api/translate",
            json={
                "video_path": str(video),
                "targets": ["es"],
                "provider": "ollama",
                "model": "qwen3:8b",
                "ollama_host": host,
            },
        )
    assert resp.status_code == 400
    assert "host" in resp.get_json()["error"].lower()


def test_keyterm_generate_rejects_malformed_ollama_host(client, tmp_path):
    video, _ = _make_media_with_srt(tmp_path)
    with _patched_env(app_module, tmp_path):
        resp = client.post(
            "/api/keyterms/generate",
            json={
                "video_path": str(video),
                "provider": "ollama",
                "model": "qwen3:8b",
                "ollama_host": "http://ollama:11434/evil/path",
            },
        )
    assert resp.status_code == 400
