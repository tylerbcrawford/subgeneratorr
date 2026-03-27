FROM python:3.11-slim

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

ENTRYPOINT ["/entrypoint.sh"]

CMD ["gunicorn", "-w", "2", "-k", "gevent", "--worker-connections", "100", "-b", "0.0.0.0:5000", "app:app"]
