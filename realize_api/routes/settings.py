"""
Settings API routes — feature flags, governance gates, system info, maintenance.
"""

import logging
import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/settings")
async def get_settings(request: Request):
    """Get current settings: features, gates, providers, system info."""
    config = getattr(request.app.state, "config", {})
    features = config.get("features", {})
    governance = config.get("governance", {})
    gates = governance.get("gates", {})

    # LLM providers
    providers = []
    try:
        from realize_core.llm.registry import get_registry

        registry = get_registry()
        for name, provider in registry._providers.items():
            providers.append(
                {
                    "name": name,
                    "available": provider.is_available(),
                    "models": provider.list_models() if provider.is_available() else [],
                }
            )
    except Exception:
        pass

    # System info
    v = sys.version_info
    data_path = Path(os.getenv("DATA_PATH", "./data"))
    db_size = 0
    try:
        db_file = data_path / "realize_ops.db"
        if db_file.exists():
            db_size = db_file.stat().st_size
    except Exception:
        pass

    kb_path = getattr(request.app.state, "kb_path", Path("."))
    kb_file_count = 0
    try:
        kb_file_count = sum(1 for _ in kb_path.rglob("*.md") if _.is_file())
    except Exception:
        pass

    return {
        "features": features,
        "gates": gates,
        "providers": providers,
        "system_info": {
            "python_version": f"{v.major}.{v.minor}.{v.micro}",
            "db_size_bytes": db_size,
            "kb_file_count": kb_file_count,
            "config_path": str(Path(os.getenv("REALIZE_CONFIG", "realize-os.yaml")).resolve()),
        },
    }


@router.put("/settings/features")
async def update_features(request: Request):
    """Update feature flags in realize-os.yaml."""
    body = await request.json()

    # Validate: all values must be boolean
    for key, val in body.items():
        if not isinstance(val, bool):
            raise HTTPException(status_code=400, detail=f"Feature '{key}' must be true or false")

    config_path = Path(os.getenv("REALIZE_CONFIG", "realize-os.yaml"))
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Config file not found")

    try:
        import yaml

        # Read existing
        original_text = config_path.read_text(encoding="utf-8")
        config = yaml.safe_load(original_text)
        if not isinstance(config, dict):
            config = {}

        if "features" not in config:
            config["features"] = {}
        config["features"].update(body)

        # Validate YAML can round-trip before writing
        new_text = yaml.dump(config, default_flow_style=False, sort_keys=False)
        yaml.safe_load(new_text)  # Validate the output parses

        config_path.write_text(new_text, encoding="utf-8")

        # Reload in-memory config
        from realize_core.config import build_systems_dict, load_config

        new_config = load_config()
        request.app.state.config = new_config
        request.app.state.systems = build_systems_dict(new_config)

        return {"status": "updated", "features": config["features"]}
    except HTTPException:
        raise
    except Exception as e:
        # Rollback on failure
        try:
            config_path.write_text(original_text, encoding="utf-8")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)[:200]}")


@router.put("/settings/gates")
async def update_gates(request: Request):
    """Update governance gates in realize-os.yaml."""
    body = await request.json()
    config_path = Path(os.getenv("REALIZE_CONFIG", "realize-os.yaml"))
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Config file not found")

    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if "governance" not in config:
            config["governance"] = {}
        if "gates" not in config["governance"]:
            config["governance"]["gates"] = {}
        config["governance"]["gates"].update(body)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        # Reload
        from realize_core.config import build_systems_dict, load_config

        new_config = load_config()
        request.app.state.config = new_config
        request.app.state.systems = build_systems_dict(new_config)

        return {"status": "updated", "gates": config["governance"]["gates"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/reindex")
async def reindex_kb(request: Request):
    """Trigger a KB re-index."""
    kb_path = getattr(request.app.state, "kb_path", Path("."))
    try:
        from realize_core.kb.indexer import index_kb_files

        count = index_kb_files(str(kb_path), force=True)
        return {"status": "reindexed", "files_indexed": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Scheduled Reports (on-demand trigger)
# ---------------------------------------------------------------------------


@router.post("/reports/morning-briefing")
async def trigger_morning_briefing(request: Request):
    """Generate a morning briefing on demand."""
    config = getattr(request.app.state, "config", {})
    systems = getattr(request.app.state, "systems", {})
    kb_path = getattr(request.app.state, "kb_path", Path("."))
    features = config.get("features", {})

    from realize_core.scheduler.reports import generate_morning_briefing

    content = await generate_morning_briefing(systems, kb_path, features)
    return {"report": "morning_briefing", "content": content}


@router.post("/reports/weekly-review")
async def trigger_weekly_review(request: Request):
    """Generate a weekly review on demand."""
    config = getattr(request.app.state, "config", {})
    systems = getattr(request.app.state, "systems", {})
    kb_path = getattr(request.app.state, "kb_path", Path("."))
    features = config.get("features", {})

    from realize_core.scheduler.reports import generate_weekly_review

    content = await generate_weekly_review(systems, kb_path, features)
    return {"report": "weekly_review", "content": content}


# ---------------------------------------------------------------------------
# Tools & Integrations
# ---------------------------------------------------------------------------


@router.get("/tools")
async def get_tools(request: Request):
    """List all registered tools with availability and action schemas."""
    tools = []
    try:
        from realize_core.tools.tool_registry import get_tool_registry

        registry = get_tool_registry()
        for tool in registry._tools.values():
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category.value if hasattr(tool.category, "value") else str(tool.category),
                    "available": tool.is_available(),
                    "actions": [s.name for s in tool.get_schemas()],
                }
            )
    except Exception:
        pass

    # Google Workspace status
    google_status = {"gmail": False, "calendar": False, "drive": False}
    try:
        from realize_core.tools.google_auth import get_credentials

        creds = get_credentials()
        if creds:
            google_status = {"gmail": True, "calendar": True, "drive": True}
    except Exception:
        pass

    # MCP status
    mcp_servers = []
    try:
        from realize_core.tools.mcp import get_mcp_hub

        hub = get_mcp_hub()
        for name, conn in hub._connections.items():
            mcp_servers.append(
                {
                    "name": name,
                    "connected": conn.connected if hasattr(conn, "connected") else False,
                    "tools_count": len(conn.tools) if hasattr(conn, "tools") else 0,
                }
            )
    except Exception:
        pass

    # Browser status
    browser_enabled = os.getenv("BROWSER_ENABLED", "false").lower() == "true"

    # Channels
    config = getattr(request.app.state, "config", {})
    channels_config = config.get("channels", [])
    channels = []
    channels.append({"name": "API", "type": "api", "enabled": True})
    for ch in channels_config:
        channels.append(
            {
                "name": ch.get("name", ch.get("type", "unknown")),
                "type": ch.get("type", "unknown"),
                "enabled": ch.get("enabled", True),
            }
        )

    return {
        "tools": tools,
        "google_workspace": google_status,
        "mcp_servers": mcp_servers,
        "browser_enabled": browser_enabled,
        "channels": channels,
    }


# ---------------------------------------------------------------------------
# LLM Routing & Usage
# ---------------------------------------------------------------------------


@router.get("/llm/routing")
async def get_llm_routing():
    """Get task classification rules and model assignments."""
    routing_rules = {
        "simple": {"model": "gemini_flash", "description": "Quick answers, FAQs, status checks"},
        "content": {"model": "claude_sonnet", "description": "Writing, content creation, analysis"},
        "complex": {"model": "claude_opus", "description": "Strategy, complex reasoning, multi-step"},
        "creative": {"model": "claude_sonnet", "description": "Creative writing, brainstorming"},
        "code": {"model": "claude_sonnet", "description": "Code generation, technical tasks"},
        "reasoning": {"model": "claude_opus", "description": "Deep analysis, decision-making"},
    }

    providers = []
    try:
        from realize_core.llm.registry import get_registry

        registry = get_registry()
        for name, provider in registry._providers.items():
            avail = provider.is_available()
            providers.append(
                {
                    "name": name,
                    "available": avail,
                    "models": provider.list_models() if avail else [],
                }
            )
    except Exception:
        pass

    return {"routing_rules": routing_rules, "providers": providers}


@router.get("/llm/usage")
async def get_llm_usage():
    """Get LLM usage statistics."""
    try:
        from realize_core.memory.store import get_usage_stats

        stats = get_usage_stats()
        return {"usage": stats}
    except Exception as e:
        return {"usage": {}, "error": str(e)}


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@router.get("/memory/search")
async def search_memory(q: str, venture: str = ""):
    """Search stored memories."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query required")
    try:
        from realize_core.memory.store import search_memories

        results = search_memories(q.strip(), system_key=venture or None, limit=20)
        return {"query": q, "results": results}
    except Exception as e:
        return {"query": q, "results": [], "error": str(e)}


@router.get("/memory/stats")
async def get_memory_stats():
    """Get memory store statistics."""
    try:
        from realize_core.memory.store import get_usage_stats

        stats = get_usage_stats()
        return {"stats": stats}
    except Exception as e:
        return {"stats": {}, "error": str(e)}


# ---------------------------------------------------------------------------
# Trust Ladder
# ---------------------------------------------------------------------------


@router.get("/trust")
async def get_trust_matrix(request: Request):
    """Get the full trust matrix with current level and all action rules."""
    config = getattr(request.app.state, "config", {})
    from realize_core.governance.trust_ladder import get_trust_matrix

    return get_trust_matrix(config)


@router.put("/trust/level")
async def update_trust_level(request: Request):
    """Update the system trust level (1-5)."""
    body = await request.json()
    level = body.get("level", 3)
    config_path = os.getenv("REALIZE_CONFIG", "realize-os.yaml")

    from realize_core.governance.trust_ladder import set_trust_level

    success = set_trust_level(config_path, level)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update trust level")

    # Reload config
    from realize_core.config import build_systems_dict, load_config

    new_config = load_config()
    request.app.state.config = new_config
    request.app.state.systems = build_systems_dict(new_config)

    return {"status": "updated", "level": level}


# ---------------------------------------------------------------------------
# Security Scanner
# ---------------------------------------------------------------------------


@router.post("/security/scan")
async def run_security_scan(request: Request):
    """Run a security scan of the system."""
    kb_path = getattr(request.app.state, "kb_path", Path("."))
    config = getattr(request.app.state, "config", {})

    from realize_core.security.scanner import run_security_scan as _scan

    results = _scan(kb_path, config)
    return results


# ---------------------------------------------------------------------------
# Skill Library
# ---------------------------------------------------------------------------


@router.get("/skills/library")
async def get_skill_library():
    """Get all available skill templates from the library."""
    from realize_core.skills.library import get_categories, get_library

    return {"skills": get_library(), "categories": get_categories()}


@router.get("/skills/library/{skill_id}")
async def get_skill_detail(skill_id: str):
    """Get a specific skill template with full YAML content."""
    from realize_core.skills.library import get_skill_template

    template = get_skill_template(skill_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    return template


@router.post("/skills/install")
async def install_skill(request: Request):
    """Install a skill template to a venture."""
    body = await request.json()
    skill_id = body.get("skill_id", "")
    venture_key = body.get("venture_key", "")

    if not skill_id or not venture_key:
        raise HTTPException(status_code=400, detail="skill_id and venture_key required")

    systems = getattr(request.app.state, "systems", {})
    kb_path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    from realize_core.skills.library import install_skill as _install

    result = _install(skill_id, kb_path, systems[venture_key])

    if not result.get("installed"):
        raise HTTPException(status_code=409, detail=result.get("error", "Install failed"))

    return result
