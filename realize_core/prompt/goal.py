"""
Workspace Goal Injection — Venture-level goal prepended to every agent prompt.

Goals can be defined in two ways (resolution order):
1. ``GOAL.md`` file in the venture's FABRIC directory root
2. ``goal`` field in the venture config YAML

The goal provides high-level strategic direction for all agents operating
within a venture, ensuring alignment across the entire AI team.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_goal(
    kb_path: Path,
    system_config: dict,
    system_key: str,
    max_chars: int = 2000,
) -> str:
    """
    Load the venture goal from GOAL.md or venture config.

    Resolution order:
    1. ``GOAL.md`` file in the venture's root FABRIC directory
    2. ``goal`` field in the system config

    Args:
        kb_path: Root knowledge base path.
        system_config: System/venture configuration dict.
        system_key: System identifier.
        max_chars: Maximum characters to include from GOAL.md.

    Returns:
        Goal text, or empty string if no goal is defined.
    """
    # 1. Try GOAL.md file
    goal_text = _load_goal_file(kb_path, system_config, max_chars)
    if goal_text:
        logger.debug("Loaded goal from GOAL.md for system '%s'", system_key)
        return goal_text

    # 2. Try config field
    goal_field = system_config.get("goal", "")
    if goal_field:
        logger.debug("Loaded goal from config field for system '%s'", system_key)
        if len(goal_field) > max_chars:
            goal_field = goal_field[:max_chars] + "\n\n[...truncated]"
        return goal_field.strip()

    logger.debug("No goal found for system '%s'", system_key)
    return ""


def _load_goal_file(
    kb_path: Path,
    system_config: dict,
    max_chars: int,
) -> str:
    """Try to load GOAL.md from the venture's FABRIC directory."""
    # Determine the venture root directory
    # Try common directory keys from system_config
    for dir_key in ["fabric_dir", "root_dir", "base_dir"]:
        base_dir = system_config.get(dir_key)
        if base_dir:
            goal_path = kb_path / base_dir / "GOAL.md"
            if goal_path.exists():
                return _read_goal(goal_path, max_chars)

    # Fallback: try systems/<key>/GOAL.md
    for pattern in [
        f"systems/{system_config.get('key', '')}/GOAL.md",
        f"systems/{system_config.get('name', '')}/GOAL.md",
    ]:
        goal_path = kb_path / pattern
        if goal_path.exists():
            return _read_goal(goal_path, max_chars)

    return ""


def _read_goal(path: Path, max_chars: int) -> str:
    """Read a GOAL.md file with truncation."""
    try:
        content = path.read_text(encoding="utf-8").strip()
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[...truncated]"
        return content
    except Exception as e:
        logger.warning("Failed to read goal file %s: %s", path, e)
        return ""


def goal_to_prompt(goal_text: str, system_name: str = "") -> str:
    """
    Format goal text as a prompt layer.

    Args:
        goal_text: Raw goal text.
        system_name: Optional venture name for context.

    Returns:
        Formatted prompt section, or empty string if no goal.
    """
    if not goal_text:
        return ""

    header = "## Venture Goal"
    if system_name:
        header += f" — {system_name}"

    return f"{header}\n{goal_text}"
