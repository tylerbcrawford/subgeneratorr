# Technical Documentation

This document contains detailed technical information about Subgeneratorr's architecture, implementation, and advanced configuration options.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [ASR Engines (Cloud and Local)](#asr-engines-cloud-and-local)
- [File Structure](#file-structure)
- [Subtitle File Naming](#subtitle-file-naming)
- [Directory Structure](#directory-structure)
- [Language Support](#language-support)
- [Detailed Configuration](#detailed-configuration)
- [Platform-Specific Details](#platform-specific-details)
- [API Endpoints](#api-endpoints)
- [Advanced Usage](#advanced-usage)
- [Keyterm Prompting Deep Dive](#keyterm-prompting-deep-dive)
- [Speaker Maps Technical Details](#speaker-maps-technical-details)
- [Utilities and Scripts](#utilities-and-scripts)

---

## Architecture Overview

### CLI Architecture

The CLI tool is a standalone Python application that:
- Scans directories for media files
- Extracts audio using FFmpeg
- Calls Deepgram API for transcription
- Generates SRT subtitle files and optional speaker-labeled transcripts
- Manages keyterms and speaker maps via CSV files

**Key Components:**
- `cli/generate_subtitles.py` - Main entry point
- `cli/config.py` - Configuration management
- `cli/transcript_generator.py` - Transcript generation with speaker mapping
- `core/transcribe.py` - Shared transcription logic
- `core/asr_engine.py` - Pluggable ASR engine interface (Deepgram Nova-3 cloud, faster-whisper local)
- `core/srt_writer.py` - Native SRT writer with readability-focused cue segmentation

### Web UI Architecture

The Web UI adds asynchronous processing capabilities:

**Components:**
- **Flask API** (`web/app.py`) - REST endpoints for job submission and monitoring
- **Celery Workers** (`web/tasks.py`) - Background task processing
- **Redis** - Message broker and result backend
- **Shared Core** (`core/transcribe.py`, `core/asr_engine.py`) - Same transcription logic and engine registry as CLI
- **Language catalog** (`core/languages.py`, `core/model_languages.py`) - One list of every language with per-engine and translation flags, plus the per-model translation support table. The Web UI renders its dropdowns from it instead of hardcoded lists
- **Settings store** (`core/settings_store.py`) - Saves the Customize languages choices as JSON at `SETTINGS_PATH`

**Workflow:**
1. User submits batch via Web UI
2. Flask API creates Celery task group
3. Workers process files in parallel (configurable concurrency)
4. Progress updates sent via Server-Sent Events (SSE)
5. Results returned to the UI

---

## ASR Engines (Cloud and Local)

Since v3.0.0, transcription goes through a pluggable engine interface in `core/asr_engine.py`. Two engines ship today:

| Engine | `name` | Runs where | Ships in |
|--------|--------|------------|----------|
| `DeepgramEngine` | `deepgram` | Deepgram cloud (Nova-3) | every image (default) |
| `WhisperEngine` | `whisper` | your CPU via [faster-whisper](https://github.com/SYSTRAN/faster-whisper), int8 | `-local` images only |

### Engine interface

Every engine subclasses `ASREngine` and implements three things:

- **`capabilities()`** — the set of feature flags the engine supports. The vocabulary is `keyterm`, `audio_intelligence`, `redaction`, `diarization`, `smart_format`, `multichannel`, `utterances`, `profanity_filter`, `find_replace`, `language_detect`. Deepgram supports all ten; Whisper supports `keyterm`, `find_replace`, and `language_detect`.
- **`is_available()`** — whether the engine can actually run in the current image. Deepgram is available only when `DEEPGRAM_API_KEY` is set; Whisper only when `faster_whisper` is importable. This is checked at submit time so a job that can't run fails at the API boundary, not mid-worker.
- **`transcribe(buf, opts, progress_callback)`** — takes an audio buffer and an engine-agnostic `TranscribeOptions` and returns a `NormalizedResult` (segments with word-level timestamps plus a detected language). Engines ignore options they can't use.

Both engines normalize to the same `NormalizedResult` shape, so everything downstream — the SRT writer, transcripts, translation, speaker maps — is engine-agnostic. `get_engine(name)` resolves a name through the `ENGINES` registry; adding a third engine means one new subclass and one registry entry.

### Capability gating

`GET /api/capabilities` serializes the registry (see [API Endpoints](#api-endpoints)). The Web UI fetches it on load and:

- preselects the engine from the server's `ASR_ENGINE` and disables any engine whose `available` is `false` (with an engine-specific tooltip);
- hides every option whose capability the selected engine lacks, so the local engine never shows audio intelligence, redaction, or diarization controls;
- drops Deepgram-only options restored from saved preferences before submitting a whisper job.

The single source of truth is the engine's `capabilities()` set — there is no separate list in the frontend.

### Whisper engine details

- **Model loading.** One model is cached per worker process; selecting a different size evicts the previous one first, because `small` + `medium` + `large-v3` together (≈5 GB) would exceed the worker's 4 GB memory limit.
- **Options mapping.** Keyterms become faster-whisper `hotwords` (capped by `cap_keyterms`; best-effort, weaker than Nova-3 keyterm prompting). `LANGUAGE=multi` and auto-detect both map to Whisper's language auto-detection. Regional variants such as `pt-BR` normalize to their base code because Whisper rejects them.
- **Anti-hallucination.** `vad_filter=True` and `condition_on_previous_text=False` are fixed, which stops the model from repeating itself across long silences in movie and TV audio.
- **Progress.** Each finished segment reports `(segment_end, total_duration)` through the progress callback, which the worker forwards to the UI as a realtime multiplier.
- **Timeouts.** Batch timeouts are engine-aware: local jobs get a 4-hour-per-file budget instead of the cloud engine's 10 minutes.

### Native SRT writer

`core/srt_writer.py` turns a `NormalizedResult` into subtitle cues without depending on Deepgram's captions library:

| Rule | Value |
|------|-------|
| Max characters per line | 42 |
| Max lines per cue | 2 |
| Max cue duration | 7 s |
| Min cue duration | 1 s |
| Split on silence gap | ≥ 1 s |

Cues prefer to break at sentence ends (`.`, `?`, `!`, `…`) and at silence gaps; segments without word timestamps are split proportionally. Cloud output goes through the same writer, which is why v3 stopped embedding `[speaker N]` tags in cues by default (`SPEAKER_LABELS=1` or the "Speaker labels in subtitles" toggle restores them).

### Image build targets

`web/Dockerfile` and `cli/Dockerfile` are multi-stage with two final targets:

- **`default`** — lean image, Deepgram only.
- **`local`** — installs `faster-whisper>=1.0,<2` and bakes the `small` model into `/models` at build time, so the container transcribes offline from first boot. Sets `WHISPER_MODEL=small`, `WHISPER_MODEL_DIR=/models`, `WHISPER_COMPUTE_TYPE=int8`.

Published images: `ghcr.io/tylerbcrawford/subgeneratorr-{web,worker,cli}` (default) and the same names with a `-local` suffix. `examples/docker-compose.local.example.yml` builds the `local` target for web, worker, and CLI and mounts a model cache volume so larger models download once.

---

## File Structure

```
subgeneratorr/
├── cli/                          # CLI tool for batch processing
│   ├── generate_subtitles.py    # Main CLI script
│   ├── config.py                 # Configuration management
│   ├── transcript_generator.py  # Transcript generation with speaker maps
│   ├── Dockerfile                # CLI container definition
│   ├── entrypoint.sh            # Container entrypoint script
│   └── requirements.txt          # CLI dependencies
├── core/                         # Shared core functionality
│   ├── __init__.py
│   ├── asr_engine.py            # Pluggable ASR engines (Deepgram, faster-whisper)
│   ├── srt_writer.py            # Native SRT writer (cue segmentation)
│   ├── transcribe.py            # Reusable transcription functions
│   ├── translate.py             # LLM subtitle translation
│   ├── llm_providers.py         # Model catalog (MODEL_SPECS) + Claude / GPT / Gemini / Ollama adapters
│   ├── keyterm_search.py        # AI keyterm generation
│   ├── languages.py             # Language catalog (Nova-3, Whisper, translation flags)
│   ├── model_languages.py       # Per-model translation language support table
│   ├── settings_store.py        # Saved language-list choices (JSON at SETTINGS_PATH)
│   └── media_metadata.py        # ffprobe helpers
├── web/                          # Web UI (optional)
│   ├── app.py                   # Flask API server
│   ├── tasks.py                 # Celery background workers
│   ├── requirements.txt          # Web dependencies
│   ├── static/                  # Frontend assets
│   │   ├── app.js               # Main JavaScript application
│   │   ├── languages.js         # Language dropdowns + Customize languages panel
│   │   ├── ollama.js            # Installed-model picker for Ollama
│   │   ├── translate.js         # Translate panel
│   │   └── styles.css           # Stylesheet
│   └── templates/               # HTML templates
│       └── index.html           # Main UI template
├── scripts/                      # Utility scripts
│   ├── postprocess_subtitles.py # Rename existing subtitle files
│   └── validate_setup.py        # Setup validation tool
├── docs/                         # Documentation
│   ├── technical.md             # This file
│   ├── languages.md             # Language support guide
│   └── roadmap.md               # Project roadmap
├── examples/                     # Example configurations
│   ├── docker-compose.example.yml  # Cloud (Deepgram) compose template
│   ├── docker-compose.local.example.yml  # Fully-local (Whisper) compose template
│   ├── docker-compose.hostnet.override.yml  # Linux host-network override
│   └── video-list-example.txt   # Example file list
├── tests/                        # pytest suite (`make test`, no Docker or keys needed)
├── deepgram-logs/               # Processing logs (gitignored)
├── .env.example                 # Environment template
├── .github/                     # Issue/PR templates + CI workflows
├── .gitignore
├── CHANGELOG.md                 # Release history
├── CODE_OF_CONDUCT.md           # Contributor Covenant v2.1
├── CONTRIBUTING.md              # Contributing guidelines
├── LICENSE
├── Makefile                     # Command shortcuts
├── README.md                    # Main documentation
└── SECURITY.md                  # Security policy
```

---

## Subtitle File Naming

Subgeneratorr generates subtitle files with proper ISO-639-2 language tags (for example `.eng.srt` or `.spa.srt`) to ensure automatic recognition by Plex, Jellyfin, and other media servers. If a language cannot be resolved safely, Subgeneratorr falls back to `.und.srt` rather than mislabeling the subtitle as English.

Skip decisions use the same shared output inspection path in both the CLI and Celery worker. That means auto-detect preflight recognizes existing same-stem language-tagged sidecars before transcription starts, and transcript-enabled reruns only skip fully when both the resolved subtitle output and transcript already exist.

### Generated Files

**For a video file `Movie.mkv`:**
- `Movie.eng.srt` - English subtitles (automatically recognized by media servers)
- `Movie.spa.srt` - Spanish subtitles
- `Movie.und.srt` - Neutral fallback when `LANGUAGE=multi` or auto-detect cannot map the detected language safely

**If transcript generation is enabled (`ENABLE_TRANSCRIPT=1`):**

**TV Shows (at show level):**
```
/media/tv/Show Name/
├── Transcripts/                       # At show level, alongside seasons
│   ├── episode1.transcript.speakers.txt
│   ├── episode2.transcript.speakers.txt
│   ├── JSON/
│   │   ├── episode1.deepgram.json    # Raw API response (if enabled)
│   │   └── episode2.deepgram.json
│   ├── Intelligence/
│   │   └── episode1.intelligence.json # Audio Intelligence results (if enabled)
│   ├── Keyterms/
│   │   └── Show Name_keyterms.csv     # Shared across all episodes
│   └── Speakermap/
│       └── speakers.csv                # Shared speaker map
├── Season 01/
│   ├── episode1.mkv
│   └── episode1.eng.srt
└── Season 02/
    ├── episode2.mkv
    └── episode2.eng.srt
```

**Movies:**
```
/media/movies/Movie Name (2024)/
├── Movie.mkv
├── Movie.eng.srt
└── Transcripts/
    ├── Movie.transcript.speakers.txt
    ├── JSON/
    │   └── Movie.deepgram.json        # Raw API response (if enabled)
    ├── Intelligence/
    │   └── Movie.intelligence.json    # Audio Intelligence results (if enabled)
    ├── Keyterms/
    │   └── Movie Name (2024)_keyterms.csv
    └── Speakermap/
        └── speakers.csv
```

### Renaming Existing Subtitles

Use the included `scripts/postprocess_subtitles.py` script to rename existing subtitle files:

```bash
# Preview what would be renamed (dry run)
python3 scripts/postprocess_subtitles.py --dry-run /path/to/media/

# Rename a single file
python3 scripts/postprocess_subtitles.py /path/to/Movie.srt

# Rename all subtitles in a directory
python3 scripts/postprocess_subtitles.py /path/to/media/

# Process specific files
python3 scripts/postprocess_subtitles.py file1.srt file2.en.srt file3.srt
```

**Script behavior:**
- Convert `*.srt` → `*.eng.srt` (if no other language subtitles exist)
- Convert `*.en.srt` → `*.eng.srt`
- Skip files that already have proper `.eng.srt` naming
- Provide detailed feedback on what was renamed or skipped

**Clear transcode cache after renaming:**
```bash
# For Plex (Docker):
docker exec -it plex rm -rf "/config/Library/Application Support/Plex Media Server/Cache/Transcode/*"
```

---

## Language Support

The Cloud engine (Nova-3) transcribes 59 languages (91 language codes including regional variants) with multilingual processing and automatic language detection. The Local engine (Whisper) transcribes 99 languages, 40 of them Whisper-only. The Web UI's transcription dropdown follows the selected engine.

**Quick reference:**
- Set `LANGUAGE=en` (or any supported code) in `.env`
- Regional variants: `en-GB`, `pt-BR`, `es-419`, etc.
- Multilingual: `LANGUAGE=multi` (10 languages simultaneously)
- Auto-detect: `DETECT_LANGUAGE=1` (35 languages, batch mode only)
- Translate finished subtitles into 98 languages with an LLM — see [LLM-Powered Translation](languages.md#llm-powered-translation). Targets the selected model doesn't support are greyed out in the Web UI
- Trim either dropdown to the languages you use with **Customize languages…** — see [Customizing the language lists](languages.md#customizing-the-language-lists)

For the complete language matrix, regional variant guide, keyterm examples per language, translation details, and multilingual troubleshooting, see **[Language Support Guide](languages.md)**.

---

## Directory Structure

### File List Format

Create text files with video paths for batch processing:

```
# Comments start with #
# Empty lines are ignored

# TV Shows
/media/tv/Show Name/Season 01/Episode 01.mkv
/media/tv/Show Name/Season 01/Episode 02.mkv

# Movies
/media/movies/Movie Title (2024).mp4
```

See `examples/video-list-example.txt` for a complete example.

---

## Detailed Configuration

### Environment Variables (Complete Reference)

#### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPGRAM_API_KEY` | (required for cloud) | Your Deepgram API key; optional when `ASR_ENGINE=whisper` |
| `DEEPGRAM_TIMEOUT` | `900` | Seconds to wait for one Deepgram request (upload + transcription). deepgram-sdk 7.x defaults to 60 s, too short for feature-length audio |
| `MEDIA_PATH` | `/media` | Path to scan for videos (inside container) |
| `FILE_LIST_PATH` | - | Path to text file with specific media files to process |
| `LOG_PATH` | `/logs` | Directory for processing logs |
| `BATCH_SIZE` | `0` | Max videos per run (0 = unlimited with FILE_LIST_PATH, otherwise defaults to 10) |
| `LANGUAGE` | `en` | Language code (e.g., `en`, `es`, `fr`) |

#### ASR Engine (v3)

| Variable | Default | Description |
|----------|---------|-------------|
| `ASR_ENGINE` | `deepgram` | `deepgram` (cloud) or `whisper` (local; requires a `-local` image). Preselects the engine in the Web UI |
| `WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, or `large-v3` |
| `WHISPER_MODEL_DIR` | `/models` | Model cache directory (a named volume in the local compose) |
| `WHISPER_COMPUTE_TYPE` | `int8` | CTranslate2 compute type; `int8` is the CPU sweet spot |
| `WHISPER_CPU_THREADS` | `0` | CPU threads for inference (`0` = auto) |
| `SPEAKER_LABELS` | `0` | Set to `1` to embed `[speaker N]` tags in subtitle cues (cloud engine; off by default since v3) |

#### Feature Toggles

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_TRANSCRIPT` | `0` | Set to `1` to enable speaker-labeled transcript generation |
| `FORCE_REGENERATE` | `0` | Set to `1` to regenerate SRT files even if they already exist |
| `SAVE_RAW_JSON` | `0` | Set to `1` to save raw Deepgram API responses to Transcripts/JSON/ |

#### Transcription Quality Options

| Variable | Default | Description |
|----------|---------|-------------|
| `PROFANITY_FILTER` | `off` | Profanity filter: `off`, `tag`, or `remove` |
| `NUMERALS` | `0` | Convert spoken numbers to digits (e.g., "twenty twenty four" → "2024") |
| `FILLER_WORDS` | `0` | Include filler words like "uh", "um" (usually off for subtitles) |
| `DETECT_LANGUAGE` | `0` | Auto-detect language for international content |
| `MEASUREMENTS` | `0` | Convert spoken measurements (e.g., "fifty meters" → "50m") |
| `DICTATION` | `0` | Convert spoken punctuation to symbols (e.g., "period" → ".") |

#### Web UI Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `change-me` | Flask session secret (generate with `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `MEDIA_ROOT` | `/media` | Media root path |
| `LOG_ROOT` | `/logs` | Log directory path |
| `DEFAULT_MODEL` | `nova-3` | Default transcription model |
| `DEFAULT_LANGUAGE` | `en` | Default language |
| `SETTINGS_PATH` | `/logs/subgeneratorr-settings.json` | Where the Customize languages choices are saved (JSON). The default sits on the logs volume, so it survives container recreation |
| `DISABLE_AUTH` | `true` in example compose | Disable auth entirely for local-only deployments |
| `ALLOWED_EMAILS` | - | Comma-separated list of allowed email addresses for OAuth |
| `WORKER_CONCURRENCY` | `1` | Number of concurrent transcription jobs per worker |
| `PUID` | `1000` in example compose | Host user ID for file ownership on Linux/NAS deployments |
| `PGID` | `1000` in example compose | Host group ID for file ownership on Linux/NAS deployments |

#### LLM API Keys (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | - | Anthropic API key for AI keyterm generation and subtitle translation (optional) |
| `OPENAI_API_KEY` | - | OpenAI API key for AI keyterm generation and subtitle translation (optional) |
| `GEMINI_API_KEY` | - | Google Gemini API key for AI keyterm generation and subtitle translation (optional; both Gemini models have a free tier) |
| `OLLAMA_HOST` | - | Local Ollama server for free, offline keyterm generation and subtitle translation, e.g. `http://localhost:11434` (optional). The Web UI lists the models installed there; users can also type a host in the UI |
| `OLLAMA_TIMEOUT` | `600` | Seconds to wait for one Ollama completion. Requests are not retried, because a timed-out local generation would only repeat the same CPU work. Raise this for large models on slow hardware |
| `OLLAMA_THINKING_HEADROOM` | `8192` | Extra tokens added to every Ollama request so thinking models (qwen3, deepseek-r1, gpt-oss) can reason before answering instead of returning nothing. Non-thinking models stop early, so it costs them nothing |

---

## Platform-Specific Details

### Linux

- **Docker:** Native support with Docker Engine or Docker Desktop
- **File Permissions:** Use `PUID` and `PGID` environment variables to match your user across the web, worker, and CLI containers
- **Performance:** Best performance, no virtualization overhead
- **Tested On:** Ubuntu, Debian, Fedora, Arch Linux

**Find your UID/GID:**
```bash
id -u  # Get your UID
id -g  # Get your GID
```

**Set in `.env` or `docker-compose.yml`:**
```yaml
environment:
  - PUID=1000  # Your user ID
  - PGID=1000  # Your group ID
```

### Authentication Headers

When `DISABLE_AUTH=false`, the app trusts an upstream authenticated identity only if the reverse proxy forwards one of these headers:

- `X-Auth-Request-Email`
- `X-Forwarded-User`

OAuth2-Proxy can emit `X-Auth-Request-Email` directly. Other proxies such as Authelia or Nginx auth setups must be configured to forward one of those headers explicitly.

### macOS

- **Docker:** Requires Docker Desktop for Mac
- **File Permissions:** Automatically handled by Docker Desktop (PUID/PGID not needed)
- **Performance:** Runs containers in lightweight VM
- **M1/M2 Macs:** Fully supported via Docker's ARM64 compatibility
- **Path Format:** Unix-style paths (e.g., `/Users/username/Videos`)

### Windows

- **Docker:** Requires Docker Desktop with WSL2 backend
- **File Permissions:** Automatically handled by Docker Desktop (PUID/PGID not needed)
- **Performance:** Near-native Linux performance with WSL2
- **Path Formats:**
  - Windows-style: `C:/Users/YourName/Videos:/media`
  - WSL2 format: `/c/Users/YourName/Videos:/media`
  - Network drives: `//server/share:/media`
- **Line Endings:** Ensure `entrypoint.sh` has LF endings (not CRLF)

---

## API Endpoints

### Web UI REST API

#### Configuration

**GET `/api/config`**

Get default model and language settings, including LLM API key availability.

**Response:**
```json
{
  "default_model": "nova-3",
  "default_language": "en",
  "anthropic_api_key_configured": true,
  "openai_api_key_configured": false,
  "google_api_key_configured": true,
  "ollama_configured": true,
  "providers": {"anthropic": true, "openai": false, "google": true, "ollama": true}
}
```

`ollama_configured` is true when `OLLAMA_HOST` is set (Ollama needs no key). The flat `*_configured` fields are kept for backward compatibility.

**GET `/api/capabilities`**

Per-engine capability sets used by the UI for option gating, plus the server's default engine, the local model picker choices, and the cloud LLM roster (`llm_models`) for the keyterm and translate pickers. See [ASR Engines](#asr-engines-cloud-and-local).

**Response:**
```json
{
  "engines": {
    "deepgram": {"available": true, "capabilities": ["audio_intelligence", "diarization", "find_replace", "keyterm", "language_detect", "multichannel", "profanity_filter", "redaction", "smart_format", "utterances"]},
    "whisper": {"available": false, "capabilities": ["find_replace", "keyterm", "language_detect"]}
  },
  "default_engine": "deepgram",
  "whisper_models": ["tiny", "base", "small", "medium", "large-v3"],
  "default_whisper_model": "small",
  "llm_models": ["… one entry per MODEL_SPECS model …"]
}
```

#### Languages and Settings

**GET `/api/languages`**

The language catalog the Web UI builds its dropdowns from, plus the saved visibility choices. `prefs` values are a list of codes, or `null` for "show all".

**Response:**
```json
{
  "languages": [
    {"code": "auto", "name": "Auto-detect", "base": "auto", "deepgram": true, "whisper": true, "translate": false, "special": true},
    {"code": "cy", "name": "Welsh", "base": "cy", "deepgram": false, "whisper": true, "translate": true, "special": false},
    {"code": "pt-BR", "name": "Portuguese (Brazil)", "base": "pt", "deepgram": true, "whisper": false, "translate": false, "special": false}
  ],
  "prefs": {"transcription": null, "translation": ["es", "fr", "ja"]}
}
```

- `deepgram` / `whisper` — selectable for transcription on the Cloud / Local engine.
- `translate` — offered as a translation target (98 codes; English is the source language and isn't a target).
- `special` — `auto` and `multi`, which aren't real languages.

**GET `/api/languages/translation-support?provider=ollama&model=llama3.2:3b`**

Which translation targets a model officially supports. The Web UI greys out the rest; the backend never blocks a translation.

**Response:**
```json
{
  "supported": ["de", "es", "fr", "hi", "it", "pt", "th"],
  "verified": true,
  "label": "Llama 3",
  "source": "github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md"
}
```

`supported: null` means every target: cloud providers, broadly multilingual families (Qwen 3, Gemma 3+), and unrecognized Ollama models. Unrecognized models also return `verified: false`, which the UI shows as "unverified". The table lives in `core/model_languages.py`.

**GET `/api/settings/languages`**

The saved choices: `{"transcription": [codes] | null, "translation": [codes] | null}`. A missing or unreadable file reads as all `null`.

**PUT `/api/settings/languages`**

Save the choices. Send either key or both; an omitted key keeps its saved value.

```json
{"transcription": ["en", "es", "fr", "cy"], "translation": null}
```

Returns the saved object. Unknown codes, an empty list, or a non-list value → 400. An unwritable `SETTINGS_PATH` → 500.

#### Ollama

**GET `/api/ollama/models?host=http://localhost:11434`**

Lists the models installed on an Ollama server (a proxy for Ollama's `/api/tags`). `host` is optional and falls back to `OLLAMA_HOST`; it must look like `host:port` or `http(s)://host:port`.

**Response:**
```json
{
  "host": "http://localhost:11434",
  "models": [
    {"name": "llama3.2:3b", "family": "llama", "parameter_size": "3.2B"},
    {"name": "qwen3:8b", "family": "qwen3", "parameter_size": "8.2B"}
  ]
}
```

No host or a malformed host → 400. Server unreachable, a non-200 reply, or a redirect → 502 with `{"error", "host"}`. The request times out after 3 s.

#### File Browsing

**GET `/api/browse?path=/media&show_all=false`**

Browse directories and media files.

**Parameters:**
- `path` - Directory path to browse
- `show_all` - Show all files (true) or only media without subtitles (false)

**Response:**
```json
{
  "current_path": "/media/tv",
  "parent_path": "/media",
  "directories": [
    {"name": "Show Name", "path": "/media/tv/Show Name"}
  ],
  "files": [
    {
      "name": "episode.mkv",
      "path": "/media/tv/Show Name/episode.mkv",
      "has_subtitles": false,
      "size": 1234567890,
      "duration": 2700
    }
  ]
}
```

**GET `/api/scan?root=/media/tv`**

Scan directory recursively for media without subtitles.

**Response:**
```json
{
  "files": [
    "/media/tv/Show/Season 01/episode1.mkv",
    "/media/tv/Show/Season 01/episode2.mkv"
  ],
  "count": 2
}
```

#### Cost Estimation

**POST `/api/estimate`**

Get cost and time estimates for selected files.

**Request:**
```json
{
  "files": ["/media/tv/Show/episode.mkv"]
}
```

**Response:**
```json
{
  "total_duration": 2700,
  "estimated_cost": 0.26,
  "estimated_time": 180,
  "file_count": 1
}
```

#### Job Management

**POST `/api/submit`**

Submit batch of files for processing.

**Request:**
```json
{
  "language": "en",
  "model": "nova-3",
  "files": ["/media/tv/Show/episode.mkv"],
  "force_regenerate": false,
  "enable_transcript": false,
  "profanity_filter": "off",
  "keyterms": ["ProductName", "TechnicalTerm", "account number"],
  "numerals": false,
  "filler_words": false,
  "detect_language": false,
  "measurements": false,
  "diarize": true,
  "utterances": true,
  "paragraphs": true,
  "dictation": false,
  "multichannel": false,
  "redact": [],
  "replace": [],
  "utt_split": 0.8,
  "sentiment": false,
  "summarize": false,
  "topics": false,
  "intents": false,
  "detect_entities": false,
  "search": [],
  "tag": ""
}
```

**Additional request body parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | `"nova-3"` | Transcription model: `"nova-3"` (General) or `"nova-3-medical"` (Medical) |
| `dictation` | bool | `false` | Convert spoken punctuation to symbols (e.g., "period" → ".") |
| `multichannel` | bool | `false` | Process stereo audio channels separately |
| `redact` | array | `[]` | Redact sensitive info: `["pci"]`, `["pii"]`, `["numbers"]` (combinable) |
| `replace` | array | `[]` | Find & replace terms: `["wrong:right", ...]` (max 200) |
| `utt_split` | float | `0.8` | Pause threshold for utterance segmentation (0.1–5.0 seconds) |
| `sentiment` | bool | `false` | Sentiment analysis (English only, saved to Intelligence/) |
| `summarize` | bool | `false` | Summarization (English only, saved to Intelligence/) |
| `topics` | bool | `false` | Topic detection (English only, saved to Intelligence/) |
| `intents` | bool | `false` | Intent detection (English only, saved to Intelligence/) |
| `detect_entities` | bool | `false` | Entity detection (English only, saved to Intelligence/) |
| `search` | array | `[]` | Search for terms in audio (English only, saved to Intelligence/) |
| `tag` | string | `""` | Request label for tracking/tagging API requests |

**Language shortcuts:** Set `language` to `"auto"` for auto-detection (sends `detect_language: true` to Deepgram) or `"multi"` for multilingual code-switching.

**Response:**
```json
{
  "batch_id": "abc123-def456-ghi789",
  "status": "pending",
  "file_count": 1
}
```

**GET `/api/job/<batch_id>`**

Check job status with child task details.

**Response:**
```json
{
  "batch_id": "abc123",
  "status": "processing",
  "progress": {
    "completed": 5,
    "total": 10,
    "percentage": 50
  },
  "files": [
    {
      "path": "/media/tv/Show/episode.mkv",
      "status": "completed",
      "cost": 0.26,
      "duration": 2700
    }
  ],
  "estimated_cost": 2.57,
  "total_duration": 27000
}
```

**POST `/api/job/<batch_id>/cancel`**

Cancel a running job.

**Response:**
```json
{
  "status": "cancelled",
  "message": "Job cancelled successfully"
}
```

**GET `/api/progress`**

Server-Sent Events stream for real-time updates.

**Event Format:**
```
event: job_progress
data: {"batch_id": "abc123", "progress": 50, "status": "processing"}

event: job_complete
data: {"batch_id": "abc123", "status": "completed"}
```

#### Keyterm Management

**GET `/api/keyterms/load?video_path=/media/tv/Show/episode.mkv`**

Load keyterms for a video from CSV.

**Response:**
```json
{
  "keyterms": ["Name1", "Name2", "Term3"],
  "count": 3
}
```

**POST `/api/keyterms/upload`**

Upload keyterms CSV for a video.

**Request (multipart/form-data):**
- `file` - CSV file
- `video_path` - Video file path

**Response:**
```json
{
  "status": "success",
  "count": 25,
  "path": "/media/tv/Show/Transcripts/Keyterms/Show_keyterms.csv"
}
```

**GET `/api/keyterms/download?video_path=/media/tv/Show/episode.mkv`**

Download keyterms CSV for a video.

**Response:** CSV file download

#### Library Scan

**POST `/api/library-scan`**

Launch a library-wide scan for files missing subtitles. Uses a two-phase approach: fast sidecar file check, then optional ffprobe embedded subtitle detection.

**Request:**
```json
{
  "skip_embedded": false
}
```

**Response:**
```json
{
  "task_id": "abc123-def456",
  "status": "pending"
}
```

**GET `/api/library-scan/status/<task_id>`**

Check scan progress. Returns phase, file counts, and percentage.

**Response (in progress):**
```json
{
  "state": "PROGRESS",
  "phase": "sidecar_scan",
  "scanned": 2100,
  "total": 4286,
  "missing_so_far": 312,
  "progress": 49.0
}
```

**Response (complete):**
```json
{
  "state": "SUCCESS",
  "missing_files": [
    {"path": "/media/tv/Show/episode.mkv", "name": "episode.mkv", "directory": "/media/tv/Show"}
  ],
  "total_scanned": 4286,
  "total_missing": 312,
  "scan_time_seconds": 45.2
}
```

**POST `/api/library-scan/<task_id>/cancel`**

Cancel a running scan.

**Response:**
```json
{
  "status": "cancelled",
  "task_id": "abc123-def456"
}
```

**GET `/api/library-scan/export/<task_id>`**

Export scan results as CSV download. Only available for completed scans.

**Response:** CSV file download (`missing-subtitles-YYYY-MM-DD.csv`) with columns: `path`, `name`, `directory`.

**Performance Benchmark:**

| Library Size | Scan Mode | Time | Result |
|-------------|-----------|------|--------|
| 4,662 files | Full (sidecar + embedded) | ~346s (~6 min) | 573 missing |
| 4,662 files | Sidecar-only (skip embedded) | ~5s | Faster, but misses files with embedded-only subs |

The two-phase approach means Phase 1 (sidecar detection) is instant: pure in-memory string matching against filenames. Phase 2 (ffprobe embedded check) runs only on files without sidecars and accounts for the majority of scan time (~50-100ms per file).

#### LLM Keyterm Generation

**POST `/api/keyterms/generate`**

Generate keyterms with an LLM from the show/movie name inferred from the file path. Runs as a background task; the result is also saved to the show's keyterms CSV.

**Request:**
```json
{
  "video_path": "/media/tv/Show/Season 01/Show - S01E01.mkv",
  "provider": "anthropic",
  "model": "claude-sonnet-5-5",
  "preserve_existing": false,
  "estimate_only": false
}
```

- `provider` — `anthropic` · `openai` · `google` · `ollama` (default `anthropic`).
- `model` — a model id from the [model table](#ai-powered-generation); defaults to the provider's best-quality model. Retired ids (`claude-sonnet-4-6`, `gpt-4.1`, `gemini-2.5-flash`, …) are accepted and mapped to their replacements. For Ollama, an installed model name such as `qwen3:8b` (required).
- `ollama_host` — Ollama endpoint for `provider: "ollama"`; falls back to the `OLLAMA_HOST` env var. Without either → 400.
- `preserve_existing` — merge with the show's existing keyterms instead of replacing them.
- `estimate_only` — return `{estimated_tokens, estimated_cost, model}` instead of queueing. Ollama estimates are always `0`.

**Response:**
```json
{
  "task_id": "abc123",
  "status": "pending"
}
```

**GET `/api/keyterms/generate/status/<task_id>`** — returns `state` (`PENDING`, `PROGRESS`, `SUCCESS`, `FAILURE`). On success:
```json
{
  "state": "SUCCESS",
  "keyterms": ["Character Name", "Location", "Technical Term"],
  "keyterm_count": 25,
  "token_count": 1450,
  "actual_cost": 0.0012,
  "provider": "anthropic",
  "model": "claude-sonnet-5-5"
}
```

#### Subtitle Translation

**POST `/api/translate`**

Translate a video's existing `.srt` into one or more target languages, writing language-tagged sidecars (`.spa.srt`, `.fre.srt`, …). Timestamps are copied from the source verbatim — only the text is translated — and the show's keyterms ride along as a glossary.

**Request:**
```json
{
  "video_path": "/media/tv/Show/episode.mkv",
  "targets": ["es", "fr"],
  "provider": "anthropic",
  "model": "claude-sonnet-5-5",
  "overwrite": false,
  "ollama_host": "http://localhost:11434",
  "source_srt": "/media/tv/Show/episode.eng.srt",
  "estimate_only": false
}
```

- `video_path` (required), `targets` (required) — list of language codes from the [98 translation targets](languages.md#llm-powered-translation). Any target is accepted; model support (see `/api/languages/translation-support`) is advisory.
- `provider` — `anthropic` · `openai` · `google` · `ollama` (default `anthropic`).
- `model` — model id for cloud providers (defaults to the provider's best-quality model; retired ids are mapped to their replacements), or an installed model name for Ollama (required; the Web UI lists them via `/api/ollama/models`).
- `ollama_host` — Ollama endpoint; falls back to the `OLLAMA_HOST` env var.
- `source_srt` — explicit source subtitle; defaults to the auto-located sidecar.
- `overwrite` — re-translate even if the target sidecar already exists (default `false`).
- `estimate_only` — return a cost estimate instead of queueing the job.

**Response:**
```json
{
  "task_id": "abc123",
  "status": "pending"
}
```

With `"estimate_only": true`, returns a cost estimate instead:
```json
{
  "estimated_cost": 0.0234
}
```

**GET `/api/translate/status/<task_id>`**

Poll a translation task (mirrors the keyterm-generate status endpoint). Returns `state` — `PENDING`, `PROGRESS`, `SUCCESS`, or `FAILURE` — with progress detail while running and, on completion, how many sidecars were written and skipped.

---

## Advanced Usage

### CLI Processing Examples

**Process entire library:**
```bash
docker compose run --rm cli
```

**Process specific directory:**
```bash
docker compose run --rm -e MEDIA_PATH=/media/tv/ShowName cli
```

**Process specific season:**
```bash
docker compose run --rm -e MEDIA_PATH=/media/tv/ShowName/Season\ 01 cli
```

**Process from file list:**
```bash
docker compose run --rm -e FILE_LIST_PATH=/config/video-list.txt cli
```

**Batch processing (limit to 10 files):**
```bash
docker compose run --rm -e BATCH_SIZE=10 cli
```

**Process non-English content:**
```bash
docker compose run --rm -e LANGUAGE=es cli
```

**Generate speaker-labeled transcripts:**
```bash
docker compose run --rm -e ENABLE_TRANSCRIPT=1 cli
```

**Force regenerate SRT files:**
```bash
docker compose run --rm -e FORCE_REGENERATE=1 cli
```

**Enable all Nova-3 quality features:**
```bash
docker compose run --rm \
  -e NUMERALS=1 \
  -e MEASUREMENTS=1 \
  -e DETECT_LANGUAGE=1 \
  cli
```

### Automation with Cron

Process new videos daily:

```bash
# Add to crontab
0 5 * * * cd /path/to/subgeneratorr && docker compose run --rm -e BATCH_SIZE=50 cli
```

Weekly scan for missing subtitles:

```bash
# Every Sunday at 3 AM
0 3 * * 0 cd /path/to/subgeneratorr && docker compose run --rm cli
```

---

## Keyterm Prompting Deep Dive

For an overview of keyterms (what they are, how to create them, AI generation), see the [README](../README.md#keyterm-prompting). This section covers API parameters, token limits, and CSV format details.

**What are keyterms?** Keyterms are custom vocabulary hints passed directly to the Deepgram Nova-3 API at transcription time. They are not a post-processing step; they influence the model's recognition probabilities during decoding. This is also referred to as keyword boosting or vocabulary prompting in the speech-to-text literature.

**API Parameter** (deepgram-sdk 7.x; see the [Nova-3 Configuration Reference](#nova-3-configuration-reference)):
```python
client.listen.v1.media.transcribe_file(
    request=audio_bytes, model="nova-3", keyterm=["Walter White", "Jesse Pinkman", "Heisenberg"]
)
```

**Token Estimation:**
- Approximately 1.3 tokens per word
- Recommended: 20-50 focused keyterms
- Maximum: 500 tokens per request

### CSV Format Specification

**File Location:**
- TV Shows: `{Show Directory}/Transcripts/Keyterms/{show_name}_keyterms.csv`
- Movies: `{Movie Directory}/Transcripts/Keyterms/{movie_name}_keyterms.csv`

**Format Rules:**
- UTF-8 encoding
- One keyterm per line
- No header row required
- Empty lines ignored
- Lines starting with `#` treated as comments
- Case-sensitive (preserve proper capitalization)

**Example:**
```csv
Walter White
Jesse Pinkman
Heisenberg
Los Pollos Hermanos
Albuquerque
methylamine
DEA
# Add more as characters appear
```

### AI-Powered Generation

The Web UI supports AI-powered keyterm generation and subtitle translation using Anthropic Claude, OpenAI GPT, Google Gemini, or a local Ollama model. For Ollama, both panels list the models installed on your server (with a refresh button and a Host field) and fall back to a free-text model name if the server can't be reached. Ollama calls cost nothing.

**Supported Models** (prices as of October 2026; the source of truth is `MODEL_SPECS` in `core/llm_providers.py`):

| Provider | Model | API Model ID | Input $/1M | Output $/1M | Notes |
|----------|-------|-------------|-----------|------------|-------|
| Anthropic | Claude Sonnet 5.5 | `claude-sonnet-5-5` | $2.00 | $10.00 | Best quality (provider default) |
| Anthropic | Claude Haiku 5.5 | `claude-haiku-5-5` | $0.10 | $0.50 | Fast & cheap |
| OpenAI | GPT-6.1 Sol | `gpt-6.1-sol` | $2.00 | $10.00 | Best quality (provider default) |
| OpenAI | GPT-6 Luna | `gpt-6-luna` | $0.10 | $0.50 | Fast & cheap |
| Google | Gemini 3.8 Flash | `gemini-3.8-flash` | $1.50 | $7.50 | Best quality (provider default); free tier available |
| Google | Gemini 3.5 Flash-Lite | `gemini-3.5-flash-lite` | $0.30 | $2.50 | Fast & cheap; free tier available |

Gemini prices are paid-tier list prices. On the free tier (rate-limited per key), calls cost nothing, but the UI still shows the paid estimate. Retired ids are accepted and mapped to replacements: `claude-sonnet-4`/`claude-sonnet-4-6` → Sonnet 5.5, `claude-haiku-4-5` → Haiku 5.5, `gpt-4.1` → Sol, `gpt-4.1-mini` → Luna, `gemini-2.5-flash` → Flash-Lite.

**Model Benchmarks (October 2026):**

Measured end-to-end through the Web API on a 3-minute Community S01E01 clip (70 cues), with each model at its pinned reasoning setting. Keyterm times include Celery queueing.

| Model | Keyterms | Time | Cost/Call | Translation (70 cues) | Time | Cost |
|-------|---------|------|-----------|------------------------|------|------|
| Claude Sonnet 5.5 | 43 | 7.1s | $0.0059 | → es, 97% of cues changed | 15s | $0.0278 |
| Claude Haiku 5.5 | 36 | 2.0s | $0.0003 | → fr, 99% | 12s | $0.0014 |
| GPT-6.1 Sol | 50 | 12.2s | $0.0050 | → pt, 99% | 27s | $0.0162 |
| GPT-6 Luna | 47 | 3.1s | $0.0002 | → ja, 97% | 15s | $0.0009 |
| Gemini 3.8 Flash | 42 | 21.3s | $0.0028 | → de, 97% | 106s | $0.0148 |
| Gemini 3.5 Flash-Lite | 32 | 1.0s | $0.0006 | → it, 97% | 6s | $0.0048 |
| Ollama `qwen2.5:3b` (M2, Metal) | — | — | free | → nl, 77% | 91s | free |

All six cloud models returned the main cast with full names (Jeff Winger, Britta Perry, Abed Nadir, Troy Barnes, …) plus show-specific terms such as Greendale, Dean Pelton, and Señor Chang. Every translation kept cue count and timing identical. The unchanged cues are names and interjections that stay the same in the target language.

**Recommendations:**
- **Free:** Gemini 3.5 Flash-Lite on the free tier. It is the fastest model and has a solid keyterm list.
- **Best value (paid):** GPT-6 Luna or Claude Haiku 5.5. Each costs a fraction of a cent per call, with near-premium keyterm lists and clean translations.
- **Premium quality:** Claude Sonnet 5.5 or GPT-6.1 Sol, for the richest keyterms and the most natural translations.
- **Offline:** Ollama with a 7B+ model (e.g. `qwen2.5:7b` or `qwen3:8b`) on a GPU or Apple Silicon. 3B models finish but produce noticeably rougher translations. Thinking models work too: on an M2, `qwen3:4b` returned 19 keyterms in about 35 s, helped by `OLLAMA_THINKING_HEADROOM`. Small models support fewer languages; the Translate panel greys out targets the model's card doesn't list. On a low-power CPU, generation can fall below 1 token/s; set `OLLAMA_TIMEOUT` or use a faster host.
- Gemini 3.8 Flash's lowest accepted thinking level still reasons, so it is the slowest cloud option, especially for translation.

> **Reasoning controls.** Every model above thinks by default. Keyterm lists and subtitle translation gain nothing from long reasoning, which only adds latency and output-token cost. Each model is therefore pinned to the lowest setting its API accepts:
>
> | Model | Setting |
> |---|---|
> | Sonnet 5.5 | `thinking: between_tools`; the API rejects `disabled` |
> | Haiku 5.5 | `thinking: disabled` |
> | GPT-6.1 Sol | `reasoning_effort: low`; it has no `none` |
> | GPT-6 Luna | `reasoning_effort: none` |
> | Gemini 3.8 Flash | `thinking_level: low`; `minimal` is rejected |
> | Gemini 3.5 Flash-Lite | `thinking_level: minimal` |
>
> Models that still reason at their floor get extra output-token headroom so reasoning can't consume the keyterm budget. Gemini thought tokens are billed as output and included in the reported cost. Settings live in `MODEL_SPECS[...].request_options`.

**How It Works:**
1. User selects video in Web UI
2. Opens Advanced Options → AI Keyterm Generation
3. Selects provider and model
4. Clicks "Generate Keyterms with AI"
5. AI researches show/movie and generates 20-50 optimized keyterms
6. Keyterms populate text box for review/editing
7. On transcribe, saved to CSV for reuse

---

## Speaker Maps Technical Details

For an overview of speaker maps, see the [README](../README.md#speaker-maps). This section covers CSV format and speaker ID assignment details.

### CSV Format

```csv
speaker_id,name
0,Walter White
1,Jesse Pinkman
2,Skyler White
3,Hank Schrader
```

**Rules:**
- Header row required: `speaker_id,name`
- Speaker IDs are integers starting from 0
- UTF-8 encoding
- One mapping per line

### Speaker ID Assignment

Speaker IDs are assigned by Deepgram's diarization algorithm based on voice characteristics. IDs may vary between episodes, so speaker maps often need per-episode adjustment.

**Workflow:**
1. Generate transcript without speaker map
2. Review `.transcript.speakers.txt` to see Speaker IDs
3. Create/update speaker map CSV
4. Regenerate transcript with speaker map applied

---

## Utilities and Scripts

### Postprocess Subtitles Script

Location: `scripts/postprocess_subtitles.py`

Renames existing subtitle files to proper ISO-639-2 format.

**Usage:**
```bash
# Dry run (preview)
python3 scripts/postprocess_subtitles.py --dry-run /path/to/media/

# Process directory
python3 scripts/postprocess_subtitles.py /path/to/media/

# Process specific files
python3 scripts/postprocess_subtitles.py file1.srt file2.srt
```

### Validate Setup Script

Location: `scripts/validate_setup.py`

Validates Docker, API keys, and configuration.

**Usage:**
```bash
python3 scripts/validate_setup.py
```

### Makefile Commands

```bash
# Web UI
make web-up        # Start Web UI services
make web-down      # Stop Web UI services
make web-logs      # Follow Web UI logs
make web-restart   # Restart Web UI services

# CLI
make cli-run       # Run CLI tool
make cli-build     # Build CLI container

# Development
make clean         # Clean up containers and volumes
make logs          # View all logs
```

---

## Logs and Statistics

Processing statistics are saved to `deepgram-logs/` in JSON format:

```json
{
  "processed": 5,
  "skipped": 2,
  "failed": 0,
  "total_minutes": 42.5,
  "estimated_cost": 0.24,
  "model": "nova-3",
  "language": "en",
  "start_time": "2024-01-15T10:30:00",
  "end_time": "2024-01-15T10:45:00",
  "files": [
    {
      "path": "/media/tv/Show/episode.mkv",
      "duration": 2700,
      "cost": 0.26,
      "status": "completed"
    }
  ]
}
```

---

## Nova-3 Configuration Reference

The request every transcription sends (`core/transcribe.py` → `transcribe_file`, shared by the CLI and the web worker), using deepgram-sdk 7.x. Options are keyword arguments; list values are sent as repeated query parameters (`keyterm=A&keyterm=B`). Disabled features are omitted rather than sent as `false`.

```python
from deepgram import DeepgramClient

client = DeepgramClient(api_key=api_key, timeout=DEEPGRAM_TIMEOUT)  # default 900 s

opts = {
    "model": model,  # "nova-3" (general) or "nova-3-medical"
    "smart_format": True,
    "utterances": True,
    "punctuate": True,
    "paragraphs": True,
    "language": language,  # e.g. "en", "es-419", "multi"
    "profanity_filter": profanity_filter != "off",  # boolean
}
if keyterms and "nova-3" in model:
    opts["keyterm"] = keyterms  # list; ≤500 tokens total, 20–50 terms recommended

# Optional features, sent only when enabled:
#   numerals, filler_words, detect_language, measurements, dictation, multichannel
#   redact=["pci", "pii", "numbers"], replace=["wrong:right", ...], utt_split=1.2
#   Audio Intelligence (English only, saved to Transcripts/Intelligence/):
#   sentiment, summarize="v2", topics, intents, detect_entities, search=[...]
#   tag=["label"]

# Diarization: diarize_model ALONE enables Deepgram's v2 speaker model. Never
# also send the legacy `diarize=true` — the pair is rejected with HTTP 400, and
# `diarize=true` on its own is deprecated and routes to the older v1 model.
if diarize:
    opts["diarize_model"] = "v2"

response = client.listen.v1.media.transcribe_file(request=audio_bytes, **opts)
```

The response is a typed `ListenV1Response` (pydantic). Code reads it by attribute (`response.results.channels[0].alternatives[0].words`); `response_to_dict()` produces the plain-JSON form used for `deepgram-captions` SRT generation and the saved `.deepgram.json`.

---

## Security Considerations

### Web UI Security

- Web UI can be protected with OAuth authentication (configured at reverse proxy level)
- Both web and worker containers require read-write media mounts (web writes keyterms to `Transcripts/Keyterms/`, worker writes subtitles and transcripts)
- Language-tagged `.srt` subtitle files are written next to source media files; transcript outputs are written under sibling `Transcripts/` folders
- Email allowlist available for additional access control via `ALLOWED_EMAILS` environment variable
- API key never exposed to browser (server-side only)

### File Permissions

- CLI and workers need write access to create language-tagged `.srt` files
- Web UI needs read access to browse media
- Use `PUID`/`PGID` on Linux to match your user
- On macOS/Windows, Docker Desktop handles permissions automatically

---

## Performance Tuning

### Worker Concurrency

Start with `WORKER_CONCURRENCY=1`, increase to 2-3 if your system can handle it:

```yaml
environment:
  - WORKER_CONCURRENCY=2
```

**Resource Requirements:**
- 1-2GB RAM per concurrent job
- 1 CPU core per concurrent job
- Network bandwidth for API calls

### Batch Size Limits

Limit processing to avoid overwhelming your system or API:

```bash
docker compose run --rm -e BATCH_SIZE=10 cli
```

### Processing Speed

- Average: 0.0109x real-time (10 hours of video takes ~6.5 minutes to process)
- Nova-3 is optimized for accuracy, not speed
- Parallel processing with Web UI workers can significantly increase throughput

---

For additional information, see:
- [README.md](../README.md) - Main documentation
- [Language Support Guide](languages.md) - Complete language matrix and multilingual features
- [roadmap.md](roadmap.md) - Project roadmap and future features
