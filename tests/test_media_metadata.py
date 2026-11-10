#!/usr/bin/env python3
"""Path -> show/movie metadata extraction that feeds LLM keyterm prompts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.media_metadata import (
    MediaMetadata,
    extract_media_metadata,
    format_metadata_for_prompt,
    get_show_or_movie_name,
)


def test_tv_episode_with_title():
    meta = extract_media_metadata(
        Path("/media/TV/Breaking Bad/Season 01/Breaking Bad - S01E05 - Gray Matter.mkv")
    )
    assert meta.to_dict() == {
        "media_type": "tv",
        "name": "Breaking Bad",
        "season": 1,
        "episode": 5,
        "episode_title": "Gray Matter",
        "year": None,
        "filename": "Breaking Bad - S01E05 - Gray Matter",
    }
    assert format_metadata_for_prompt(meta) == (
        'Show: "Breaking Bad"\nContext: Season 1, Episode 5: "Gray Matter"'
    )
    assert "S01E05" in repr(meta)


def test_tv_release_style_filename_uses_show_folder_name():
    meta = extract_media_metadata(
        Path("/media/TV/The Office (US)/Season 2/The.Office.S02E03.1080p.WEB-DL.mkv")
    )
    assert (meta.media_type, meta.name, meta.season, meta.episode) == (
        "tv",
        "The Office (US)",
        2,
        3,
    )
    assert meta.episode_title is None
    assert (
        format_metadata_for_prompt(meta) == 'Show: "The Office (US)"\nContext: Season 2, Episode 3'
    )


def test_tv_specials_season_zero():
    meta = extract_media_metadata(Path("/media/TV/Pioneer One/Specials/Pioneer One - S00E01.mkv"))
    assert (meta.media_type, meta.name, meta.season, meta.episode) == ("tv", "Pioneer One", 0, 1)


def test_movie_with_year():
    meta = extract_media_metadata(Path("/media/Movies/Inception (2010)/Inception (2010).mkv"))
    assert (meta.media_type, meta.name, meta.year) == ("movie", "Inception (2010)", "2010")
    assert format_metadata_for_prompt(meta) == 'Movie: "Inception (2010)"'
    assert get_show_or_movie_name(meta) == "Inception (2010)"


def test_movie_without_year_uses_folder_name():
    meta = extract_media_metadata(Path("/media/Movies/Tears of Steel/tears_of_steel.mp4"))
    assert (meta.media_type, meta.name, meta.year) == ("movie", "Tears of Steel", None)
    assert repr(meta) == "<MediaMetadata Movie: Tears of Steel>"


def test_prompt_format_for_show_without_episode_context():
    assert format_metadata_for_prompt(MediaMetadata("tv", "Pioneer One")) == 'Show: "Pioneer One"'
