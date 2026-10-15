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
    {
        "id": "litellm",
        "name": "LiteLLM (any other provider)",
        "category": "llm",
        "env_key": "LITELLM_MODEL",
        "type": "text",
        "description": "Default model for the generic LiteLLM provider (e.g. mistral/mistral-large-latest)",
        "help": "Set the provider's own API key in .env (e.g. MISTRAL_API_KEY); LiteLLM reads it automatically",
    },
    {
        "id": "litellm_api_base",
        "name": "LiteLLM — API base URL",
        "category": "llm",
        "env_key": "LITELLM_API_BASE",
        "type": "url",
        "description": "Optional gateway or proxy URL for the generic LiteLLM provider",
        "help": "Leave empty to call the model's own provider directly",
    },
    {
        "id": "llm_primary",
        "name": "Primary LLM provider",
        "category": "llm",
        "env_key": "LLM_PRIMARY",
        "type": "text",
        "description": "Provider tried first: anthropic, gemini, openai, ollama or litellm",
        "help": "Leave empty to use the first available provider",
    },
    {
        "id": "llm_fallback",
        "name": "LLM fallback order",
        "category": "llm",
        "env_key": "LLM_FALLBACK",
        "type": "text",
        "description": "Comma-separated provider order used when the primary fails",
        "help": "Example: gemini,openai,ollama",
    },
    {
        "id": "llm_model_fast",
        "name": "Model for fast tasks",
        "category": "llm",
        "env_key": "LLM_MODEL_FAST",
        "type": "text",
        "description": "LiteLLM model string for quick, simple tasks (e.g. gemini/gemini-2.5-flash)",
        "help": "Leave empty to use the primary provider's default",
    },
    {
        "id": "llm_model_standard",
        "name": "Model for standard tasks",
        "category": "llm",
        "env_key": "LLM_MODEL_STANDARD",
        "type": "text",
        "description": "LiteLLM model string for writing and analysis (e.g. openai/gpt-4o)",
        "help": "Leave empty to use the primary provider's default",
    },
    {
        "id": "llm_model_deep",
        "name": "Model for deep tasks",
        "category": "llm",
        "env_key": "LLM_MODEL_DEEP",
        "type": "text",
        "description": "LiteLLM model string for complex reasoning (e.g. gemini/gemini-2.5-pro)",
        "help": "Leave empty to use the primary provider's default",
    },
    {
        "id": "gemini_flash_model",
        "name": "Gemini Flash model id",
        "category": "llm",
        "env_key": "GEMINI_FLASH_MODEL",
        "type": "text",
        "description": "Override the Gemini fast model id",
        "help": "Leave empty for the default",
    },
    {
        "id": "gemini_pro_model",
        "name": "Gemini Pro model id",
        "category": "llm",
        "env_key": "GEMINI_PRO_MODEL",
        "type": "text",
        "description": "Override the Gemini pro model id",
        "help": "Leave empty for the default",
    },
    {
        "id": "ollama_model",
        "name": "Ollama model",
        "category": "llm",
        "env_key": "OLLAMA_MODEL",
        "type": "text",
        "description": "Model served by Ollama (e.g. qwen3)",
        "help": "Run `ollama list` to see installed models",
    },
    {
        "id": "anthropic_workspace_id",
        "name": "Anthropic workspace ID",
        "category": "llm",
        "env_key": "ANTHROPIC_WORKSPACE_ID",
        "type": "text",
        "description": "Optional: send requests under a specific Anthropic workspace",
        "help": "Find it in console.anthropic.com under Workspaces",
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
    """Mask a secret for display: at most its last 4 characters, never its start.

    QA 5.14 D-2: the first 4 and last 3 characters were returned, which for
    many key formats is most of what identifies the key.
    """
    if not value:
        return ""
    if conn_type == "toggle":
        return value
    if conn_type in ("url", "number", "text"):
        return value
    if len(value) < 16:
        return "••••"
    return "••••" + value[-4:]


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


def _has_line_break(text: str) -> bool:
    return "\r" in text or "\n" in text


def _write_env_value(key: str, value: str) -> None:
    """Write or update a single key in the .env file atomically.

    Raises:
        ValueError: the key or value contains a line break (it would add a line to .env).
    """
    if _has_line_break(key) or _has_line_break(value):
        raise ValueError(f"{key.splitlines()[0] if key else key}: the value must not contain a line break")
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

    if _has_line_break(value):
        raise HTTPException(status_code=400, detail="The value must not contain a line break")

    # Write to .env
    try:
        _write_env_value(env_key, value)
    except Exception as e:
        logger.error(f"Failed to write .env: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    # Reload system config
    try:
        from realize_core.config_runtime import reload_app_config

        reload_app_config(request.app.state)
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
