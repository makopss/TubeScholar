# TubeScholar Dockerfile for Hugging Face Spaces & Cloud Deployment
FROM python:3.12-slim

# Install system dependencies (FFmpeg is required for audio extraction/processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set up user for Hugging Face Spaces (UID 1000)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy dependency definition
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project source files
COPY backend ./backend
COPY frontend ./frontend

# Create data directories with permissions for appuser
RUN mkdir -p data/notes data/audio data/cache && \
    chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1
ENV WEB_MODE=1
ENV PORT=7860
ENV HOST=0.0.0.0

EXPOSE 7860

# Run FastAPI backend via Uvicorn
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
