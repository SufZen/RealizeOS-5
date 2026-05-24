"""
Runtime Adapter System — The Limbs of RealizeOS.

Defines the protocol every agent runtime must satisfy to participate
in RealizeOS as a first-class peer.
"""

from realize_core.runtimes.contract import (
    AgentRuntime,
    CapabilitySet,
    Capability,
    CostClass,
    Modality,
    ToolProtocol,
    HealthStatus,
    Task,
    MissionStep,
    StepConstraints,
    Context,
    CostEstimate,
    CostActual,
    Skill,
    ErrorType,
)
from realize_core.runtimes.events import (
    RuntimeEvent,
    ProgressEvent,
    TextEvent,
    ToolCallEvent,
    ToolResultEvent,
    ApprovalRequestEvent,
    KnowledgeWriteEvent,
    FinalResultEvent,
    ErrorEvent,
)
from realize_core.runtimes.registry import RuntimeRegistry

__all__ = [
    "AgentRuntime",
    "CapabilitySet",
    "Capability",
    "CostClass",
    "Modality",
    "ToolProtocol",
    "HealthStatus",
    "Task",
    "MissionStep",
    "StepConstraints",
    "Context",
    "CostEstimate",
    "CostActual",
    "Skill",
    "ErrorType",
    "RuntimeEvent",
    "ProgressEvent",
    "TextEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "ApprovalRequestEvent",
    "KnowledgeWriteEvent",
    "FinalResultEvent",
    "ErrorEvent",
    "RuntimeRegistry",
]
