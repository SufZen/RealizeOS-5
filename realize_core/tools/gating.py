"""
Per-Agent Tool Gating — Filter available tools based on persona allowlist/denylist.

Provides a ``gate_tools_for_persona()`` function that filters a ToolRegistry
based on persona-defined ``tools_allowlist`` and ``tools_denylist``.

Resolution logic:
1. If ``tools_allowlist`` is non-empty → only those tools are available
2. If ``tools_denylist`` is non-empty → those tools are blocked
3. If neither is set → all tools are available (fallback)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from realize_core.agents.persona import AgentPersona
    from realize_core.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


def gate_tools_for_persona(
    all_tools: list[BaseTool],
    persona: AgentPersona | None,
) -> list[BaseTool]:
    """
    Filter tools based on persona allow/deny lists.

    Args:
        all_tools: All available tools.
        persona: The agent's persona (may be None).

    Returns:
        Filtered list of tools the agent is allowed to use.
    """
    if persona is None:
        return all_tools

    allowlist = getattr(persona, "tools_allowlist", []) or []
    denylist = getattr(persona, "tools_denylist", []) or []

    # If allowlist is defined, only those tools pass
    if allowlist:
        allowed = set(allowlist)
        filtered = [t for t in all_tools if t.name in allowed]
        blocked_count = len(all_tools) - len(filtered)
        if blocked_count:
            logger.info(
                "Tool gating for '%s': %d allowed, %d blocked (allowlist)",
                persona.name,
                len(filtered),
                blocked_count,
            )
        return filtered

    # If denylist is defined, those tools are blocked
    if denylist:
        denied = set(denylist)
        filtered = [t for t in all_tools if t.name not in denied]
        blocked_count = len(all_tools) - len(filtered)
        if blocked_count:
            logger.info(
                "Tool gating for '%s': %d allowed, %d blocked (denylist)",
                persona.name,
                len(filtered),
                blocked_count,
            )
        return filtered

    # Fallback: all tools available
    return all_tools


def get_gated_schemas(
    all_tools: list[BaseTool],
    persona: AgentPersona | None,
) -> list[dict]:
    """
    Get Claude-format tool schemas filtered by persona gating.

    This is the primary integration point: call this instead of
    ``registry.get_all_schemas()`` when persona-based gating is needed.
    """
    gated = gate_tools_for_persona(all_tools, persona)
    schemas = []
    for tool in gated:
        if tool.is_available():
            schemas.extend(tool.get_claude_schemas())
    return schemas


def check_tool_access(
    tool_name: str,
    persona: AgentPersona | None,
) -> tuple[bool, str]:
    """
    Check if a specific tool is accessible for the given persona.

    Args:
        tool_name: Name of the tool to check.
        persona: The agent's persona.

    Returns:
        (allowed, reason) tuple.
    """
    if persona is None:
        return True, "No persona defined — all tools accessible"

    allowlist = getattr(persona, "tools_allowlist", []) or []
    denylist = getattr(persona, "tools_denylist", []) or []

    if allowlist and tool_name not in allowlist:
        return False, f"Tool '{tool_name}' not in allowlist: {allowlist}"

    if denylist and tool_name in denylist:
        return False, f"Tool '{tool_name}' in denylist: {denylist}"

    return True, "Tool access permitted"
