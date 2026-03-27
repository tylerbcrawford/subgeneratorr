import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))


def _install_dependency_stubs():
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


_install_dependency_stubs()

from core.transcribe import get_audio_selection_language, resolve_subtitle_path
from generate_subtitles import Config, SubtitleGenerator


def _make_generator():
    generator = SubtitleGenerator.__new__(SubtitleGenerator)
    generator.stats = {
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "total_minutes": 0,
        "failed_files": [],
    }
    generator.log = lambda *args, **kwargs: None
    return generator


def test_resolve_subtitle_path_keeps_english_tag():
    media = Path("/media/show/episode.mkv")
    assert resolve_subtitle_path(media, "en") == Path("/media/show/episode.eng.srt")


def test_resolve_subtitle_path_normalizes_regional_variants():
    media = Path("/media/movies/filme.mkv")
    assert resolve_subtitle_path(media, "pt-BR") == Path("/media/movies/filme.por.srt")


def test_resolve_subtitle_path_uses_detected_language_when_available():
    media = Path("/media/show/episode.mkv")
    response = SimpleNamespace(
        results=SimpleNamespace(
            channels=[SimpleNamespace(detected_language="es-419")]
        )
    )

    assert resolve_subtitle_path(
        media,
        "en",
        detect_language=True,
        resp=response,
    ) == Path("/media/show/episode.spa.srt")


def test_resolve_subtitle_path_uses_neutral_fallback_for_multi():
    media = Path("/media/show/episode.mkv")
    assert resolve_subtitle_path(media, "multi") == Path("/media/show/episode.und.srt")


def test_resolve_subtitle_path_uses_neutral_fallback_for_unknown_detected_language():
    media = Path("/media/show/episode.mkv")
    response = SimpleNamespace(
        results=SimpleNamespace(
            channels=[SimpleNamespace(detected_language="xx-YY")]
        )
    )

    assert resolve_subtitle_path(
        media,
        "en",
        detect_language=True,
        resp=response,
    ) == Path("/media/show/episode.und.srt")


def test_auto_detect_does_not_bias_audio_stream_selection():
    assert get_audio_selection_language("en", detect_language=True) is None
    assert get_audio_selection_language("multi") is None
    assert get_audio_selection_language("pt-BR") == "pt-br"


def test_read_video_list_accepts_audio_files(monkeypatch, tmp_path):
    audio_file = tmp_path / "track.mp3"
    video_file = tmp_path / "episode.mkv"
    text_file = tmp_path / "notes.txt"
    for path in (audio_file, video_file, text_file):
        path.write_text("test")

    file_list = tmp_path / "files.txt"
    file_list.write_text(f"{audio_file}\n{video_file}\n{text_file}\n")

    monkeypatch.setattr(Config, "LANGUAGE", "en")
    monkeypatch.setattr(Config, "DETECT_LANGUAGE", False)
    monkeypatch.setattr(Config, "ENABLE_TRANSCRIPT", False)
    monkeypatch.setattr(Config, "FORCE_REGENERATE", False)

    generator = _make_generator()
    results = generator.read_video_list_from_file(str(file_list))

    assert results == [audio_file, video_file]


def test_read_video_list_skips_existing_language_tagged_sidecar_in_auto_detect(monkeypatch, tmp_path):
    media_file = tmp_path / "episode.mkv"
    media_file.write_text("video")
    (tmp_path / "episode.spa.srt").write_text("subtitle")

    file_list = tmp_path / "files.txt"
    file_list.write_text(f"{media_file}\n")

    monkeypatch.setattr(Config, "LANGUAGE", "en")
    monkeypatch.setattr(Config, "DETECT_LANGUAGE", True)
    monkeypatch.setattr(Config, "ENABLE_TRANSCRIPT", False)
    monkeypatch.setattr(Config, "FORCE_REGENERATE", False)

    generator = _make_generator()
    results = generator.read_video_list_from_file(str(file_list))

    assert results == []
    assert generator.stats["skipped"] == 1


def test_directory_scan_uses_resolved_language_tag_for_audio(monkeypatch, tmp_path):
    audio_file = tmp_path / "album" / "track.m4a"
    audio_file.parent.mkdir(parents=True)
    audio_file.write_text("audio")
    (audio_file.parent / "track.por.srt").write_text("subtitle")

    video_file = tmp_path / "show" / "episode.mkv"
    video_file.parent.mkdir(parents=True)
    video_file.write_text("video")

    monkeypatch.setattr(Config, "MEDIA_PATH", str(tmp_path))
    monkeypatch.setattr(Config, "LANGUAGE", "pt-BR")
    monkeypatch.setattr(Config, "DETECT_LANGUAGE", False)
    monkeypatch.setattr(Config, "ENABLE_TRANSCRIPT", False)
    monkeypatch.setattr(Config, "FORCE_REGENERATE", False)

    generator = _make_generator()
    results = generator.find_videos_without_subtitles()

    assert results == [video_file]


def test_directory_scan_skips_language_tagged_sidecar_in_auto_detect(monkeypatch, tmp_path):
    media_file = tmp_path / "podcasts" / "episode.mp3"
    media_file.parent.mkdir(parents=True)
    media_file.write_text("audio")
    (media_file.parent / "episode.spa.srt").write_text("subtitle")

    monkeypatch.setattr(Config, "MEDIA_PATH", str(tmp_path))
    monkeypatch.setattr(Config, "LANGUAGE", "en")
    monkeypatch.setattr(Config, "DETECT_LANGUAGE", True)
    monkeypatch.setattr(Config, "ENABLE_TRANSCRIPT", False)
    monkeypatch.setattr(Config, "FORCE_REGENERATE", False)

    generator = _make_generator()
    results = generator.find_videos_without_subtitles()

    assert results == []
