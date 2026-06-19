#!/usr/bin/env python3
"""
Celery tasks for background transcription processing.

Handles asynchronous video transcription jobs using Celery workers.
Supports batched processing with per-file progress tracking.
"""

import json
import logging
import os
import subprocess
import sys
import time

import redis as redis_lib

logger = logging.getLogger(__name__)
from pathlib import Path

from celery import Celery, group

# Add parent directory to path to import core module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.transcribe import (
    extract_audio,
    find_speaker_map,
    get_audio_selection_language,
    get_video_duration,
    has_sidecar_subtitle,
    inspect_requested_outputs,
    is_media,
    is_video,
    load_keyterms_from_csv,
    resolve_synced_marker_path,
    save_keyterms_to_csv,
    transcribe_file,
    write_intelligence_summary,
    write_raw_json,
    write_srt,
    write_transcript,
)

# Configuration from environment
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
_redis = redis_lib.from_url(REDIS_URL, decode_responses=True)
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/media"))
LOG_ROOT = Path(os.environ.get("LOG_ROOT", "/logs"))
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "nova-3")
DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "en")
BAZARR_BASE_URL = os.environ.get("BAZARR_BASE_URL", "")
BAZARR_API_KEY = os.environ.get("BAZARR_API_KEY", "")
DG_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
SAVE_RAW_JSON = os.environ.get("SAVE_RAW_JSON", "0") == "1"

# Initialize Celery app
celery_app = Celery(__name__, broker=REDIS_URL, backend=REDIS_URL)

# Configure task routing
celery_app.conf.task_routes = {
    "transcribe_task": {"queue": "transcribe"},
    "batch_finalize": {"queue": "transcribe"},
    "generate_keyterms_task": {"queue": "transcribe"},
    "translate_subtitles_task": {"queue": "transcribe"},
    "library_scan_task": {"queue": "scan"},
}


def _save_job_log(payload: dict):
    """
    Save job result to JSON log file.

    Args:
        payload: Job result data to log
    """
    try:
        LOG_ROOT.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)
        log_file = LOG_ROOT / f"job_{timestamp}.json"
        log_file.write_text(json.dumps(payload, indent=2))
    except Exception as exc:
        print(f"Warning: Failed to write job log to {LOG_ROOT}: {exc}", file=sys.stderr)


@celery_app.task(bind=True, name="transcribe_task")
def transcribe_task(
    self,
    video_path: str,
    model=DEFAULT_MODEL,
    language=DEFAULT_LANGUAGE,
    profanity_filter="off",
    force_regenerate=False,
    enable_transcript=False,
    keyterms=None,
    save_raw_json=False,
    auto_save_keyterms=False,
    numerals=False,
    filler_words=False,
    detect_language=False,
    measurements=False,
    diarization=True,
    utterances=True,
    paragraphs=True,
    dictation=False,
    multichannel=False,
    redact=None,
    replace=None,
    utt_split=None,
    sentiment=False,
    summarize=False,
    topics=False,
    intents=False,
    detect_entities=False,
    search=None,
    tag=None,
):
    """
    Transcribe a single video file.

    Args:
        video_path: Path to video file
        model: Deepgram model to use (default: nova-3)
        language: Language code (default: en)
        profanity_filter: Profanity filter mode - "off", "tag", or "remove" (default: off)
        force_regenerate: Force overwrite existing subtitles
        enable_transcript: Generate transcript file in addition to subtitles
        keyterms: Optional list of keyterms for better recognition (Nova-3, all languages)
        save_raw_json: Save raw Deepgram API response for debugging (default: false)
        auto_save_keyterms: Automatically save keyterms to CSV in Transcripts/Keyterms/ (default: false)
        numerals: Convert spoken numbers to digits (e.g., "twenty twenty four" → "2024")
        filler_words: Include filler words like "uh", "um" in transcription (default: False)
        detect_language: Auto-detect language for international content
        measurements: Convert spoken measurements (e.g., "fifty meters" → "50m")
        diarization: Enable speaker diarization (default: True)
        utterances: Enable utterance segmentation (default: True)
        paragraphs: Enable paragraph formatting (default: True)
        dictation: Convert spoken punctuation to symbols (default: False)
        multichannel: Process stereo channels separately (default: False)
        redact: List of redaction types ["pci", "pii", "numbers"] (default: None)
        replace: List of "wrong:right" replacement terms (default: None)
        utt_split: Utterance split threshold in seconds (default: None = 0.8)
        sentiment: Enable sentiment analysis (default: False)
        summarize: Enable summarization (default: False)
        topics: Enable topic detection (default: False)
        intents: Enable intent detection (default: False)
        detect_entities: Enable entity detection (default: False)
        search: List of search terms (default: None)
        tag: Request label tag (default: None)

    Returns:
        dict: Status and file paths

    The task will:
    1. Check if SRT already exists (skip if yes unless force_regenerate)
    2. Auto-load keyterms from CSV if available (or use provided keyterms)
    3. Extract audio from video
    4. Transcribe with Deepgram API
    5. Generate and save SRT file
    6. Remove Subsyncarr marker file if present (so Subsyncarr knows to reprocess)
    7. Optionally save keyterms to CSV in Transcripts/Keyterms/
    8. Optionally generate transcript file to Transcripts folder with auto-detected speaker map
    9. Optionally save raw JSON to Transcripts/JSON folder
    10. Log the result
    11. Clean up temporary audio file
    """
    vp = Path(video_path)
    if not DG_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY not set — configure it in .env")
    output_state = inspect_requested_outputs(
        vp,
        language,
        detect_language=detect_language,
        enable_transcript=enable_transcript,
        force_regenerate=force_regenerate,
    )
    srt_out = output_state["subtitle_path"]
    txt_out = output_state["transcript_path"]

    # Start timing
    start_time = time.time()

    # Get video duration for timing analysis
    video_duration = get_video_duration(vp)

    meta = {
        "video": str(vp),
        "srt": str(srt_out),
        "filename": vp.name,
        "video_duration_seconds": video_duration,
        "start_time": start_time,
    }

    if enable_transcript:
        meta["transcript"] = str(txt_out)

    # Update task state to show current file
    self.update_state(state="PROGRESS", meta={"current_file": vp.name, "stage": "checking"})

    if output_state["should_skip"]:
        return {"status": "skipped", **meta}

    # Auto-load keyterms from CSV if no keyterms provided
    if not keyterms:
        csv_keyterms = load_keyterms_from_csv(vp)
        if csv_keyterms:
            keyterms = csv_keyterms
            logger.info("Auto-loaded %d keyterms from CSV", len(keyterms))

    audio_tmp = None
    try:
        # Extract audio
        self.update_state(
            state="PROGRESS", meta={"current_file": vp.name, "stage": "extracting_audio"}
        )
        audio_tmp = extract_audio(
            vp,
            language=get_audio_selection_language(
                language,
                detect_language=detect_language,
            ),
        )

        # Transcribe with optional parameters
        self.update_state(state="PROGRESS", meta={"current_file": vp.name, "stage": "transcribing"})
        with open(audio_tmp, "rb") as f:
            resp = transcribe_file(
                f.read(),
                DG_KEY,
                model,
                language,
                profanity_filter=profanity_filter,
                diarize=diarization,
                keyterms=keyterms,
                numerals=numerals,
                filler_words=filler_words,
                detect_language=detect_language,
                measurements=measurements,
                utterances=utterances,
                paragraphs=paragraphs,
                dictation=dictation,
                multichannel=multichannel,
                redact=redact,
                replace=replace,
                utt_split=utt_split,
                sentiment=sentiment,
                summarize=summarize,
                topics=topics,
                intents=intents,
                detect_entities=detect_entities,
                search=search,
                tag=tag,
            )

        # Generate SRT
        self.update_state(
            state="PROGRESS", meta={"current_file": vp.name, "stage": "generating_srt"}
        )
        post_response_state = inspect_requested_outputs(
            vp,
            language,
            detect_language=detect_language,
            enable_transcript=enable_transcript,
            force_regenerate=force_regenerate,
            resp=resp,
        )
        resolved_srt_out = post_response_state["subtitle_path"]
        resolved_synced_marker = resolve_synced_marker_path(
            vp,
            language,
            detect_language=detect_language,
            resp=resp,
        )
        meta["srt"] = str(resolved_srt_out)

        produced_outputs = []

        if post_response_state["needs_subtitle"]:
            write_srt(resp, resolved_srt_out)
            produced_outputs.append("subtitle")

            # Remove Subsyncarr marker file if it exists so Subsyncarr knows to reprocess
            if resolved_synced_marker.exists():
                resolved_synced_marker.unlink()
                logger.debug("Removed Subsyncarr marker: %s", resolved_synced_marker)
        else:
            logger.debug("Skipping subtitle write for existing file: %s", resolved_srt_out)

        # Save keyterms to CSV if enabled and keyterms were provided
        if auto_save_keyterms and keyterms:
            self.update_state(
                state="PROGRESS", meta={"current_file": vp.name, "stage": "saving_keyterms"}
            )
            try:
                if save_keyterms_to_csv(vp, keyterms):
                    logger.info("Saved %d keyterms to CSV", len(keyterms))
            except Exception as e:
                logger.warning("Failed to save keyterms: %s", e)

        # Generate transcript if requested
        if enable_transcript:
            txt_out = post_response_state["transcript_path"]
            meta["transcript"] = str(txt_out)
            self.update_state(
                state="PROGRESS", meta={"current_file": vp.name, "stage": "generating_transcript"}
            )

            if post_response_state["needs_transcript"]:
                # Auto-detect speaker map from Transcripts/Speakermap/
                speaker_map_path = find_speaker_map(vp)

                if speaker_map_path:
                    logger.debug("Using speaker map: %s", speaker_map_path)

                write_transcript(resp, txt_out, speaker_map_path)
                if txt_out.exists():
                    produced_outputs.append("transcript")
            else:
                logger.debug("Skipping transcript write for existing file: %s", txt_out)

        # Save raw JSON if enabled (either globally or per-request)
        if SAVE_RAW_JSON or save_raw_json:
            self.update_state(
                state="PROGRESS", meta={"current_file": vp.name, "stage": "saving_raw_json"}
            )
            try:
                write_raw_json(resp, vp)
                produced_outputs.append("raw_json")
            except Exception as e:
                logger.warning("Failed to save raw JSON: %s", e)

        # Save intelligence summary if any intelligence features were enabled
        has_intelligence = any([sentiment, summarize, topics, intents, detect_entities, search])
        if has_intelligence:
            self.update_state(
                state="PROGRESS", meta={"current_file": vp.name, "stage": "saving_intelligence"}
            )
            try:
                write_intelligence_summary(resp, vp)
                produced_outputs.append("intelligence")
            except Exception:
                logger.exception("Failed to save intelligence summary for %s", vp.name)

        # Calculate processing time
        end_time = time.time()
        processing_time = end_time - start_time

        # Calculate time multiplier (actual_time / video_duration)
        time_multiplier = processing_time / video_duration if video_duration > 0 else 0

        # Add timing data to meta
        timing_data = {
            "end_time": end_time,
            "processing_time_seconds": processing_time,
            "time_multiplier": time_multiplier,
            "processing_time_formatted": f"{int(processing_time // 60)}:{int(processing_time % 60):02d}",
            "video_duration_formatted": f"{int(video_duration // 60)}:{int(video_duration % 60):02d}",
        }

        status = "ok" if produced_outputs else "skipped"

        # Log success with timing data
        _save_job_log({"status": status, **meta, **timing_data})

        return {"status": status, **meta, **timing_data}

    except Exception as e:
        # Log error
        _save_job_log({"status": "error", "error": str(e), **meta})
        raise

    finally:
        # Clean up temporary audio file
        if audio_tmp and Path(audio_tmp).exists():
            try:
                Path(audio_tmp).unlink()
            except Exception:
                pass


@celery_app.task(name="batch_finalize")
def batch_finalize(results):
    """
    Legacy batch finalizer kept for deferred Bazarr rescan work.

    The current release path uses plain Celery groups for progress tracking,
    so this task is not attached automatically when a batch completes.

    Args:
        results: List of results from transcribe_task

    Returns:
        dict: Batch completion status
    """
    # Trigger Bazarr rescan once per batch (only if configured)
    if BAZARR_BASE_URL and BAZARR_API_KEY:
        import requests

        try:
            response = requests.post(
                f"{BAZARR_BASE_URL}/api/system/tasks/SearchWantedSubtitles",
                headers={"X-API-KEY": BAZARR_API_KEY},
                timeout=10,
            )
            logger.info("Bazarr rescan triggered: %s", response.status_code)
        except Exception as e:
            msg = str(e)
            if BAZARR_API_KEY:
                msg = msg.replace(BAZARR_API_KEY, "***")
            logger.warning("Bazarr rescan failed: %s", msg)

    return {"batch_status": "done", "results": results}


@celery_app.task(bind=True, name="generate_keyterms_task")
def generate_keyterms_task(
    self, video_path: str, provider: str, model: str, preserve_existing: bool = False
):
    """
    Async task to generate keyterms using LLM.

    Args:
        video_path: Path to video file
        provider: LLM provider ("anthropic" or "openai")
        model: Model identifier (e.g., "claude-sonnet-4", "gpt-4")
        preserve_existing: If True, merge with existing; if False, overwrite

    Returns:
        dict: Generated keyterms and metadata

    Updates state with progress:
        - PROGRESS: Initializing, generating, saving
        - SUCCESS: Complete with keyterms
        - FAILURE: Error details
    """
    vp = Path(video_path)

    try:
        # Update: Initializing
        self.update_state(state="PROGRESS", meta={"stage": "initializing", "progress": 0})

        # Get API key from environment
        if provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        elif provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
        elif provider == "google":
            api_key = os.environ.get("GEMINI_API_KEY")
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        if not api_key:
            raise ValueError(f"API key not configured for {provider}")

        # Extract metadata from video path
        from core.media_metadata import extract_media_metadata

        metadata = extract_media_metadata(vp)

        # Load existing keyterms if any
        existing = load_keyterms_from_csv(vp)

        # Update: Generating
        self.update_state(state="PROGRESS", meta={"stage": "generating", "progress": 30})

        # Import here to avoid import errors if dependencies not installed
        from core.keyterm_search import KeytermSearcher, LLMModel, LLMProvider

        # Convert string provider/model to enums using bracket notation (access by NAME)
        try:
            provider_enum = LLMProvider[provider.upper()]
            model_enum = LLMModel[model.upper().replace("-", "_").replace(".", "_")]
        except KeyError:
            raise ValueError(f"Invalid provider or model: {provider}, {model}")

        # Generate keyterms
        searcher = KeytermSearcher(provider=provider_enum, model=model_enum, api_key=api_key)

        result = searcher.generate_from_metadata(
            metadata=metadata, existing_keyterms=existing, preserve_existing=preserve_existing
        )

        # Update: Saving
        self.update_state(state="PROGRESS", meta={"stage": "saving", "progress": 80})

        # Save to CSV
        if save_keyterms_to_csv(vp, result["keyterms"]):
            logger.info("Saved %d LLM-generated keyterms to CSV", len(result["keyterms"]))

        # Return results
        return {
            "keyterms": result["keyterms"],
            "token_count": result["token_count"],
            "actual_cost": result["estimated_cost"],
            "provider": provider,
            "model": model,
            "keyterm_count": len(result["keyterms"]),
        }

    except Exception as e:
        # Convert to a simple RuntimeError before re-raising.
        # Complex exception objects (e.g., Google API errors with nested
        # dicts) cause Celery's Redis backend serialization to fail,
        # which corrupts the task state and makes frontend polling hang forever.
        error_msg = str(e)
        if len(error_msg) > 500:
            error_msg = error_msg[:500] + "..."
        raise RuntimeError(error_msg)


def _normalize_ollama_base_url(host: str) -> str:
    """Coerce a user-supplied Ollama host into an OpenAI-compatible base URL.

    Accepts ``ollama:11434``, ``http://ollama:11434``, or a full ``.../v1`` and
    always returns ``http(s)://host:port/v1``.
    """
    base = host.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = "http://" + base
    if not base.endswith("/v1"):
        base = base + "/v1"
    return base


# Provider -> environment variable holding its API key (cloud providers only).
_TRANSLATE_ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
}


@celery_app.task(bind=True, name="translate_subtitles_task")
def translate_subtitles_task(
    self,
    video_path: str,
    source_srt: str,
    targets: list,
    provider: str,
    model: str,
    overwrite: bool = False,
    ollama_host: str = None,
):
    """
    Async task to translate a source SRT into one or more target languages.

    Args:
        video_path: Path to the video (used only to load its keyterm glossary).
        source_srt: Path to the generated SRT to translate from.
        targets: Target language codes, e.g. ["es", "fr"].
        provider: anthropic/openai/google/ollama.
        model: Model id (cloud) or free-text model name (ollama).
        overwrite: Re-translate even if the target sidecar exists.
        ollama_host: Ollama endpoint (falls back to OLLAMA_HOST env).

    Returns a per-target summary; mirrors generate_keyterms_task's progress and
    error-to-RuntimeError handling (Celery's Redis backend can't serialize rich
    provider exceptions).
    """
    vp = Path(video_path)
    src = Path(source_srt)

    try:
        self.update_state(state="PROGRESS", meta={"stage": "initializing", "progress": 0})

        # Resolve credentials / host.
        api_key = None
        ollama_base_url = None
        if provider == "ollama":
            host = ollama_host or os.environ.get("OLLAMA_HOST")
            if not host:
                raise ValueError("Ollama host not configured")
            ollama_base_url = _normalize_ollama_base_url(host)
        else:
            env_key = _TRANSLATE_ENV_KEYS.get(provider)
            if not env_key:
                raise ValueError(f"Unsupported provider: {provider}")
            api_key = os.environ.get(env_key)
            if not api_key:
                raise ValueError(f"API key not configured for {provider}")

        from core.llm_providers import LLMModel, LLMProvider
        from core.translate import SubtitleTranslator

        provider_enum = LLMProvider[provider.upper()]
        if provider == "ollama":
            model_arg = model  # free-text model name; no enum/pricing
        else:
            try:
                model_arg = LLMModel[model.upper().replace("-", "_").replace(".", "_")]
            except KeyError:
                raise ValueError(f"Invalid model: {model}")

        # Reuse the show's keyterms (if any) as a translation glossary so proper
        # nouns stay consistent with the transcription.
        keyterms = load_keyterms_from_csv(vp)

        translator = SubtitleTranslator(
            provider_enum,
            model_arg,
            api_key,
            ollama_base_url=ollama_base_url,
        )

        results = []
        total_cost = 0.0
        n = len(targets)
        for i, target in enumerate(targets):
            self.update_state(
                state="PROGRESS",
                meta={"stage": f"translating to {target}", "progress": int((i / max(1, n)) * 100)},
            )
            r = translator.translate_file(src, target, keyterms=keyterms, overwrite=overwrite)
            results.append(
                {
                    "target": target,
                    "tag": r.target_tag,
                    "output_path": str(r.output_path) if r.output_path else None,
                    "skipped": bool(r.skipped),
                    "cost": r.cost,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                }
            )
            total_cost += r.cost

        return {
            "results": results,
            "total_cost": total_cost,
            "provider": provider,
            "model": model,
            "target_count": n,
            "translated": sum(1 for r in results if not r["skipped"]),
            "skipped_count": sum(1 for r in results if r["skipped"]),
        }

    except Exception as e:
        error_msg = str(e)
        if len(error_msg) > 500:
            error_msg = error_msg[:500] + "..."
        raise RuntimeError(error_msg)


@celery_app.task(bind=True, name="library_scan_task")
def library_scan_task(self, skip_embedded=False):
    """
    Scan the entire media library for files missing subtitles.

    Args:
        skip_embedded: If True, only check for sidecar subtitle files (faster).
                       If False (default), also probe for embedded subtitle tracks.

    Returns:
        dict with missing_files list, total_scanned, total_missing, scan_time_seconds
    """
    start = time.time()
    cancel_key = f"library_scan_cancel:{self.request.id}"

    # Phase 0: Collect all media files and group by directory
    self.update_state(
        state="PROGRESS",
        meta={"phase": "collecting", "scanned": 0, "total": 0, "missing_so_far": 0},
    )

    all_files = []
    for i, p in enumerate(MEDIA_ROOT.rglob("*"), start=1):
        if i % 100 == 0:
            if _redis.exists(cancel_key):
                _redis.delete(cancel_key)
                return {
                    "missing_files": [],
                    "total_scanned": len(all_files),
                    "total_missing": 0,
                    "scan_time_seconds": round(time.time() - start, 1),
                    "cancelled": True,
                }
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": "collecting",
                    "scanned": len(all_files),
                    "total": 0,
                    "missing_so_far": 0,
                },
            )
        if p.is_file() and is_media(p):
            all_files.append(p)

    if _redis.exists(cancel_key):
        _redis.delete(cancel_key)
        return {
            "missing_files": [],
            "total_scanned": len(all_files),
            "total_missing": 0,
            "scan_time_seconds": round(time.time() - start, 1),
            "cancelled": True,
        }

    total = len(all_files)
    if total == 0:
        return {"missing_files": [], "total_scanned": 0, "total_missing": 0, "scan_time_seconds": 0}

    # Build per-directory filename sets (avoids redundant iterdir() calls)
    dir_filenames = {}
    for f in all_files:
        parent = f.parent
        if parent not in dir_filenames:
            try:
                dir_filenames[parent] = {p.name for p in parent.iterdir() if p.is_file()}
            except (PermissionError, OSError):
                dir_filenames[parent] = set()

    missing = []
    scanned = 0

    # Phase 1: Sidecar scan (fast — string matching only)
    needs_embedded_check = []
    for f in all_files:
        scanned += 1
        if scanned % 100 == 0 and _redis.exists(cancel_key):
            _redis.delete(cancel_key)
            return {
                "missing_files": missing,
                "total_scanned": scanned,
                "total_missing": len(missing),
                "scan_time_seconds": round(time.time() - start, 1),
                "cancelled": True,
            }
        filenames = dir_filenames.get(f.parent, set())
        if has_sidecar_subtitle(f.stem, filenames):
            continue  # Has sidecar subtitles, skip

        if skip_embedded or not is_video(f):
            # No sidecar and we're not checking embedded (or it's audio)
            missing.append({"path": str(f), "name": f.name, "directory": str(f.parent)})
        else:
            needs_embedded_check.append(f)

        if scanned % 100 == 0:
            if _redis.exists(cancel_key):
                _redis.delete(cancel_key)
                return {
                    "missing_files": missing,
                    "total_scanned": scanned,
                    "total_missing": len(missing),
                    "scan_time_seconds": round(time.time() - start, 1),
                    "cancelled": True,
                }
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": "sidecar_scan",
                    "scanned": scanned,
                    "total": total,
                    "missing_so_far": len(missing),
                },
            )

    # Phase 2: Embedded subtitle check via ffprobe (slower)
    if needs_embedded_check:
        for i, f in enumerate(needs_embedded_check):
            embedded_scanned = total - len(needs_embedded_check) + i
            if _redis.exists(cancel_key):
                _redis.delete(cancel_key)
                return {
                    "missing_files": missing,
                    "total_scanned": embedded_scanned,
                    "total_missing": len(missing),
                    "scan_time_seconds": round(time.time() - start, 1),
                    "cancelled": True,
                }
            has_embedded = False
            try:
                result = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "quiet",
                        "-select_streams",
                        "s",
                        "-show_entries",
                        "stream=codec_type",
                        "-of",
                        "csv=p=0",
                        str(f),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.stdout.strip():
                    has_embedded = True
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

            if not has_embedded:
                missing.append({"path": str(f), "name": f.name, "directory": str(f.parent)})

            if (i + 1) % 50 == 0:
                if _redis.exists(cancel_key):
                    _redis.delete(cancel_key)
                    embedded_scanned = total - len(needs_embedded_check) + i + 1
                    return {
                        "missing_files": missing,
                        "total_scanned": embedded_scanned,
                        "total_missing": len(missing),
                        "scan_time_seconds": round(time.time() - start, 1),
                        "cancelled": True,
                    }
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "phase": "embedded_scan",
                        "scanned": total - len(needs_embedded_check) + i + 1,
                        "total": total,
                        "missing_so_far": len(missing),
                    },
                )

    elapsed = round(time.time() - start, 1)
    return {
        "missing_files": missing,
        "total_scanned": total,
        "total_missing": len(missing),
        "scan_time_seconds": elapsed,
    }


def make_batch(
    files,
    model,
    language,
    profanity_filter="off",
    force_regenerate=False,
    enable_transcript=False,
    keyterms=None,
    save_raw_json=False,
    auto_save_keyterms=False,
    numerals=False,
    filler_words=False,
    detect_language=False,
    measurements=False,
    diarization=True,
    utterances=True,
    paragraphs=True,
    dictation=False,
    multichannel=False,
    redact=None,
    replace=None,
    utt_split=None,
    sentiment=False,
    summarize=False,
    topics=False,
    intents=False,
    detect_entities=False,
    search=None,
    tag=None,
):
    """
    Create a batch of transcription jobs.

    Uses Celery's group to run jobs in parallel with progress tracking.

    Args:
        files: List of Path objects for videos to transcribe
        model: Deepgram model to use
        language: Language code
        profanity_filter: Profanity filter mode - "off", "tag", or "remove"
        force_regenerate: Force overwrite existing subtitles
        enable_transcript: Generate transcript files in addition to subtitles
        keyterms: Optional list of keyterms for better recognition
        save_raw_json: Save raw Deepgram API response for debugging
        auto_save_keyterms: Automatically save keyterms to CSV
        numerals: Convert spoken numbers to digits
        filler_words: Include filler words in transcription
        detect_language: Auto-detect language
        measurements: Convert spoken measurements
        diarization: Enable speaker diarization
        utterances: Enable utterance segmentation
        paragraphs: Enable paragraph formatting
        dictation: Convert spoken punctuation to symbols
        multichannel: Process stereo channels separately
        redact: List of redaction types
        replace: List of replacement terms
        utt_split: Utterance split threshold
        sentiment: Enable sentiment analysis
        summarize: Enable summarization
        topics: Enable topic detection
        intents: Enable intent detection
        detect_entities: Enable entity detection
        search: List of search terms
        tag: Request label tag

    Returns:
        AsyncResult: Celery async result for tracking batch progress
    """
    jobs = [
        transcribe_task.s(
            str(f),
            model,
            language,
            profanity_filter,
            force_regenerate,
            enable_transcript,
            keyterms,
            save_raw_json,
            auto_save_keyterms,
            numerals,
            filler_words,
            detect_language,
            measurements,
            diarization,
            utterances,
            paragraphs,
            dictation,
            multichannel,
            redact,
            replace,
            utt_split,
            sentiment,
            summarize,
            topics,
            intents,
            detect_entities,
            search,
            tag,
        )
        for f in files
    ]
    # Use group() instead of chord to allow progress tracking
    # GroupResult allows the API to query individual task states
    job_group = group(jobs)
    result = job_group.apply_async()

    # Save the GroupResult so it can be restored later
    result.save()

    return result
