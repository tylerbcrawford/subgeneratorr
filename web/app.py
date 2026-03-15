#!/usr/bin/env python3
"""
Flask API for Subgeneratorr Web UI.

Provides REST API endpoints for scanning media directories, submitting
transcription jobs, and monitoring progress via Server-Sent Events (SSE).
"""

import os
import io
import csv
import json
import time
from datetime import date
from pathlib import Path
import subprocess
from flask import Flask, request, jsonify, Response, abort, render_template, send_file
from werkzeug.utils import secure_filename
import redis as redis_lib
from tasks import celery_app, make_batch, generate_keyterms_task, library_scan_task
from core.transcribe import (
    is_video, is_media, get_video_duration,
    load_keyterms_from_csv, save_keyterms_to_csv,
    get_keyterms_folder, check_subtitles, SUBTITLE_EXTS
)

MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/media"))
DEFAULT_MODEL = "nova-3"  # Hardcoded to Nova-3
DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "en")
ALLOWED = set([e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()])

def _check_media_path(p: Path) -> bool:
    """Check if a path is safely under MEDIA_ROOT."""
    try:
        return p.resolve().is_relative_to(MEDIA_ROOT.resolve())
    except (ValueError, AttributeError):
        return str(p.resolve()).startswith(str(MEDIA_ROOT.resolve()))


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")


# Redis client for batch metadata (timeout tracking)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
_redis = redis_lib.from_url(REDIS_URL, decode_responses=True)


def _require_auth():
    """
    Require authentication via OAuth proxy headers.
    
    The OAuth proxy (oauth2-proxy) sets the X-Auth-Request-Email header
    when a user successfully authenticates with Google OAuth.
    
    Returns:
        str: Authenticated user's email
        
    Raises:
        401: If no authentication header is present
        403: If user's email is not in the allowlist
    """
    user = request.headers.get("X-Auth-Request-Email") or request.headers.get("X-Forwarded-User")
    if not user:
        abort(401)
    if ALLOWED and user.lower() not in ALLOWED:
        abort(403)
    return user


@app.get("/")
def index():
    """Serve the web UI (optional)."""
    # Temporarily disabled for local testing - uncomment _require_auth() for production
    # _require_auth()
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    """Health check endpoint for container orchestration."""
    return ("ok", 200)


@app.get("/api/config")
def api_config():
    """
    Get current configuration defaults.
    
    Returns default model and language settings plus API key configuration status.
    """
    # _require_auth()
    return jsonify({
        "default_model": DEFAULT_MODEL,
        "default_language": DEFAULT_LANGUAGE,
        "anthropic_api_key_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
        "openai_api_key_configured": bool(os.getenv('OPENAI_API_KEY')),
        "google_api_key_configured": bool(os.getenv('GEMINI_API_KEY'))
    })


@app.get("/api/browse")
def api_browse():
    """
    Browse directories and video files within MEDIA_ROOT.
    
    Query Parameters:
        path: Subdirectory to list (default: MEDIA_ROOT)
        show_all: Include videos with existing subtitles (default: false)
        only_folders_with_videos: Filter out empty folders (default: true)
        
    Returns:
        JSON with list of subdirectories and video files
        
    Security:
        - Path must be under MEDIA_ROOT
    """
    # _require_auth()
    path = request.args.get("path", str(MEDIA_ROOT))
    show_all = request.args.get("show_all", "false").lower() == "true"
    only_folders_with_videos = request.args.get("only_folders_with_videos", "true").lower() == "true"
    path = Path(path).resolve()
    media_root_resolved = MEDIA_ROOT.resolve()
    
    # Security: Ensure path is under MEDIA_ROOT
    try:
        # Use is_relative_to for proper path comparison (Python 3.9+)
        if not path.is_relative_to(media_root_resolved):
            abort(400, "Path must be under MEDIA_ROOT")
    except (ValueError, AttributeError):
        # Fallback for older Python or path comparison issues
        if not str(path).startswith(str(media_root_resolved)):
            abort(400, "Path must be under MEDIA_ROOT")
    
    if not path.exists() or not path.is_dir():
        abort(404, "Directory not found")
    
    directories = []
    files = []

    try:
        # Build sorted directory listing and filename set for subtitle detection
        dir_entries = sorted(path.iterdir(), key=lambda x: x.name.lower())
        dir_filenames = {p.name for p in dir_entries if p.is_file()}

        for item in dir_entries:
            if item.is_dir() and not item.name.startswith('.'):
                # Count media files in this directory (recursive)
                media_count = sum(1 for p in item.rglob("*") if p.is_file() and is_media(p))

                # Apply folder filter if enabled
                if only_folders_with_videos and media_count == 0:
                    continue

                directories.append({
                    "name": item.name,
                    "path": str(item),
                    "video_count": media_count  # Keep name for compatibility, but now includes audio
                })
            elif item.is_file() and is_media(item):
                sub_info = check_subtitles(item, dir_filenames)
                # Only include if showing all OR subtitle doesn't exist
                if show_all or not sub_info["has_subtitles"]:
                    files.append({
                        "name": item.name,
                        "path": str(item),
                        "has_subtitles": sub_info["has_subtitles"],
                        "subtitle_source": sub_info["subtitle_source"],
                    })
    except PermissionError:
        abort(403, "Permission denied")
    
    return jsonify({
        "current_path": str(path),
        "parent_path": str(path.parent) if path != MEDIA_ROOT else None,
        "directories": directories,
        "files": files,
        "file_count": len(files)
    })


@app.get("/api/search")
def api_search():
    """
    Search for directories and files by name, recursively up to 3 levels deep.

    Query Parameters:
        q: Search query (minimum 2 characters)
        path: Root path to search from (default: MEDIA_ROOT)

    Returns:
        JSON with matching directories and files, each including a context path
        showing where the match lives relative to MEDIA_ROOT.
    """
    query = request.args.get("q", "").strip()
    root = request.args.get("path", str(MEDIA_ROOT))

    if len(query) < 2:
        return jsonify({"directories": [], "files": [], "query": query})

    q_lower = query.lower()
    root_path = Path(root).resolve()
    media_root_resolved = MEDIA_ROOT.resolve()

    try:
        if not root_path.is_relative_to(media_root_resolved):
            abort(400, "Path must be under MEDIA_ROOT")
    except (ValueError, AttributeError):
        if not str(root_path).startswith(str(media_root_resolved)):
            abort(400, "Path must be under MEDIA_ROOT")

    matching_dirs = []
    matching_files = []
    MAX_RESULTS = 50
    MAX_DEPTH = 5

    def _walk(path, depth):
        if depth > MAX_DEPTH or len(matching_dirs) + len(matching_files) >= MAX_RESULTS:
            return
        try:
            for item in sorted(path.iterdir(), key=lambda x: x.name.lower()):
                if len(matching_dirs) + len(matching_files) >= MAX_RESULTS:
                    return
                if item.is_dir() and not item.name.startswith('.'):
                    if q_lower in item.name.lower():
                        context = str(item.relative_to(media_root_resolved).parent)
                        matching_dirs.append({
                            "name": item.name,
                            "path": str(item),
                            "video_count": None,
                            "context": context if context != '.' else None,
                        })
                    else:
                        _walk(item, depth + 1)
                elif item.is_file() and is_media(item) and q_lower in item.stem.lower():
                    sub_info = check_subtitles(item)
                    matching_files.append({
                        "name": item.name,
                        "path": str(item),
                        "has_subtitles": sub_info["has_subtitles"],
                        "subtitle_source": sub_info["subtitle_source"],
                    })
        except PermissionError:
            pass

    _walk(root_path, 1)

    return jsonify({
        "query": query,
        "directories": matching_dirs,
        "files": matching_files,
    })


@app.get("/api/scan")
def api_scan():
    """
    Scan a directory for videos.
    
    Query Parameters:
        root: Directory path to scan (default: MEDIA_ROOT)
        show_all: Include videos with existing subtitles (default: false)
        
    Returns:
        JSON with count and list of video files
        
    Security:
        - Path must be under MEDIA_ROOT
        - Limited to 500 results
    """
    # _require_auth()
    root = request.args.get("root", str(MEDIA_ROOT))
    show_all = request.args.get("show_all", "false").lower() == "true"
    root = Path(root).resolve()

    # Security: Ensure path is under MEDIA_ROOT
    if not _check_media_path(root):
        abort(400, "Path must be under MEDIA_ROOT")

    files = []
    for p in root.rglob("*"):
        if p.is_file() and is_media(p):
            if show_all:
                files.append(str(p))
            else:
                sub_info = check_subtitles(p)
                if not sub_info["has_subtitles"]:
                    files.append(str(p))
            if len(files) >= 500:
                break
    
    return jsonify({"count": len(files), "files": files, "show_all": show_all})


@app.post("/api/estimate")
def api_estimate():
    """
    Get cost and time estimates for a batch of videos.
    
    Request Body (JSON):
        files: List of video file paths
        
    Returns:
        JSON with duration metadata and cost estimates
        - Nova-3 pricing: $0.0043 per minute of audio
        - Estimated processing time: ~0.1x real-time (rough estimate)
    """
    # _require_auth()
    body = request.get_json(force=True) or {}
    raw_files = body.get("files", [])
    
    # Updated Nova-3 pricing to match actual API charges
    # Previous estimate was ~25% low (e.g., estimated $0.71 vs actual $0.94)
    NOVA3_PRICE_PER_MINUTE = 0.0057  # Corrected from 0.0043
    NOVA2_PRICE_PER_MINUTE = 0.0043
    PROCESSING_TIME_MULTIPLIER = 0.0109  # Based on real data: ~1.09% of video length (25 jobs, 23.3 hours analyzed)
    
    total_duration = 0.0
    file_durations = []
    
    for f in raw_files:
        p = Path(f)
        # Security: Ensure path is under MEDIA_ROOT
        if not _check_media_path(p):
            continue
        if p.exists():
            duration = get_video_duration(p)
            total_duration += duration
            file_durations.append({
                "file": str(p),
                "duration_seconds": duration,
                "duration_minutes": duration / 60.0
            })
    
    total_minutes = total_duration / 60.0
    estimated_cost = total_minutes * NOVA3_PRICE_PER_MINUTE
    estimated_time = total_duration * PROCESSING_TIME_MULTIPLIER
    
    return jsonify({
        "total_files": len(file_durations),
        "total_duration_seconds": total_duration,
        "total_duration_minutes": total_minutes,
        "estimated_cost_usd": round(estimated_cost, 4),
        "estimated_processing_time_seconds": estimated_time,
        "price_per_minute": NOVA3_PRICE_PER_MINUTE,
        "files": file_durations
    })


@app.post("/api/submit")
def api_submit():
    """
    Submit a batch of videos for transcription.
    
    Request Body (JSON):
        model: Deepgram model to use (default: nova-3)
        language: Language code (default: en)
        profanity_filter: Profanity filter mode - "off", "tag", or "remove" (default: off)
        files: List of video file paths to process
        force_regenerate: Force overwrite existing subtitles (default: false)
        enable_transcript: Generate transcript in addition to subtitles (default: false)
        keyterms: Optional list of key terms for better recognition (Nova-3)
        save_raw_json: Save raw Deepgram API response for debugging (default: false)
        auto_save_keyterms: Automatically save keyterms to CSV (default: false)
        
    Returns:
        JSON with batch_id, count of enqueued files, and submitter email
        
    Security:
        - All file paths must be under MEDIA_ROOT
        - Files must exist before submission
    """
    # user = _require_auth()
    user = "local_user"
    body = request.get_json(force=True) or {}
    
    model = body.get("model", "nova-3")  # Support model selection (nova-3, nova-3-medical)
    language = body.get("language", DEFAULT_LANGUAGE)
    profanity_filter = body.get("profanity_filter", "off")
    raw_files = body.get("files", [])
    force_regenerate = body.get("force_regenerate", False)
    enable_transcript = body.get("enable_transcript", False)
    keyterms = body.get("keyterms")
    save_raw_json = body.get("save_raw_json", False)
    auto_save_keyterms = body.get("auto_save_keyterms", False)

    # Nova-3 Quality Enhancement parameters
    numerals = body.get("numerals", False)
    filler_words = body.get("filler_words", False)
    detect_language = body.get("detect_language", False)
    measurements = body.get("measurements", False)
    dictation = body.get("dictation", False)
    multichannel = body.get("multichannel", False)

    # Redaction & replacement
    redact = body.get("redact")  # list of types: ["pci", "pii", "numbers"]
    replace = body.get("replace")  # list of "wrong:right" strings

    # Advanced Transcript Features
    diarization = body.get("diarization", True)  # Default to True (current behavior)
    utterances = body.get("utterances", True)   # Default to True (current behavior)
    paragraphs = body.get("paragraphs", True)   # Default to True (current behavior)
    utt_split = body.get("utt_split")  # float, only sent when non-default

    # Audio Intelligence features (English only)
    sentiment = body.get("sentiment", False)
    summarize = body.get("summarize", False)
    topics = body.get("topics", False)
    intents = body.get("intents", False)
    detect_entities = body.get("detect_entities", False)
    search = body.get("search")  # list of search terms

    # Operational
    tag = body.get("tag")

    # Handle auto-detect language
    if language == "auto":
        detect_language = True
        language = DEFAULT_LANGUAGE  # Deepgram ignores language when detect_language=true

    # Validate and filter files
    files = []
    for f in raw_files:
        p = Path(f)
        # Security: Ensure path is under MEDIA_ROOT
        if not _check_media_path(p):
            continue
        if p.exists():
            files.append(p)
    
    # Submit batch job with all options
    async_result = make_batch(
        files,
        model,
        language,
        profanity_filter=profanity_filter,
        force_regenerate=force_regenerate,
        enable_transcript=enable_transcript,
        keyterms=keyterms,
        save_raw_json=save_raw_json,
        auto_save_keyterms=auto_save_keyterms,
        numerals=numerals,
        filler_words=filler_words,
        detect_language=detect_language,
        measurements=measurements,
        diarization=diarization,
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
        tag=tag
    )
    
    # Store batch metadata in Redis for timeout tracking
    file_count = len(files)
    timeout_seconds = max(600, file_count * 300)  # 5 min per file, minimum 10 min
    batch_meta = {
        "submitted_at": time.time(),
        "file_count": file_count,
        "timeout_seconds": timeout_seconds
    }
    meta_key = f"batch:{async_result.id}:meta"
    _redis.set(meta_key, json.dumps(batch_meta), ex=timeout_seconds + 3600)  # TTL = timeout + 1hr buffer

    return jsonify({
        "batch_id": async_result.id,
        "enqueued": len(files),
        "by": user
    })


@app.get("/api/job/<rid>")
def api_job(rid):
    """
    Get status of a specific job or batch.

    Parameters:
        rid: Job/batch ID returned from /api/submit

    Returns:
        JSON with job state and result data including detailed child task progress
    """
    # _require_auth()
    from celery.result import GroupResult

    # Try to get as GroupResult first (for batch jobs)
    try:
        group_result = GroupResult.restore(rid, app=celery_app)
    except Exception as e:
        print(f"Failed to restore GroupResult: {e}")
        group_result = None

    # Check for batch timeout
    meta_key = f"batch:{rid}:meta"
    batch_meta_raw = _redis.get(meta_key)
    batch_meta = json.loads(batch_meta_raw) if batch_meta_raw else None
    elapsed_seconds = None
    if batch_meta:
        elapsed_seconds = time.time() - batch_meta["submitted_at"]

    # If it's a group result, handle it specially
    if group_result is not None and hasattr(group_result, 'results') and group_result.results:
        children_info = []
        completed_count = 0
        failed_count = 0
        started_count = 0
        pending_count = 0

        for child in group_result.results:
            try:
                child_info = {
                    'id': child.id,
                    'state': child.state,
                }

                # Get task metadata if available
                if child.state == 'PROGRESS':
                    started_count += 1
                    if child.info:
                        child_info['current_file'] = child.info.get('current_file', '')
                        child_info['stage'] = child.info.get('stage', '')
                elif child.state == 'SUCCESS':
                    completed_count += 1
                    try:
                        result = child.get(propagate=False)
                        if isinstance(result, dict):
                            child_info['filename'] = result.get('filename', '')
                            child_info['status'] = result.get('status', '')
                            child_info['video'] = result.get('video', '')
                    except Exception as e:
                        print(f"Error getting result for {child.id}: {e}")
                elif child.state == 'STARTED':
                    started_count += 1
                elif child.state == 'FAILURE':
                    failed_count += 1
                    try:
                        result = child.get(propagate=False)
                        if isinstance(result, Exception):
                            child_info['error'] = str(result)
                            child_info['status'] = 'error'
                    except Exception as e:
                        print(f"Error getting failure info for {child.id}: {e}")
                elif child.state == 'PENDING':
                    pending_count += 1

                children_info.append(child_info)
            except Exception as child_error:
                print(f"Error processing child task: {child_error}")
                import traceback
                traceback.print_exc()
                continue

        # Determine overall state
        total = len(group_result.results)

        if total == 0:
            state = 'PENDING'
        elif completed_count == total:
            state = 'SUCCESS'
        elif failed_count == total:
            state = 'FAILURE'
        elif started_count > 0 or completed_count > 0:
            state = 'STARTED'
        else:
            state = 'PENDING'

        # Check for timeout on non-terminal states
        if batch_meta and state in ('PENDING', 'STARTED') and elapsed_seconds > batch_meta["timeout_seconds"]:
            state = 'TIMEOUT'
            print(f"Batch {rid} timed out after {elapsed_seconds:.0f}s (limit: {batch_meta['timeout_seconds']}s)")

        print(f"Batch {rid}: {state} ({completed_count}/{total} done, {failed_count} failed)")

        # Build results array for SUCCESS state
        # The frontend expects data.data.results with status='ok'|'skipped'|'error'
        results_data = None
        if state == 'SUCCESS':
            results_data = {
                'results': [
                    {
                        'status': child_info.get('status', 'ok'),
                        'filename': child_info.get('filename', ''),
                        'video': child_info.get('video', '')
                    }
                    for child_info in children_info
                ]
            }

        response_data = {
            "state": state,
            "data": results_data,
            "children": children_info
        }
        if elapsed_seconds is not None:
            response_data["elapsed_seconds"] = round(elapsed_seconds, 1)
        return jsonify(response_data)

    # Fall back to regular AsyncResult handling
    res = celery_app.AsyncResult(rid)
    state = res.state
    data = None
    children_info = []

    try:
        if res.ready():
            data = res.get(propagate=False)

            # Handle ChordError or other exceptions that aren't JSON serializable
            if isinstance(data, Exception):
                data = {"error": str(data), "error_type": type(data).__name__}

        # Get child task information for detailed progress
        if hasattr(res, 'children') and res.children:
            for child in res.children:
                try:
                    child_result = celery_app.AsyncResult(child.id)
                    child_info = {
                        'id': child.id,
                        'state': child_result.state,
                    }

                    # Get task metadata if available
                    if child_result.state == 'PROGRESS' and child_result.info:
                        child_info['current_file'] = child_result.info.get('current_file', '')
                        child_info['stage'] = child_result.info.get('stage', '')
                    elif child_result.ready():
                        result = child_result.get(propagate=False)
                        # Handle exceptions in child results
                        if isinstance(result, Exception):
                            child_info['error'] = str(result)
                            child_info['status'] = 'error'
                        elif isinstance(result, dict):
                            child_info['filename'] = result.get('filename', '')
                            child_info['status'] = result.get('status', '')
                            child_info['video'] = result.get('video', '')

                    children_info.append(child_info)
                except Exception as child_error:
                    # Skip problematic children but continue processing
                    print(f"Error processing child task: {child_error}")
                    continue

    except Exception as e:
        print(f"Error in api_job: {e}")
        data = {"error": str(e), "error_type": type(e).__name__}

    # Check for timeout on non-terminal states (fallback path)
    if batch_meta and state in ('PENDING', 'STARTED') and elapsed_seconds > batch_meta["timeout_seconds"]:
        state = 'TIMEOUT'

    response_data = {
        "state": state,
        "data": data,
        "children": children_info
    }
    if elapsed_seconds is not None:
        response_data["elapsed_seconds"] = round(elapsed_seconds, 1)
    return jsonify(response_data)


@app.post("/api/job/<rid>/cancel")
def api_cancel_job(rid):
    """
    Cancel a running job and all its child tasks.

    Parameters:
        rid: Job/batch ID to cancel

    Returns:
        JSON with cancellation status
    """
    # _require_auth()
    from celery.result import GroupResult
    try:
        revoked_ids = [rid]
        # Revoke the group ID itself
        celery_app.control.revoke(rid, terminate=True, signal='SIGTERM')
        # Also revoke each child task so workers actually stop
        group_result = GroupResult.restore(rid, app=celery_app)
        if group_result and hasattr(group_result, 'results'):
            for child in group_result.results:
                celery_app.control.revoke(child.id, terminate=True, signal='SIGTERM')
                revoked_ids.append(child.id)
        return jsonify({"status": "cancelled", "job_id": rid, "revoked": len(revoked_ids)})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.get("/api/progress")
def api_progress():
    """
    Server-Sent Events (SSE) endpoint for real-time progress updates.
    
    Sends periodic ping events to keep the connection alive.
    Clients can poll /api/job/<batch_id> to get actual job status.
    """
    # _require_auth()
    
    def stream():
        while True:
            yield f"event: ping\ndata: {json.dumps({'t': time.time()})}\n\n"
            time.sleep(2)
    
    return Response(stream(), mimetype="text/event-stream")


@app.post("/api/keyterms/upload")
def api_keyterms_upload():
    """
    Upload keyterms CSV file for a show/movie.
    
    Form Data:
        file: CSV file with one keyterm per line
        video_path: Path to any video file in the show/movie directory
        
    Returns:
        JSON with success status and keyterms count
    """
    # _require_auth()
    
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    video_path = request.form.get('video_path')
    
    if not video_path:
        return jsonify({"error": "No video_path provided"}), 400
    
    vp = Path(video_path)

    # Security: Ensure path is under MEDIA_ROOT
    if not _check_media_path(vp):
        return jsonify({"error": "Invalid path"}), 400

    try:
        # Read keyterms from uploaded file
        content = file.read().decode('utf-8')
        keyterms = [line.strip() for line in content.split('\n') if line.strip() and not line.strip().startswith('#')]
        
        # Save keyterms using the core function
        if save_keyterms_to_csv(vp, keyterms):
            return jsonify({
                "success": True,
                "keyterms_count": len(keyterms),
                "message": f"Uploaded {len(keyterms)} keyterms"
            })
        else:
            return jsonify({"error": "Failed to save keyterms"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/keyterms/save")
def api_keyterms_save():
    """
    Save keyterms to CSV file for a show/movie.

    JSON Body:
        video_path: Path to any video file in the show/movie directory
        keyterms: List of keyterm strings or comma-separated string

    Returns:
        JSON with success status and keyterms count
    """
    # _require_auth()

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    video_path = data.get('video_path')
    keyterms = data.get('keyterms')

    if not video_path:
        return jsonify({"error": "No video_path provided"}), 400

    if not keyterms:
        return jsonify({"error": "No keyterms provided"}), 400

    vp = Path(video_path)

    # Security: Ensure path is under MEDIA_ROOT
    if not _check_media_path(vp):
        return jsonify({"error": "Invalid path"}), 400

    try:
        # Convert keyterms to list if it's a string
        if isinstance(keyterms, str):
            keyterms = [k.strip() for k in keyterms.split(',') if k.strip()]

        # Save keyterms using the core function
        if save_keyterms_to_csv(vp, keyterms):
            return jsonify({
                "success": True,
                "keyterms_count": len(keyterms),
                "message": f"Saved {len(keyterms)} keyterms"
            })
        else:
            return jsonify({"error": "Failed to save keyterms"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/keyterms/load")
def api_keyterms_load():
    """
    Load keyterms for a video from its CSV file.
    
    Query Parameters:
        video_path: Path to any video file in the show/movie directory
        
    Returns:
        JSON with keyterms array or empty array if none found
    """
    # _require_auth()
    
    video_path = request.args.get('video_path')
    
    if not video_path:
        return jsonify({"keyterms": []}), 200
    
    vp = Path(video_path)
    
    # Security: Ensure path is under MEDIA_ROOT
    if not _check_media_path(vp):
        return jsonify({"keyterms": []}), 200

    try:
        # Load keyterms
        keyterms = load_keyterms_from_csv(vp)
        
        return jsonify({
            "keyterms": keyterms if keyterms else [],
            "count": len(keyterms) if keyterms else 0
        })
            
    except Exception as e:
        return jsonify({"keyterms": [], "error": str(e)}), 200


@app.get("/api/keyterms/download")
def api_keyterms_download():
    """
    Download keyterms CSV file for a show/movie.
    
    Query Parameters:
        video_path: Path to any video file in the show/movie directory
        
    Returns:
        CSV file download or 404 if not found
    """
    # _require_auth()
    
    video_path = request.args.get('video_path')
    
    if not video_path:
        return jsonify({"error": "No video_path provided"}), 400
    
    vp = Path(video_path)
    
    # Security: Ensure path is under MEDIA_ROOT
    if not _check_media_path(vp):
        return jsonify({"error": "Invalid path"}), 400

    try:
        # Load keyterms
        keyterms = load_keyterms_from_csv(vp)
        
        if not keyterms:
            return jsonify({"error": "No keyterms found"}), 404
        
        # Get the CSV file path
        keyterms_folder = get_keyterms_folder(vp)
        path_parts = vp.parts
        show_or_movie_name = None
        for i, part in enumerate(path_parts):
            if 'season' in part.lower():
                if i > 0:
                    show_or_movie_name = path_parts[i - 1]
                break
        
        if not show_or_movie_name:
            show_or_movie_name = vp.parent.name
        
        csv_path = keyterms_folder / f"{show_or_movie_name}_keyterms.csv"
        
        if csv_path.exists():
            return send_file(
                csv_path,
                mimetype='text/csv',
                as_attachment=True,
                download_name=f"{show_or_movie_name}_keyterms.csv"
            )
        else:
            return jsonify({"error": "Keyterms file not found"}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/keyterms/generate")
def api_keyterms_generate():
    """
    Generate keyterms using LLM (Anthropic Claude or OpenAI GPT).
    
    Request Body (JSON):
        video_path: Path to video file (required)
        provider: LLM provider - "anthropic" or "openai" (default: "anthropic")
        model: Model name - see LLMModel enum (default: "claude-sonnet-4")
        preserve_existing: Merge with existing keyterms (default: false)
        estimate_only: Only return cost estimate (default: false)
        
    Returns:
        If estimate_only=true:
            JSON with estimated_tokens and estimated_cost
        Otherwise:
            JSON with task_id for async generation
    """
    # _require_auth()
    
    body = request.get_json(force=True) or {}
    video_path = body.get('video_path')
    provider = body.get('provider', 'anthropic')
    model = body.get('model', 'claude-sonnet-4')
    preserve_existing = body.get('preserve_existing', False)
    estimate_only = body.get('estimate_only', False)
    
    # Validate inputs
    if not video_path:
        return jsonify({'error': 'video_path required'}), 400
    
    vp = Path(video_path)
    
    # Security: Ensure path is under MEDIA_ROOT
    if not _check_media_path(vp):
        return jsonify({'error': 'Invalid path'}), 400
    
    # Extract metadata from path
    try:
        from core.media_metadata import extract_media_metadata
        metadata = extract_media_metadata(vp)

        print(f"[DEBUG] Extracted metadata from path: {vp}")
        print(f"[DEBUG] Media type: {metadata.media_type}")
        print(f"[DEBUG] Name: {metadata.name}")
        if metadata.media_type == 'tv':
            print(f"[DEBUG] Season: {metadata.season}, Episode: {metadata.episode}")
            if metadata.episode_title:
                print(f"[DEBUG] Episode title: {metadata.episode_title}")

        if not metadata.name or metadata.name.strip() == '':
            print(f"[ERROR] Empty name extracted from path: {vp}")
            return jsonify({'error': 'Could not extract show/movie name from video path. Please ensure video is in a properly named directory.'}), 400

    except Exception as e:
        print(f"[ERROR] Exception extracting metadata: {str(e)}")
        return jsonify({'error': f'Failed to extract metadata: {str(e)}'}), 400
    
    # Get API key from environment
    if provider == 'anthropic':
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return jsonify({'error': 'ANTHROPIC_API_KEY not configured'}), 500
    elif provider == 'openai':
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            return jsonify({'error': 'OPENAI_API_KEY not configured'}), 500
    elif provider == 'google':
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            return jsonify({'error': 'GEMINI_API_KEY not configured'}), 500
    else:
        return jsonify({'error': f'Unsupported provider: {provider}'}), 400
    
    # If estimate only, return cost estimate
    if estimate_only:
        try:
            from core.keyterm_search import KeytermSearcher, LLMProvider, LLMModel

            print(f"[DEBUG] Estimating cost for: '{metadata.name}'")
            print(f"[DEBUG] Provider: {provider}, Model: {model}")

            # Use bracket notation to access enum by NAME, not by VALUE
            provider_enum = LLMProvider[provider.upper()]
            model_enum_name = model.upper().replace('-', '_').replace('.', '_')
            print(f"[DEBUG] Looking up enum: LLMModel.{model_enum_name}")
            model_enum = LLMModel[model_enum_name]

            print(f"[DEBUG] Initializing KeytermSearcher...")
            searcher = KeytermSearcher(provider_enum, model_enum, api_key)

            print(f"[DEBUG] Calling estimate_cost...")
            estimate = searcher.estimate_cost(metadata)

            print(f"[DEBUG] Cost estimation successful: {estimate}")
            return jsonify(estimate)
        except KeyError as e:
            print(f"[ERROR] KeyError in cost estimation: {str(e)}")
            return jsonify({'error': f'Invalid provider or model: {provider}, {model}'}), 400
        except Exception as e:
            print(f"[ERROR] Exception in cost estimation: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Cost estimation failed: {str(e)}'}), 500
    
    # Queue async generation task
    try:
        task = generate_keyterms_task.delay(
            video_path=video_path,
            provider=provider,
            model=model,
            preserve_existing=preserve_existing
        )
        
        return jsonify({
            'task_id': task.id,
            'status': 'pending'
        })
    except Exception as e:
        return jsonify({'error': f'Failed to queue task: {str(e)}'}), 500


@app.get("/api/keyterms/generate/status/<task_id>")
def api_keyterms_generate_status(task_id):
    """
    Check status of keyterm generation task.
    
    Parameters:
        task_id: Celery task ID from /api/keyterms/generate
        
    Returns:
        JSON with state and result data:
        - PENDING: Task is queued
        - PROGRESS: Task is running (includes stage and progress)
        - SUCCESS: Task completed (includes keyterms, token_count, actual_cost)
        - FAILURE: Task failed (includes error message)
    """
    # _require_auth()
    
    try:
        task = celery_app.AsyncResult(task_id)

        if task.state == 'PENDING':
            return jsonify({'state': 'PENDING'})
        elif task.state == 'PROGRESS':
            # Return progress info
            info = task.info or {}
            return jsonify({
                'state': 'PROGRESS',
                'stage': info.get('stage', '') if isinstance(info, dict) else '',
                'progress': info.get('progress', 0) if isinstance(info, dict) else 0
            })
        elif task.state == 'FAILURE':
            # task.info is the exception instance when state is FAILURE
            error_msg = str(task.info) if task.info else 'Unknown error'
            return jsonify({
                'state': 'FAILURE',
                'error': error_msg
            })
        elif task.state == 'SUCCESS':
            result = task.info or {}
            # Handle case where task returned an error dict instead of raising
            if isinstance(result, dict) and result.get('status') == 'error':
                return jsonify({
                    'state': 'FAILURE',
                    'error': result.get('error', 'Unknown error')
                })
            return jsonify({
                'state': 'SUCCESS',
                **result
            })
        else:
            return jsonify({
                'state': task.state,
                'info': str(task.info) if task.info else None
            })
    except Exception as e:
        # If we can't read the task state at all (e.g., corrupted Redis entry),
        # report it as a failure rather than returning 500 which the frontend
        # might not handle, causing infinite polling.
        return jsonify({
            'state': 'FAILURE',
            'error': f'Task state unreadable: {str(e)}'
        })


@app.post("/api/library-scan")
def api_library_scan():
    """
    Launch a library-wide scan for files missing subtitles.

    Request Body (JSON):
        skip_embedded: Skip ffprobe embedded subtitle check (default: false)

    Returns:
        JSON with task_id and status
    """
    body = request.get_json(force=True) or {}
    skip_embedded = body.get('skip_embedded', False)

    task = library_scan_task.delay(skip_embedded=skip_embedded)

    return jsonify({
        'task_id': task.id,
        'status': 'pending'
    })


@app.get("/api/library-scan/status/<task_id>")
def api_library_scan_status(task_id):
    """
    Check status of a library scan task.

    Parameters:
        task_id: Celery task ID from /api/library-scan

    Returns:
        JSON with state and progress/result data
    """
    try:
        task = celery_app.AsyncResult(task_id)

        if task.state == 'PENDING':
            return jsonify({'state': 'PENDING'})
        elif task.state == 'PROGRESS':
            info = task.info or {}
            return jsonify({
                'state': 'PROGRESS',
                'phase': info.get('phase', '') if isinstance(info, dict) else '',
                'scanned': info.get('scanned', 0) if isinstance(info, dict) else 0,
                'total': info.get('total', 0) if isinstance(info, dict) else 0,
                'missing_so_far': info.get('missing_so_far', 0) if isinstance(info, dict) else 0,
                'progress': round(info.get('scanned', 0) / max(info.get('total', 1), 1) * 100, 1) if isinstance(info, dict) else 0
            })
        elif task.state == 'FAILURE':
            error_msg = str(task.info) if task.info else 'Unknown error'
            return jsonify({
                'state': 'FAILURE',
                'error': error_msg
            })
        elif task.state == 'SUCCESS':
            result = task.info or {}
            return jsonify({
                'state': 'SUCCESS',
                **result
            })
        else:
            return jsonify({
                'state': task.state,
                'info': str(task.info) if task.info else None
            })
    except Exception as e:
        return jsonify({
            'state': 'FAILURE',
            'error': f'Task state unreadable: {str(e)}'
        })


@app.post("/api/library-scan/<task_id>/cancel")
def api_library_scan_cancel(task_id):
    """
    Cancel a running library scan task.

    Parameters:
        task_id: Celery task ID to cancel

    Returns:
        JSON with cancellation status
    """
    try:
        celery_app.control.revoke(task_id, terminate=True, signal='SIGTERM')
        return jsonify({'status': 'cancelled', 'task_id': task_id})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.get("/api/library-scan/export/<task_id>")
def api_library_scan_export(task_id):
    """
    Export library scan results as a CSV file download.

    Parameters:
        task_id: Celery task ID of a completed library scan

    Returns:
        CSV file download with columns: path, name, directory
    """
    try:
        task = celery_app.AsyncResult(task_id)

        if task.state != 'SUCCESS':
            return jsonify({'error': f'Task not complete (state: {task.state})'}), 400

        result = task.info or {}
        missing_files = result.get('missing_files', [])

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['path', 'name', 'directory'])
        for f in missing_files:
            writer.writerow([f.get('path', ''), f.get('name', ''), f.get('directory', '')])

        output = io.BytesIO(buf.getvalue().encode('utf-8'))
        filename = f"missing-subtitles-{date.today().isoformat()}.csv"

        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)