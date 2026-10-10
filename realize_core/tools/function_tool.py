"""
FunctionMapTool — expose a module of plain async tool functions as a BaseTool.

Several integrations (Google Workspace, Sheets, ClickUp, browser) predate the
Tool SDK: they ship a list of Claude-format schemas, a ``name -> coroutine``
map and a set of write actions. This adapter registers them with the
:class:`~realize_core.tools.tool_registry.ToolRegistry` unchanged, so they go
through the registry's single dispatch point (and therefore the governance
gate) instead of being called directly.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

logger = logging.getLogger(__name__)

#: Cap on the text handed back to the model for one tool call.
MAX_OUTPUT_CHARS = 12_000


def render_output(result: Any) -> str:
    """Render a tool function's return value as model-readable text.

    Strings pass through; anything else is JSON (UTF-8 kept readable, so
    Hebrew/Portuguese content isn't turned into ``\\u`` escapes).
    """
    if isinstance(result, str):
        text = result
    else:
        text = json.dumps(result, ensure_ascii=False, default=str, indent=1)
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + "\n[...truncated]"
    return text


def _error_of(result: Any) -> str | None:
    """Return the error message if a tool function reported one in-band."""
    if isinstance(result, dict) and result.get("error"):
        return str(result["error"])
    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict) and result[0].get("error"):
        return str(result[0]["error"])
    return None


class FunctionMapTool(BaseTool):
    """A BaseTool backed by Claude-format schemas and a function map.

    Args:
        name: Registry tool name (e.g. ``"google_workspace"``).
        description: Human-readable summary.
        category: Tool category.
        schemas: Claude-format dicts (``name``, ``description``, ``input_schema``).
        functions: Action name → async callable taking the schema's params.
        write_actions: Actions that modify external state (gated / need approval).
        availability: Zero-arg callable telling whether the integration is usable.
        requires_auth: Whether the actions need configured credentials.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        category: ToolCategory,
        schemas: Iterable[dict[str, Any]],
        functions: dict[str, Callable[..., Awaitable[Any]]],
        write_actions: Iterable[str] = (),
        availability: Callable[[], bool] = lambda: True,
        requires_auth: bool = False,
    ) -> None:
        self._name = name
        self._description = description
        self._category = category
        self._functions = dict(functions)
        self._availability = availability
        writes = set(write_actions)
        self._schemas = [
            ToolSchema(
                name=s["name"],
                description=s.get("description", ""),
                input_schema=s.get("input_schema", {"type": "object", "properties": {}}),
                category=category,
                requires_auth=requires_auth,
                is_destructive=s["name"] in writes,
            )
            for s in schemas
            if s["name"] in self._functions
        ]
        missing = {s["name"] for s in schemas} - set(self._functions)
        if missing:
            logger.warning("Tool '%s': schemas without functions ignored: %s", name, sorted(missing))

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def category(self) -> ToolCategory:
        return self._category

    def get_schemas(self) -> list[ToolSchema]:
        return list(self._schemas)

    def is_available(self) -> bool:
        try:
            return bool(self._availability())
        except Exception:
            logger.debug("Availability check failed for tool '%s'", self._name, exc_info=True)
            return False

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        func = self._functions.get(action)
        if func is None:
            return ToolResult.fail(f"Unknown action: {action}")
        try:
            result = await func(**params)
        except TypeError as exc:
            # Wrong/missing arguments from the model — tell it so it can retry.
            return ToolResult.fail(f"Invalid parameters for {action}: {exc}")
        error = _error_of(result)
        if error:
            return ToolResult.fail(error, data=result)
        return ToolResult.ok(output=render_output(result), data=result)
