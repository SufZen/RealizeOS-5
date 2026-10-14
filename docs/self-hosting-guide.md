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

You also need one LLM provider; any one is enough, and every feature works on all of them:
- **Anthropic** (`ANTHROPIC_API_KEY`) — Claude models
- **Google** (`GOOGLE_AI_API_KEY`) — Gemini models
- **OpenAI** (`OPENAI_API_KEY`) — GPT models
- **Ollama** (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`) — local models, **no API key**
- Anything else [LiteLLM](https://docs.litellm.ai) supports (`LITELLM_MODEL`)

## Quick Deploy

```bash
# 1. Clone the repository
git clone https://github.com/SufZen/RealizeOS-5.git
cd RealizeOS-5

# 2. Configure environment
cp .env.example .env
# Edit .env — set any one LLM provider (a key, or a local Ollama)

# 3. Initialize a template
realize-os init --template consulting

# 4. Deploy
docker compose up -d

# 5. Verify
curl http://localhost:8080/api/health
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
| `ANTHROPIC_API_KEY` | One provider needed | Claude API key |
| `GOOGLE_AI_API_KEY` | One provider needed | Gemini API key |
| `OPENAI_API_KEY` | One provider needed | OpenAI API key |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | One provider needed | Local Ollama, no key (`OLLAMA_HOST` also works) |
| `LLM_PRIMARY`, `LLM_FALLBACK`, `LLM_MODEL_FAST` / `_STANDARD` / `_DEEP` | No | Which provider is tried first, the fallback order, and the model per task size. See [configuration.md](configuration.md#llm-routing) |
| `KB_EMBED_MODEL` | No | Embedding model for knowledge-base search; `none` turns it off |
| `REALIZE_PORT` | No | API port (default: 8080) |
| `REALIZE_API_KEY` | Recommended | API authentication key |
| `REALIZE_JWT_ENABLED` | No | Enable JWT authentication (`true`/`false`) |
| `REALIZE_JWT_SECRET` | If JWT on | JWT signing secret (min 32 chars) |
| `REALIZE_AUDIT_LOG_DIR` | No | Directory for persistent audit logs |
| `RATE_LIMIT_PER_MINUTE` | No | API rate limit (default: 60) |
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

### Developer Mode (Optional)

Developer Mode enables integration with AI coding tools for system development and extension authoring. Add this section to `realize-os.yaml` to configure:

```yaml
developer_mode:
  enabled: false
  tools: [claude_desktop, claude_code_cli, gemini_cli, antigravity, vscode, cursor, windsurf, codex, aider]
  protection_level: standard   # strict | standard | relaxed
  auto_snapshot: true
  cost_optimization:
    use_local_models: false
    review_with: gemini-flash
    cache_embeddings: true
```

Protection levels control which files AI tools may modify:

| Level | Description |
|-------|-------------|
| `strict` | All core + config files read-only to AI tools |
| `standard` | Core engine protected, config editable with auto-backup |
| `relaxed` | Only security/DB files protected, everything else open |

See [Developer Mode in the API reference](api-reference.md#developer-mode) for the endpoints.

### Storage & Backup (Optional)

Configure cloud storage for backup and sync:

```bash
# In .env
STORAGE_PROVIDER=s3              # 'local' (default) or 's3'
S3_BUCKET=my-realizeos-backup
S3_REGION=us-east-1
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_ENDPOINT_URL=                 # Leave empty for AWS S3
STORAGE_SYNC_ENABLED=false
```

Supported S3-compatible providers:
- **AWS S3** — Leave endpoint empty
- **MinIO** (self-hosted) — `http://localhost:9000`
- **DigitalOcean Spaces** — `https://{region}.digitaloceanspaces.com`
- **Backblaze B2** — `https://s3.{region}.backblazeb2.com`
- **Cloudflare R2** — `https://{account_id}.r2.cloudflarestorage.com`

You can also configure storage from the Dashboard under **Settings → Storage & Backup**.

### Volume Mounts

Docker Compose configures these volumes:

| Volume | Host Path | Container Path | Purpose |
|--------|-----------|----------------|---------|
| `realize-data` | Docker managed | `/app/data` | SQLite DB, operational data |
| `realize-shared` | Docker managed | `/app/shared` | Shared KB content |
| bind | `./realize-os.yaml` | `/app/realize-os.yaml` | System config (read-only) |
| bind | `./systems` | `/app/systems` | Venture FABRIC directories |
| bind | `./.credentials` | `/app/.credentials` | Google OAuth (read-only) |
| bind (optional) | `./packs-custom` | `/app/packs-custom` | Your own or modified packs, with `REALIZE_PACKS_PATH=/app/packs-custom` |

Everything RealizeOS writes lives under `DATA_PATH` (`/app/data`): `memory.db`, the operational database `realize_data.db` (sign-in sessions, approvals, MCP OAuth), `synapse/` (FABRIC index and Dream Inbox), `packs/verification.json` (pack verification levels raised by approvals) and the audit log.

The application folder, including the shipped profession and market packs in `/app/packs`, is read-only in the production image; approving a pack's verification never writes there. For your own packs, or a modified copy of a shipped pack, mount a writable folder and point `REALIZE_PACKS_PATH` at it (packs there win over shipped ones with the same id; see [packs.md](packs.md#where-packs-come-from)):

```yaml
    volumes:
      - ./packs-custom:/app/packs-custom
    environment:
      - REALIZE_PACKS_PATH=/app/packs-custom
```

The storage export includes `DATA_PATH/packs/verification.json`, the `REALIZE_PACKS_PATH` folder and a `packs-inventory.json` to check a restore with `python cli.py packs inventory --compare packs-inventory.json` (see [Move to another server](#move-to-another-server-export-and-restore)). The KB index `kb_index.db` stays next to the knowledge base when that folder is writable and moves to `DATA_PATH` otherwise. Set `REALIZE_DB_PATH` to put the operational database somewhere else.

Upgrading from 5.14 or earlier: an existing `realize_data.db` in the working directory or `.synapse/` in the KB root keeps being used (the log warns if it isn't on `DATA_PATH`). To move it, stop the container, copy it into the data volume, and remove the old copy.

### Google Workspace Setup (Optional)

To enable Gmail, Calendar, Drive, and Sheets tools:

1. Create a Google Cloud project and enable the relevant APIs
2. Create OAuth 2.0 credentials (Desktop application)
3. Download `client_secrets.json` to `.credentials/`
4. Run the OAuth flow (from the project root):
   ```bash
   python scripts/google_signin.py
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
- [ ] Enable JWT authentication for multi-user deployments
- [ ] Configure audit logging for compliance
- [ ] Run the security scanner to verify posture

### Security Configuration

RealizeOS V5 includes a layered security system with middleware, RBAC, JWT authentication, and audit logging.

#### JWT Authentication (Optional)

Enable JWT for token-based authentication:

```bash
# In .env
REALIZE_JWT_ENABLED=true
REALIZE_JWT_SECRET=your-very-long-random-secret-at-least-32-characters
```

When enabled, the system provides:
- `POST /api/auth/token` — generate access + refresh token pair
- `POST /api/auth/refresh` — refresh an expired access token
- `GET /api/auth/me` — verify current token and return claims

> **Note**: Use a secret of at least 32 characters. The security scanner flags short secrets.

#### RBAC (Role-Based Access Control)

Built-in roles:

| Role | Description |
|------|-------------|
| `owner` | Full access to all operations |
| `admin` | Full access except user management |
| `operator` | Can execute agents and approve pipelines |
| `user` | Standard read/write, no admin or execution |
| `viewer` | Read-only access |
| `guest` | Minimal read-only access |

Custom roles can be defined in YAML:

```yaml
# config/custom-roles.yaml
roles:
  content-creator:
    description: Content generation only
    permissions:
      - system:read
      - content:generate
      - content:publish
    system_scopes:
      - my-venture
```

#### Audit Logging

Enable persistent audit logging:

```bash
# In .env
REALIZE_AUDIT_LOG_DIR=./data/audit
```

Audit events are written as JSONL files and include:
- User login/logout events
- Access denied attempts
- Prompt injection detections
- Token creation/refresh events
- Configuration changes

View audit events from the dashboard under **Settings → Security → Audit Log**.

#### Security Middleware Stack

The API uses four middleware layers (processed in order):

1. **Rate Limiter** — configurable per-minute request limits
2. **Injection Guard** — scans requests for prompt injection patterns
3. **Audit Logger** — records all API interactions
4. **JWT Auth** (optional) — validates Bearer tokens

#### Security Scanner

Run the built-in security scanner to check your configuration:

```bash
python -c "from realize_core.security.scanner import run_security_scan; from pathlib import Path; r = run_security_scan(Path('.')); print(f'Score: {r[\"passed\"]}/{r[\"total\"]} checks passed')"
```

The scanner checks:
- API key configuration
- LLM provider key security
- JWT configuration strength
- Audit logging setup
- RBAC module availability
- Injection guard status
- Middleware stack registration
- Storage configuration
- Database file permissions

View full results in the dashboard under **Settings → Security**.

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
      - DATA_PATH=/app/data
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

### Export (the complete backup)

**Settings → Storage & Backup → Export**, or from the server:

```bash
curl -fsS -X POST -H "X-API-Key: $REALIZE_API_KEY" -o realizeos-export-$(date +%Y%m%d).zip \
  http://localhost:8080/api/storage/export
```

The ZIP holds `realize-os.yaml`, `systems/`, `shared/`, consistent snapshots of the databases (`data/memory.db`, `data/realize_data.db`, `data/synapse/`), the pack verification state (`data/packs/verification.json`), your `REALIZE_PACKS_PATH` folder (`custom-packs/`) and `packs-inventory.json`. It never holds `.env`, `users.yaml` or `.credentials/`, and the dashboard sign-in sessions are removed from the database snapshot, so the ZIP can't be used to sign in to the running server. Agent tokens travel as hashes only. Keep the ZIP private all the same: it is the whole brain of your ventures. It is built in `/tmp`, which is all the production container needs.

Back up `.env`, `users.yaml` and `.credentials/` separately, somewhere as safe as the secrets they are.

### Move to another server: export and restore

1. Export on the old server (above).
2. On the new server, restore into a new or empty folder. Nothing is overwritten; an archive with anything outside an export's layout is refused before anything is written:

   ```bash
   python cli.py storage restore realizeos-export-20261013.zip --directory /srv/realizeos
   ```

3. Copy `.env`, `users.yaml` and `.credentials/` from the old server into `/srv/realizeos`.
4. Run RealizeOS from `/srv/realizeos` with `DATA_PATH=/srv/realizeos/data` and, if the export had custom packs, `REALIZE_PACKS_PATH=/srv/realizeos/custom-packs`. With Docker, use the folder's `realize-os.yaml`, `systems/` and `custom-packs/` as the compose bind mounts (`./realize-os.yaml`, `./systems`, `./packs-custom`), and copy `data/` and `shared/` into the named volumes before the first start, owned by the container's user (uid 1000):

   ```bash
   docker run --rm --user 0:0 -v realizeos-data:/app/data -v /srv/realizeos/data:/from:ro \
     ghcr.io/sufzen/realizeos-5 sh -c 'cp -a /from/. /app/data/ && chown -R 1000:1000 /app/data'
   docker run --rm --user 0:0 -v realizeos-shared:/app/shared -v /srv/realizeos/shared:/from:ro \
     ghcr.io/sufzen/realizeos-5 sh -c 'cp -a /from/. /app/shared/ && chown -R 1000:1000 /app/shared'
   ```

5. Check that the new installation resolves the same packs, levels and rules (exit code 1 lists each difference):

   ```bash
   python cli.py packs inventory --kb /srv/realizeos --compare /srv/realizeos/packs-inventory.json
   # Docker:
   docker compose -f docker-compose.prod.yml exec -T api python cli.py packs inventory --compare /dev/stdin \
     < /srv/realizeos/packs-inventory.json
   ```

People sign in again on the new server. Approvals, decisions, skill runs, agent tokens and conversations come back as they were. `tests/test_export_restore.py` runs this whole round trip (export through the API, `storage restore`, `packs inventory --compare`) in CI, and checks that no secret is in the ZIP.

### Database files

The databases live in the data volume (`DATA_PATH`): `realize_data.db` (approvals, sessions, agent tokens, decisions queue), `memory.db` (conversations) and `synapse/`. Copying a live SQLite file can catch it mid-write; prefer the export, or stop the container first:

```bash
docker compose -f docker-compose.prod.yml stop api
docker run --rm -v realizeos-data:/data:ro -v $(pwd)/backups:/backups alpine \
  tar czf /backups/realizeos-data-$(date +%Y%m%d).tgz -C /data .
docker compose -f docker-compose.prod.yml start api
```

### Automated Daily Backups

Add a cron job that saves the export:

```bash
# crontab -e
0 2 * * * cd /path/to/RealizeOS-5 && . ./.env && curl -fsS -X POST -H "X-API-Key: $REALIZE_API_KEY" -o backups/realizeos-export-$(date +\%Y\%m\%d).zip http://localhost:8080/api/storage/export
```

## Monitoring

### Health Check

```bash
curl http://localhost:8080/api/health
# → {"status": "ok"}
```

A required store that failed to start (the operational database) returns **503** `{"status": "unavailable", "failed": ["operational_db"]}`; an optional one (Synapse) returns `{"status": "degraded", ...}` with 200. Point your monitor at this endpoint.

### Detailed Status

```bash
curl -H "X-API-Key: $REALIZE_API_KEY" http://localhost:8080/api/status
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
curl http://localhost:8080/api/health
```

### Update & Migration Scripts (Windows)

For Windows installations (non-Docker), RealizeOS includes utility scripts:

```bash
# Update to latest version (backs up data, downloads update, restores)
Update-RealizeOS.bat

# Migrate data from a previous installation
Migrate-RealizeOS.bat

# Clean uninstall (optionally preserves user data)
Uninstall-RealizeOS.bat
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

At least one provider must be configured in `.env`: an API key (`ANTHROPIC_API_KEY`, `GOOGLE_AI_API_KEY`, `OPENAI_API_KEY`), or a reachable Ollama (`OLLAMA_BASE_URL`, no key needed):

```bash
# Check which providers are detected
curl -H "X-API-Key: $REALIZE_API_KEY" http://localhost:8080/api/status | python -m json.tool
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
