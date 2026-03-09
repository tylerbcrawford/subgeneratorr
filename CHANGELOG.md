# Changelog

All notable changes to Subgeneratorr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- **Cost Tracking** — Real-time per-file and session cost estimates with detailed logging (~$0.0043/min)
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

[Unreleased]: https://github.com/tylerbcrawford/subgeneratorr/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/tylerbcrawford/subgeneratorr/releases/tag/v2.0.0
