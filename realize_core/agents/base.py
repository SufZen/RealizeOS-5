"""
Agent base interfaces for RealizeOS V2 composable agents.

Defines the shared contracts that all agent implementations must follow:
- BaseAgent: Protocol for agent execution and introspection
- AgentConfig: Pydantic model for V2 YAML agent definitions
- HandoffData: Structured inter-agent communication payload
- PipelineStage: Definition of a single pipeline stage
- HandoffType: Enum of supported handoff modes

These interfaces are the foundation for Agent 1's pipeline executor,
multi-agent orchestration, and Dev-QA retry loops.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class HandoffType(StrEnum):
    """
    Types of handoff between agents in a pipeline.

    - standard:    Normal sequential handoff
    - qa_pass:     QA agent approved the output
    - qa_fail:     QA agent rejected — triggers retry or escalation
    - escalation:  Automatic escalation after max retries
    - phase_gate:  Human approval required before continuing
    - sprint:      Sprint boundary — checkpoint and report
    - incident:    Error-triggered handoff to incident handler
    """
    STANDARD = "standard"
    QA_PASS = "qa_pass"
    QA_FAIL = "qa_fail"
    ESCALATION = "escalation"
    PHASE_GATE = "phase_gate"
    SPRINT = "sprint"
    INCIDENT = "incident"


class AgentStatus(StrEnum):
    """Runtime status of an agent instance."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Dataclasses — lightweight value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HandoffData:
    """
    Structured payload for inter-agent communication.

    Carries context, artifacts, and metadata from one agent
    to the next in a pipeline or delegation chain.
    """
    source_agent: str
    target_agent: str
    handoff_type: HandoffType
    payload: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3

    @property
    def is_retry_exhausted(self) -> bool:
        """True when retry budget is spent — should escalate."""
        return self.retry_count >= self.max_retries

    def with_retry(self) -> HandoffData:
        """Return a copy with incremented retry count."""
        return HandoffData(
            source_agent=self.source_agent,
            target_agent=self.target_agent,
            handoff_type=HandoffType.QA_FAIL,
            payload=self.payload,
            artifacts=self.artifacts,
            context=self.context,
            retry_count=self.retry_count + 1,
            max_retries=self.max_retries,
        )


@dataclass
class PipelineStage:
    """
    Definition of a single stage within an agent pipeline.

    Stages are executed sequentially. Each stage specifies which agent
    handles it, what handoff type leads in, and optional guardrails.
    """
    name: str
    agent_key: str
    description: str = ""
    handoff_type: HandoffType = HandoffType.STANDARD
    guardrails: list[str] = field(default_factory=list)
    timeout_seconds: int | None = None
    required_inputs: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pydantic model — V2 YAML agent configuration
# ---------------------------------------------------------------------------

class GuardrailConfig(BaseModel):
    """A single guardrail rule for an agent."""
    name: str
    description: str = ""
    enforcement: str = Field(
        default="strict",
        pattern=r"^(strict|advisory)$",
        description="strict = block on violation, advisory = warn only",
    )


class AgentConfig(BaseModel):
    """
    Pydantic model for V2 composable agent definitions (YAML).

    Enriched schema supporting: scope, inputs, outputs, guardrails,
    tools, critical rules, decision logic, success metrics, learning,
    and communication style.

    V1 .md agents remain fully supported — this model is for V2 only.
    """
    # Identity
    name: str
    key: str
    version: str = "2"
    description: str = ""

    # Scope & role
    scope: str = Field(
        default="",
        description="What this agent is responsible for",
    )
    persona: str = Field(
        default="",
        description="Persona bundle key (e.g. exec-assistant, writer, PM)",
    )
    reports_to: str | None = Field(
        default=None,
        description="Key of the supervising agent (hierarchy)",
    )

    # I/O contract
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)

    # Behaviour
    guardrails: list[GuardrailConfig] = Field(default_factory=list)
    tools: list[str] = Field(
        default_factory=list,
        description="Tool names this agent is allowed to use",
    )
    critical_rules: list[str] = Field(
        default_factory=list,
        description="Non-negotiable rules the agent must follow",
    )
    decision_logic: str = Field(
        default="",
        description="Markdown or structured logic for decision-making",
    )

    # Performance
    success_metrics: list[str] = Field(default_factory=list)
    learning: dict[str, Any] = Field(
        default_factory=dict,
        description="Learning config — feedback loops, memory settings",
    )

    # Communication
    communication_style: str = Field(
        default="professional",
        description="Tone/style for agent outputs (professional, casual, exec-brief)",
    )

    # Pipeline
    pipeline_stages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ordered list of pipeline stage definitions",
    )

    # Schedule (optional)
    schedule_cron: str | None = None
    schedule_interval_sec: int | None = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Protocol — runtime interface for agent implementations
# ---------------------------------------------------------------------------

@runtime_checkable
class BaseAgent(Protocol):
    """
    Protocol that all RealizeOS agent implementations must satisfy.

    This is a structural subtype (duck-typing) — implementations do NOT
    need to explicitly inherit from BaseAgent; they just need to provide
    the required attributes and methods.
    """

    @property
    def key(self) -> str:
        """Unique identifier for this agent."""
        ...

    @property
    def config(self) -> AgentConfig:
        """The parsed V2 configuration for this agent."""
        ...

    @property
    def status(self) -> AgentStatus:
        """Current runtime status."""
        ...

    async def process(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Process an incoming message and return a response.

        Args:
            message: The user/system message to handle.
            context: Optional context dict (venture, session, handoff data).

        Returns:
            The agent's text response.
        """
        ...

    async def handle_handoff(self, handoff: HandoffData) -> HandoffData:
        """
        Receive a handoff from another agent and produce a result handoff.

        Args:
            handoff: Incoming handoff payload.

        Returns:
            Outgoing handoff with results for the next stage.
        """
        ...

    def is_available(self) -> bool:
        """Whether this agent is ready to accept work."""
        ...
