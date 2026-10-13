"""
Shared utility functions for API route handlers.

These helpers are used by multiple route modules (dashboard, ventures, etc.)
to avoid duplication and ensure consistent behavior.
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def count_skills(kb_path: Path, sys_conf: dict) -> int:
    """Count YAML skill files in a venture's R-routines/skills/ directory."""
    routines_dir = sys_conf.get("routines_dir", "")
    if not routines_dir:
        return 0
    skills_path = kb_path / routines_dir / "skills"
    if not skills_path.exists():
        return 0
    return sum(1 for _ in skills_path.glob("*.yaml"))


def analyze_fabric(kb_path: Path, sys_conf: dict) -> dict:
    """Analyze FABRIC directory completeness for a venture."""
    fabric_dirs = {
        "F-foundations": sys_conf.get("foundations", ""),
        "A-agents": sys_conf.get("agents_dir", ""),
        "B-brain": sys_conf.get("brain_dir", ""),
        "R-routines": sys_conf.get("routines_dir", ""),
        "I-insights": sys_conf.get("insights_dir", ""),
        "C-creations": sys_conf.get("creations_dir", ""),
    }

    analysis = {}
    dirs_exist = 0
    dirs_with_content = 0
    total = len(fabric_dirs)
    for label, rel_path in fabric_dirs.items():
        full_path = kb_path / rel_path if rel_path else None
        exists = full_path is not None and full_path.exists()
        file_count = sum(1 for _ in full_path.glob("*") if _.is_file()) if exists else 0
        analysis[label] = {
            "exists": exists,
            "file_count": file_count,
        }
        if exists:
            dirs_exist += 1
            if file_count > 0:
                dirs_with_content += 1

    # completeness = structure presence; content_completeness = files present
    return {
        "directories": analysis,
        "completeness": round(dirs_exist / total * 100) if total else 0,
        "content_completeness": round(dirs_with_content / total * 100) if total else 0,
    }


#: Where a pack keeps its agent definitions (``realize_core.packs.loader``).
PACK_AGENTS_DIR = "A-agents"


def public_definition_path(sys_conf: dict, agent_key: str, kb_path: Path | None = None) -> str:
    """Where an agent's definition lives, as anyone who may see the agent may read it.

    Never an absolute server path. A venture's own agent reads its path
    relative to the KB root (``systems/acme/A-agents/writer.md``). A pack agent
    (one listed in ``agent_provenance``) reads ``<layer>:<pack ref>/<path in the
    pack>``, e.g. ``profession:developer@0.1.0/A-agents/procurement.md``: the
    pack may live outside the KB, and where it is installed on the server is
    nobody's business but the operator's.

    Args:
        sys_conf: The venture's entry in ``app.state.systems``.
        agent_key: The agent's key in ``sys_conf["agents"]``.
        kb_path: The KB root; an absolute venture path under it is made relative.

    Returns:
        The path to show, with ``/`` separators; ``""`` for an unknown agent.
    """
    stored = (sys_conf.get("agents") or {}).get(agent_key)
    if not stored:
        return ""
    path = Path(str(stored))
    provenance = (sys_conf.get("agent_provenance") or {}).get(agent_key)
    if isinstance(provenance, dict) and provenance.get("layer"):
        pack = provenance.get("pack")
        ref = f"{provenance['layer']}:{pack}" if pack else str(provenance["layer"])
        return f"{ref}/{PACK_AGENTS_DIR}/{path.name}"
    if not path.is_absolute():
        return path.as_posix()
    if kb_path is not None:
        try:
            return path.resolve().relative_to(Path(kb_path).resolve()).as_posix()
        except (OSError, ValueError):
            pass
    # Outside the KB: the file name alone, never where it sits on the server.
    return path.name


def get_agents_with_status(sys_conf: dict, venture_key: str, kb_path: Path | None = None) -> list[dict]:
    """Get agent list with current status from DB.

    ``definition_path`` is the public form (:func:`public_definition_path`), never absolute.
    """
    agents = []
    for agent_key in sys_conf.get("agents", {}):
        agent_data = {
            "key": agent_key,
            "definition_path": public_definition_path(sys_conf, agent_key, kb_path),
            "status": "idle",
            "last_run_at": None,
            "last_error": None,
        }

        try:
            from realize_core.scheduler.lifecycle import get_agent_status

            state = get_agent_status(agent_key, venture_key)
            if state:
                agent_data["status"] = state["status"]
                agent_data["last_run_at"] = state.get("last_run_at")
                agent_data["last_error"] = state.get("last_error")
        except Exception as exc:
            logger.debug("Agent status lookup failed for %s/%s: %s", agent_key, venture_key, exc)

        agents.append(agent_data)

    return agents


def get_skills(kb_path: Path, sys_conf: dict) -> list[dict]:
    """Get skill list from YAML files."""
    routines_dir = sys_conf.get("routines_dir", "")
    if not routines_dir:
        return []

    skills_path = kb_path / routines_dir / "skills"
    if not skills_path.exists():
        return []

    skills = []
    try:
        import yaml

        for yaml_file in sorted(skills_path.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data and isinstance(data, dict):
                    skills.append(
                        {
                            "name": data.get("name", yaml_file.stem),
                            "version": "v2" if "steps" in data else "v1",
                            "triggers": data.get("triggers", []),
                            "task_type": data.get("task_type", "general"),
                        }
                    )
            except Exception as exc:
                logger.debug("Failed to parse skill YAML %s: %s", yaml_file.name, exc)
    except ImportError:
        pass

    return skills


# ---------------------------------------------------------------------------
# Async wrappers — use these in route handlers to avoid blocking the event loop
# ---------------------------------------------------------------------------


async def analyze_fabric_async(kb_path: Path, sys_conf: dict) -> dict:
    """Async wrapper for analyze_fabric (filesystem I/O)."""
    return await asyncio.to_thread(analyze_fabric, kb_path, sys_conf)


async def count_skills_async(kb_path: Path, sys_conf: dict) -> int:
    """Async wrapper for count_skills (filesystem I/O)."""
    return await asyncio.to_thread(count_skills, kb_path, sys_conf)


async def get_skills_async(kb_path: Path, sys_conf: dict) -> list[dict]:
    """Async wrapper for get_skills (filesystem + YAML I/O)."""
    return await asyncio.to_thread(get_skills, kb_path, sys_conf)
