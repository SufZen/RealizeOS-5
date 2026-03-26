"""
Tool Registry: Discovers, registers, and manages tools.

Supports:
- Programmatic registration of BaseTool subclasses
- Auto-discovery from a tools directory
- YAML-based tool definitions
- Schema aggregation for LLM tool_use calls
"""

import importlib
import logging
from pathlib import Path
from typing import Any

from realize_core.tools.base_tool import (
    BaseTool,
    ToolCategory,
    ToolResult,
)

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all available tools.

    Manages tool discovery, registration, and execution.
    Acts as the single entry point for LLM tool_use calls.
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._action_map: dict[str, BaseTool] = {}  # action_name → tool

    def register(self, tool: BaseTool) -> bool:
        """
        Register a tool instance.

        Args:
            tool: A BaseTool subclass instance

        Returns:
            True if registered successfully, False if unavailable or duplicate
        """
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, skipping")
            return False

        self._tools[tool.name] = tool

        # Map each action to this tool
        for schema in tool.get_schemas():
            if schema.name in self._action_map:
                logger.warning(
                    f"Action '{schema.name}' conflicts with tool "
                    f"'{self._action_map[schema.name].name}', "
                    f"overriding with '{tool.name}'"
                )
            self._action_map[schema.name] = tool

        logger.info(
            f"Registered tool '{tool.name}' ({len(tool.get_schemas())} actions, available={tool.is_available()})"
        )
        return True

    def unregister(self, tool_name: str) -> bool:
        """Remove a tool from the registry."""
        tool = self._tools.pop(tool_name, None)
        if tool:
            for name in tool.get_action_names():
                self._action_map.pop(name, None)
            return True
        return False

    async def execute(self, action_name: str, params: dict[str, Any]) -> ToolResult:
        """
        Execute a tool action by name.

        Args:
            action_name: The action to execute (e.g., "web_search")
            params: Parameters for the action

        Returns:
            ToolResult with the execution outcome
        """
        tool = self._action_map.get(action_name)
        if not tool:
            return ToolResult.fail(f"Unknown action: '{action_name}'")

        if not tool.is_available():
            return ToolResult.fail(f"Tool '{tool.name}' is not available (missing API key or dependency)")

        try:
            return await tool.execute(action_name, params)
        except Exception as e:
            logger.error(f"Tool execution error: {action_name}: {e}", exc_info=True)
            return ToolResult.fail(f"Execution failed: {str(e)[:300]}")

    def get_all_schemas(self, available_only: bool = True) -> list[dict]:
        """
        Get all tool schemas in Claude tool_use format.

        Args:
            available_only: If True, only return schemas for available tools

        Returns:
            List of Claude-format tool schemas
        """
        schemas = []
        for tool in self._tools.values():
            if available_only and not tool.is_available():
                continue
            schemas.extend(tool.get_claude_schemas())
        return schemas

    def get_tools_by_category(self, category: ToolCategory) -> list[BaseTool]:
        """Get all tools in a specific category."""
        return [t for t in self._tools.values() if t.category == category]

    def get_available_tools(self) -> list[BaseTool]:
        """Get all currently available tools."""
        return [t for t in self._tools.values() if t.is_available()]

    def get_tool(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_tool_for_action(self, action_name: str) -> BaseTool | None:
        """Get the tool that handles a specific action."""
        return self._action_map.get(action_name)

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def action_count(self) -> int:
        return len(self._action_map)

    def status_summary(self) -> dict:
        """Get a status summary of all registered tools."""
        return {
            "total_tools": self.tool_count,
            "total_actions": self.action_count,
            "available": len(self.get_available_tools()),
            "tools": {
                name: {
                    "category": tool.category.value,
                    "available": tool.is_available(),
                    "actions": tool.get_action_names(),
                }
                for name, tool in self._tools.items()
            },
        }

    # -----------------------------------------------------------------------
    # Auto-discovery
    # -----------------------------------------------------------------------

    def auto_discover(self, package_path: str = "realize_core.tools"):
        """
        Auto-discover and register tool classes from a Python package.

        Looks for modules that define BaseTool subclasses and
        registers them if they're available.
        """
        # Known tool modules (explicit list for safety)
        known_modules = [
            "realize_core.tools.web_tool",
            "realize_core.tools.google_workspace_tool",
            "realize_core.tools.browser_tool",
            "realize_core.tools.gws_cli_tool",
            "realize_core.tools.google_sheets_tool",
            "realize_core.tools.approval",
            "realize_core.tools.messaging",
        ]

        for module_name in known_modules:
            try:
                mod = importlib.import_module(module_name)
                # Look for a get_tool() factory function
                factory = getattr(mod, "get_tool", None)
                if factory:
                    tool = factory()
                    if isinstance(tool, BaseTool):
                        self.register(tool)
                else:
                    # Look for BaseTool subclass instances
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if isinstance(attr, type) and issubclass(attr, BaseTool) and attr is not BaseTool:
                            try:
                                self.register(attr())
                            except Exception as e:
                                logger.debug(f"Cannot instantiate {attr_name}: {e}")
            except ImportError:
                logger.debug(f"Tool module '{module_name}' not found, skipping")
            except Exception as e:
                logger.warning(f"Error discovering tools in '{module_name}': {e}")

    def load_from_yaml(self, yaml_path: str | Path):
        """
        Load tool configs from a YAML file.

        The YAML format maps tool names to their module paths:

        ```yaml
        tools:
          web:
            module: realize_core.tools.web_tool
            enabled: true
          custom:
            module: my_project.tools.custom_tool
            enabled: true
        ```
        """
        path = Path(yaml_path)
        if not path.exists():
            logger.info(f"Tool config not found: {path}")
            return

        try:
            import yaml
        except ImportError:
            logger.warning("pyyaml not installed, cannot load tool config")
            return

        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        for tool_name, tool_config in config.get("tools", {}).items():
            if not tool_config.get("enabled", True):
                continue
            module_path = tool_config.get("module")
            if not module_path:
                continue
            try:
                mod = importlib.import_module(module_path)
                factory = getattr(mod, "get_tool", None)
                if factory:
                    self.register(factory())
            except Exception as e:
                logger.warning(f"Failed to load tool '{tool_name}' from {module_path}: {e}")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry singleton."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
