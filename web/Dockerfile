FROM python:3.11-slim AS base

LABEL org.opencontainers.image.source="https://github.com/tylerbcrawford/subgeneratorr" \
      org.opencontainers.image.description="Subgeneratorr web UI — AI-powered subtitle generation for Plex, Jellyfin, and Emby" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="2.2.0"

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg gosu wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
COPY web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared core module
COPY core/ /app/core/

# Copy web application
COPY web/app.py web/tasks.py ./
COPY web/entrypoint.sh /entrypoint.sh
COPY web/static/ ./static/
COPY web/templates/ ./templates/

# Create non-root user; strip any CRLF the entrypoint may carry from a
# Windows checkout so the Linux shebang resolves (see issue #1).
RUN useradd -u 1000 -m -s /bin/bash appuser && \
    sed -i 's/\r$//' /entrypoint.sh && \
    chmod +x /entrypoint.sh

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=5 \
    CMD wget -qO- http://127.0.0.1:5000/healthz | grep -q ok || exit 1

ENTRYPOINT ["/entrypoint.sh"]

CMD ["gunicorn", "-w", "2", "-k", "gevent", "--worker-connections", "100", "-b", "0.0.0.0:5000", "app:app"]


# ============================================================================
# -local variant (build with: docker build --target local -f web/Dockerfile .)
# Adds the faster-whisper engine and bakes the default model into the image so
# a fully-local deployment works offline from first boot. Mount a volume at
# /models to persist larger models downloaded later (a named volume seeds
# itself from the baked image content on first use).
# ============================================================================
FROM base AS local

RUN pip install --no-cache-dir "faster-whisper>=1.0,<2"

ENV ASR_ENGINE=whisper \
    WHISPER_MODEL=small \
    WHISPER_MODEL_DIR=/models \
    WHISPER_COMPUTE_TYPE=int8

# Bake the default model. download_model() only fetches files (no ctranslate2
# model load), so this also works under QEMU cross-arch builds in CI. Bake
# appuser ownership so the default PUID/PGID needs no startup chown — a
# blanket runtime chown would copy-up ~500 MB into the writable layer on
# every container recreate (overlayfs).
RUN python -c "from faster_whisper import download_model; download_model('small', cache_dir='/models')" && \
    chown -R appuser:appuser /models && \
    chmod -R a+rX /models


# Lean default image — this stage is last so an untargeted `docker build`
# produces the Deepgram-only image, unchanged in size for existing users.
FROM base AS default
