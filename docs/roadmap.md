# Roadmap

Future enhancements under consideration. Community contributions welcome — open an issue or PR if any of these interest you.

---

## Planned

### Single-Container Option
Consolidate Redis, Flask, and Celery into a single Docker container for simpler deployment. Reduce `docker-compose.yml` to one service for users who don't need horizontal scaling.

### Bazarr Auto-Fallback
Automatically trigger Subgeneratorr for files where Bazarr can't find community subtitles. The library scan feature (shipped in v2.1.0) provides the scanning capability; remaining work is webhook/scheduled integration with Bazarr's post-processing pipeline.

### Language Detection UX
Surface Nova-3's language detection metadata in the Web UI — show detected language with confidence score after transcription, display language breakdown for code-switching content, and add visual indicators when auto-detect or multi-language mode is active.

---

## Ideas

### Drag-and-Drop File Input
Modern drag-and-drop interface for selecting files across multiple directories. Queue management with priority ordering and per-file progress tracking.

### Subtitle Synchronization
Built-in timing correction for generated subtitles using FFmpeg. Auto-correct drift without external tools like Subsyncarr.

### CLI/Web Feature Parity
Audit and align features between CLI and Web UI. LLM keyterm generation is intentionally Web-only, but other gaps should be documented or closed.

---

## Completed (V3.0 – V3.1)

- Local transcription engine: pluggable `ASREngine` interface, faster-whisper (CPU, int8) behind opt-in `-local` images with the `small` model baked in, capability-gated Web UI via `/api/capabilities`, native SRT writer with readability-focused cue segmentation
- Fully offline pipeline: Local Whisper + Ollama for keyterms and translation, no API key required
- Five new Nova-3 languages (Afrikaans, Armenian, Georgian, Nepali, Punjabi); translation targets grown to 54
- GHCR release pipeline gated on the full test and lint suite

### Deferred from the local engine
GPU acceleration and local speaker diarization remain future tiers.

## Completed (V2.4)

- LLM-powered subtitle translation: translate a generated SRT into 49 target languages (54 as of v3.1) with Claude, GPT, Gemini, or a local Ollama model, preserving timing and writing language-tagged sidecars (one transcription, many languages)
- Ollama as a fourth LLM provider for keyterm generation and translation, enabling free fully-offline translation through a local OpenAI-compatible endpoint

## Completed (V2.1)

- Library-wide missing subtitle scan with async progress tracking, grouped results, and CSV export
- Scan results keyword filter with persistent exclusions across sessions
- Persistent scan results surviving page reload and browser close
- Resume scan from where you left off
- Chunked batch processing with auto-pause and cost/time estimates between chunks
- Language-aware subtitle naming (correct media-server tags instead of hardcoded `.eng.srt`)
- CI pipeline with unit tests and Docker build smoke tests on every push
- Authentication re-enabled on all API routes with explicit `DISABLE_AUTH` opt-out
- Loopback-only Docker Compose binding by default

## Completed (V2.0)

- Nova-3 transcription with 50+ language support
- Web UI with zone-based layout and dark/light themes
- LLM keyterm generation (Claude, GPT, Gemini)
- Speaker diarization and labeled transcripts
- File browser with search and global directory search
- Batch processing with Celery/Redis and real-time progress
- Subtitle detection (sidecar glob + ffprobe fallback)
- Docker deployment with health checks and resource limits
- Media server integration (Plex, Jellyfin, Emby, Bazarr)
- Cost tracking and estimation
