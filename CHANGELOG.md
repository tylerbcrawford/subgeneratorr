# Changelog

All notable changes to Subgeneratorr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Local transcription engine (Whisper).** An opt-in `-local` Docker image bundles [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CPU, int8) with the `small` model baked in, so the whole pipeline — transcription, keyterms, and translation (via Ollama) — can run offline with nothing leaving your machine and no per-minute cost. Deepgram Nova-3 remains the default engine and its output is byte-for-byte unchanged. Select the engine per job in the Web UI (or set `ASR_ENGINE=whisper`); `DEEPGRAM_API_KEY` is no longer required when running local-only. Includes a native SRT writer with readability-focused cue segmentation (max 2×42-char lines, ≤7 s cues, splits at sentence ends and silence gaps), VAD + anti-hallucination settings tuned for movie/TV audio, per-segment progress reporting, a model picker with RAM/speed guidance, and `examples/docker-compose.local.example.yml` for a fully-local stack. Web UI options the local engine can't support (audio intelligence, redaction, diarization, and so on) hide automatically via the new `/api/capabilities` endpoint; keyterms map to whisper hotwords (best-effort, capped). The CLI honors `ASR_ENGINE=whisper` for subtitle generation via the new `subgeneratorr-cli-local` image (or `pip install faster-whisper` on the lean one).

### Fixed
- The Web UI now reflects the server's engine configuration: `/api/capabilities` reports whether each engine is actually installed, the UI preselects `ASR_ENGINE` and disables engines the running image can't execute (the lean image previously offered a Local engine that failed every job with a `ModuleNotFoundError`), and the whisper model picker follows `WHISPER_MODEL` instead of silently overriding it with `small`.
- `/api/submit` rejects whisper jobs when faster-whisper is not installed, and the worker fails fast before audio extraction instead of dying mid-batch on a lazy import; the CLI performs the same check at startup.
- Batch timeouts are engine-aware: local whisper jobs (near-realtime) get a 4-hour-per-file budget instead of being falsely flipped to TIMEOUT after 10 minutes while still transcribing.
- Deepgram-only options (audio intelligence, raw JSON dumps) restored from saved preferences are dropped from whisper submissions instead of being silently ignored, and the worker logs a warning if such a request still arrives; the CLI logs when `SAVE_RAW_JSON=1` has nothing to save locally.
- The whisper model cache evicts the previous model before loading a new one — switching small → medium → large-v3 across jobs no longer accumulates ~5 GB and OOM-kills a memory-capped worker.
- Switching engines refreshes the cost estimate immediately (a broken function reference kept showing Deepgram pricing for $0 local runs until the file selection changed), and `/api/estimate` validates the `engine` value like `/api/submit` does.
- The `-local` images bake model-cache ownership at build time and the entrypoints only chown mismatched files, so recreating a container no longer copies the ~500 MB baked model into the writable layer on every start.

## [2.4.0] - 2026-06-26

### Added
- LLM-powered subtitle translation. Translate a generated SRT into one or more target languages and write language-tagged sidecars (`.spa.srt`, `.fre.srt`, and so on) that Plex, Jellyfin, and Emby auto-detect. Timing is copied from the source verbatim so translations stay in sync, and the show's keyterms are passed to the model as a glossary. Available in the web UI Translate panel via `POST /api/translate`.
- 49 target languages for translation, written with the same media-server language tags used for transcription output.
- Ollama as a fourth LLM provider for keyterm generation and translation. Set `OLLAMA_HOST` to a local Ollama server (OpenAI-compatible endpoint) to translate fully offline at no cost; the cost estimate reports $0.00. The cloud providers (Anthropic, OpenAI, Google) are unchanged.
- Gujarati (`gu`) and Thai (`th`) in the transcription language dropdown. Gujarati is a
  Nova-3 language that was not previously offered; Thai was already supported by the
  backend but was missing from the menu.

### Changed
- Refreshed the web UI: Keyterms, Transcription Settings, and Translate are now collapsible sections (click-to-open, collapsed by default) so the page stays focused on the primary transcribe flow — a big improvement on mobile. Each section's open/closed state and the light/dark theme are remembered across reloads. The Translate panel is also a self-contained card that surfaces its cost estimate up front (instead of hiding it behind the settings gear) and shows provider status as the same colored dot used elsewhere. ("Translate Subtitles" shortened to "Translate".)
- Profanity filter is now a single on/off toggle. The previous Off/Tag/Remove options all
  produced the same request because Deepgram's `profanity_filter` is boolean (it masks
  with asterisks), so Tag and Remove behaved identically. Saved Tag/Remove preferences are
  treated as on.
- Numerals formatting now also applies in Multi-language mode, following Deepgram's
  expansion of numerals to the Nova-3 multilingual languages (Subgeneratorr already sent
  `numerals` regardless of language; the control's tooltip now notes this).
- No change was required for Deepgram's May 2026 `nova-3-medical` batch model upgrade
  (improved medical-term recognition, ~97.20% KRR): Subgeneratorr already uses
  `model=nova-3-medical`, so existing medical jobs benefit automatically.

### Fixed
- Sixteen languages that transcribe correctly but were tagged with the neutral `.und.srt`
  suffix now produce proper ISO 639-2/B sidecars (for example `.tam.srt`, `.ben.srt`,
  `.srp.srt`) so Plex, Jellyfin, and Emby can identify them: Belarusian (`be`→`bel`),
  Bengali (`bn`→`ben`), Bosnian (`bs`→`bos`), Croatian (`hr`→`hrv`), Gujarati (`gu`→`guj`),
  Hebrew (`he`→`heb`), Kannada (`kn`→`kan`), Macedonian (`mk`→`mac`), Marathi (`mr`→`mar`),
  Persian (`fa`→`per`), Serbian (`sr`→`srp`), Slovenian (`sl`→`slv`), Tagalog (`tl`→`tgl`),
  Tamil (`ta`→`tam`), Telugu (`te`→`tel`), and Urdu (`ur`→`urd`). The same mapping gap had
  blocked these as translation targets (HTTP 400 "Unsupported target language(s)").
- Translation no longer drops cues when the model returns blank or empty output for a line;
  the source text is kept so the translated SRT always has the same cue count and timing as
  its source.
- The Celery worker now has its own Docker healthcheck (`celery inspect ping`) so an
  unhealthy worker surfaces in `docker compose ps` and orchestration instead of failing
  silently.

## [2.3.0] - 2026-06-19

### Added
- Chinese language options in the web UI: Mandarin Simplified (`zh`), Mandarin Traditional (`zh-Hant`), and Cantonese (`zh-HK`). Available on the `nova-3` model (not `nova-3-medical`, which stays English-only).
- PHI (medical) and aggressive-numbers redaction options in the web UI. PHI works best with the `nova-3-medical` model.

### Changed
- Diarized batch jobs now use Deepgram's v2 speaker diarization model (`diarize_model=v2`) for improved multi-speaker accuracy. Sent via the SDK addons parameter because the installed `deepgram-sdk` 3.x does not serialize `diarize_model` on `PrerecordedOptions`.

### Fixed
- Mobile accessibility: re-enabled pinch-zoom (removed `user-scalable=no` from the viewport) and kept text-entry fields at 16px so iOS Safari no longer auto-zooms on focus.
- Mobile touch targets: raised the settings gear, AI-config toggle, language selector, and advanced-settings toggle to the 44px minimum tap size.
- Windows: `web` and `worker` containers no longer restart-loop with `exec /entrypoint.sh: no such file or directory`. Pinned `*.sh` and the Dockerfiles to LF via `.gitattributes` and strip CRLF at build time so existing Windows clones build without re-cloning. (#1)

## [2.2.0] - 2026-06-14

### Added
- Web UI screenshots and workflow GIF in README (launch gate visuals)
- Ruff linting and formatting in CI (`make lint` / `make fmt`; `ruff check` + `ruff format --check` gate on every push)
- Trivy vulnerability scan in the publish workflow (report-only: surfaces fixable HIGH/CRITICAL CVEs in the build log, non-blocking)
- OCI image labels (`org.opencontainers.image.source`, `.description`, `.licenses`, `.version`) on both `web/Dockerfile` and `cli/Dockerfile`
- Docker `HEALTHCHECK` on `web/Dockerfile` using `wget` against `http://127.0.0.1:5000/healthz` (matches compose healthcheck convention)
- Provider key status in `/api/config` response (Anthropic, OpenAI, Gemini key presence)
- First-run and provider status UI in the web UI settings panel
- Loading spinners on long-running actions in the web UI
- Minimal `pyproject.toml` with build metadata and ruff tool configuration

### Changed
- Documentation cleanup pass: tone, readability, and accuracy improvements across README and technical docs
- Accessibility improvements: aria-labels and focus styles added to interactive elements
- Inline event handlers moved to `addEventListener` calls throughout the frontend

### Fixed
- Keyterm-generation null-reference console error when provider list was empty
- Silent permission errors now logged (previously swallowed without user feedback)

### Security
- `SECRET_KEY` no longer falls back to a hardcoded value; generates a random per-process default when not set
- Bazarr API key redacted from error logs
- Dependency upper bounds added to prevent silent breakage from upstream major bumps

## [2.1.1] - 2026-04-05

### Fixed
- **Web default model handling**: `DEFAULT_MODEL` now flows through the Flask config endpoint, request fallback path, and browser UI defaults so `nova-3-medical` and other configured defaults are honored in real deployments
- **Linux/NAS runtime permissions for the web stack**: the web and worker containers now respect `PUID` and `PGID` at startup so generated subtitles, transcripts, and keyterms can be written with the expected host ownership
- **Contributor setup path**: `CONTRIBUTING.md` now includes the required `docker-compose.yml` bootstrap step before `docker compose build`

### Changed
- Clarified reverse-proxy auth requirements in the README and technical docs: when `DISABLE_AUTH=false`, upstream auth must forward either `X-Auth-Request-Email` or `X-Forwarded-User`
- Expanded deployment docs and example environment guidance for shared `PUID`/`PGID` configuration across CLI, web, and worker services
- Added regression coverage for runtime `DEFAULT_MODEL` behavior in the API test suite

## [2.1.0] - 2026-04-03

### Added
- **Find All Missing Subtitles**: Library-wide async scan from gear menu with progress tracking, grouped results, and CSV export
- Four new API endpoints: `POST /api/library-scan`, `GET /api/library-scan/status/<task_id>`, `POST /api/library-scan/<task_id>/cancel`, `GET /api/library-scan/export/<task_id>`
- `library_scan_task` Celery task with two-phase scan (fast sidecar check + optional ffprobe embedded check)
- `library_scan_task` routed to a separate `scan` Celery queue, enabling dedicated scan workers in multi-worker deployments; the default single worker consumes both `transcribe,scan` queues (no isolation benefit at `WORKER_CONCURRENCY=1`)
- **Scan results keyword filter**: exclude files by keyword (e.g. "trailer, extras") with persistent filter across sessions
- **Persistent scan results**: library scan data saved to localStorage, survives page reload and browser close
- **Resume scan**: gear menu shows "Resume Scan (N remaining)" when previous scan data exists
- **Chunked batch processing**: large selections auto-split into 25-file chunks with auto-pause between each
- **Batch confirmation dialog** with accurate cost/time estimate before first chunk
- **Auto-pause prompt** between chunks showing cumulative results and remaining cost/time
- `requirements-dev.txt` with `pytest`, `pytest-timeout`, and `flask` for test environments
- `make test` target: creates a `.venv`, installs dev dependencies, runs `pytest tests/ -v`
- `.github/workflows/ci.yml`: push/PR validation workflow: Python 3.11 unit tests + Docker build smoke test for both CLI and web images (runs on every push to every branch)

### Changed
- Moved `check_subtitles()` and `SUBTITLE_EXTS` from `web/app.py` to `core/transcribe.py` for reuse across modules
- Debounced cost estimation to prevent API flooding on rapid file selection
- Polling watchdog scales with batch size instead of fixed 10-minute timeout
- LLM cost estimation uses single-file extrapolation for large batches (prevents request flooding)
- Scan results update in-place after each chunk (completed files marked, counts updated)
- Reduced noisy per-child logging in batch status polling
- Test/docs wording now reflects media-wide input support and language-tagged subtitle outputs

### Fixed
- **Resume scan state for single-batch runs**: files processed in batches of ≤ 25 were not being marked complete in saved scan state; now correctly calls `addCompletedFiles()` to match chunked-batch behavior
- **Language-aware subtitle naming**: CLI and Celery worker no longer hardcode `.eng.srt`; explicit language requests map to the correct media-server tag, auto-detect uses Deepgram's detected language, and `multi` or unmappable cases fall back to `.und.srt`
- **Auto-detect skip + transcript resume logic**: shared output inspection now recognizes existing language-tagged sidecars during CLI and worker preflight, and transcript-enabled worker runs no longer return early `skipped` after a resolved subtitle collision
- **CLI audio discovery parity**: file-list and directory-scan modes now accept supported audio inputs through shared media detection instead of a CLI-only video extension list
- **Browse performance default**: `/api/browse` no longer recursively counts every visible subtree on load; normal navigation now uses direct-child counts and keeps the "folders with media" filter opt-in
- `test_keyterms_consistency.py` import now succeeds without `deepgram` package installed (added dependency stubs matching the pattern in `test_check_subtitles.py`)
- Corrected test path bug in `test_csv_format_consistency`: keyterms CSV was being created inside the Season folder instead of the show-level `Transcripts/Keyterms/` folder where `load_keyterms_from_csv()` looks

### Security
- Re-enabled authentication on all API routes (`_require_auth()` was temporarily disabled during development)
- Added `DISABLE_AUTH` environment variable as an explicit opt-out for local-only deployments without a reverse proxy
- Example Docker Compose binds web port to loopback (`127.0.0.1`) by default to prevent unintended external exposure
- Added security callout to README quick-start documenting safe vs unsafe deployment postures

## [2.0.0] - 2026-02-25

Initial public release.

### Added

- **Core Transcription Engine**: Deepgram Nova-3 speech recognition with SRT subtitle output
- **Nova-3 Full Feature Coverage**: Model selector (General/Medical), redaction (PCI/PII/numbers), find & replace, dictation mode, multichannel processing, utterance split threshold (0.1–5.0s), and request tagging
- **Audio Intelligence**: Sentiment analysis, summarization, topic/intent/entity detection, and term search (English only, saved to Intelligence/ folder)
- **Web UI**: Flask-based interface with dark/light themes, zone-based layout, gear popover for preferences, and collapsible Transcription Settings panel
- **CLI**: Command-line tool for batch processing directories, individual files, or file lists
- **LLM-Enhanced Keyterms**: Optional AI-powered generation of character names and terminology using Claude, GPT, or Gemini to improve transcription accuracy
- **Multi-Language Support**: 50+ languages with regional variants (English, Spanish, French, German, Japanese, Korean, Hindi, and many more)
- **Multilingual Model**: Special `multi` mode processes 10 languages simultaneously with automatic language detection
- **Language-Aware Audio Selection**: Automatically selects the correct audio track in multi-language containers with surround sound center channel extraction
- **Speaker Diarization**: Identify and label speakers in generated transcripts
- **Subtitle Detection**: Sidecar file glob (`.en.srt`, `.ass`, `.vtt`) with ffprobe fallback to identify existing subtitles before processing
- **File Browser**: Navigate media directories with client-side filtering and API-backed global search across the entire library
- **Batch Processing**: Queue multiple files with Celery/Redis, real-time progress tracking, and polling watchdog for reliability
- **Overwrite Protection**: Confirmation dialog before regenerating existing subtitles
- **Cost Tracking**: Real-time per-file and session cost estimates with detailed logging (~$0.0057/min)
- **Smart Skipping**: Automatically skip files that already have subtitles
- **Docker Deployment**: Docker Compose with `MEDIA_PATH` env var, Dockerfile builds, health checks, and resource limits
- **GHCR Docker Images**: Multi-arch (amd64 + arm64) pre-built images via GitHub Actions
- **Media Server Integration**: Output `.eng.srt` files auto-recognized by Plex, Jellyfin, and Emby
- **Sticky Action Bar**: Language selector and transcribe button remain accessible while scrolling
- **iOS Safari Compatibility**: Fixed scroll bounce and viewport issues for mobile access
- **Documentation**: Setup guide, technical reference, language support guide, API docs, contributing guidelines, and community files (CODE_OF_CONDUCT, SECURITY, issue/PR templates)

### Security

- **Path traversal protection**: Input validation on file paths to prevent directory escape
- **Error path hardening**: Removed bare excepts, added timeout guards, and safe handling of empty API responses

[Unreleased]: https://github.com/tylerbcrawford/subgeneratorr/compare/v2.4.0...HEAD
[2.4.0]: https://github.com/tylerbcrawford/subgeneratorr/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/tylerbcrawford/subgeneratorr/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/tylerbcrawford/subgeneratorr/compare/v2.1.1...v2.2.0
[2.1.1]: https://github.com/tylerbcrawford/subgeneratorr/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/tylerbcrawford/subgeneratorr/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/tylerbcrawford/subgeneratorr/releases/tag/v2.0.0
