# Contributing to Subgeneratorr

Thanks for your interest in contributing! This guide covers everything you need to get started.

## Getting Started

1. **Fork** the repository
2. **Clone** your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/subgeneratorr.git
   cd subgeneratorr
   ```
3. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Set up your environment**:
   ```bash
   cp .env.example .env
   # Add your DEEPGRAM_API_KEY to .env
   docker compose build
   ```

## Development Workflow

### Running Locally

```bash
# Start Web UI + Redis + Worker
docker compose up -d redis web worker

# Run CLI tool
docker compose run --profile cli --rm cli

# View logs
docker compose logs -f web worker
```

### Making Changes

- **Backend** (`web/app.py`, `web/tasks.py`, `core/`) — Python 3.11+, Flask, Celery
- **Frontend** (`web/static/app.js`, `web/static/styles.css`) — Vanilla JS, no build tools
- **CLI** (`cli/`) — Standalone Python scripts

### Code Style

- **Python**: Follow PEP 8. Use type hints for function signatures. Docstrings for public functions.
- **JavaScript**: Vanilla JS only (no frameworks). Use `const`/`let`, never `var`. Descriptive function names.
- **CSS**: Use CSS custom properties (`var(--color-blue)`). Follow the 4px spacing grid (`--space-*` scale).
- **HTML**: Semantic elements. Include `aria-label` for interactive elements.

### Testing

```bash
# Run the full test suite (preferred — this is what CI runs)
make test

# Validate project structure (no API key needed)
python3 scripts/validate_setup.py

# Test a single video end-to-end (requires DEEPGRAM_API_KEY)
python3 tests/test_single_video.py /path/to/video.mkv
```

## Pull Requests

1. **Keep PRs focused** — one feature or fix per PR
2. **Write a clear description** — explain what changed and why
3. **Test your changes** — run `make test` to execute the full test suite
4. **Update docs** if your change affects configuration, CLI flags, or API endpoints

### PR Title Format

```
feat: add new feature
fix: resolve specific bug
docs: update documentation
style: CSS/UI changes (no logic change)
refactor: code restructuring (no behavior change)
```

## Reporting Issues

- **Bug reports**: Include steps to reproduce, expected vs actual behavior, and Docker/OS version
- **Feature requests**: Describe the use case and why it would be valuable
- **Questions**: Use GitHub Discussions if available, otherwise open an issue

## Architecture Notes

- `core/transcribe.py` is shared between CLI and Web UI — changes here affect both
- The Web UI uses Celery groups (not chords) for batch processing to allow per-task progress tracking
- Frontend is vanilla JS with no build step — edit and reload
- CSS uses a design system with custom properties defined in `:root`

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
