#!/usr/bin/env python3
"""
Media metadata extraction utilities for video files.

Parses video file paths to extract structured metadata including:
- Media type (TV show vs Movie)
- Show/movie names
- Season and episode numbers (for TV shows)
- Episode titles (for TV shows)
- Years (for movies)
"""

from typing import Dict, Optional
from pathlib import Path
import re


class MediaMetadata:
    """Container for extracted media metadata."""

    def __init__(
        self,
        media_type: str,  # "tv" or "movie"
        name: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        episode_title: Optional[str] = None,
        year: Optional[str] = None,
        filename: Optional[str] = None
    ):
        self.media_type = media_type
        self.name = name
        self.season = season
        self.episode = episode
        self.episode_title = episode_title
        self.year = year
        self.filename = filename

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            'media_type': self.media_type,
            'name': self.name,
            'season': self.season,
            'episode': self.episode,
            'episode_title': self.episode_title,
            'year': self.year,
            'filename': self.filename
        }

    def __repr__(self) -> str:
        if self.media_type == 'tv':
            ep_info = f"S{self.season:02d}E{self.episode:02d}" if self.season and self.episode else ""
            title_info = f" - {self.episode_title}" if self.episode_title else ""
            return f"<MediaMetadata TV: {self.name} {ep_info}{title_info}>"
        else:
            year_info = f" ({self.year})" if self.year else ""
            return f"<MediaMetadata Movie: {self.name}{year_info}>"


def extract_media_metadata(video_path: Path) -> MediaMetadata:
    """
    Extract structured metadata from video file path.

    Supports common media library directory structures:
    - TV: /media/tv/{Show Name}/Season XX/{Show} - SxxExx - {Title}.mkv
    - Movies: /media/movies/{Movie Name (Year)}/{Movie}.mkv

    Args:
        video_path: Path to video file

    Returns:
        MediaMetadata object with extracted information

    Examples:
        >>> extract_media_metadata(Path("/media/tv/Breaking Bad/Season 01/Breaking Bad - S01E05.mkv"))
        <MediaMetadata TV: Breaking Bad S01E05>

        >>> extract_media_metadata(Path("/media/movies/Inception (2010)/movie.mkv"))
        <MediaMetadata Movie: Inception (2010)>
    """
    path_parts = video_path.parts
    filename = video_path.stem  # filename without extension

    # Determine media type by checking for "Season" or "Specials" in path
    is_tv = any('season' in part.lower() or part.lower() == 'specials'
                for part in path_parts)

    if is_tv:
        return _extract_tv_metadata(video_path, path_parts, filename)
    else:
        return _extract_movie_metadata(video_path, path_parts, filename)


def _extract_tv_metadata(video_path: Path, path_parts: tuple, filename: str) -> MediaMetadata:
    """
    Extract metadata for TV show episodes.

    Expected patterns:
    - Directory: /media/tv/{Show Name}/Season XX/
    - Filename: {Show} - SxxExx - {Episode Title}.mkv
    - Filename alt: {Show} - SxxExx.mkv
    """
    # Extract show name from directory structure
    show_name = None
    for i, part in enumerate(path_parts):
        part_lower = part.lower()
        if 'season' in part_lower or part_lower == 'specials':
            if i > 0:
                show_name = path_parts[i - 1]
            break

    # Fallback: use parent directory name
    if not show_name:
        show_name = video_path.parent.name

    # Parse season and episode from filename
    # Pattern: SxxExx or S{season}E{episode}
    season_episode_pattern = r'[Ss](\d{1,2})[Ee](\d{1,2})'
    match = re.search(season_episode_pattern, filename)

    season = None
    episode = None
    episode_title = None

    if match:
        season = int(match.group(1))
        episode = int(match.group(2))

        # Try to extract episode title
        # Pattern: "Show Name - S01E05 - Episode Title"
        title_pattern = r'[Ss]\d{1,2}[Ee]\d{1,2}\s*-\s*(.+?)(?:\s+\[|\s+\(|\s+WEBDL|$)'
        title_match = re.search(title_pattern, filename)
        if title_match:
            episode_title = title_match.group(1).strip()
            # Remove any trailing quality markers
            episode_title = re.sub(r'\s+(WEBDL|BluRay|WEB-DL|HDTV|1080p|720p|480p).*$', '', episode_title, flags=re.IGNORECASE)

    return MediaMetadata(
        media_type='tv',
        name=show_name,
        season=season,
        episode=episode,
        episode_title=episode_title,
        filename=filename
    )


def _extract_movie_metadata(video_path: Path, path_parts: tuple, filename: str) -> MediaMetadata:
    """
    Extract metadata for movies.

    Expected patterns:
    - Directory: /media/movies/{Movie Name (Year)}/
    - Filename: {Movie}.mkv
    """
    # Use parent directory name as movie name
    movie_name = video_path.parent.name

    # Try to extract year from movie name
    # Pattern: "Movie Name (2010)" or "Movie Name (Year)"
    year_pattern = r'\((\d{4})\)'
    match = re.search(year_pattern, movie_name)

    year = None
    if match:
        year = match.group(1)
        # Remove year from movie name for cleaner display
        # Keep it for now as it's the standard format

    return MediaMetadata(
        media_type='movie',
        name=movie_name,
        year=year,
        filename=filename
    )


def get_show_or_movie_name(metadata: MediaMetadata) -> str:
    """
    Extract just the show or movie name from metadata.

    Useful for file naming and show-level operations.

    Args:
        metadata: MediaMetadata object

    Returns:
        Show or movie name

    Examples:
        >>> metadata = MediaMetadata('tv', 'Breaking Bad', season=1, episode=5)
        >>> get_show_or_movie_name(metadata)
        'Breaking Bad'

        >>> metadata = MediaMetadata('movie', 'Inception (2010)')
        >>> get_show_or_movie_name(metadata)
        'Inception (2010)'
    """
    return metadata.name


def format_metadata_for_prompt(metadata: MediaMetadata) -> str:
    """
    Format metadata into a human-readable string for LLM prompts.

    For TV shows, formats as "Show: X" with episode/season as context.
    For movies, just returns the movie name.

    Args:
        metadata: MediaMetadata object

    Returns:
        Formatted string suitable for LLM prompts

    Examples:
        >>> metadata = MediaMetadata('tv', 'Breaking Bad', season=1, episode=5, episode_title='Gray Matter')
        >>> format_metadata_for_prompt(metadata)
        'Show: "Breaking Bad"\\nContext: Season 1, Episode 5: "Gray Matter"'

        >>> metadata = MediaMetadata('movie', 'Inception (2010)', year='2010')
        >>> format_metadata_for_prompt(metadata)
        'Movie: "Inception (2010)"'
    """
    if metadata.media_type == 'tv':
        # Always start with show name
        result = f'Show: "{metadata.name}"'

        # Add context if we have episode/season info
        context_parts = []

        if metadata.season is not None:
            context_parts.append(f'Season {metadata.season}')

        if metadata.episode is not None:
            context_parts.append(f'Episode {metadata.episode}')

        if metadata.episode_title:
            context_parts[-1] = f'{context_parts[-1]}: "{metadata.episode_title}"'

        # Add context line if we have any context
        if context_parts:
            result += f'\nContext: {", ".join(context_parts)}'

        return result
    else:
        return f'Movie: "{metadata.name}"'
