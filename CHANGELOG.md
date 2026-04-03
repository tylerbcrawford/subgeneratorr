# Changelog

All notable changes to Subgeneratorr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.0] - 2026-04-03

### Added
- **Find All Missing Subtitles** — Library-wide async scan from gear menu with progress tracking, grouped results, and CSV export
- Four new API endpoints: `POST /api/library-scan`, `GET /api/library-scan/status/<task_id>`, `POST /api/library-scan/<task_id>/cancel`, `GET /api/library-scan/export/<task_id>`
- `library_scan_task` Celery task with two-phase scan (fast sidecar check + optional ffprobe embedded check)
- `library_scan_task` routed to a separate `scan` Celery queue, enabling dedicated scan workers in multi-worker deployments; the default single worker consumes both `transcribe,scan` queues (no isolation benefit at `WORKER_CONCURRENCY=1`)
- **Scan results keyword filter** — exclude files by keyword (e.g. "trailer, extras") with persistent filter across sessions
- **Persistent scan results** — library scan data saved to localStorage, survives page reload and browser close
- **Resume scan** — gear menu shows "Resume Scan (N remaining)" when previous scan data exists
- **Chunked batch processing** — large selections auto-split into 25-file chunks with auto-pause between each
- **Batch confirmation dialog** with accurate cost/time estimate before first chunk
- **Auto-pause prompt** between chunks showing cumulative results and remaining cost/time
- `requirements-dev.txt` with `pytest`, `pytest-timeout`, and `flask` for test environments
- `make test` target: creates a `.venv`, installs dev dependencies, runs `pytest tests/ -v`
- `.github/workflows/ci.yml` — push/PR validation workflow: Python 3.11 unit tests + Docker build smoke test for both CLI and web images (runs on every push to every branch)

### Changed
- Moved `check_subtitles()` and `SUBTITLE_EXTS` from `web/app.py` to `core/transcribe.py` for reuse across modules
- Debounced cost estimation to prevent API flooding on rapid file selection
- Polling watchdog scales with batch size instead of fixed 10-minute timeout
- LLM cost estimation uses single-file extrapolation for large batches (prevents request flooding)
- Scan results update in-place after each chunk (completed files marked, counts updated)
- Reduced noisy per-child logging in batch status polling
- Test/docs wording now reflects media-wide input support and language-tagged subtitle outputs

### Fixed
- **Resume scan state for single-batch runs** — files processed in batches of ≤ 25 were not being marked complete in saved scan state; now correctly calls `addCompletedFiles()` to match chunked-batch behavior
- **Language-aware subtitle naming** — CLI and Celery worker no longer hardcode `.eng.srt`; explicit language requests map to the correct media-server tag, auto-detect uses Deepgram's detected language, and `multi` or unmappable cases fall back to `.und.srt`
- **Auto-detect skip + transcript resume logic** — shared output inspection now recognizes existing language-tagged sidecars during CLI and worker preflight, and transcript-enabled worker runs no longer return early `skipped` after a resolved subtitle collision
- **CLI audio discovery parity** — file-list and directory-scan modes now accept supported audio inputs through shared media detection instead of a CLI-only video extension list
- **Browse performance default** — `/api/browse` no longer recursively counts every visible subtree on load; normal navigation now uses direct-child counts and keeps the "folders with media" filter opt-in
- `test_keyterms_consistency.py` import now succeeds without `deepgram` package installed (added dependency stubs matching the pattern in `test_check_subtitles.py`)
- Corrected test path bug in `test_csv_format_consistency` — keyterms CSV was being created inside the Season folder instead of the show-level `Transcripts/Keyterms/` folder where `load_keyterms_from_csv()` looks

### Security
- Re-enabled authentication on all API routes (`_require_auth()` was temporarily disabled during development)
- Added `DISABLE_AUTH` environment variable as an explicit opt-out for local-only deployments without a reverse proxy
- Example Docker Compose binds web port to loopback (`127.0.0.1`) by default to prevent unintended external exposure
- Added security callout to README quick-start documenting safe vs unsafe deployment postures

## [2.0.0] - 2026-02-25

Initial public release.

### Added

- **Core Transcription Engine** — Deepgram Nova-3 speech recognition with SRT subtitle output
- **Nova-3 Full Feature Coverage** — Model selector (General/Medical), redaction (PCI/PII/numbers), find & replace, dictation mode, multichannel processing, utterance split threshold (0.1–5.0s), and request tagging
- **Audio Intelligence** — Sentiment analysis, summarization, topic/intent/entity detection, and term search (English only, saved to Intelligence/ folder)
- **Web UI** — Flask-based interface with dark/light themes, zone-based layout, gear popover for preferences, and collapsible Transcription Settings panel
- **CLI** — Command-line tool for batch processing directories, individual files, or file lists
- **LLM-Enhanced Keyterms** — Optional AI-powered generation of character names and terminology using Claude, GPT, or Gemini to improve transcription accuracy
- **Multi-Language Support** — 50+ languages with regional variants (English, Spanish, French, German, Japanese, Korean, Hindi, and many more)
- **Multilingual Model** — Special `multi` mode processes 10 languages simultaneously with automatic language detection
- **Language-Aware Audio Selection** — Automatically selects the correct audio track in multi-language containers with surround sound center channel extraction
- **Speaker Diarization** — Identify and label speakers in generated transcripts
- **Subtitle Detection** — Sidecar file glob (`.en.srt`, `.ass`, `.vtt`) with ffprobe fallback to identify existing subtitles before processing
- **File Browser** — Navigate media directories with client-side filtering and API-backed global search across the entire library
- **Batch Processing** — Queue multiple files with Celery/Redis, real-time progress tracking, and polling watchdog for reliability
- **Overwrite Protection** — Confirmation dialog before regenerating existing subtitles
- **Cost Tracking** — Real-time per-file and session cost estimates with detailed logging (~$0.0057/min)
- **Smart Skipping** — Automatically skip files that already have subtitles
- **Docker Deployment** — Docker Compose with `MEDIA_PATH` env var, Dockerfile builds, health checks, and resource limits
- **GHCR Docker Images** — Multi-arch (amd64 + arm64) pre-built images via GitHub Actions
- **Media Server Integration** — Output `.eng.srt` files auto-recognized by Plex, Jellyfin, and Emby
- **Sticky Action Bar** — Language selector and transcribe button remain accessible while scrolling
- **iOS Safari Compatibility** — Fixed scroll bounce and viewport issues for mobile access
- **Documentation** — Setup guide, technical reference, language support guide, API docs, contributing guidelines, and community files (CODE_OF_CONDUCT, SECURITY, issue/PR templates)

### Security

- **Path traversal protection** — Input validation on file paths to prevent directory escape
- **Error path hardening** — Removed bare excepts, added timeout guards, and safe handling of empty API responses

[Unreleased]: https://github.com/tylerbcrawford/subgeneratorr/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/tylerbcrawford/subgeneratorr/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/tylerbcrawford/subgeneratorr/releases/tag/v2.0.0
