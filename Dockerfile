FROM python:3.12-slim

WORKDIR /app

# System deps for Playwright (optional, only if browser tools enabled)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY realize_core/ ./realize_core/
COPY realize_api/ ./realize_api/
COPY realize_lite/ ./realize_lite/
COPY templates/ ./templates/
COPY cli.py .
COPY .env.example .

# Create data directory for SQLite persistence
RUN mkdir -p /app/data

# NOTE: realize-os.yaml, shared/, and systems/ are mounted at runtime
# via docker-compose volumes — they are NOT copied during build.
# This allows users to edit their config and KB files without rebuilding.

# Expose API port
EXPOSE 8080

# Default: run the API server
ENV REALIZE_HOST=0.0.0.0
ENV REALIZE_PORT=8080

CMD ["python", "-m", "uvicorn", "realize_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
