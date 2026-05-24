"""
Runtime Adapter Contract — v0.1

The most consequential new interface in RealizeOS v5.5.0. Defines how any
agent runtime (internal, Hermes, Claude Code CLI, Codex CLI, Gemini CLI,
OpenClaw, Grok CLI, or future) plugs into the kernel as a peer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import AsyncIterator, Protocol, runtime_checkable

from realize_core.runtimes.events import RuntimeEvent


# ─── Enums ────────────────────────────────────────────────────────────────────

class CostClass(str, Enum):
    CHEAP = "cheap"
    MODERATE = "moderate"
    EXPENSIVE = "expensive"


class Modality(str, Enum):
    TEXT = "text"
    CODE = "code"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class ToolProtocol(str, Enum):
    MCP = "mcp"
    OPENAI_FUNCTION = "openai_function"
    ANTHROPIC_TOOL = "anthropic_tool"
    CUSTOM = "custom"


class ErrorType(str, Enum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"
    TOOL_FAILED = "tool_failed"
    INVALID_INPUT = "invalid_input"
    INTERNAL = "internal"
    UPSTREAM = "upstream"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


# ─── Data Types ───────────────────────────────────────────────────────────────

@dataclass
class Capability:
    """A semantic tag describing what the runtime is good at."""

    name: str
    confidence: float = 0.8
    cost_class: CostClass = CostClass.MODERATE
    notes: str | None = None


@dataclass
class CapabilitySet:
    """What this runtime can do."""

    capabilities: list[Capability] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    modalities: list[Modality] = field(default_factory=lambda: [Modality.TEXT])
    tool_protocols: list[ToolProtocol] = field(default_factory=lambda: [ToolProtocol.MCP])
    streaming: bool = True
    cancellation: bool = False
    parallelism: int = 1
    requires_internet: bool = True
    is_local: bool = False


@dataclass
class HealthStatus:
    """Runtime health check result."""

    ready: bool = True
    degraded: bool = False
    last_check: datetime = field(default_factory=datetime.now)
    latency_ms: int | None = None
    error: str | None = None
    runtime_version: str | None = None


@dataclass
class Task:
    """High-level task description for routing and estimation."""

    description: str
    required_capabilities: list[str] = field(default_factory=list)
    preferred_capabilities: list[str] = field(default_factory=list)
    expected_output_tokens: int | None = None
    language: str | None = None
    modality: Modality = Modality.TEXT
    venture_id: str | None = None


@dataclass
class StepConstraints:
    """Constraints on a mission step execution."""

    max_cost_eur: float | None = None
    max_duration_sec: int | None = None
    max_tokens: int | None = None
    requires_approval_for: list[str] = field(default_factory=list)
    deny_actions: list[str] = field(default_factory=list)


@dataclass
class MissionStep:
    """What actually gets executed by a runtime."""

    step_id: str
    mission_id: str
    description: str
    inputs: dict = field(default_factory=dict)
    expected_output_schema: dict | None = None
    tool_allowlist: list[str] | None = None
    constraints: StepConstraints = field(default_factory=StepConstraints)


@dataclass
class Context:
    """What the runtime gets to see from the Heart."""

    user_soul: dict = field(default_factory=dict)
    agent_soul: dict | None = None
    venture_id: str | None = None
    venture_summary: str | None = None
    fabric_toc: dict | None = None
    mission_memory: dict | None = None
    available_tools: list[dict] = field(default_factory=list)
    history: list[dict] | None = None
    audit_trace_id: str = ""


@dataclass
class CostEstimate:
    """Estimated cost for executing a task."""

    estimated_tokens: int = 0
    estimated_duration_sec: float = 0.0
    estimated_cost_eur: float = 0.0
    confidence: float = 0.5


@dataclass
class CostActual:
    """Actual cost after execution."""

    actual_tokens: int = 0
    actual_duration_sec: float = 0.0
    actual_cost_eur: float = 0.0
    breakdown: dict = field(default_factory=dict)


@dataclass
class Skill:
    """A portable skill definition."""

    skill_id: str
    name: str
    description: str
    capability_tags: list[str] = field(default_factory=list)
    body: str = ""
    source_runtime: str = ""
    portable: bool = True
    usage_count: int = 0
    last_used: datetime | None = None


# ─── Protocol ─────────────────────────────────────────────────────────────────

@runtime_checkable
class AgentRuntime(Protocol):
    """
    Contract every agent runtime satisfies to participate in RealizeOS.

    This is the most consequential interface in v5.5.0. Without it,
    RealizeOS picks a single agent framework and gets locked in. With it,
    the user mixes runtimes and RealizeOS routes intelligently while
    keeping the knowledge/identity layer constant.
    """

    # === Identity & metadata ===

    runtime_id: str
    display_name: str
    version: str
    runtime_version: str | None

    # === Capability declaration ===

    def capabilities(self) -> CapabilitySet:
        """Declare what this runtime can do."""
        ...

    # === Lifecycle ===

    async def health_check(self) -> HealthStatus:
        """Is the runtime alive and ready to accept work?"""
        ...

    async def warmup(self) -> None:
        """Optional: pre-warm caches, validate credentials."""
        ...

    async def shutdown(self) -> None:
        """Optional: graceful cleanup before deregistration."""
        ...

    # === Cost & estimation ===

    async def cost_estimate(self, task: Task, context: Context) -> CostEstimate:
        """Estimated cost (tokens, time, monetary) for executing this task."""
        ...

    # === Execution ===

    async def invoke(
        self,
        mission_step: MissionStep,
        context: Context,
    ) -> AsyncIterator[RuntimeEvent]:
        """
        Execute a mission step. Yields events as work progresses.
        """
        ...

    async def cancel(self, run_id: str) -> bool:
        """Cancel an in-flight invocation."""
        ...

    # === Skill exchange (optional) ===

    async def export_skills(self) -> list[Skill] | None:
        """If the runtime maintains its own skill library, export it."""
        ...

    async def import_skill(self, skill: Skill) -> bool:
        """Optional: import a skill from another runtime."""
        ...
