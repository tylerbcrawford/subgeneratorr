"""Engine-conditional DEEPGRAM_API_KEY validation (cli/config.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli"))
from config import Config  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_config(monkeypatch):
    """Snapshot/restore the class attributes we mutate."""
    monkeypatch.setattr(Config, "DEEPGRAM_API_KEY", None, raising=False)
    monkeypatch.setattr(Config, "ASR_ENGINE", "deepgram", raising=False)
    yield


def test_default_engine_is_deepgram():
    assert Config.ASR_ENGINE == "deepgram"


def test_validate_requires_key_for_deepgram():
    with pytest.raises(ValueError, match="DEEPGRAM_API_KEY"):
        Config.validate()


def test_validate_passes_with_key_for_deepgram(monkeypatch):
    monkeypatch.setattr(Config, "DEEPGRAM_API_KEY", "dg-test")
    assert Config.validate() is True


def test_validate_whisper_needs_no_key(monkeypatch):
    """Zero-cloud mode: ASR_ENGINE=whisper with no Deepgram key must not raise."""
    monkeypatch.setattr(Config, "ASR_ENGINE", "whisper")
    assert Config.validate() is True


def test_validate_rejects_unknown_engine(monkeypatch):
    monkeypatch.setattr(Config, "ASR_ENGINE", "siri")
    with pytest.raises(ValueError, match="ASR_ENGINE"):
        Config.validate()
