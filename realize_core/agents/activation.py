"""
Activation — context-rich agent activation prompt assembly.

Builds the system prompt prefix that activates a V2 composable agent,
incorporating:
- Agent identity (name, scope, description)
- Persona bundle defaults (if specified)
- Guardrails as critical rules
- I/O contracts
- Communication style
- Pipeline context (current stage, upstream results)
"""

from __future__ import annotations

import logging
from typing import Any

from realize_core.agents.base import HandoffData
from realize_core.agents.personas import PersonaBundle, get_persona
from realize_core.agents.schema import V2AgentDef

logger = logging.getLogger(__name__)


def build_activation_prompt(
    agent: V2AgentDef,
    *,
    venture_name: str = "",
    handoff: HandoffData | None = None,
    pipeline_context: dict[str, Any] | None = None,
    extra_instructions: str = "",
) -> str:
    """
    Build a context-rich activation prompt for a V2 agent.

    Assembles a comprehensive system prompt prefix from the agent's
    definition, persona, guardrails, and pipeline context.

    Args:
        agent: The V2 agent definition.
        venture_name: Name of the active venture (for context).
        handoff: Optional incoming handoff data (pipeline mode).
        pipeline_context: Optional dict with pipeline state info.
        extra_instructions: Additional instructions to append.

    Returns:
        A multi-section activation prompt string.
    """
    sections: list[str] = []

    # ---- Identity ----
    sections.append(_build_identity_section(agent, venture_name))

    # ---- Persona ----
    persona = get_persona(agent.persona) if agent.persona else None
    if persona:
        sections.append(_build_persona_section(persona))

    # ---- Scope & I/O ----
    if agent.scope:
        sections.append(f"## Scope\n{agent.scope}")

    if agent.inputs or agent.outputs:
        sections.append(_build_io_section(agent))

    # ---- Critical Rules ----
    if agent.critical_rules:
        rules = "\n".join(f"- {r}" for r in agent.critical_rules)
        sections.append(f"## Critical Rules (MUST FOLLOW)\n{rules}")

    # ---- Guardrails ----
    if agent.guardrails:
        sections.append(_build_guardrails_section(agent))

    # ---- Decision Logic ----
    if agent.decision_logic:
        sections.append(f"## Decision Logic\n{agent.decision_logic}")

    # ---- Communication Style ----
    style = agent.communication_style or "professional"
    sections.append(f"## Communication Style\n{_style_instruction(style)}")

    # ---- Handoff Context ----
    if handoff:
        sections.append(_build_handoff_section(handoff))

    # ---- Pipeline Context ----
    if pipeline_context:
        sections.append(_build_pipeline_section(pipeline_context))

    # ---- Extra Instructions ----
    if extra_instructions:
        sections.append(f"## Additional Instructions\n{extra_instructions}")

    # ---- Success Metrics ----
    if agent.success_metrics:
        metrics = "\n".join(f"- {m}" for m in agent.success_metrics)
        sections.append(f"## Success Metrics\n{metrics}")

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_identity_section(agent: V2AgentDef, venture_name: str) -> str:
    """Build the agent identity section."""
    parts = [f"# Agent: {agent.name}"]
    if venture_name:
        parts.append(f"**Venture:** {venture_name}")
    if agent.description:
        parts.append(f"\n{agent.description}")
    if agent.reports_to:
        parts.append(f"\n**Reports to:** {agent.reports_to}")
    return "\n".join(parts)


def _build_persona_section(persona: PersonaBundle) -> str:
    """Build the persona context section."""
    lines = [f"## Persona: {persona.display_name}"]
    if persona.system_prompt_prefix:
        lines.append(persona.system_prompt_prefix)
    if persona.default_guardrails:
        lines.append("\n**Persona guardrails:**")
        for g in persona.default_guardrails:
            lines.append(f"- {g}")
    return "\n".join(lines)


def _build_io_section(agent: V2AgentDef) -> str:
    """Build the inputs/outputs contract section."""
    lines = ["## I/O Contract"]
    if agent.inputs:
        lines.append("**Inputs:**")
        for inp in agent.inputs:
            lines.append(f"- {inp}")
    if agent.outputs:
        lines.append("**Outputs:**")
        for out in agent.outputs:
            lines.append(f"- {out}")
    return "\n".join(lines)


def _build_guardrails_section(agent: V2AgentDef) -> str:
    """Build guardrails as enforceable constraints."""
    lines = ["## Guardrails"]
    for g in agent.guardrails:
        enforcement_tag = "🔒 STRICT" if g.enforcement == "strict" else "⚠️ ADVISORY"
        lines.append(f"- [{enforcement_tag}] {g.name}: {g.description}")
    return "\n".join(lines)


def _build_handoff_section(handoff: HandoffData) -> str:
    """Build context about the incoming handoff."""
    lines = [
        "## Incoming Handoff",
        f"**From:** {handoff.source_agent}",
        f"**Type:** {handoff.handoff_type.value}",
    ]
    if handoff.retry_count > 0:
        lines.append(f"**Retry:** {handoff.retry_count}/{handoff.max_retries} (previous attempt was rejected)")
    if handoff.context:
        lines.append("**Context:**")
        for k, v in handoff.context.items():
            lines.append(f"- {k}: {v}")
    if handoff.artifacts:
        lines.append(f"**Artifacts:** {', '.join(handoff.artifacts)}")
    return "\n".join(lines)


def _build_pipeline_section(context: dict[str, Any]) -> str:
    """Build pipeline execution context."""
    lines = ["## Pipeline Context"]
    if "stage_name" in context:
        lines.append(f"**Current stage:** {context['stage_name']}")
    if "stage_index" in context and "total_stages" in context:
        lines.append(f"**Progress:** Stage {context['stage_index'] + 1} of {context['total_stages']}")
    if "previous_output" in context:
        prev = context["previous_output"]
        if len(prev) > 500:
            prev = prev[:500] + "... (truncated)"
        lines.append(f"**Previous stage output:**\n{prev}")
    return "\n".join(lines)


def _style_instruction(style: str) -> str:
    """Convert a communication style key into a natural language instruction."""
    styles = {
        "professional": "Communicate in a clear, professional tone. Be thorough but concise.",
        "exec-brief": (
            "Use executive briefing format: lead with the conclusion, "
            "use bullet points, keep it under 200 words unless asked for detail."
        ),
        "casual": "Be conversational and approachable. Use plain language.",
        "analytical": (
            "Be data-driven and precise. Support claims with evidence. Use structured formats (tables, numbered lists)."
        ),
        "adaptive": ("Match the user's tone and formality level. Default to professional if unsure."),
        "direct": "Be concise and direct. Lead with actionable feedback.",
    }
    return styles.get(style, styles["professional"])
