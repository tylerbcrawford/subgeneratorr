# Subgeneratorr

**Subtitle and Transcript Generation via Deepgram Nova-3**

[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Why Subgeneratorr?

I built this tool to solve a persistent problem in my media library: **hundreds of episodes missing subtitles**. While [Bazarr](https://www.bazarr.media/) does an excellent job finding subtitles for most content, there are always gaps like obscure shows, older episodes, or content that doesn't have community-contributed subtitles available.

I looked around for options with free trials but most only gave a couple hours free and then required subscription. Deepgram's $200 free signup credit offer was the best deal I could find. Their Nova-3 model produces high-quality transcriptions at ~$0.004/minute, and adding keyterms—character names, locations, and show-specific terminology—dramatically improves accuracy for proper nouns that would otherwise be misrecognized. This creates subtitles that fill the gaps in your library without requiring intensive manual correction. It's not perfect, but it's very useful for jargon heavy dialogue.

**Subgeneratorr is for media enthusiasts** who care about complete subtitle coverage, accessibility, and having a polished library experience in Plex, Jellyfin, or Emby.

> **Disclaimer:** This is a free and open-source project. Not affiliated with Deepgram, Anthropic, OpenAI, or any other service providers.

---

## Features

- 🎯 **Nova-3 Transcription** - Deepgram's flagship model with General and Medical variants
- 🔑 **LLM-Enhanced Keyterms** - AI-powered generation of character names and terminology (optional)
- 🗣️ **Speaker Diarization** - Identify speakers and create labeled transcripts
- 🌍 **Multi-Language Support** - 50+ languages with auto-detect, multilingual code-switching, and regional variants
- 🛡️ **Content Control** - Redaction (PCI/PII/numbers), profanity filtering, find & replace, dictation mode
- 🧠 **Audio Intelligence** - Sentiment analysis, summarization, topic/intent/entity detection, term search (English)
- 🐳 **Docker-Based** - Easy deployment with CLI and optional Web UI
- 📁 **Flexible Processing** - Batch process directories, specific files, or from lists
- 💰 **Cost Tracking** - Real-time estimates and detailed logs (~$0.0043/min)
- ⚡ **Smart Skipping** - Skip files that already have subtitles
- 🔍 **Library-Wide Scan** - Find all files missing subtitles across your entire media library
- 📺 **Media Server Ready** - Auto-recognized by Plex, Jellyfin, Emby (`.eng.srt` format)

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
docker compose run --profile cli --rm cli
```

### Basic Usage

**Process entire media library (CLI):**
```bash
docker compose run --profile cli --rm cli
```

**Process specific show/season:**
```bash
docker compose run --profile cli --rm -e MEDIA_PATH=/media/tv/ShowName/Season\ 01 cli
```

**Start the Web UI:**
```bash
docker compose up -d
# Open http://localhost:5000
```

---

## Web UI (Optional)

The Web UI provides a browser-based interface for remote management, batch processing, and AI-powered keyterm generation.

### Start Web UI

```bash
docker compose up -d
```

Access at `http://localhost:5000` (or configure reverse proxy for remote access)

### Web UI Features

- 🌐 **Remote access** from any device
- 📊 **Real-time progress tracking** with per-file status
- 🤖 **AI Keyterm Generation** with Claude, GPT, or Gemini (optional)
- 📁 **Directory browser** with search and file filtering
- 🔄 **Bazarr integration** for automatic subtitle rescans
- ⚡ **Batch processing** with parallel workers
- 🔍 **Find Missing Subtitles** — one-click async library scan with CSV export
- ⚙️ **Full Nova-3 feature control** — model selection, redaction, dictation, multichannel, Audio Intelligence, and more via collapsible Transcription Settings panel

---

## Key Features Explained

### Keyterm Prompting

Improve transcription accuracy by up to 90% for important terms like character names, locations, and show-specific jargon.

**Create keyterms CSV:**
```bash
# For TV shows (at show level)
/media/tv/Breaking Bad/Transcripts/Keyterms/Breaking Bad_keyterms.csv

# Format: one term per line
Walter White
Jesse Pinkman
Heisenberg
Los Pollos Hermanos
```

**Or use AI generation** (Web UI only):
- Select video → Click "Generate Keyterms"
- Supports Claude, GPT, and Gemini
- Costs ~$0.002-0.08 per generation depending on model

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

1. Open Web UI → click gear icon → "Find All Missing Subtitles"
2. Optionally skip embedded subtitle check for faster scan
3. Review results grouped by directory
4. Select files → Transcribe, or download CSV report

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

Deepgram Nova-3 charges ~$0.0043 per minute of audio:

- 10-minute TV episode: ~$0.04
- 45-minute episode: ~$0.19
- 90-minute movie: ~$0.39
- 100 episodes (10 min each): ~$4.30

**New users get $200 in free credits** - enough for ~46,000 minutes (~767 hours) of transcription.

---

## Documentation

- **[Technical Documentation](docs/technical.md)** - Architecture, API endpoints, advanced configuration
- **[Language Support Guide](docs/languages.md)** - Complete language matrix and multilingual features
- **[Project Roadmap](docs/roadmap.md)** - Future features and development plans

---

## Media Server Integration

Generated `.eng.srt` files are automatically recognized by:

- **Plex** - Shows as "English (SRT External)"
- **Jellyfin** - Auto-detected with proper language tags
- **Emby** - Supports ISO-639-2 language codes
- **Bazarr** - Use as fallback when online subtitles unavailable

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
2. Run: `docker compose run --profile cli --rm -e MEDIA_PATH=/media/tv/ShowName/Season\ 01 cli`
3. Subtitles generated automatically
4. Bazarr rescan triggers (if Web UI integration enabled)

### Generate Transcripts for Archive

1. Create keyterms CSV with character names
2. Create speaker map CSV
3. Run with transcripts enabled: `docker compose run --profile cli --rm -e ENABLE_TRANSCRIPT=1 cli`
4. Get both `.eng.srt` subtitles and `.transcript.speakers.txt` files

---

## Troubleshooting

### Videos Being Skipped

Files are skipped if `.eng.srt` already exists. Use `FORCE_REGENERATE=1` to reprocess.

### Permission Errors (Linux)

Set `PUID` and `PGID` in docker-compose.yml to match your user:
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
