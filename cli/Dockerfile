FROM python:3.11-slim AS base

LABEL org.opencontainers.image.source="https://github.com/tylerbcrawford/subgeneratorr" \
      org.opencontainers.image.description="Subgeneratorr CLI — headless batch subtitle generation for Plex, Jellyfin, and Emby (Deepgram Nova-3 or local Whisper)" \
      org.opencontainers.image.licenses="MIT"

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg gosu && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
COPY cli/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared core module
COPY core/ /app/core/

# Copy CLI application
COPY cli/config.py cli/generate_subtitles.py cli/transcript_generator.py ./
COPY cli/entrypoint.sh /entrypoint.sh
# Strip any CRLF the entrypoint may carry from a Windows checkout so the
# Linux shebang resolves (see issue #1).
RUN sed -i 's/\r$//' /entrypoint.sh && \
    chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-u", "generate_subtitles.py"]


# ============================================================================
# -local variant (build with: docker build --target local -f cli/Dockerfile .)
# Adds the faster-whisper engine and bakes the default model into the image so
# ASR_ENGINE=whisper works offline from first run (mirrors web/Dockerfile).
# ============================================================================
FROM base AS local

RUN pip install --no-cache-dir "faster-whisper>=1.0,<2"

ENV ASR_ENGINE=whisper \
    WHISPER_MODEL=small \
    WHISPER_MODEL_DIR=/models \
    WHISPER_COMPUTE_TYPE=int8

# Bake the default model. download_model() only fetches files (no ctranslate2
# model load), so this also works under QEMU cross-arch builds in CI. Bake
# uid/gid 1000 ownership so the default PUID/PGID needs no startup chown.
RUN python -c "from faster_whisper import download_model; download_model('small', cache_dir='/models')" && \
    chown -R 1000:1000 /models && \
    chmod -R a+rX /models


# Lean default image — this stage is last so an untargeted `docker build`
# produces the Deepgram-only image, unchanged in size for existing users.
FROM base AS default
