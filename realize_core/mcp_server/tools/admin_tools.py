"""Admin / write tools — hard-gated by ``mcp.allow_admin`` + ``role=owner``.

These tools mutate global state (venture FABRIC directories, settings
files, agent registry). They are **off by default**. To expose them:

1. Set ``mcp.allow_admin: true`` in ``realize-os.yaml`` (or ``MCP_ALLOW_ADMIN=true``).
2. The caller's JWT/X-API-Key role must be ``owner``.
3. In ``REALIZE_ENV=production``, the server refuses to start unless
   ``REALIZE_JWT_ENABLED=true`` and ``REALIZE_JWT_SECRET`` is ≥ 32 chars.
   See :func:`realize_core.mcp_server.auth.validate_production_auth`.

Every admin call is audit-logged with full payload, regardless of the
``mcp.audit_full_payload`` toggle (see :func:`realize_core.mcp_server.server._audit_call`).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from realize_api.dependencies import CurrentUser

from realize_core.mcp_server.registry import MCPTool, ToolRegistry

logger = logging.getLogger(__name__)

#: Cap on venture key length (matches the REST handler).
MAX_VENTURE_KEY_LEN = 50

#: Cap on the number of feature flags settable in one call.
MAX_FEATURES_PER_CALL = 50


def _validate_venture_key(key: str) -> str | None:
    """Return an error message string if ``key`` is invalid; ``None`` if OK."""
    if not key:
        return "Venture key is required"
    if len(key) > MAX_VENTURE_KEY_LEN:
        return f"Key must be {MAX_VENTURE_KEY_LEN} characters or less"
    if not key.replace("-", "").replace("_", "").isalnum():
        return "Key must be alphanumeric (hyphens and underscores allowed)"
    return None


# ---------------------------------------------------------------------------
# create_venture
# ---------------------------------------------------------------------------

CREATE_VENTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {"type": "string", "maxLength": MAX_VENTURE_KEY_LEN},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "template": {
            "type": "string",
            "description": "Optional FABRIC template (e.g. 'real-estate'). Empty = default.",
        },
    },
    "required": ["key"],
    "additionalProperties": False,
}


async def create_venture(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Scaffold a new venture's FABRIC directory tree + register it.

    Wraps :func:`realize_core.scaffold.scaffold_venture` and refreshes
    ``app.state.systems`` so subsequent MCP calls see the new venture.
    """
    key = (args.get("key") or "").strip()
    err = _validate_venture_key(key)
    if err:
        return {"error": err, "code": "MCP_VALIDATION"}

    kb_path = getattr(app_state, "kb_path", None)
    if kb_path is None:
        return {"error": "KB root not configured", "code": "MCP_INTERNAL"}

    try:
        from realize_core.scaffold import scaffold_venture as _scaffold
    except ImportError as exc:
        return {"error": f"Scaffold module unavailable: {exc}", "code": "MCP_INTERNAL"}

    try:
        result = _scaffold(
            str(kb_path),
            key,
            name=(args.get("name") or "").strip(),
            description=(args.get("description") or "").strip(),
            template=(args.get("template") or "").strip(),
        )
    except Exception as exc:
        logger.exception("create_venture(%r) failed", key)
        return {"error": f"Scaffold failed: {exc}", "code": "MCP_INTERNAL"}

    if not result.get("created"):
        return {
            "error": result.get("error", "Venture already exists"),
            "code": "MCP_CONFLICT",
        }

    # Refresh in-memory config so the new venture is visible immediately.
    try:
        from realize_core.config import build_systems_dict, load_config

        config = load_config()
        app_state.config = config
        app_state.systems = build_systems_dict(config, Path(kb_path))
    except Exception as exc:
        logger.warning("Config refresh after create_venture failed: %s", exc)

    return {"status": "created", "key": key, "name": (args.get("name") or key)}


# ---------------------------------------------------------------------------
# delete_venture
# ---------------------------------------------------------------------------

DELETE_VENTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "venture_key": {"type": "string"},
        "confirm": {
            "type": "boolean",
            "description": "Must be true to proceed. Belt-and-suspenders gate.",
        },
    },
    "required": ["venture_key", "confirm"],
    "additionalProperties": False,
}


async def delete_venture(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Delete a venture's FABRIC directory + remove from config.

    Requires an explicit ``confirm: true`` flag — protects against
    accidental invocation by an over-eager external agent.
    """
    venture_key = (args.get("venture_key") or "").strip()
    if not venture_key:
        return {"error": "venture_key is required", "code": "MCP_VALIDATION"}
    if not args.get("confirm"):
        return {
            "error": "Refusing to delete without confirm=true",
            "code": "MCP_CONFIRMATION_REQUIRED",
        }

    systems = getattr(app_state, "systems", {}) or {}
    if venture_key not in systems:
        return {"error": f"Venture '{venture_key}' not found", "code": "MCP_NOT_FOUND"}

    kb_path = getattr(app_state, "kb_path", None)
    if kb_path is None:
        return {"error": "KB root not configured", "code": "MCP_INTERNAL"}

    try:
        from realize_core.scaffold import delete_venture as _delete
    except ImportError as exc:
        return {"error": f"Scaffold module unavailable: {exc}", "code": "MCP_INTERNAL"}

    try:
        ok = _delete(str(kb_path), venture_key, confirm_name=venture_key)
    except Exception as exc:
        logger.exception("delete_venture(%r) failed", venture_key)
        return {"error": f"Delete failed: {exc}", "code": "MCP_INTERNAL"}

    if not ok:
        return {"error": "Failed to delete venture", "code": "MCP_INTERNAL"}

    try:
        from realize_core.config import build_systems_dict, load_config

        config = load_config()
        app_state.config = config
        app_state.systems = build_systems_dict(config)
    except Exception as exc:
        logger.warning("Config refresh after delete_venture failed: %s", exc)

    return {"status": "deleted", "key": venture_key}


# ---------------------------------------------------------------------------
# update_setting (feature flags)
# ---------------------------------------------------------------------------

UPDATE_SETTING_SCHEMA = {
    "type": "object",
    "properties": {
        "features": {
            "type": "object",
            "description": "Map of feature_name -> bool. Merged into realize-os.yaml features:.",
            "additionalProperties": {"type": "boolean"},
        }
    },
    "required": ["features"],
    "additionalProperties": False,
}


async def update_setting(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Update feature flags in ``realize-os.yaml``.

    Mirrors ``PUT /api/settings/features`` — atomic write with rollback
    on YAML parse failure, then reloads the in-memory config.
    """
    features = args.get("features")
    if not isinstance(features, dict) or not features:
        return {"error": "features map is required", "code": "MCP_VALIDATION"}
    if len(features) > MAX_FEATURES_PER_CALL:
        return {
            "error": f"Too many feature flags ({len(features)}, max {MAX_FEATURES_PER_CALL})",
            "code": "MCP_VALIDATION",
        }
    if not all(isinstance(v, bool) for v in features.values()):
        return {"error": "All feature values must be boolean", "code": "MCP_VALIDATION"}

    import os

    config_path = Path(os.getenv("REALIZE_CONFIG", "realize-os.yaml"))
    if not config_path.exists():
        return {"error": "Config file not found", "code": "MCP_NOT_FOUND"}

    try:
        import yaml
    except ImportError as exc:
        return {"error": f"yaml unavailable: {exc}", "code": "MCP_INTERNAL"}

    original_text = config_path.read_text(encoding="utf-8")
    try:
        cfg = yaml.safe_load(original_text)
        if not isinstance(cfg, dict):
            cfg = {}
        cfg.setdefault("features", {}).update(features)
        new_text = yaml.dump(cfg, default_flow_style=False, sort_keys=False)
        yaml.safe_load(new_text)  # validate round-trip
        config_path.write_text(new_text, encoding="utf-8")
    except Exception as exc:
        # Rollback
        try:
            config_path.write_text(original_text, encoding="utf-8")
        except Exception:
            logger.warning("update_setting rollback failed")
        return {"error": f"Failed to update: {exc}", "code": "MCP_INTERNAL"}

    try:
        from realize_core.config import build_systems_dict, load_config

        new_cfg = load_config()
        app_state.config = new_cfg
        app_state.systems = build_systems_dict(new_cfg)
    except Exception as exc:
        logger.warning("Config refresh after update_setting failed: %s", exc)

    return {"status": "updated", "features": cfg.get("features", {})}


# ---------------------------------------------------------------------------
# reload_agents
# ---------------------------------------------------------------------------

RELOAD_AGENTS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


async def reload_agents(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Hot-reload all agents from their source directories.

    Mirrors ``POST /api/agents/reload``.
    """
    try:
        from realize_core.agents.registry import AgentRegistry
    except ImportError as exc:
        return {"error": f"Agent registry unavailable: {exc}", "code": "MCP_INTERNAL"}

    registry = getattr(app_state, "agent_registry", None)
    if registry is None:
        registry = AgentRegistry()
        systems = getattr(app_state, "systems", {}) or {}
        kb_path = getattr(app_state, "kb_path", None)
        if kb_path is not None and systems:
            for sys_key, sys_conf in systems.items():
                agents_dir = Path(kb_path) / sys_conf.get("agents_dir", f"systems/{sys_key}/A-agents")
                if agents_dir.is_dir():
                    registry.load_from_directory(agents_dir)
        app_state.agent_registry = registry

    try:
        total = registry.reload()
    except Exception as exc:
        logger.exception("reload_agents failed")
        return {"error": f"Reload failed: {exc}", "code": "MCP_INTERNAL"}

    return {
        "status": "reloaded",
        "total_agents": total,
        "source_dirs": [str(d) for d in getattr(registry, "source_dirs", [])],
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="create_venture",
        family="admin",
        description="Create a new venture with FABRIC scaffolding. Requires confirm-free admin scope.",
        input_schema=CREATE_VENTURE_SCHEMA,
        scope="owner",
        handler=create_venture,
    ),
    MCPTool(
        name="delete_venture",
        family="admin",
        description="Delete a venture and its FABRIC directories. Requires explicit confirm=true.",
        input_schema=DELETE_VENTURE_SCHEMA,
        scope="owner",
        handler=delete_venture,
    ),
    MCPTool(
        name="update_setting",
        family="admin",
        description="Update feature flags in realize-os.yaml (atomic write, rollback on YAML failure).",
        input_schema=UPDATE_SETTING_SCHEMA,
        scope="owner",
        handler=update_setting,
    ),
    MCPTool(
        name="reload_agents",
        family="admin",
        description="Hot-reload all agents from their source directories.",
        input_schema=RELOAD_AGENTS_SCHEMA,
        scope="owner",
        handler=reload_agents,
    ),
)


def register(registry: ToolRegistry) -> None:
    """Register every admin tool with the shared registry."""
    for tool in _TOOLS:
        registry.register(tool)
