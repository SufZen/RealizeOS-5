"""
Agents — V2 composable agent definitions, pipelines, and handoffs.

Public API:
- ``base`` — BaseAgent protocol, AgentConfig, HandoffData, HandoffType
- ``schema`` — V1AgentDef, V2AgentDef Pydantic models
- ``loader`` — load V1/V2 agents from files or directories
- ``registry`` — AgentRegistry with hot-reload
- ``personas`` — Persona bundles (exec-assistant, writer, PM, etc.)
- ``handoff`` — 7 handoff type handlers
- ``guardrails`` — Safety constraints and PASS/FAIL parsing
- ``pipeline`` — Sequential pipeline executor with Dev-QA retry
- ``activation`` — Context-rich activation prompt builder
"""

from realize_core.agents.base import (
    AgentConfig,
    BaseAgent,
    GuardrailConfig,
    HandoffData,
    HandoffType,
    PipelineStage,
)
from realize_core.agents.loader import AgentDef, detect_format, load_agent
from realize_core.agents.registry import AgentRegistry
from realize_core.agents.schema import V1AgentDef, V2AgentDef

__all__ = [
    # base
    "AgentConfig",
    "BaseAgent",
    "GuardrailConfig",
    "HandoffData",
    "HandoffType",
    "PipelineStage",
    # schema
    "V1AgentDef",
    "V2AgentDef",
    # loader
    "AgentDef",
    "detect_format",
    "load_agent",
    # registry
    "AgentRegistry",
]
