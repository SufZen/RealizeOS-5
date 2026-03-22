# Self-Hosting Guide

This guide covers deploying RealizeOS V5 on your own infrastructure using Docker.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Deploy](#quick-deploy)
- [Configuration](#configuration)
- [Production Deployment](#production-deployment)
- [Reverse Proxy](#reverse-proxy)
- [Backups](#backups)
- [Monitoring](#monitoring)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Docker | 24.0+ | Latest |
| Docker Compose | v2.20+ | Latest |
| RAM | 512 MB | 2 GB |
| Disk | 1 GB | 10 GB |
| CPU | 1 core | 2+ cores |
| OS | Any with Docker | Ubuntu 22.04+ |

You also need at least one LLM API key:
- **Anthropic** (`ANTHROPIC_API_KEY`) — for Claude models
- **Google** (`GOOGLE_AI_API_KEY`) — for Gemini models

## Quick Deploy

```bash
# 1. Clone the repository
git clone https://github.com/SufZen/RealizeOS-5.git
cd RealizeOS-5

# 2. Configure environment
cp .env.example .env
# Edit .env — add your API keys

# 3. Initialize a template
python cli.py init --template consulting

# 4. Deploy
docker compose up -d

# 5. Verify
curl http://localhost:8080/health
# → {"status": "ok"}
```

The dashboard is served at `http://localhost:8080`.

## Configuration

### Environment Variables

Create a `.env` file from the provided template:

```bash
cp .env.example .env
```

Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | One of these | Claude API key |
| `GOOGLE_AI_API_KEY` | required | Gemini API key |
| `REALIZE_PORT` | No | API port (default: 8080) |
| `REALIZE_API_KEY` | Recommended | API authentication key |
| `TELEGRAM_BOT_TOKEN` | No | Enable Telegram channel |
| `BRAVE_API_KEY` | No | Enable web search |
| `GOOGLE_CLIENT_ID` | No | Google Workspace OAuth |
| `GOOGLE_CLIENT_SECRET` | No | Google Workspace OAuth |

### System Configuration

Edit `realize-os.yaml` to configure:

```yaml
# Feature flags
features:
  review_pipeline: true        # Auto-route to reviewer agent
  auto_memory: true            # Log learnings after interactions
  proactive_mode: true         # Proactive suggestions
  activity_log: true           # SQLite activity logging
  agent_lifecycle: true        # Agent status tracking
  heartbeats: false            # Scheduled agent runs
  approval_gates: false        # Human-in-the-loop approvals

# Extensions (optional)
extensions:
  - name: cron
    type: integration
    config:
      jobs: []

  - name: hooks
    type: hook
```

### Volume Mounts

Docker Compose configures these volumes:

| Volume | Host Path | Container Path | Purpose |
|--------|-----------|----------------|---------|
| `realize-data` | Docker managed | `/app/data` | SQLite DB, operational data |
| `realize-shared` | Docker managed | `/app/shared` | Shared KB content |
| bind | `./realize-os.yaml` | `/app/realize-os.yaml` | System config (read-only) |
| bind | `./systems` | `/app/systems` | Venture FABRIC directories |
| bind | `./.credentials` | `/app/.credentials` | Google OAuth (read-only) |

### Google Workspace Setup (Optional)

To enable Gmail, Calendar, Drive, and Sheets tools:

1. Create a Google Cloud project and enable the relevant APIs
2. Create OAuth 2.0 credentials (Desktop application)
3. Download `client_secrets.json` to `.credentials/`
4. Run the OAuth flow:
   ```bash
   python cli.py setup-google
   ```
5. The tokens will be saved to `.credentials/tokens.json`
6. Mount `.credentials/` in Docker Compose (already configured)

## Production Deployment

### Security Checklist

- [ ] Set a strong `REALIZE_API_KEY` in `.env`
- [ ] Restrict `CORS_ORIGINS` to your domain
- [ ] Use HTTPS via a reverse proxy (see below)
- [ ] Never expose port 8080 directly to the internet
- [ ] Keep `.env` and `.credentials/` out of version control
- [ ] Set `RATE_LIMIT_PER_MINUTE` and `COST_LIMIT_PER_HOUR_USD`
- [ ] Review and restrict Docker volume permissions

### Resource Limits

Add resource constraints to `docker-compose.yml`:

```yaml
services:
  api:
    # ... existing config ...
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "2.0"
        reservations:
          memory: 512M
          cpus: "0.5"
```

### Logging

Configure Docker logging to prevent disk fills:

```yaml
services:
  api:
    # ... existing config ...
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
```

### Telegram Bot (Optional)

Uncomment the `telegram` service in `docker-compose.yml`:

```yaml
services:
  telegram:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: realizeos-telegram
    command: python cli.py bot
    volumes:
      - realize-data:/app/data
      - realize-shared:/app/shared
      - ./realize-os.yaml:/app/realize-os.yaml:ro
      - ./systems:/app/systems
      - ./.credentials:/app/.credentials:ro
    env_file:
      - .env
    environment:
      - DATA_DIR=/app/data
      - KB_PATH=/app
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped
```

## Reverse Proxy

### Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name realize.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/realize.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/realize.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support (activity stream)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }
}
```

### Caddy

```
realize.yourdomain.com {
    reverse_proxy localhost:8080
}
```

## Backups

### Database Backup

```bash
# Backup SQLite database
docker cp realizeos-api:/app/data/realizeos.db ./backups/realizeos-$(date +%Y%m%d).db

# Or using volumes directly
docker run --rm \
  -v realizeos-data:/data \
  -v $(pwd)/backups:/backups \
  alpine cp /data/realizeos.db /backups/realizeos-$(date +%Y%m%d).db
```

### Full Backup

```bash
# Backup everything: config, systems, data
tar czf realizeos-backup-$(date +%Y%m%d).tar.gz \
  realize-os.yaml \
  .env \
  systems/ \
  .credentials/
```

### Automated Daily Backups

Add a cron job:

```bash
# crontab -e
0 2 * * * cd /path/to/RealizeOS-5 && docker cp realizeos-api:/app/data/realizeos.db backups/realizeos-$(date +\%Y\%m\%d).db
```

## Monitoring

### Health Check

```bash
curl http://localhost:8080/health
# → {"status": "ok"}
```

### Detailed Status

```bash
curl http://localhost:8080/status
# → {"status": "ok", "ventures": 3, "agents": 12, ...}
```

### Docker Logs

```bash
# Follow logs
docker compose logs -f api

# Last 100 lines
docker compose logs --tail 100 api
```

### Activity Stream (SSE)

```bash
curl -N http://localhost:8080/api/activity/stream
```

## Updating

```bash
# 1. Pull latest changes
git pull origin main

# 2. Rebuild and restart
docker compose down
docker compose build --no-cache
docker compose up -d

# 3. Verify
curl http://localhost:8080/health
```

> **Note:** Your data is safe across updates — SQLite databases and venture files are stored in Docker volumes and bind mounts, not in the container filesystem.

## Troubleshooting

### Container won't start

```bash
# Check logs for errors
docker compose logs api

# Common causes:
# - Missing .env file
# - Invalid API key
# - Port 8080 already in use (change REALIZE_PORT in .env)
```

### "No LLM providers available"

At least one API key must be set in `.env`:

```bash
# Check which providers are detected
curl http://localhost:8080/status | python -m json.tool
```

### Google Workspace tools not working

1. Verify `.credentials/client_secrets.json` exists
2. Verify `.credentials/tokens.json` exists (run OAuth flow if not)
3. Check that the credentials volume is mounted in docker-compose.yml
4. Check container logs for OAuth errors

### High memory usage

- Set resource limits (see [Resource Limits](#resource-limits))
- Reduce `RATE_LIMIT_PER_MINUTE` to limit concurrent requests
- Check for memory leaks in custom extensions

### Dashboard not loading

The dashboard static files are built into the Docker image. If the dashboard doesn't load:

```bash
# Check that static/ directory exists in the container
docker exec realizeos-api ls /app/static/

# Rebuild if needed
docker compose build --no-cache
docker compose up -d
```
