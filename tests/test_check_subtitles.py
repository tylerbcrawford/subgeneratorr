import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _install_core_dependency_stubs():
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


_install_core_dependency_stubs()

from core.transcribe import SUBTITLE_EXTS, check_subtitles, has_sidecar_subtitle


def test_has_sidecar_subtitle_srt():
    assert ".srt" in SUBTITLE_EXTS
    assert has_sidecar_subtitle("video", {"video.srt", "video.mkv"}) is True


def test_has_sidecar_subtitle_with_lang_code():
    assert has_sidecar_subtitle("video", {"video.en.srt", "video.mkv"}) is True


def test_has_sidecar_subtitle_ass():
    assert has_sidecar_subtitle("video", {"video.ass"}) is True


def test_has_sidecar_subtitle_no_match():
    assert has_sidecar_subtitle("video", {"video.mkv", "other.srt"}) is False


def test_has_sidecar_partial_stem_no_match():
    assert has_sidecar_subtitle("video", {"video2.srt"}) is False


def test_has_sidecar_empty_dir():
    assert has_sidecar_subtitle("video", set()) is False


def test_check_subtitles_finds_sidecar(tmp_path):
    media_path = tmp_path / "video.mkv"
    media_path.write_text("")
    (tmp_path / "video.srt").write_text("")
    dir_filenames = {path.name for path in tmp_path.iterdir()}

    result = check_subtitles(media_path, dir_filenames)

    assert result["has_subtitles"] is True
    assert result["subtitle_source"] == "sidecar"


def test_check_subtitles_finds_embedded(tmp_path):
    media_path = tmp_path / "video.mkv"
    media_path.write_text("")

    with patch(
        "core.transcribe.subprocess.run",
        return_value=SimpleNamespace(stdout="subtitle\n"),
    ) as mock_run:
        result = check_subtitles(media_path, {"video.mkv"})

    assert result["has_subtitles"] is True
    assert result["subtitle_source"] == "embedded"
    mock_run.assert_called_once()


def test_check_subtitles_none(tmp_path):
    media_path = tmp_path / "video.mkv"
    media_path.write_text("")

    with patch(
        "core.transcribe.subprocess.run",
        return_value=SimpleNamespace(stdout=""),
    ) as mock_run:
        result = check_subtitles(media_path, {"video.mkv"})

    assert result["has_subtitles"] is False
    assert result["subtitle_source"] is None
    mock_run.assert_called_once()
