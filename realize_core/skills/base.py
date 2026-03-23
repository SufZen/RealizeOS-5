"""
Skill base interfaces for RealizeOS dual-format skill system.

Defines the shared contracts for skill implementations:
- BaseSkill: Protocol for skill detection, matching, and execution
- SkillFormat: Enum distinguishing YAML vs SKILL.md formats
- SkillTriggerResult: Result of skill trigger matching

These interfaces support both YAML skills (v1/v2) and Anthropic-inspired
SKILL.md markdown skills with semantic triggering fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SkillFormat(StrEnum):
    """Format of the skill definition file."""

    YAML = "yaml"
    SKILL_MD = "skill_md"


class TriggerMethod(StrEnum):
    """How a skill was matched to a user message."""

    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    EXPLICIT = "explicit"  # User directly named the skill
    PIPELINE = "pipeline"  # Invoked as part of a pipeline stage


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillTriggerResult:
    """
    Result of attempting to match a user message to a skill.

    Contains the match score (0.0–1.0), the method used to trigger,
    and any extracted parameters from the message.
    """

    skill_key: str
    score: float
    trigger_method: TriggerMethod
    matched_keywords: list[str] = field(default_factory=list)
    extracted_params: dict[str, Any] = field(default_factory=dict)
    confidence_reason: str = ""

    @property
    def is_match(self) -> bool:
        """True if the score exceeds the default threshold (0.6)."""
        return self.score >= 0.6

    def exceeds_threshold(self, threshold: float) -> bool:
        """True if the score exceeds a custom threshold."""
        return self.score >= threshold


@dataclass
class SkillMetadata:
    """
    Lightweight metadata extracted from a skill definition.

    Used by the skill registry for indexing without loading
    the full skill body into memory.
    """

    key: str
    name: str
    description: str = ""
    format: SkillFormat = SkillFormat.YAML
    version: str = "1"
    tags: list[str] = field(default_factory=list)
    trigger_keywords: list[str] = field(default_factory=list)
    file_path: str = ""


# ---------------------------------------------------------------------------
# Protocol — runtime interface for skill implementations
# ---------------------------------------------------------------------------


@runtime_checkable
class BaseSkill(Protocol):
    """
    Protocol that all RealizeOS skill implementations must satisfy.

    Supports both YAML (v1/v2) and SKILL.md formats.
    Implementations provide trigger matching, parameter extraction,
    and execution logic.
    """

    @property
    def key(self) -> str:
        """Unique identifier for this skill."""
        ...

    @property
    def name(self) -> str:
        """Human-readable name."""
        ...

    @property
    def format(self) -> SkillFormat:
        """The format of this skill's source definition."""
        ...

    @property
    def metadata(self) -> SkillMetadata:
        """Lightweight metadata for registry indexing."""
        ...

    def match(self, message: str) -> SkillTriggerResult:
        """
        Attempt to match a user message to this skill.

        Args:
            message: The user's input message.

        Returns:
            SkillTriggerResult with match score and method.
        """
        ...

    async def execute(
        self,
        params: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the skill with the given parameters.

        Args:
            params: Extracted or provided parameters for execution.
            context: Optional context (venture, agent, session data).

        Returns:
            Dict containing the skill's output (format varies by skill).
        """
        ...
