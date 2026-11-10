import json
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

        deepgram.DeepgramClient = DeepgramClient
        sys.modules["deepgram"] = deepgram

    if "deepgram_captions" not in sys.modules:
        deepgram_captions = types.ModuleType("deepgram_captions")
        deepgram_captions.DeepgramConverter = object
        deepgram_captions.srt = object()
        sys.modules["deepgram_captions"] = deepgram_captions


_install_core_dependency_stubs()

from core.transcribe import (
    SUBTITLE_EXTS,
    check_subtitles,
    has_embedded_subtitle,
    has_sidecar_subtitle,
)


def _ffprobe(*streams):
    """Fake ffprobe JSON for subtitle streams given as (language, forced) pairs."""
    payload = {
        "streams": [
            {
                "index": i,
                "tags": {"language": lang} if lang else {},
                "disposition": {"forced": int(forced)},
            }
            for i, (lang, forced) in enumerate(streams)
        ]
    }
    return SimpleNamespace(stdout=json.dumps(payload))


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
        return_value=_ffprobe(("eng", False)),
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


def _has_embedded(tmp_path, streams, language=None):
    media_path = tmp_path / "video.mkv"
    media_path.write_text("")
    with patch("core.transcribe.subprocess.run", return_value=_ffprobe(*streams)):
        return has_embedded_subtitle(media_path, language)


def test_embedded_any_language_counts_without_a_requested_language(tmp_path):
    assert _has_embedded(tmp_path, [("spa", False)]) is True


def test_embedded_other_language_does_not_count(tmp_path):
    assert _has_embedded(tmp_path, [("spa", False)], language="en") is False


def test_embedded_matching_language_counts_across_tag_forms(tmp_path):
    assert _has_embedded(tmp_path, [("ger", False)], language="de") is True
    assert _has_embedded(tmp_path, [("eng", False)], language="en-US") is True


def test_embedded_forced_track_never_counts(tmp_path):
    assert _has_embedded(tmp_path, [("eng", True)], language="en") is False
    assert _has_embedded(tmp_path, [("eng", True)]) is False


def test_embedded_untagged_track_counts(tmp_path):
    assert _has_embedded(tmp_path, [("", False)], language="en") is True
    assert _has_embedded(tmp_path, [("und", False)], language="en") is True


def test_embedded_auto_and_multi_accept_any_language(tmp_path):
    assert _has_embedded(tmp_path, [("spa", False)], language="auto") is True
    assert _has_embedded(tmp_path, [("spa", False)], language="multi") is True


def test_embedded_unparseable_ffprobe_output_means_none(tmp_path):
    media_path = tmp_path / "video.mkv"
    media_path.write_text("")
    with patch("core.transcribe.subprocess.run", return_value=SimpleNamespace(stdout="not json")):
        assert has_embedded_subtitle(media_path) is False


def test_check_subtitles_passes_language_to_embedded_check(tmp_path):
    media_path = tmp_path / "video.mkv"
    media_path.write_text("")
    with patch("core.transcribe.subprocess.run", return_value=_ffprobe(("spa", False))):
        result = check_subtitles(media_path, {"video.mkv"}, language="en")
    assert result == {"has_subtitles": False, "subtitle_source": None}
