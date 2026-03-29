"""
Agent Persona System (SOUL) — Persistent per-agent identity.

Each agent can have a persona YAML that defines:
- Role and title
- Personality traits
- Expertise domains
- Communication style preferences
- Reporting hierarchy
- Tool access lists (used by Intent 3.2 - Tool Gating)

See Also:
    ``realize_core.agents.personas`` — Built-in persona presets
    (exec-assistant, writer, analyst, etc.) that provide opinionated
    defaults.  This module (``persona.py``) handles *dynamic* persona
    resolution from YAML files, while ``personas.py`` provides the
    *static* preset registry.

Personas are loaded from YAML files in the agent directory and injected
into the prompt builder to give each agent a consistent personality.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentPersona(BaseModel):
    """
    Rich persona definition for a V2 agent.

    Loaded from a ``persona.yaml`` file alongside the agent definition,
    or embedded directly in the agent YAML under a ``persona:`` key.
    """

    # Identity
    name: str = Field(description="Display name (e.g. 'Maya Chen')")
    title: str = Field(default="", description="Role title (e.g. 'Senior Content Strategist')")
    role: str = Field(default="", description="Functional role description")

    # Personality
    personality: list[str] = Field(
        default_factory=list,
        description="Personality traits (e.g. ['analytical', 'detail-oriented', 'pragmatic'])",
    )
    expertise: list[str] = Field(
        default_factory=list,
        description="Domains of expertise (e.g. ['content strategy', 'SEO', 'copywriting'])",
    )

    # Communication
    communication_style: str = Field(
        default="professional",
        description="Tone/style: professional, casual, academic, executive, creative",
    )
    voice_notes: str = Field(
        default="",
        description="Free-form notes on how this agent should sound",
    )

    # Hierarchy
    reports_to: str | None = Field(
        default=None,
        description="Key of the supervising agent",
    )

    # Tool access control (used by Intent 3.2)
    tools_allowlist: list[str] = Field(
        default_factory=list,
        description="If set, agent can ONLY use these tools",
    )
    tools_denylist: list[str] = Field(
        default_factory=list,
        description="If set, agent CANNOT use these tools",
    )

    # Extra context
    background: str = Field(
        default="",
        description="Brief backstory or context for this persona",
    )
    operating_principles: list[str] = Field(
        default_factory=list,
        description="Core principles this agent follows",
    )

    model_config = {"extra": "allow"}


_persona_cache: dict[Path, tuple[float, AgentPersona]] = {}


def load_persona(path: Path | str) -> AgentPersona | None:
    """
    Load a persona from a YAML file.

    Args:
        path: Path to persona YAML file.

    Returns:
        AgentPersona instance, or None if file doesn't exist.

    Raises:
        ValueError: If the YAML is invalid.
    """
    path = Path(path)
    if not path.exists():
        logger.debug("Persona file not found: %s", path)
        return None

    mtime = path.stat().st_mtime
    if path in _persona_cache:
        cached_mtime, cached_persona = _persona_cache[path]
        if cached_mtime == mtime:
            return cached_persona

    try:
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in persona file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Persona YAML must be a mapping, got {type(data).__name__} in {path}")

    if "name" not in data:
        data["name"] = path.stem.replace("-", " ").replace("_", " ").title()

    persona = AgentPersona(**data)
    _persona_cache[path] = (mtime, persona)
    return persona


def load_persona_from_dict(data: dict[str, Any] | str | None) -> AgentPersona | None:
    """
    Load a persona from a dictionary (e.g. embedded in agent YAML).

    Args:
        data: Dictionary with persona fields.

    Returns:
        AgentPersona instance, or None if data is empty.
    """
    if not data:
        return None

    if isinstance(data, str):
        # Persona is just a key reference — return a minimal persona
        return AgentPersona(name=data, role=data)

    if "name" not in data:
        data["name"] = "Agent"

    return AgentPersona(**data)


def persona_to_prompt(persona: AgentPersona) -> str:
    """
    Convert an AgentPersona into a prompt injection string.

    Produces a structured markdown section that the prompt builder
    can insert into the system prompt.

    Args:
        persona: The persona to format.

    Returns:
        Formatted markdown string for prompt injection.
    """
    parts = [f"## Agent Persona: {persona.name}"]

    if persona.title:
        parts.append(f"**Title:** {persona.title}")

    if persona.role:
        parts.append(f"**Role:** {persona.role}")

    if persona.personality:
        traits = ", ".join(persona.personality)
        parts.append(f"**Personality:** {traits}")

    if persona.expertise:
        domains = ", ".join(persona.expertise)
        parts.append(f"**Expertise:** {domains}")

    if persona.communication_style:
        parts.append(f"**Communication Style:** {persona.communication_style}")

    if persona.voice_notes:
        parts.append(f"**Voice:** {persona.voice_notes}")

    if persona.background:
        parts.append(f"\n{persona.background}")

    if persona.operating_principles:
        parts.append("\n**Operating Principles:**")
        for principle in persona.operating_principles:
            parts.append(f"- {principle}")

    if persona.reports_to:
        parts.append(f"\n**Reports to:** {persona.reports_to}")

    return "\n".join(parts)


def resolve_persona(
    agent_def: Any,
    agents_dir: Path | None = None,
) -> AgentPersona | None:
    """
    Resolve the persona for an agent definition.

    Resolution order:
    1. Embedded persona dict in agent YAML (``persona:`` key)
    2. Companion file: ``<agent_key>.persona.yaml`` in agents_dir
    3. None (no persona defined — graceful fallback)

    Args:
        agent_def: V2AgentDef or similar with key/persona attributes.
        agents_dir: Directory containing agent files.

    Returns:
        AgentPersona or None.
    """
    # 1. Check for embedded persona dict
    persona_data = getattr(agent_def, "persona", None)
    if isinstance(persona_data, dict) and persona_data:
        logger.debug("Loading embedded persona for agent '%s'", agent_def.key)
        return load_persona_from_dict(persona_data)

    # 2. Check for companion file
    if agents_dir:
        companion_path = agents_dir / f"{agent_def.key}.persona.yaml"
        if companion_path.exists():
            logger.debug("Loading companion persona file for agent '%s'", agent_def.key)
            return load_persona(companion_path)

        # 2b. Try persona string key as filename
        if isinstance(persona_data, str) and persona_data:
            alt_path = agents_dir / f"{persona_data}.persona.yaml"
            if alt_path.exists():
                logger.debug("Loading companion persona file via string key '%s'", persona_data)
                return load_persona(alt_path)

    # 3. No persona found
    logger.debug("No persona found for agent '%s', using fallback", agent_def.key)
    return None
