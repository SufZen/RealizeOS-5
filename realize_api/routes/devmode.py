"""
Developer Mode API endpoints.

Provides dashboard access to Developer Mode features:
  - Status/toggle
  - Context file generation
  - Health check
  - Git snapshots
  - AI modification history
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/devmode", tags=["Developer Mode"])


class DevModeToggle(BaseModel):
    """Toggle request for developer mode."""

    enabled: bool
    protection_level: str = "standard"
    acknowledged: bool = False


class SetupRequest(BaseModel):
    """Request to generate context files."""

    tools: list[str] | None = None
    protection_level: str = "standard"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_root() -> Path:
    """Get the project root directory."""
    return Path.cwd()


def _load_devmode_state(root: Path) -> dict[str, Any]:
    """Load developer mode state from realize-os.yaml."""
    import yaml

    config_path = root / "realize-os.yaml"
    if not config_path.exists():
        return {"enabled": False, "protection_level": "standard"}

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return data.get("developer_mode", {"enabled": False, "protection_level": "standard"})


def _save_devmode_state(root: Path, state: dict[str, Any]) -> None:
    """Save developer mode state to realize-os.yaml."""
    import yaml

    config_path = root / "realize-os.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    data["developer_mode"] = state
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_devmode_status(request: Request) -> dict[str, Any]:
    """Get developer mode status, connected tools, and last snapshot."""
    root = _get_root()
    state = _load_devmode_state(root)

    # Detect which AI tool context files exist
    from realize_core.devmode.protection import FileProtection

    tools_config = FileProtection.get_supported_tools()
    connected_tools = []
    for key, tool_info in tools_config.items():
        ctx_file = tool_info.get("context_file", "")
        if ctx_file and (root / ctx_file).exists():
            connected_tools.append({
                "key": key,
                "name": tool_info["name"],
                "context_file": ctx_file,
                "active": True,
            })

    # Get latest snapshot
    last_snapshot = None
    try:
        from realize_core.devmode.git_safety import GitSafety

        git = GitSafety(root)
        snapshots = git.list_snapshots()
        if snapshots:
            last_snapshot = {
                "tag": snapshots[0].tag,
                "timestamp": snapshots[0].timestamp,
                "message": snapshots[0].message,
            }
    except Exception as exc:
        logger.debug("Git snapshot lookup failed: %s", exc)

    # Protection level info
    from realize_core.devmode.protection import FileProtection as FP

    levels = FP.available_levels()

    return {
        "enabled": state.get("enabled", False),
        "protection_level": state.get("protection_level", "standard"),
        "available_levels": levels,
        "connected_tools": connected_tools,
        "last_snapshot": last_snapshot,
    }


@router.put("/toggle")
async def toggle_devmode(body: DevModeToggle) -> dict[str, str]:
    """Enable or disable developer mode."""
    root = _get_root()

    if body.enabled and not body.acknowledged:
        return {
            "status": "error",
            "message": "You must acknowledge the risks before enabling Developer Mode.",
        }

    state = _load_devmode_state(root)
    state["enabled"] = body.enabled
    state["protection_level"] = body.protection_level
    _save_devmode_state(root, state)

    # Auto-snapshot on enable
    if body.enabled:
        try:
            from realize_core.devmode.git_safety import GitSafety

            git = GitSafety(root)
            if git.is_git_repo():
                git.create_snapshot(label="Developer Mode activated", tool="dashboard")
        except Exception as e:
            logger.warning("Failed to create snapshot: %s", e)

    action = "enabled" if body.enabled else "disabled"
    return {"status": "ok", "message": f"Developer Mode {action} (level: {body.protection_level})"}


@router.post("/setup")
async def setup_context_files(body: SetupRequest) -> dict[str, Any]:
    """Generate AI tool context files."""
    root = _get_root()

    from realize_core.devmode.context_generator import generate_all

    generated = generate_all(
        root=root,
        level=body.protection_level,
        tools=body.tools,
    )

    return {
        "status": "ok",
        "generated": [str(p.relative_to(root)) for p in generated],
        "count": len(generated),
    }


@router.post("/check")
async def run_health_check_api() -> dict[str, Any]:
    """Run system health check."""
    root = _get_root()

    from realize_core.devmode.health_check import CheckStatus, run_health_check

    results = run_health_check(root, quick=True)

    return {
        "status": "ok",
        "checks": [
            {
                "name": r.name,
                "status": r.status,
                "icon": r.icon,
                "message": r.message,
                "details": r.details,
            }
            for r in results
        ],
        "summary": {
            "passed": sum(1 for r in results if r.status == CheckStatus.PASS),
            "warnings": sum(1 for r in results if r.status == CheckStatus.WARN),
            "failures": sum(1 for r in results if r.status == CheckStatus.FAIL),
        },
    }


@router.post("/snapshot")
async def create_snapshot(label: str = "Manual snapshot") -> dict[str, str]:
    """Create a git safety snapshot."""
    root = _get_root()

    from realize_core.devmode.git_safety import GitSafety

    git = GitSafety(root)
    if not git.is_git_repo():
        return {"status": "error", "message": "Not a git repository"}

    tag = git.create_snapshot(label=label, tool="dashboard")
    return {"status": "ok", "tag": tag, "message": f"Snapshot created: {tag}"}


@router.get("/history")
async def get_modification_history() -> dict[str, Any]:
    """Get recent AI modification snapshots."""
    root = _get_root()

    from realize_core.devmode.git_safety import GitSafety

    git = GitSafety(root)
    if not git.is_git_repo():
        return {"snapshots": []}

    snapshots = git.list_snapshots()
    return {
        "snapshots": [
            {"tag": s.tag, "timestamp": s.timestamp, "message": s.message}
            for s in snapshots[:20]
        ]
    }


@router.get("/protection")
async def get_protection_map() -> dict[str, Any]:
    """Get the file protection tier map."""
    root = _get_root()
    state = _load_devmode_state(root)
    level = state.get("protection_level", "standard")

    from realize_core.devmode.protection import FileProtection

    fp = FileProtection(level=level, root=root)
    tiers = fp.get_all_tiers()

    return {
        "level": level,
        "description": fp.level_description,
        "tiers": {
            "protected": tiers.get("protected", []),
            "guarded": tiers.get("guarded", []),
            "open": tiers.get("open", []),
        },
    }
