#!/usr/bin/env python3
"""
Core transcription functionality for Subgeneratorr.

This module provides reusable functions for video processing and transcription
that can be used by both the CLI tool and the Web UI.
"""

from pathlib import Path
from deepgram import DeepgramClient, PrerecordedOptions
from deepgram_captions import DeepgramConverter, srt
import subprocess
import tempfile
import os
import json
import csv
from typing import Optional, List

# Subtitle file extensions to detect as sidecar files
SUBTITLE_EXTS = {'.srt', '.ass', '.ssa', '.sub', '.vtt'}

# Supported video file extensions
VIDEO_EXTS = {'.mkv', '.mp4', '.avi', '.mov', '.m4v', '.wmv', '.flv'}

# Supported audio file extensions (Deepgram compatible)
AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.ogg', '.opus', '.m4a', '.aac', '.wma'}

# Neutral language tag used when the output language cannot be resolved safely
NEUTRAL_SUBTITLE_LANG = "und"

# Preferred subtitle suffixes use ISO 639-2/B tags for media server compatibility.
# Regional variants are normalized to their base language for filename purposes.
_SUBTITLE_LANG_MAP = {
    "ar": "ara",
    "bg": "bul",
    "ca": "cat",
    "cs": "cze",
    "da": "dan",
    "de": "ger",
    "el": "gre",
    "en": "eng",
    "es": "spa",
    "et": "est",
    "fi": "fin",
    "fr": "fre",
    "hi": "hin",
    "hu": "hun",
    "id": "ind",
    "it": "ita",
    "ja": "jpn",
    "ko": "kor",
    "lt": "lit",
    "lv": "lav",
    "ms": "may",
    "nl": "dut",
    "no": "nor",
    "pl": "pol",
    "pt": "por",
    "ro": "rum",
    "ru": "rus",
    "sk": "slo",
    "sv": "swe",
    "th": "tha",
    "tr": "tur",
    "uk": "ukr",
    "vi": "vie",
    "zh": "chi",
}

# ISO 639-1/BCP-47 request codes → stream tags to match during ffprobe selection.
# Includes both /B and /T variants where they differ.
_STREAM_LANG_MAP = {
    "ar": {"ar", "ara"},
    "bg": {"bg", "bul"},
    "ca": {"ca", "cat"},
    "cs": {"cs", "cze", "ces"},
    "da": {"da", "dan"},
    "de": {"de", "ger", "deu"},
    "el": {"el", "gre", "ell"},
    "en": {"en", "eng"},
    "es": {"es", "spa"},
    "et": {"et", "est"},
    "fi": {"fi", "fin"},
    "fr": {"fr", "fre", "fra"},
    "hi": {"hi", "hin"},
    "hu": {"hu", "hun"},
    "id": {"id", "ind"},
    "it": {"it", "ita"},
    "ja": {"ja", "jpn"},
    "ko": {"ko", "kor"},
    "lt": {"lt", "lit"},
    "lv": {"lv", "lav"},
    "ms": {"ms", "may", "msa"},
    "nl": {"nl", "dut", "nld"},
    "no": {"no", "nor"},
    "pl": {"pl", "pol"},
    "pt": {"pt", "por"},
    "ro": {"ro", "rum", "ron"},
    "ru": {"ru", "rus"},
    "sk": {"sk", "slo", "slk"},
    "sv": {"sv", "swe"},
    "th": {"th", "tha"},
    "tr": {"tr", "tur"},
    "uk": {"uk", "ukr"},
    "vi": {"vi", "vie"},
    "zh": {"zh", "chi", "zho"},
}


def is_video(p: Path) -> bool:
    """
    Check if a path points to a supported video file.
    
    Args:
        p: Path to check
        
    Returns:
        True if the file has a supported video extension
    """
    return p.suffix.lower() in VIDEO_EXTS


def is_audio(p: Path) -> bool:
    """
    Check if a path points to a supported audio file.
    
    Args:
        p: Path to check
        
    Returns:
        True if the file has a supported audio extension
    """
    return p.suffix.lower() in AUDIO_EXTS


def is_media(p: Path) -> bool:
    """
    Check if a path points to a supported media file (video or audio).
    
    Args:
        p: Path to check
        
    Returns:
        True if the file has a supported media extension
    """
    return is_video(p) or is_audio(p)


def normalize_language_code(language: Optional[str]) -> Optional[str]:
    """Normalize request/response language codes to lowercase BCP-47 style."""
    if not language:
        return None

    normalized = str(language).strip().lower().replace("_", "-")
    return normalized or None


def get_detected_language(resp) -> Optional[str]:
    """
    Extract Deepgram's detected language code from a response object or dict.

    For prerecorded requests with detect_language enabled, Deepgram returns the
    dominant language at results.channels[*].detected_language.
    """
    if not resp:
        return None

    results = getattr(resp, "results", None)
    if results is None and isinstance(resp, dict):
        results = resp.get("results")

    channels = getattr(results, "channels", None)
    if channels is None and isinstance(results, dict):
        channels = results.get("channels")

    if not channels:
        return None

    for channel in channels:
        detected = getattr(channel, "detected_language", None)
        if detected is None and isinstance(channel, dict):
            detected = channel.get("detected_language")
        normalized = normalize_language_code(detected)
        if normalized:
            return normalized

    return None


def resolve_subtitle_language_tag(
    requested_language: Optional[str] = None,
    *,
    detect_language: bool = False,
    detected_language: Optional[str] = None,
    resp=None,
) -> str:
    """
    Resolve the subtitle filename language suffix.

    Explicit language requests use the requested language. Auto-detect uses
    Deepgram's detected_language field when available. Multilingual and unknown
    languages fall back to the neutral `.und.srt` suffix instead of mislabeling
    the output as English.
    """
    requested = normalize_language_code(requested_language)
    detected = normalize_language_code(detected_language) or get_detected_language(resp)

    if detect_language:
        if detected:
            candidate = detected
        else:
            return NEUTRAL_SUBTITLE_LANG
    else:
        candidate = requested

    if not candidate or candidate == "multi":
        return NEUTRAL_SUBTITLE_LANG

    base = candidate.split("-", 1)[0]
    return _SUBTITLE_LANG_MAP.get(candidate) or _SUBTITLE_LANG_MAP.get(base) or NEUTRAL_SUBTITLE_LANG


def resolve_subtitle_path(
    media_path: Path,
    requested_language: Optional[str] = None,
    *,
    detect_language: bool = False,
    detected_language: Optional[str] = None,
    resp=None,
) -> Path:
    """Build the final sidecar subtitle path for a media file."""
    lang = resolve_subtitle_language_tag(
        requested_language,
        detect_language=detect_language,
        detected_language=detected_language,
        resp=resp,
    )
    return media_path.with_name(f"{media_path.stem}.{lang}.srt")


def resolve_synced_marker_path(
    media_path: Path,
    requested_language: Optional[str] = None,
    *,
    detect_language: bool = False,
    detected_language: Optional[str] = None,
    resp=None,
) -> Path:
    """Build the matching Subsyncarr marker path for a resolved subtitle file."""
    return resolve_subtitle_path(
        media_path,
        requested_language,
        detect_language=detect_language,
        detected_language=detected_language,
        resp=resp,
    ).with_suffix(".synced")


def find_existing_sidecar_subtitle(
    media_path: Path,
    dir_filenames: Optional[set] = None,
) -> Optional[Path]:
    """
    Return an existing same-stem sidecar subtitle path, if any.

    Used by auto-detect preflight checks where the final language-tagged output
    path is not known yet.
    """
    stem = media_path.stem

    if dir_filenames is None:
        dir_filenames = {
            p.name for p in media_path.parent.iterdir()
            if p.is_file()
        }

    for name in sorted(dir_filenames):
        if not name.startswith(stem):
            continue
        remainder = name[len(stem):]
        if remainder.startswith('.') and any(remainder.endswith(ext) for ext in SUBTITLE_EXTS):
            return media_path.with_name(name)

    return None


def _resolve_transcripts_folder_path(video_path: Path) -> Path:
    """Resolve the Transcripts folder path without touching the filesystem."""
    video_parent = video_path.parent
    path_str = str(video_path).lower()
    parent_name_lower = video_parent.name.lower()

    if 'season' in path_str or parent_name_lower.startswith('season') or parent_name_lower == 'specials':
        return video_parent.parent / "Transcripts"

    return video_parent / "Transcripts"


def resolve_transcript_path(video_path: Path) -> Path:
    """Build the transcript path for a media file without creating directories."""
    transcripts_folder = _resolve_transcripts_folder_path(video_path)
    return transcripts_folder / f"{video_path.stem}.transcript.speakers.txt"


def inspect_requested_outputs(
    media_path: Path,
    requested_language: Optional[str] = None,
    *,
    detect_language: bool = False,
    enable_transcript: bool = False,
    force_regenerate: bool = False,
    dir_filenames: Optional[set] = None,
    detected_language: Optional[str] = None,
    resp=None,
) -> dict:
    """
    Inspect which requested outputs already exist for a media file.

    Auto-detect preflight treats any same-stem sidecar subtitle as satisfying
    subtitle output, because the final resolved language tag is not known until
    Deepgram returns.
    """
    transcript_path = resolve_transcript_path(media_path) if enable_transcript else None

    existing_sidecar = None
    if detect_language and not resp and not detected_language:
        existing_sidecar = find_existing_sidecar_subtitle(
            media_path,
            dir_filenames=dir_filenames,
        )

    if existing_sidecar:
        subtitle_path = existing_sidecar
        subtitle_exists = True
    else:
        subtitle_path = resolve_subtitle_path(
            media_path,
            requested_language,
            detect_language=detect_language,
            detected_language=detected_language,
            resp=resp,
        )
        subtitle_exists = subtitle_path.exists()

    transcript_exists = transcript_path.exists() if transcript_path else False
    needs_subtitle = force_regenerate or not subtitle_exists
    needs_transcript = bool(enable_transcript and (force_regenerate or not transcript_exists))

    return {
        "subtitle_path": subtitle_path,
        "subtitle_exists": subtitle_exists,
        "transcript_path": transcript_path,
        "transcript_exists": transcript_exists,
        "needs_subtitle": needs_subtitle,
        "needs_transcript": needs_transcript,
        "should_skip": not needs_subtitle and not needs_transcript,
    }


def get_audio_selection_language(
    requested_language: Optional[str],
    *,
    detect_language: bool = False,
) -> Optional[str]:
    """
    Return the language hint to use for audio-stream selection.

    Auto-detect and multilingual requests should not pre-select a specific
    stream; they need the default stream so language resolution can happen from
    the actual transcription response.
    """
    normalized = normalize_language_code(requested_language)
    if detect_language or not normalized or normalized == "multi":
        return None
    return normalized


def has_sidecar_subtitle(stem: str, dir_filenames: set) -> bool:
    """Check if sidecar subtitle files exist for a given media file stem."""
    return find_existing_sidecar_subtitle(Path(stem), dir_filenames=dir_filenames) is not None


def check_subtitles(media_path: Path, dir_filenames: set = None) -> dict:
    """
    Check if a media file has subtitles (sidecar files or embedded tracks).

    Args:
        media_path: Path to the media file
        dir_filenames: Optional pre-built set of filenames in the same directory.
                       If None, will scan the directory (slower for batch calls).

    Returns:
        dict with 'has_subtitles' (bool) and 'subtitle_source' ("sidecar"|"embedded"|None)
    """
    import subprocess
    stem = media_path.stem

    # Step 1: Check for sidecar subtitle files (instant — in-memory string matching)
    if dir_filenames is None:
        dir_filenames = {p.name for p in media_path.parent.iterdir() if p.is_file()}

    if has_sidecar_subtitle(stem, dir_filenames):
        return {"has_subtitles": True, "subtitle_source": "sidecar"}

    # Step 2: Fallback — ffprobe for embedded subtitle tracks (~50-100ms)
    if is_video(media_path):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-select_streams", "s",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                 str(media_path)],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                return {"has_subtitles": True, "subtitle_source": "embedded"}
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    return {"has_subtitles": False, "subtitle_source": None}


def get_video_duration(video: Path) -> float:
    """
    Get video duration in seconds using ffprobe.
    
    Args:
        video: Path to video file
        
    Returns:
        Duration in seconds, or 0 if unable to determine
    """
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def get_audio_stream_index(video: Path, language: str) -> Optional[int]:
    """
    Find the audio stream index matching a target language using ffprobe.

    Args:
        video: Path to video file
        language: ISO 639-1 language code (e.g., 'en', 'de')

    Returns:
        Absolute stream index for the matching audio track, or None if
        no match found (caller should fall back to default behavior)
    """
    normalized = normalize_language_code(language)
    if not normalized or normalized == "multi":
        return None

    base = normalized.split("-", 1)[0]
    target_codes = set(_STREAM_LANG_MAP.get(base, {base}))
    target_codes.add(normalized)

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index:stream_tags=language",
            "-of", "json",
            str(video)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])

        # Single audio stream — no selection needed
        if len(streams) <= 1:
            return None

        for stream in streams:
            tag = stream.get("tags", {}).get("language", "").lower()
            if tag in target_codes:
                return stream["index"]

        return None
    except Exception:
        return None


def _get_channel_count(video: Path, stream_index: Optional[int] = None) -> int:
    """
    Get the number of audio channels for a stream using ffprobe.

    Args:
        video: Path to video file
        stream_index: Absolute stream index to query. If None, queries the
                      default audio stream.

    Returns:
        Channel count, or 0 on failure
    """
    try:
        cmd = ["ffprobe", "-v", "error"]
        if stream_index is not None:
            cmd += ["-select_streams", str(stream_index)]
        else:
            cmd += ["-select_streams", "a:0"]
        cmd += [
            "-show_entries", "stream=channels",
            "-of", "json",
            str(video)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if streams:
            return int(streams[0].get("channels", 0))
    except Exception:
        pass
    return 0


def extract_audio(video: Path, language: Optional[str] = None) -> Path:
    """
    Extract audio from video file using FFmpeg.

    Args:
        video: Path to source video file
        language: Optional ISO 639-1 language code (e.g., 'en'). When provided,
                  ffprobe is used to find a matching audio stream so the correct
                  track is extracted from multi-language containers.

    Returns:
        Path to temporary MP3 audio file

    Raises:
        subprocess.CalledProcessError: If FFmpeg extraction fails
    """
    tmp = Path(tempfile.mkstemp(suffix=".mp3")[1])

    # Build -map flag if a specific language stream is found
    map_args = []
    stream_idx = None
    if language:
        stream_idx = get_audio_stream_index(video, language)
        if stream_idx is not None:
            map_args = ["-map", f"0:{stream_idx}"]

    # Detect surround sound and extract center channel for better speech recognition
    filter_args = []
    channels = _get_channel_count(video, stream_idx)
    if channels >= 6:
        # 5.1/7.1 surround: extract center channel (FC = dialogue)
        filter_args = ["-af", "pan=mono|c0=FC"]

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(video),
        *map_args,
        *filter_args,
        "-vn", "-acodec", "mp3", "-ar", "16000", "-ac", "1",
        "-y", str(tmp)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
    except subprocess.TimeoutExpired:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(
            f"FFmpeg audio extraction timed out after 1 hour for: {video.name}"
        )
    return tmp


def transcribe_file(buf: bytes, api_key: str, model: str, language: str,
                    profanity_filter: str = "off", diarize: bool = False, keyterms: list = None,
                    numerals: bool = False, filler_words: bool = False,
                    detect_language: bool = False, measurements: bool = False,
                    utterances: bool = True, paragraphs: bool = True,
                    dictation: bool = False, multichannel: bool = False,
                    redact: list = None, replace: list = None,
                    utt_split: float = None, sentiment: bool = False,
                    summarize: bool = False, topics: bool = False,
                    intents: bool = False, detect_entities: bool = False,
                    search: list = None, tag: str = None) -> dict:
    """
    Transcribe audio buffer using Deepgram API.

    Args:
        buf: Audio file contents as bytes
        api_key: Deepgram API key
        model: Model to use (e.g., 'nova-3', 'nova-3-medical')
        language: Language code (e.g., 'en', 'multi')
        profanity_filter: Profanity filter mode - "off", "tag", or "remove"
        diarize: Enable speaker diarization
        keyterms: List of keyterms for better recognition
        numerals: Convert spoken numbers to digits
        filler_words: Include filler words in transcription
        detect_language: Auto-detect language
        measurements: Convert spoken measurements
        utterances: Enable utterance segmentation
        paragraphs: Enable paragraph formatting
        dictation: Convert spoken punctuation to symbols
        multichannel: Process stereo channels separately
        redact: List of redaction types ["pci", "pii", "numbers"]
        replace: List of "wrong:right" replacement strings
        utt_split: Utterance split threshold in seconds
        sentiment: Enable sentiment analysis
        summarize: Enable summarization
        topics: Enable topic detection
        intents: Enable intent detection
        detect_entities: Enable entity detection
        search: List of search terms
        tag: Request label tag

    Returns:
        Deepgram response object

    Raises:
        Exception: If transcription fails
    """
    client = DeepgramClient(api_key=api_key)

    # Convert profanity_filter to boolean for API compatibility
    use_profanity_filter = profanity_filter != "off"

    opts = PrerecordedOptions(
        model=model,
        smart_format=True,
        utterances=utterances,
        punctuate=True,
        paragraphs=paragraphs,
        diarize=diarize,
        language=language,
        profanity_filter=use_profanity_filter
    )

    # Add keyterms if provided (Nova-3 feature, supports all languages)
    if keyterms and "nova-3" in model:
        opts.keyterm = keyterms

    # Quality enhancement parameters
    if numerals:
        opts.numerals = True
    if filler_words:
        opts.filler_words = True
    if detect_language:
        opts.detect_language = True
    if measurements:
        opts.measurements = True
    if dictation:
        opts.dictation = True
    if multichannel:
        opts.multichannel = True

    # Redaction
    if redact:
        opts.redact = redact

    # Find & replace
    if replace:
        opts.replace = replace

    # Utterance split threshold
    if utt_split is not None:
        opts.utt_split = utt_split

    # Audio Intelligence features
    if sentiment:
        opts.sentiment = True
    if summarize:
        opts.summarize = "v2"
    if topics:
        opts.topics = True
    if intents:
        opts.intents = True
    if detect_entities:
        opts.detect_entities = True
    if search:
        opts.search = search

    # Operational
    if tag:
        opts.tag = [tag]

    return client.listen.rest.v("1").transcribe_file({"buffer": buf}, opts)


def write_srt(resp: dict, dest: Path, lang: Optional[str] = None):
    """
    Generate and write SRT subtitle file from Deepgram response.
    
    Args:
        resp: Deepgram transcription response
        dest: Path where SRT file should be written
        lang: Optional language code to force into the filename
        
    Raises:
        Exception: If SRT generation or writing fails
    """
    # Ensure the destination has the proper .lang.srt extension when a suffix
    # is explicitly provided. Otherwise, trust the caller's resolved path.
    if lang and not dest.name.endswith(f".{lang}.srt"):
        dest = dest.parent / f"{dest.stem}.{lang}.srt"

    # Guard against empty transcripts (e.g., music-only or silent files)
    try:
        words = resp.results.channels[0].alternatives[0].words
    except (AttributeError, IndexError):
        words = []

    if not words:
        raise ValueError(
            f"No speech detected in audio — Deepgram returned empty transcript. "
            f"Skipping SRT generation for: {dest.name}"
        )

    srt_content = srt(DeepgramConverter(resp))
    dest.write_text(srt_content, encoding="utf-8")


def get_transcripts_folder(video_path: Path) -> Path:
    """
    Determine the appropriate Transcripts folder for a video file.
    
    Creates folder structure:
    - TV Shows: /media/tv/Show/Transcripts/ (at show level, alongside seasons)
    - TV Specials: /media/tv/Show/Transcripts/ (at show level, alongside specials)
    - Movies: /media/movies/Movie (2024)/Transcripts/
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Path to the Transcripts folder (created if doesn't exist)
    """
    transcripts_folder = _resolve_transcripts_folder_path(video_path)
    path_str = str(video_path).lower()
    parent_name_lower = video_path.parent.name.lower()
    
    # Create folder if it doesn't exist with proper permissions
    transcripts_folder.mkdir(parents=True, exist_ok=True)
    
    # Ensure folder has proper permissions (0o755 = rwxr-xr-x)
    # This prevents permission issues when created by Docker containers
    try:
        transcripts_folder.chmod(0o755)
        # Also set permissions for parent directories if they were just created
        if 'season' in path_str or parent_name_lower.startswith('season') or parent_name_lower == 'specials':
            # For TV shows, also ensure the parent Transcripts folder has proper permissions
            parent = transcripts_folder.parent
            if parent.exists():
                parent.chmod(0o755)
    except (OSError, PermissionError):
        # If we can't set permissions (e.g., running as non-root), that's okay
        pass
    
    return transcripts_folder


def get_json_folder(video_path: Path) -> Path:
    """
    Get the JSON subfolder within the Transcripts folder.
    
    Creates: Transcripts/JSON/
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Path to the JSON folder (created if doesn't exist)
    """
    transcripts_folder = get_transcripts_folder(video_path)
    json_folder = transcripts_folder / "JSON"
    json_folder.mkdir(parents=True, exist_ok=True)
    
    # Ensure proper permissions
    try:
        json_folder.chmod(0o755)
    except (OSError, PermissionError):
        pass
    
    return json_folder


def get_keyterms_folder(video_path: Path) -> Path:
    """
    Get the Keyterms subfolder within the Transcripts folder.
    
    Creates: Transcripts/Keyterms/
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Path to the Keyterms folder (created if doesn't exist)
    """
    transcripts_folder = get_transcripts_folder(video_path)
    keyterms_folder = transcripts_folder / "Keyterms"
    keyterms_folder.mkdir(parents=True, exist_ok=True)
    
    # Ensure proper permissions
    try:
        keyterms_folder.chmod(0o755)
    except (OSError, PermissionError):
        pass
    
    return keyterms_folder


def get_speakermap_folder(video_path: Path) -> Path:
    """
    Get the Speakermap subfolder within the Transcripts folder.
    
    Creates: Transcripts/Speakermap/
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Path to the Speakermap folder (created if doesn't exist)
    """
    transcripts_folder = get_transcripts_folder(video_path)
    speakermap_folder = transcripts_folder / "Speakermap"
    speakermap_folder.mkdir(parents=True, exist_ok=True)
    
    # Ensure proper permissions
    try:
        speakermap_folder.chmod(0o755)
    except (OSError, PermissionError):
        pass
    
    return speakermap_folder


def load_keyterms_from_csv(video_path: Path) -> Optional[List[str]]:
    """
    Load keyterms from CSV file in Transcripts/Keyterms/ folder.
    
    Looks for: Transcripts/Keyterms/{show_or_movie_name}_keyterms.csv
    
    CSV Format (one keyterm per line):
    ```
    Walter White
    Jesse Pinkman
    Heisenberg
    Albuquerque
    ```
    
    Args:
        video_path: Path to the video file
        
    Returns:
        List of keyterms if CSV exists, None otherwise
    """
    try:
        keyterms_folder = get_keyterms_folder(video_path)
        
        # Determine show/movie name from path
        # For TV: /media/tv/Show Name/Season XX/episode.mkv -> "Show Name"
        # For TV Specials: /media/tv/Show Name/Specials/episode.mkv -> "Show Name"
        # For Movies: /media/movies/Movie (2024)/movie.mkv -> "Movie (2024)"
        path_parts = video_path.parts
        
        # Try to find the show/movie name
        show_or_movie_name = None
        for i, part in enumerate(path_parts):
            part_lower = part.lower()
            # Check for season folders or specials folders
            if 'season' in part_lower or part_lower == 'specials':
                # TV show - name is one level up from season/specials
                if i > 0:
                    show_or_movie_name = path_parts[i - 1]
                break
        
        if not show_or_movie_name:
            # Movie - parent directory of video file
            show_or_movie_name = video_path.parent.name
        
        # Look for keyterms CSV
        csv_path = keyterms_folder / f"{show_or_movie_name}_keyterms.csv"
        
        if not csv_path.exists():
            return None
        
        # Read keyterms from CSV
        keyterms = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].strip() and not row[0].strip().startswith('#'):
                    keyterms.append(row[0].strip())
        
        return keyterms if keyterms else None
        
    except Exception as e:
        print(f"Warning: Failed to load keyterms from CSV: {e}")
        return None


def save_keyterms_to_csv(video_path: Path, keyterms: List[str]) -> bool:
    """
    Save keyterms to CSV file in Transcripts/Keyterms/ folder.
    
    Saves to: Transcripts/Keyterms/{show_or_movie_name}_keyterms.csv
    
    Args:
        video_path: Path to the video file
        keyterms: List of keyterms to save
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        keyterms_folder = get_keyterms_folder(video_path)
        
        # Determine show/movie name from path
        path_parts = video_path.parts
        show_or_movie_name = None
        for i, part in enumerate(path_parts):
            part_lower = part.lower()
            # Check for season folders or specials folders
            if 'season' in part_lower or part_lower == 'specials':
                if i > 0:
                    show_or_movie_name = path_parts[i - 1]
                break
        
        if not show_or_movie_name:
            show_or_movie_name = video_path.parent.name
        
        # Save keyterms to CSV
        csv_path = keyterms_folder / f"{show_or_movie_name}_keyterms.csv"
        
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            for keyterm in keyterms:
                if keyterm.strip():
                    writer.writerow([keyterm.strip()])
        
        return True
        
    except Exception as e:
        print(f"Warning: Failed to save keyterms to CSV: {e}")
        return False


def find_speaker_map(video_path: Path) -> Optional[Path]:
    """
    Find speaker map for a video file.

    Looks for: Transcripts/Speakermap/speakers.csv

    Args:
        video_path: Path to the video file

    Returns:
        Path to speakers.csv if found, None otherwise
    """
    try:
        # Check Transcripts/Speakermap/ folder
        speakermap_folder = get_speakermap_folder(video_path)
        local_map = speakermap_folder / "speakers.csv"

        if local_map.exists():
            return local_map

        return None

    except Exception as e:
        print(f"Warning: Failed to find speaker map: {e}")
        return None


def write_transcript(resp: dict, dest: Path, speaker_map_path: Optional[Path] = None):
    """
    Generate and write transcript text file from Deepgram response.
    
    Args:
        resp: Deepgram transcription response with diarization
        dest: Path where transcript file should be written
        speaker_map_path: Optional path to speaker map CSV file
        
    Raises:
        Exception: If transcript generation or writing fails
    """
    # Load speaker map if provided
    speaker_map = {}
    if speaker_map_path and speaker_map_path.exists():
        try:
            with open(speaker_map_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    speaker_map[int(row['speaker_id'])] = row['name']
        except Exception as e:
            print(f"Warning: Failed to load speaker map: {e}")
    
    # Guard against empty transcripts (e.g., music-only or silent files)
    try:
        words = resp.results.channels[0].alternatives[0].words
    except (AttributeError, IndexError):
        words = []

    if not words:
        import logging
        logging.warning(
            "No speech detected — skipping transcript generation for: %s", dest.name
        )
        return

    # Generate transcript with speaker labels
    transcript_lines = []

    try:
        # Access the response data
        result = resp.results.channels[0].alternatives[0]
        
        # Check if diarization was enabled
        if hasattr(result, 'words') and result.words:
            current_speaker = None
            current_text = []
            
            for word in result.words:
                speaker_id = getattr(word, 'speaker', None)
                
                # Handle speaker changes
                if speaker_id != current_speaker:
                    # Save previous speaker's text
                    if current_speaker is not None and current_text:
                        speaker_name = speaker_map.get(current_speaker, f"Speaker {current_speaker}")
                        transcript_lines.append(f"{speaker_name}: {' '.join(current_text)}")
                    
                    # Start new speaker
                    current_speaker = speaker_id
                    current_text = [word.word]
                else:
                    current_text.append(word.word)
            
            # Save last speaker's text
            if current_text:
                speaker_name = speaker_map.get(current_speaker, f"Speaker {current_speaker}")
                transcript_lines.append(f"{speaker_name}: {' '.join(current_text)}")
        else:
            # No diarization, just write the transcript
            transcript_lines.append(result.transcript)
    
    except Exception as e:
        # Fallback to simple transcript
        try:
            result = resp.results.channels[0].alternatives[0]
            transcript_lines.append(result.transcript)
        except Exception:
            raise Exception(f"Failed to generate transcript: {e}")
    
    # Write transcript to file
    dest.write_text('\n\n'.join(transcript_lines), encoding='utf-8')


def write_raw_json(resp: dict, video_path: Path):
    """
    Save raw Deepgram API response as JSON for debugging.
    
    Saves to: Transcripts/JSON/{video_name}.deepgram.json
    
    Args:
        resp: Deepgram transcription response
        video_path: Path to the original video file
        
    Raises:
        Exception: If JSON writing fails
    """
    json_folder = get_json_folder(video_path)
    json_path = json_folder / f"{video_path.stem}.deepgram.json"
    
    try:
        # Convert response to dict if it has to_dict method
        response_data = resp.to_dict() if hasattr(resp, 'to_dict') else resp
        json_path.write_text(json.dumps(response_data, indent=2), encoding='utf-8')
    except Exception as e:
        raise Exception(f"Failed to write raw JSON: {e}")


def get_intelligence_folder(video_path: Path) -> Path:
    """
    Get the Intelligence subfolder within the Transcripts folder.

    Creates: Transcripts/Intelligence/

    Args:
        video_path: Path to the video file

    Returns:
        Path to the Intelligence folder (created if doesn't exist)
    """
    transcripts_folder = get_transcripts_folder(video_path)
    intelligence_folder = transcripts_folder / "Intelligence"
    intelligence_folder.mkdir(parents=True, exist_ok=True)

    try:
        intelligence_folder.chmod(0o755)
    except (OSError, PermissionError):
        pass

    return intelligence_folder


def write_intelligence_summary(resp, video_path: Path):
    """
    Extract and save Audio Intelligence results from a Deepgram response.

    Extracts sentiment, summary, topics, intents, entities, and search results
    from the Deepgram API response and saves to a structured JSON file.

    Saves to: Transcripts/Intelligence/{video_name}.intelligence.json

    Args:
        resp: Deepgram transcription response (with intelligence features enabled)
        video_path: Path to the original video file

    Raises:
        Exception: If writing fails
    """
    intelligence_folder = get_intelligence_folder(video_path)
    output_path = intelligence_folder / f"{video_path.stem}.intelligence.json"

    # Convert response to dict for easier extraction
    data = resp.to_dict() if hasattr(resp, 'to_dict') else resp

    summary = {}
    results = data.get("results", {})

    # Sentiment analysis
    if "sentiments" in results:
        summary["sentiments"] = results["sentiments"]

    # Summarization
    if "summary" in results:
        summary["summary"] = results["summary"]

    # Topic detection
    if "topics" in results:
        summary["topics"] = results["topics"]

    # Intent detection
    if "intents" in results:
        summary["intents"] = results["intents"]

    # Entity detection
    if "entities" in results:
        summary["entities"] = results["entities"]

    # Search results
    channels = results.get("channels", [])
    if channels:
        channel_0 = channels[0] if isinstance(channels, list) else {}
        search_results = channel_0.get("search", [])
        if search_results:
            summary["search"] = search_results

    if not summary:
        print("No intelligence data found in response")
        return

    try:
        output_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(f"Saved intelligence summary to {output_path}")
    except Exception as e:
        raise Exception(f"Failed to write intelligence summary: {e}")
