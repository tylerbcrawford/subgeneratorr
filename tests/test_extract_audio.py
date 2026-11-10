#!/usr/bin/env python3
"""extract_audio temp-file hygiene: no leaked descriptors or orphaned files."""

import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if "deepgram" not in sys.modules:
    deepgram = types.ModuleType("deepgram")
    deepgram.DeepgramClient = type("DeepgramClient", (), {})
    sys.modules["deepgram"] = deepgram
if "deepgram_captions" not in sys.modules:
    deepgram_captions = types.ModuleType("deepgram_captions")
    deepgram_captions.DeepgramConverter = object
    deepgram_captions.srt = object()
    sys.modules["deepgram_captions"] = deepgram_captions

from core import transcribe


@pytest.fixture
def tmpdir_env(tmp_path, monkeypatch):
    monkeypatch.setattr(transcribe.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(transcribe, "get_audio_stream_index", lambda *a, **k: None)
    monkeypatch.setattr(transcribe, "_get_channel_count", lambda *a, **k: 2)
    return tmp_path


def _open_fds():
    return len(os.listdir("/proc/self/fd"))


def test_extract_audio_closes_its_descriptor(tmpdir_env, monkeypatch):
    monkeypatch.setattr(transcribe.subprocess, "run", lambda *a, **k: None)
    before = _open_fds()
    tmp = transcribe.extract_audio(Path("/media/video.mkv"))
    assert _open_fds() == before
    assert tmp.parent == tmpdir_env
    assert tmp.name.startswith(transcribe.AUDIO_TMP_PREFIX)


def test_extract_audio_removes_temp_file_when_ffmpeg_fails(tmpdir_env, monkeypatch):
    def boom(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(transcribe.subprocess, "run", boom)
    with pytest.raises(subprocess.CalledProcessError):
        transcribe.extract_audio(Path("/media/video.mkv"))
    assert list(tmpdir_env.iterdir()) == []


def test_extract_audio_removes_temp_file_on_timeout(tmpdir_env, monkeypatch):
    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 3600)

    monkeypatch.setattr(transcribe.subprocess, "run", slow)
    with pytest.raises(RuntimeError, match="timed out"):
        transcribe.extract_audio(Path("/media/video.mkv"))
    assert list(tmpdir_env.iterdir()) == []


def test_sweep_removes_only_stale_audio_temp_files(tmpdir_env):
    stale = tmpdir_env / f"{transcribe.AUDIO_TMP_PREFIX}old.mp3"
    fresh = tmpdir_env / f"{transcribe.AUDIO_TMP_PREFIX}new.mp3"
    other = tmpdir_env / "unrelated.mp3"
    for f in (stale, fresh, other):
        f.write_text("x")
    old = time.time() - 7 * 3600
    os.utime(stale, (old, old))
    os.utime(other, (old, old))

    assert transcribe.sweep_stale_audio_temp_files() == 1
    assert not stale.exists()
    assert fresh.exists() and other.exists()
