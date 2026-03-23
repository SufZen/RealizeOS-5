"""
Tool SDK: Base classes for building extensible tools.

Provides the BaseTool abstract interface that all tools implement,
plus a ToolRegistry for discovery and management.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """Categories for tool classification."""

    COMMUNICATION = "communication"  # Email, messaging, notifications
    RESEARCH = "research"  # Web search, data lookup
    PRODUCTIVITY = "productivity"  # Calendar, docs, spreadsheets
    DEVELOPMENT = "development"  # Code, git, CI/CD
    MEDIA = "media"  # Image, video, audio generation
    DATA = "data"  # Database, analytics, reporting
    AUTOMATION = "automation"  # Browser automation, workflows
    CUSTOM = "custom"  # User-defined tools


@dataclass
class ToolSchema:
    """
    JSON Schema for a tool's input parameters.

    Compatible with Claude's tool_use format and MCP tool schemas.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    category: ToolCategory = ToolCategory.CUSTOM
    requires_auth: bool = False
    is_destructive: bool = False  # True for write/delete operations

    def to_claude_format(self) -> dict:
        """Convert to Claude tool_use schema format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_mcp_format(self) -> dict:
        """Convert to MCP tool schema format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class ToolResult:
    """Result from executing a tool."""

    success: bool
    output: str
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def ok(output: str, data: Any = None, **metadata) -> "ToolResult":
        return ToolResult(success=True, output=output, data=data, metadata=metadata)

    @staticmethod
    def fail(error: str, output: str = "", **metadata) -> "ToolResult":
        return ToolResult(success=False, output=output, error=error, metadata=metadata)


class BaseTool(ABC):
    """
    Abstract base class for all RealizeOS tools.

    Implement this interface to create a tool that can be discovered
    by the ToolRegistry and exposed to LLM agents.

    Example:
        class MyTool(BaseTool):
            @property
            def name(self) -> str:
                return "my_tool"

            @property
            def description(self) -> str:
                return "Does something useful"

            @property
            def category(self) -> ToolCategory:
                return ToolCategory.CUSTOM

            def get_schemas(self) -> list[ToolSchema]:
                return [ToolSchema(...)]

            async def execute(self, action, params) -> ToolResult:
                ...

            def is_available(self) -> bool:
                return True
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this tool."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        ...

    @property
    @abstractmethod
    def category(self) -> ToolCategory:
        """Category for tool organization."""
        ...

    @abstractmethod
    def get_schemas(self) -> list[ToolSchema]:
        """
        Return the tool schemas (actions) this tool exposes.

        Each schema represents one action the tool can perform.
        A single tool can expose multiple actions.
        """
        ...

    @abstractmethod
    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        """
        Execute a tool action with given parameters.

        Args:
            action: The action name (matches a schema name)
            params: Parameters matching the action's input_schema

        Returns:
            ToolResult with success/failure and output
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this tool is available (API keys configured, dependencies installed, etc.).

        Returns:
            True if the tool can be used right now
        """
        ...

    def get_action_names(self) -> list[str]:
        """Get list of all action names this tool supports."""
        return [s.name for s in self.get_schemas()]

    def get_claude_schemas(self) -> list[dict]:
        """Get all schemas in Claude tool_use format."""
        return [s.to_claude_format() for s in self.get_schemas()]

    def get_read_actions(self) -> set[str]:
        """Actions that only read data (safe to auto-approve)."""
        return {s.name for s in self.get_schemas() if not s.is_destructive}

    def get_write_actions(self) -> set[str]:
        """Actions that modify data (may need user confirmation)."""
        return {s.name for s in self.get_schemas() if s.is_destructive}
