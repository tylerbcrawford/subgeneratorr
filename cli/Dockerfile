FROM python:3.11-slim

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
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-u", "generate_subtitles.py"]
