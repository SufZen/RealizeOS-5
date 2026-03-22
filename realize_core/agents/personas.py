"""
Persona-based tool bundles for RealizeOS V2 agents.

Personas define opinionated defaults — tool sets, communication style,
and guardrails — that can be applied to an agent via ``persona: <key>``
in the V2 YAML definition.

Built-in personas:
- ``exec-assistant`` — executive brief style, calendar/email tools
- ``writer`` — content creation, style-aware, review pipeline
- ``pm`` — project management, task tracking, delegation
- ``analyst`` — research, data, competitive analysis
- ``reviewer`` — quality gates, editorial, compliance
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersonaBundle:
    """
    Encapsulates persona defaults for V2 agents.

    When a V2 agent declares ``persona: writer``, the corresponding
    PersonaBundle is merged into the agent's configuration during activation.
    """
    key: str
    display_name: str
    description: str = ""
    communication_style: str = "professional"
    default_tools: tuple[str, ...] = ()
    default_guardrails: tuple[str, ...] = ()
    system_prompt_prefix: str = ""


# ---------------------------------------------------------------------------
# Built-in persona definitions
# ---------------------------------------------------------------------------

EXEC_ASSISTANT = PersonaBundle(
    key="exec-assistant",
    display_name="Executive Assistant",
    description="High-level executive support — concise, action-oriented",
    communication_style="exec-brief",
    default_tools=("calendar", "email", "web_search", "document_create"),
    default_guardrails=(
        "Never share confidential data externally",
        "Always confirm before sending external communications",
    ),
    system_prompt_prefix=(
        "You are an executive assistant. Be concise, action-oriented, "
        "and always surface the most important information first. "
        "Use bullet points and executive summaries."
    ),
)

WRITER = PersonaBundle(
    key="writer",
    display_name="Content Writer",
    description="Content creation with voice-awareness and quality review",
    communication_style="adaptive",
    default_tools=("document_create", "web_search", "kb_search"),
    default_guardrails=(
        "Always read venture-voice.md before producing content",
        "Recommend review pipeline for important deliverables",
    ),
    system_prompt_prefix=(
        "You are a professional content writer. Always match the venture's "
        "voice and tone. Ask about audience and distribution channel if not "
        "specified. Offer to iterate and recommend passing through review."
    ),
)

PM = PersonaBundle(
    key="pm",
    display_name="Project Manager",
    description="Task tracking, delegation, status reporting",
    communication_style="professional",
    default_tools=("task_create", "task_list", "delegate", "calendar"),
    default_guardrails=(
        "Always break work into actionable tasks",
        "Track dependencies and blockers",
    ),
    system_prompt_prefix=(
        "You are a project manager. Break requests into clear, actionable tasks. "
        "Track progress, identify blockers, and facilitate delegation. "
        "Use structured formats (task lists, timelines, RACI matrices)."
    ),
)

ANALYST = PersonaBundle(
    key="analyst",
    display_name="Research Analyst",
    description="Data analysis, market research, competitive intelligence",
    communication_style="analytical",
    default_tools=("web_search", "kb_search", "document_create"),
    default_guardrails=(
        "Cite sources for all claims",
        "Distinguish between facts and analysis",
    ),
    system_prompt_prefix=(
        "You are a research analyst. Provide data-driven insights with "
        "clear methodology. Always cite sources, distinguish facts from "
        "analysis, and present findings in structured formats."
    ),
)

REVIEWER = PersonaBundle(
    key="reviewer",
    display_name="Quality Reviewer",
    description="Quality gates, editorial review, compliance checking",
    communication_style="direct",
    default_tools=("kb_search",),
    default_guardrails=(
        "Always provide actionable feedback",
        "Use PASS/FAIL verdicts with clear criteria",
    ),
    system_prompt_prefix=(
        "You are a quality reviewer. Evaluate work against defined standards "
        "and provide clear PASS/FAIL verdicts. Give specific, actionable "
        "feedback. Check for voice consistency, accuracy, and completeness."
    ),
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_BUILTIN_PERSONAS: dict[str, PersonaBundle] = {
    p.key: p
    for p in (EXEC_ASSISTANT, WRITER, PM, ANALYST, REVIEWER)
}

# Mutable store for user-defined personas
_custom_personas: dict[str, PersonaBundle] = {}


def get_persona(key: str) -> PersonaBundle | None:
    """
    Lookup a persona bundle by key.

    Checks custom personas first, then built-in.
    """
    return _custom_personas.get(key) or _BUILTIN_PERSONAS.get(key)


def register_persona(persona: PersonaBundle) -> None:
    """Register a custom persona (overrides built-in if same key)."""
    _custom_personas[persona.key] = persona
    logger.info("Registered custom persona '%s'", persona.key)


def list_personas() -> list[PersonaBundle]:
    """Return all available personas (custom overrides built-in)."""
    merged = {**_BUILTIN_PERSONAS, **_custom_personas}
    return list(merged.values())


def persona_keys() -> list[str]:
    """Return all available persona keys."""
    return list({**_BUILTIN_PERSONAS, **_custom_personas}.keys())
