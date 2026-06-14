FROM python:3.11-slim

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

# Create non-root user
RUN useradd -u 1000 -m -s /bin/bash appuser && \
    chmod +x /entrypoint.sh

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=5 \
    CMD wget -qO- http://127.0.0.1:5000/healthz | grep -q ok || exit 1

ENTRYPOINT ["/entrypoint.sh"]

CMD ["gunicorn", "-w", "2", "-k", "gevent", "--worker-connections", "100", "-b", "0.0.0.0:5000", "app:app"]
