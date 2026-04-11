# Subgeneratorr

**AI-Powered Subtitle Generation for Plex, Jellyfin & Emby — Deepgram Nova-3 Speech-to-Text with Keyterm Prompting**

[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

**Subgeneratorr** is an open-source tool that automatically generates SRT subtitle files for your media library using [Deepgram's Nova-3](https://deepgram.com/learn/nova-3-speech-to-ai) speech-to-text API. It runs as a Docker container with a Web UI and CLI, integrates directly with Plex, Jellyfin, and Emby, and supports **keyterm prompting** — a technique that feeds character names and show-specific vocabulary to the Nova-3 model to dramatically improve transcription accuracy for proper nouns. If community subtitles don't exist for a show, Subgeneratorr generates them from the audio.

---

## Why Subgeneratorr?

I built this tool to solve a persistent problem in my media library: **hundreds of episodes missing subtitles**. While [Bazarr](https://www.bazarr.media/) does an excellent job finding subtitles for most content, there are always gaps like obscure shows, older episodes, or content that doesn't have community-contributed subtitles available.

I looked around for options with free trials but most only gave a couple hours free and then required subscription. Deepgram's $200 free signup credit offer was the best deal I could find. Their Nova-3 automatic speech recognition model produces high-quality transcriptions at ~$0.0057/minute, and adding keyterms—character names, locations, and show-specific terminology—dramatically improves accuracy for proper nouns that would otherwise be misrecognized. This creates subtitles that fill the gaps in your library without requiring intensive manual correction. It's not perfect, but it's very useful for jargon heavy dialogue.

**Subgeneratorr is for media enthusiasts** who care about complete subtitle coverage, accessibility, and having a polished library experience in Plex, Jellyfin, or Emby.

> **Disclaimer:** This is a free and open-source project. Not affiliated with Deepgram, Anthropic, OpenAI, or any other service providers.

---

## Features

- 🎯 **Deepgram Nova-3 Speech-to-Text** - Flagship STT model with General and Medical variants; state-of-the-art accuracy for media transcription
- 🔑 **Keyterm Prompting (Custom Vocabulary)** - Feed character names, locations, and show-specific terms to Nova-3; AI-powered generation via Claude, GPT, or Gemini (optional)
- 🗣️ **Speaker Diarization** - Identify speakers and create labeled transcripts
- 🌍 **Multi-Language Support** - 50+ languages with auto-detect, multilingual code-switching, and regional variants
- 🛡️ **Content Control** - Redaction (PCI/PII/numbers), profanity filtering, find & replace, dictation mode
- 🧠 **Audio Intelligence** - Sentiment analysis, summarization, topic/intent/entity detection, term search (English)
- 🐳 **Docker-Based** - Easy deployment with CLI and optional Web UI
- 📁 **Flexible Processing** - Batch process directories, specific files, or from lists
- 💰 **Cost Tracking** - Real-time estimates and detailed logs (~$0.0057/min)
- ⚡ **Smart Skipping** - Skip only when the requested outputs already exist, including auto-detect language-tagged sidecars and transcript-aware reruns
- 🔍 **Library-Wide Scan** - Find all files missing subtitles across your entire media library
- 📺 **Media Server Ready** - Auto-recognized by Plex, Jellyfin, Emby with language-tagged sidecars (`.eng.srt`, `.spa.srt`, `.und.srt`, etc.)

---

## Language Support

**50+ languages** with regional variants — English, Spanish, French, German, Japanese, Korean, Hindi, Russian, Portuguese, Arabic, and many more. Includes automatic language detection, multilingual code-switching, and keyterm prompting across all supported languages.

See the **[full language list and configuration guide](docs/languages.md)** for all supported languages and regional variants.

---

## Quick Start (~10 minutes)

### Requirements

- Docker and Docker Compose ([Linux](https://docs.docker.com/engine/install/) | [macOS](https://www.docker.com/products/docker-desktop/) | [Windows](https://www.docker.com/products/docker-desktop/))
- A Deepgram API key ([Get $200 free credits](https://console.deepgram.com/))
- Media files (MKV, MP4, AVI, MOV, MP3, WAV, FLAC, etc.)

### Installation

```bash
# Clone the repository
git clone https://github.com/tylerbcrawford/subgeneratorr.git
cd subgeneratorr

# Configure environment
cp .env.example .env
cp examples/docker-compose.example.yml docker-compose.yml

# Edit .env — set these two required values:
#   DEEPGRAM_API_KEY=your_key_here
#   MEDIA_PATH=/path/to/your/media

# Build and start
docker compose build

# Start Web UI
docker compose up -d
# Open http://localhost:5000

# OR run CLI directly
docker compose run --rm cli
```

> **Security Note:** This app exposes media paths and triggers write operations. `DISABLE_AUTH=true` is the default in the example compose — suitable for local access only. For remote/production deployments, set `DISABLE_AUTH=false` and place a reverse proxy with authentication in front of the app that forwards either `X-Auth-Request-Email` or `X-Forwarded-User` after login.

### Basic Usage

**Start the Web UI (recommended):**
```bash
docker compose up -d
# Open http://localhost:5000
```

**Process via CLI (headless/batch):**
```bash
# Process entire media library
docker compose run --rm cli

# Process specific show/season
docker compose run --rm -e MEDIA_PATH=/media/tv/ShowName/Season\ 01 cli
```

### Run Tests Locally

For the local pytest suite, you do not need Docker, Redis, or API keys.

```bash
make test
```

This bootstraps a local `.venv`, installs `requirements-dev.txt`, and runs the tests in `tests/`. The heavier CLI integration checks described in `tests/README.md` still require Docker and a Deepgram API key.

---

## Web UI

The Web UI provides a browser-based interface for remote management, batch processing, and AI-powered keyterm generation.

### Start Web UI

```bash
docker compose up -d
```

Access at `http://localhost:5000` (or configure reverse proxy for remote access)

> **Security Note:** This app exposes media paths and triggers write operations. `DISABLE_AUTH=true` is the default in the example compose — suitable for local access only. For remote/production deployments, set `DISABLE_AUTH=false` and place a reverse proxy with authentication in front of the app that forwards either `X-Auth-Request-Email` or `X-Forwarded-User` after login.

### Screenshots

<!-- Recommended: main browse page, scan results, transcription progress, settings panel -->
*Screenshots coming soon.*

### Web UI Features

- 🌐 **Remote access** from any device
- 📊 **Real-time progress tracking** with per-file status
- 🤖 **AI Keyterm Generation** with Claude, GPT, or Gemini (optional)
- 📁 **Directory browser** with search and file filtering
- ⚡ **Batch processing** with parallel workers
- 🔍 **Find Missing Subtitles** — one-click async library scan with CSV export
- ⚙️ **Full Nova-3 feature control** — model selection, redaction, dictation, multichannel, Audio Intelligence, and more via collapsible Transcription Settings panel

---

## Key Features Explained

### Why Deepgram Nova-3?

Deepgram Nova-3 is Deepgram's most accurate general-purpose speech recognition model, trained on a broad corpus of audio including media content. For subtitle generation, it outperforms alternatives on:

- **Conversational accuracy** — handles fast speech, accents, and overlapping dialogue
- **Language breadth** — 50+ languages with regional variants in a single API
- **Keyterm support** — custom vocabulary prompting available across all supported languages
- **Pricing** — ~$0.0057/minute with a $200 free credit on signup (~35,000 minutes free)

Nova-3 also offers a **Medical variant** (`nova-3-medical`) tuned for clinical terminology. For most media use cases, `nova-3` (General) is the right choice.

---

### Keyterm Prompting

This is the feature I'm most proud of. Speech-to-text models are excellent at everyday words, but they struggle with proper nouns — character names, fictional locations, made-up terminology. Without guidance, "Heisenberg" becomes "Heizenberg" and "Los Pollos Hermanos" becomes gibberish. Keyterms tell Nova-3 exactly what to listen for, and the difference in accuracy is dramatic.

Keyterms are a form of **custom vocabulary prompting** — also called keyword boosting or vocabulary hints — that influence Nova-3's recognition probabilities at decode time, not as a post-processing step. Accuracy improvements of up to 90% for prompted terms have been observed on proper nouns. The limit is 500 tokens (~20–50 focused terms per request), and keyterm support is available across all 50+ Nova-3 languages.

**Best keyterms to include:**
- Main character full names and nicknames
- Fictional place names and organization names
- Made-up terminology, brand names, or technical jargon specific to the show
- Names that sound like common words (the model will otherwise pick the common word)

**Manual CSV (full control):**
```bash
# For TV shows (at show level)
/media/tv/Breaking Bad/Transcripts/Keyterms/Breaking Bad_keyterms.csv

# Format: one term per line
Walter White
Jesse Pinkman
Heisenberg
Los Pollos Hermanos
```

**AI generation (the easy way):** Select any video file in the Web UI, click "Generate Keyterms," and an LLM reads the file path to figure out what show or movie it is. It researches the title and returns 20-50 character names, locations, and jargon — the exact terms a speech model would otherwise botch. One click per show, and the keyterms apply to every episode automatically.

The whole process takes 3-5 seconds and costs less than a penny per generation ($0.0006-$0.0064 depending on model). Gemini's free tier works well here, so you can generate keyterms for your entire library at zero cost. Supports Claude, GPT, and Gemini — see the [model benchmarks](docs/technical.md#ai-powered-generation) for detailed comparisons.

### Speaker Maps

Replace generic "Speaker 0", "Speaker 1" labels with character names in transcripts.

**Create speaker map:**
```bash
# At show level
/media/tv/Breaking Bad/Transcripts/Speakermap/speakers.csv

# CSV format
speaker_id,name
0,Walter White
1,Jesse Pinkman
```

Auto-detected when you enable transcript generation (`ENABLE_TRANSCRIPT=1`)

### Find All Missing Subtitles

When you have thousands of files across TV shows, movies, and audiobooks, you have no idea which ones actually need subtitles. Manually clicking through folders isn't realistic. This scans your entire library and tells you exactly what's missing.

The scan uses a two-phase approach. Phase 1 checks for sidecar subtitle files next to the media file — this is pure filename matching and finishes in seconds. Phase 2 uses ffprobe to detect embedded subtitle tracks inside video containers, running at ~50-100ms per file. You can skip Phase 2 for a quick scan if you only care about sidecar files.

Results come back grouped by directory, so you can see at a glance which shows or seasons need work. Select files directly from the results to send them to transcription, or export the full list as CSV. Results persist across page reloads, so you can start a scan, close your laptop, and come back to it later. For large selections, the Web UI auto-chunks files into 25-file batches with a cost summary between each so you stay in control.

**Performance:** A 4,662-file library (TV, movies, audiobooks) scans in ~6 minutes with embedded subtitle detection enabled. Skipping the embedded check (sidecar-only mode) reduces this to seconds.

---

## Configuration

### Environment Variables

Key settings in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `DEEPGRAM_API_KEY` | Deepgram API key (required) | - |
| `MEDIA_PATH` | Media directory to scan | `/media` |
| `LANGUAGE` | Language code (see supported languages above) | `en` |
| `ENABLE_TRANSCRIPT` | Generate speaker-labeled transcripts | `0` |
| `FORCE_REGENERATE` | Regenerate existing subtitles | `0` |
| `PROFANITY_FILTER` | Filter mode: `off`, `tag`, or `remove` | `off` |
| `ANTHROPIC_API_KEY` | For AI keyterm generation (optional) | - |
| `OPENAI_API_KEY` | For AI keyterm generation (optional) | - |
| `GEMINI_API_KEY` | For AI keyterm generation (optional) | - |

### Media Path Configuration

Set `MEDIA_PATH` in your `.env` file to point to your media library:

| Platform | Example |
|----------|---------|
| Linux | `MEDIA_PATH=/home/username/media` |
| macOS | `MEDIA_PATH=/Users/username/Movies` |
| Windows | `MEDIA_PATH=C:/Users/YourName/Videos` |

---

## Pricing

Deepgram Nova-3 charges ~$0.0057 per minute of audio:

- 10-minute TV episode: ~$0.06
- 45-minute episode: ~$0.26
- 90-minute movie: ~$0.51
- 100 episodes (10 min each): ~$5.70

**New users get $200 in free credits** - enough for ~35,000 minutes (~585 hours) of transcription.

---

## Documentation

- **[Technical Documentation](docs/technical.md)** - Architecture, API endpoints, advanced configuration
- **[Language Support Guide](docs/languages.md)** - Complete language matrix and multilingual features
- **[Project Roadmap](docs/roadmap.md)** - Future features and development plans

---

## Media Server Integration

Generated language-tagged `.srt` files are automatically recognized by:

- **Plex** - Recognizes external subtitles using the resolved language tag
- **Jellyfin** - Auto-detected with proper language tags
- **Emby** - Supports ISO-639-2 language codes

After generation, refresh your media library to detect new subtitles.

---

## Common Workflows

### Fill Subtitle Gaps After Bazarr

1. Let Bazarr find subtitles for most content
2. Run Subgeneratorr on your media directory (skips files with subtitles)
3. Only processes files missing subtitles
4. Refresh Plex/Jellyfin library

### Batch Process New TV Season

1. Download new season via Sonarr/Radarr
2. Run: `docker compose run --rm -e MEDIA_PATH=/media/tv/ShowName/Season\ 01 cli`
3. Subtitles generated automatically
4. Refresh your media server library to pick up new subtitles

### Complete Library Cleanup

This is where the keyterm and scan features come together — the workflow I actually use:

1. **Scan** your library for missing subtitles (gear icon → "Find All Missing Subtitles")
2. **Review** results by directory — see which shows and seasons have gaps
3. **Generate AI keyterms** for each show (one click per show, shared across all episodes)
4. **Select files** from the scan results → transcribe (keyterms auto-applied per show)
5. **Resume anytime** — scan results persist, and processed files drop off the list

You can work through it show by show over a few days, or batch everything at once. The scan doesn't need to be re-run unless you add new media.

### Generate Transcripts for Archive

1. Create keyterms CSV with character names
2. Create speaker map CSV
3. Run with transcripts enabled: `docker compose run --rm -e ENABLE_TRANSCRIPT=1 cli`
4. Get language-tagged `.srt` subtitles beside the media file plus `.transcript.speakers.txt` output in the sibling `Transcripts/` folder

---

## Frequently Asked Questions

**Q: What is keyterm prompting in Deepgram Nova-3?**  
A: Keyterm prompting (also called custom vocabulary or keyword boosting) lets you provide a list of domain-specific terms — character names, locations, made-up words — that Nova-3 prioritizes during transcription. Without keyterms, proper nouns are often misrecognized; with them, accuracy improves dramatically (up to 90% for the specific terms provided).

**Q: How much does Deepgram Nova-3 transcription cost?**  
A: Nova-3 charges approximately $0.0057 per minute of audio. New Deepgram accounts receive $200 in free credits — roughly 35,000 minutes (585 hours) of transcription. A typical 45-minute TV episode costs about $0.26.

**Q: Does Subgeneratorr work with Plex, Jellyfin, and Emby?**  
A: Yes. Subgeneratorr generates language-tagged SRT sidecar files (`.eng.srt`, `.spa.srt`, etc.) that are automatically recognized by Plex, Jellyfin, and Emby without any additional configuration. Refresh your media library after generation to pick up new subtitles.

**Q: What languages does Deepgram Nova-3 support?**  
A: Nova-3 supports 50+ languages with regional variants including English, Spanish, French, German, Japanese, Korean, Hindi, Russian, Portuguese, and Arabic. It also supports automatic language detection across 35 languages and a `multi` mode for code-switching content with up to 10 languages simultaneously.

**Q: Can I generate keyterms automatically instead of writing them manually?**  
A: Yes. The Web UI includes one-click AI keyterm generation using Claude, GPT, or Gemini. The AI infers the show or movie from the file path, researches it, and returns 20–50 character names, locations, and jargon terms in 3–5 seconds. Gemini's free tier makes this effectively zero-cost. Generated keyterms apply to all episodes in a show automatically.

**Q: How is Subgeneratorr different from Bazarr?**  
A: Bazarr finds community-contributed subtitles for popular content. Subgeneratorr *generates* subtitles from audio using AI speech recognition — it fills gaps where community subtitles don't exist (obscure shows, older episodes, foreign content). They work together: run Bazarr first, then Subgeneratorr on whatever's left.

---

## Troubleshooting

### Media Being Skipped

Files are skipped only when all requested outputs already exist. English requests use `.eng.srt`, non-English requests use the matching language tag (for example `.spa.srt`), and `multi` or unresolved auto-detect requests fall back to `.und.srt`.

In auto-detect mode, Subgeneratorr also treats an existing same-stem language-tagged sidecar like `Episode.spa.srt` as already satisfied before it starts a new Deepgram request. If subtitles already exist but the transcript is still missing, transcript-enabled runs continue and create the transcript instead of returning an early `skipped` result. Use `FORCE_REGENERATE=1` to overwrite existing outputs.

### Permission Errors (Linux)

Set `PUID` and `PGID` in `docker-compose.yml` or `.env` to match your user. The CLI, web app, and worker all write files, so keep the same values across all three services:
```bash
id -u  # Get your UID
id -g  # Get your GID
```

### API Errors

- Verify API key in `.env`
- Check account balance at [Deepgram Console](https://console.deepgram.com/)
- Ensure sufficient credits

### Keyterms Not Loading

- Check file location: `{Show}/Transcripts/Keyterms/{ShowName}_keyterms.csv`
- Verify UTF-8 encoding
- Ensure filename matches show directory name exactly

---

## Known Limitations

- **Authentication**: `DISABLE_AUTH=true` is the default for local use. For remote access, place a reverse proxy with authentication in front of the app and forward either `X-Auth-Request-Email` or `X-Forwarded-User` (see Security Note above).
- **CLI vs Web UI**: The CLI processes files synchronously and does not support AI keyterm generation, library scanning, or progress tracking. The Web UI provides all features including async batch processing, real-time progress, and AI keyterm generation.

---

## Troubleshooting

### Docker build hangs on `apt-get update`

If `docker compose build` hangs at the APT layer or containers cannot resolve external hosts from Docker's default bridge network, but `--network host` works, the problem is your Docker networking or DNS, not Subgeneratorr itself.

On Linux, you can use the included host-network override:

```bash
cp examples/docker-compose.example.yml docker-compose.yml

docker compose \
  -f docker-compose.yml \
  -f examples/docker-compose.hostnet.override.yml \
  up -d --build
```

Notes:
- This is a Linux-only workaround.
- Services run on the host network directly, so the web UI binds to `127.0.0.1:${WEB_PORT}` from the base compose file.
- The override also switches Redis access from `redis://redis:6379/0` to `redis://127.0.0.1:6379/0`.

If you prefer not to use host networking, fix Docker's bridge-network DNS on the host and then use the normal compose file.

---

## Contributing

Contributions welcome! Please feel free to submit issues or pull requests.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Support

- 📖 [Documentation](docs/)
- 💬 [GitHub Issues](https://github.com/tylerbcrawford/subgeneratorr/issues)
- 🌐 [Deepgram Community](https://discord.gg/deepgram)

---

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [Deepgram](https://deepgram.com/) - AI-powered speech recognition API
- Built with [Deepgram Python SDK](https://github.com/deepgram/deepgram-python-sdk)
- Uses [deepgram-captions](https://github.com/deepgram/deepgram-python-captions) for SRT generation
