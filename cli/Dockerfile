FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/tylerbcrawford/subgeneratorr" \
      org.opencontainers.image.description="Subgeneratorr CLI — AI-powered subtitle generation for Plex, Jellyfin, and Emby" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="2.2.0"

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
