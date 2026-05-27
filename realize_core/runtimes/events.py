"""
Runtime Event Types.

The streaming event types a runtime emits during invoke().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class ProgressEvent:
    """Human-readable progress update."""

    kind: Literal["progress"] = "progress"
    run_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    message: str = ""
    percent_complete: float | None = None


@dataclass
class TextEvent:
    """Streamed text chunk."""

    kind: Literal["text"] = "text"
    run_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    delta: str = ""


@dataclass
class ToolCallEvent:
    """Runtime is invoking a tool."""

    kind: Literal["tool_call"] = "tool_call"
    run_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    tool_name: str = ""
    args: dict = field(default_factory=dict)
    tool_call_id: str = ""


@dataclass
class ToolResultEvent:
    """Result of a tool invocation."""

    kind: Literal["tool_result"] = "tool_result"
    run_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    tool_call_id: str = ""
    result: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class ApprovalRequestEvent:
    """Runtime needs human approval to proceed."""

    kind: Literal["approval_request"] = "approval_request"
    run_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    category: str = ""
    description: str = ""
    proposed_action: dict = field(default_factory=dict)


@dataclass
class KnowledgeWriteEvent:
    """Runtime proposes a write to FABRIC."""

    kind: Literal["knowledge_write"] = "knowledge_write"
    run_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    entity_id: str = ""
    entity_type: str = ""
    operation: Literal["create", "update", "annotate"] = "create"
    diff: dict = field(default_factory=dict)


@dataclass
class FinalResultEvent:
    """Mission step completed."""

    kind: Literal["final"] = "final"
    run_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    output: dict = field(default_factory=dict)
    cost_actual: dict = field(default_factory=dict)
    status: Literal["success", "partial", "failed"] = "success"


@dataclass
class ErrorEvent:
    """An error occurred during execution."""

    kind: Literal["error"] = "error"
    run_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    error_type: str = "unknown"
    message: str = ""
    retryable: bool = False


# Union type for all runtime events
RuntimeEvent = (
    ProgressEvent
    | TextEvent
    | ToolCallEvent
    | ToolResultEvent
    | ApprovalRequestEvent
    | KnowledgeWriteEvent
    | FinalResultEvent
    | ErrorEvent
)
