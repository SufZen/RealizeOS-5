"""
V2 Composable Agent Schema — Pydantic models for YAML agent definitions.

Extends the base AgentConfig with richer schema elements following ADR-007:
scope, inputs/outputs, guardrails, tools, critical_rules, decision_logic,
success_metrics, learning, communication_style, and pipeline stages.

V1 (.md) agents are represented as a minimal V1AgentDef for backward compat.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from realize_core.agents.base import GuardrailConfig, HandoffType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# V1 Agent Definition (parsed from .md frontmatter-less files)
# ---------------------------------------------------------------------------

class V1AgentDef(BaseModel):
    """
    Minimal representation of a V1 markdown agent.

    V1 agents are plain markdown files with role, personality, capabilities,
    and operating rules expressed in prose.  We extract what we can from
    the structure and expose it through a compatible interface.
    """
    key: str
    name: str = ""
    version: str = "1"
    file_path: str = ""
    raw_content: str = ""

    # Extracted sections (best-effort from markdown headers)
    role: str = ""
    personality: str = ""
    capabilities: list[str] = Field(default_factory=list)
    operating_rules: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# V2 Pipeline Stage (richer than base.PipelineStage dataclass)
# ---------------------------------------------------------------------------

class PipelineStageConfig(BaseModel):
    """
    Configuration for a single stage in a V2 agent pipeline.

    Defined in the agent YAML under ``pipeline_stages``.
    """
    name: str
    agent_key: str
    description: str = ""
    handoff_type: HandoffType = HandoffType.STANDARD
    guardrails: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = None
    required_inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    retry_on_fail: bool = False
    max_retries: int = 3


# ---------------------------------------------------------------------------
# V2 Full Agent Definition
# ---------------------------------------------------------------------------

class V2AgentDef(BaseModel):
    """
    Full V2 composable agent definition (loaded from YAML).

    Enriched schema with scope, I/O contracts, guardrails, tools,
    critical rules, decision logic, success metrics, learning config,
    and communication style.
    """
    # Identity
    name: str
    key: str
    version: str = "2"
    description: str = ""
    file_path: str = ""

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
        description="Tone/style for agent outputs",
    )

    # Pipeline
    pipeline_stages: list[PipelineStageConfig] = Field(default_factory=list)

    # Schedule (optional)
    schedule_cron: str | None = None
    schedule_interval_sec: int | None = None

    model_config = {"extra": "allow"}

    @property
    def has_pipeline(self) -> bool:
        """Whether this agent defines a pipeline."""
        return len(self.pipeline_stages) > 0

    @property
    def stage_agent_keys(self) -> list[str]:
        """Return the ordered list of agent keys in the pipeline."""
        return [s.agent_key for s in self.pipeline_stages]
