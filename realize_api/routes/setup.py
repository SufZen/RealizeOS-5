"""
Setup API routes — read/write system connections and integrations.

Endpoints:
- GET  /api/setup/connections  — list all integrations with masked values
- PUT  /api/setup/connection   — update a single connection's config
"""

import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateConnectionBody(BaseModel):
    """Request body for updating a connection."""

    id: str
    value: str


# All configurable connections with metadata
CONNECTION_DEFINITIONS = [
    # LLM Providers
    {
        "id": "anthropic",
        "name": "Claude (Anthropic)",
        "category": "llm",
        "env_key": "ANTHROPIC_API_KEY",
        "type": "secret",
        "description": "Primary AI provider — Claude Sonnet/Opus models",
        "help": "Get your key at console.anthropic.com",
    },
    {
        "id": "google_ai",
        "name": "Gemini (Google)",
        "category": "llm",
        "env_key": "GOOGLE_AI_API_KEY",
        "type": "secret",
        "description": "Google Gemini Flash/Pro models",
        "help": "Get your key at aistudio.google.com",
    },
    {
        "id": "openai",
        "name": "GPT-4 (OpenAI)",
        "category": "llm",
        "env_key": "OPENAI_API_KEY",
        "type": "secret",
        "description": "OpenAI GPT-4o models",
        "help": "Get your key at platform.openai.com",
    },
    {
        "id": "ollama",
        "name": "Ollama (Local)",
        "category": "llm",
        "env_key": "OLLAMA_BASE_URL",
        "type": "url",
        "description": "Local LLM via Ollama — no API key needed",
        "help": "Install Ollama, then set URL (default: http://localhost:11434)",
    },
    # Search & Tools
    {
        "id": "brave_search",
        "name": "Brave Search",
        "category": "tool",
        "env_key": "BRAVE_API_KEY",
        "type": "secret",
        "description": "Web search for research capabilities",
        "help": "Get your key at brave.com/search/api",
    },
    {
        "id": "browser",
        "name": "Browser Automation",
        "category": "tool",
        "env_key": "BROWSER_ENABLED",
        "type": "toggle",
        "description": "Navigate, click, extract data from web pages",
        "help": "Requires Playwright installed (pip install playwright)",
    },
    {
        "id": "mcp",
        "name": "MCP Servers",
        "category": "tool",
        "env_key": "MCP_ENABLED",
        "type": "toggle",
        "description": "Model Context Protocol — advanced tool integrations",
        "help": "Configure servers in realize-os.yaml under 'mcp:' section",
    },
    # Integrations
    {
        "id": "google_client_id",
        "name": "Google Workspace — Client ID",
        "category": "integration",
        "env_key": "GOOGLE_CLIENT_ID",
        "type": "secret",
        "description": "Gmail, Calendar, Drive integration",
        "help": "Create OAuth credentials at console.cloud.google.com",
    },
    {
        "id": "google_client_secret",
        "name": "Google Workspace — Client Secret",
        "category": "integration",
        "env_key": "GOOGLE_CLIENT_SECRET",
        "type": "secret",
        "description": "OAuth client secret for Google APIs",
        "help": "Paired with Client ID from Google Cloud Console",
    },
    {
        "id": "stripe",
        "name": "Stripe",
        "category": "integration",
        "env_key": "STRIPE_API_KEY",
        "type": "secret",
        "description": "Invoicing, payment links, subscriptions",
        "help": "Get your key at dashboard.stripe.com/apikeys",
    },
    # Channels
    {
        "id": "telegram",
        "name": "Telegram Bot",
        "category": "channel",
        "env_key": "TELEGRAM_BOT_TOKEN",
        "type": "secret",
        "description": "Chat with your AI agents via Telegram",
        "help": "Create a bot via @BotFather on Telegram",
    },
    # System
    {
        "id": "rate_limit",
        "name": "Rate Limit",
        "category": "system",
        "env_key": "RATE_LIMIT_PER_MINUTE",
        "type": "number",
        "description": "Max API requests per minute",
        "help": "Default: 30",
    },
    {
        "id": "cost_limit",
        "name": "Cost Limit",
        "category": "system",
        "env_key": "COST_LIMIT_PER_HOUR_USD",
        "type": "number",
        "description": "Max LLM spend per hour (USD)",
        "help": "Default: $5.00",
    },
]

# Env vars that cannot be changed via the API
BLOCKED_KEYS = {"REALIZE_API_KEY", "PATH", "HOME", "USER", "SHELL"}

# Build lookup
_CONN_BY_ID = {c["id"]: c for c in CONNECTION_DEFINITIONS}
_ALLOWED_ENV_KEYS = {c["env_key"] for c in CONNECTION_DEFINITIONS} - BLOCKED_KEYS


def _mask_value(value: str, conn_type: str = "secret") -> str:
    """Mask a secret value for display — show first 4 + last 3 chars."""
    if not value:
        return ""
    if conn_type == "toggle":
        return value
    if conn_type in ("url", "number"):
        return value
    if len(value) <= 8:
        return value[:2] + "..." + value[-1:]
    return value[:4] + "..." + value[-3:]


def _get_env_path() -> Path:
    """Get path to the .env file."""
    return Path(os.getenv("REALIZE_ROOT", ".")) / ".env"


def _read_env_file() -> dict[str, str]:
    """Read .env file into a dict."""
    env_path = _get_env_path()
    if not env_path.exists():
        return {}
    result = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def _write_env_value(key: str, value: str) -> None:
    """Write or update a single key in the .env file atomically."""
    env_path = _get_env_path()

    # Read existing content
    lines = []
    found = False
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                existing_key = stripped.split("=", 1)[0].strip()
                if existing_key == key:
                    lines.append(f"{key}={value}")
                    found = True
                    continue
            lines.append(line)

    if not found:
        lines.append(f"{key}={value}")

    # Atomic write
    content = "\n".join(lines) + "\n"
    env_dir = env_path.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(env_dir), suffix=".env.tmp")
    closed = False
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        closed = True
        # On Windows, need to remove target first
        if env_path.exists():
            env_path.unlink()
        Path(tmp_path).rename(env_path)
    except Exception as exc:
        logger.error("Failed to write .env key atomically: %s", exc)
        if not closed:
            try:
                os.close(fd)
            except OSError:
                pass
        Path(tmp_path).unlink(missing_ok=True)
        raise

    # Update os.environ so it takes effect immediately
    os.environ[key] = value


@router.get("/setup/connections")
async def get_connections():
    """List all configurable integrations with their current status."""
    env_values = _read_env_file()

    connections = []
    for defn in CONNECTION_DEFINITIONS:
        env_key = defn["env_key"]
        raw_value = env_values.get(env_key, "") or os.environ.get(env_key, "")
        conn_type = defn.get("type", "secret")

        # Determine if configured
        if conn_type == "toggle":
            configured = raw_value.lower() in ("true", "1", "yes")
        else:
            configured = bool(raw_value.strip())

        connections.append(
            {
                "id": defn["id"],
                "name": defn["name"],
                "category": defn["category"],
                "env_key": env_key,
                "type": conn_type,
                "configured": configured,
                "masked_value": _mask_value(raw_value, conn_type) if raw_value else None,
                "description": defn["description"],
                "help": defn.get("help", ""),
            }
        )

    # Categories in display order
    categories = ["llm", "tool", "integration", "channel", "system"]

    return {"connections": connections, "categories": categories}


@router.put("/setup/connection")
async def update_connection(body: UpdateConnectionBody, request: Request):
    """Update a single connection's configuration."""
    conn_id = body.id.strip()
    value = body.value.strip()

    if not conn_id:
        raise HTTPException(status_code=400, detail="Connection ID required")

    defn = _CONN_BY_ID.get(conn_id)
    if not defn:
        raise HTTPException(status_code=400, detail=f"Unknown connection: {conn_id}")

    env_key = defn["env_key"]
    if env_key in BLOCKED_KEYS:
        raise HTTPException(status_code=403, detail=f"Cannot modify {env_key} via this endpoint")

    if env_key not in _ALLOWED_ENV_KEYS:
        raise HTTPException(status_code=400, detail=f"Environment variable {env_key} is not configurable")

    # Write to .env
    try:
        _write_env_value(env_key, value)
    except Exception as e:
        logger.error(f"Failed to write .env: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    # Reload system config
    try:
        from realize_core.config import build_systems_dict, load_config

        new_config = load_config()
        request.app.state.config = new_config
        request.app.state.systems = build_systems_dict(new_config)
        logger.info(f"Config reloaded after updating {env_key}")
    except Exception as e:
        logger.warning(f"Config reload failed: {e}")

    conn_type = defn.get("type", "secret")
    return {
        "status": "saved",
        "id": conn_id,
        "env_key": env_key,
        "masked_value": _mask_value(value, conn_type),
        "configured": bool(value) if conn_type != "toggle" else value.lower() in ("true", "1", "yes"),
    }
