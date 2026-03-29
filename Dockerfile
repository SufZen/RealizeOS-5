# =============================================================================
# RealizeOS 5 — Multi-Stage Dockerfile
# =============================================================================
# Stage 1: Build dashboard (React 19 + Vite 8 + TypeScript)
# Stage 2: Python runtime with dashboard static assets
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Dashboard Build
# ---------------------------------------------------------------------------
FROM node:22-alpine AS dashboard-builder

WORKDIR /build

# Install pnpm globally
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy package manifests first for layer caching
COPY dashboard/package.json dashboard/pnpm-lock.yaml ./

# Install dependencies (cached unless lockfile changes)
RUN pnpm install --frozen-lockfile

# Copy dashboard source
COPY dashboard/ ./

# Build production bundle → outputs to dist/
RUN pnpm build

# ---------------------------------------------------------------------------
# Stage 2: Python Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Build argument: enable Google Workspace CLI tools (optional)
ARG INSTALL_GWS=false

WORKDIR /app

# System deps for native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Conditionally install Google Workspace SDK
RUN if [ "$INSTALL_GWS" = "true" ]; then \
    pip install --no-cache-dir \
        google-api-python-client>=2.100.0 \
        google-auth-oauthlib>=1.2.0; \
    fi

# Copy application code
COPY realize_core/ ./realize_core/
COPY realize_api/ ./realize_api/
COPY realize_lite/ ./realize_lite/
COPY templates/ ./templates/
COPY cli.py .
COPY .env.example .

# Copy built dashboard static assets from Stage 1
# Vite outputs to '../static' relative to the dashboard dir (see vite.config.ts)
COPY --from=dashboard-builder /static/ ./static/

# Create persistent directories
RUN mkdir -p /app/data /app/shared /app/systems

# NOTE: realize-os.yaml, shared/, systems/, and data/ are mounted at runtime
# via docker-compose volumes — they are NOT baked into the image.
# This allows users to edit config and KB files without rebuilding.

# ---------------------------------------------------------------------------
# Security: Run as non-root user
# ---------------------------------------------------------------------------
RUN groupadd --gid 1000 realize && \
    useradd --uid 1000 --gid realize --shell /bin/bash --create-home realize && \
    chown -R realize:realize /app

USER realize

# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------
EXPOSE 8080

ENV REALIZE_HOST=0.0.0.0
ENV REALIZE_PORT=8080

# Healthcheck — verify API is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default entrypoint: run the API server
CMD ["python", "-m", "uvicorn", "realize_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
