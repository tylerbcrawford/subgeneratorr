# Roadmap

Future enhancements under consideration. Community contributions welcome — open an issue or PR if any of these interest you.

---

## Planned

### Single-Container Option
Consolidate Redis, Flask, and Celery into a single Docker container for simpler deployment. Reduce `docker-compose.yml` to one service for users who don't need horizontal scaling.

### Local Engine (Whisper + Ollama) — in progress, targeting v3.0.0
Optional fully-local mode: swap Deepgram Nova-3 for a local Whisper engine and use Ollama for keyterm generation and translation, so nothing leaves your machine and there is no per-minute cost. The Ollama (LLM) half shipped with translation in v2.4.0; the local Whisper ASR engine (pluggable engine interface, capability-gated UI, opt-in `-local` image with a baked default model) is built on the `feat/local-engine` branch and ships as v3.0.0. GPU support and local diarization remain deferred as future tiers.

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

## Completed (V2.4)

- LLM-powered subtitle translation: translate a generated SRT into 33 target languages with Claude, GPT, Gemini, or a local Ollama model, preserving timing and writing language-tagged sidecars (one transcription, many languages)
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
