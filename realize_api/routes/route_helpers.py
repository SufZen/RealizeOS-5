"""
Shared utility functions for API route handlers.

These helpers are used by multiple route modules (dashboard, ventures, etc.)
to avoid duplication and ensure consistent behavior.
"""

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
    present = 0
    for label, rel_path in fabric_dirs.items():
        full_path = kb_path / rel_path if rel_path else None
        exists = full_path is not None and full_path.exists()
        file_count = sum(1 for _ in full_path.glob("*") if _.is_file()) if exists else 0
        analysis[label] = {
            "exists": exists,
            "file_count": file_count,
        }
        if exists and file_count > 0:
            present += 1

    return {
        "directories": analysis,
        "completeness": round(present / 6 * 100),
    }


def get_agents_with_status(sys_conf: dict, venture_key: str) -> list[dict]:
    """Get agent list with current status from DB."""
    agents = []
    for agent_key in sys_conf.get("agents", {}):
        agent_data = {
            "key": agent_key,
            "definition_path": sys_conf["agents"][agent_key],
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
