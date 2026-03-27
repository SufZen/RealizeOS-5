"""
Tests for the Agent Persona System (SOUL) — Intent 2.1.

Covers:
- Persona YAML loading from file
- Persona loading from dict (embedded in agent YAML)
- Persona-to-prompt conversion
- Persona resolution chain (embedded → companion → fallback)
- Prompt builder persona layer integration
- Graceful fallback for missing personas
"""

from pathlib import Path

import pytest
import yaml
from realize_core.agents.persona import (
    AgentPersona,
    load_persona,
    load_persona_from_dict,
    persona_to_prompt,
    resolve_persona,
)

# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_persona_data():
    """Sample persona data dict."""
    return {
        "name": "Alex Rivera",
        "title": "Chief of Staff",
        "role": "Manage executive operations",
        "personality": ["proactive", "organized", "diplomatic"],
        "expertise": ["project management", "coordination"],
        "communication_style": "executive",
        "voice_notes": "Concise and action-oriented",
        "reports_to": "ceo",
        "background": "Alex is the backbone of operations.",
        "operating_principles": [
            "Surface blockers immediately",
            "Always provide a recommended action",
        ],
        "tools_allowlist": ["crm", "email", "calendar"],
    }


@pytest.fixture
def sample_persona(sample_persona_data):
    """Sample AgentPersona instance."""
    return AgentPersona(**sample_persona_data)


@pytest.fixture
def persona_yaml_file(tmp_path, sample_persona_data):
    """Write sample persona to a YAML file and return its path."""
    filepath = tmp_path / "exec-assistant.persona.yaml"
    filepath.write_text(yaml.dump(sample_persona_data), encoding="utf-8")
    return filepath


# ---------------------------------------------------------------------------
#  AgentPersona Model
# ---------------------------------------------------------------------------


class TestAgentPersonaModel:
    """Test the AgentPersona Pydantic model."""

    def test_create_full_persona(self, sample_persona_data):
        persona = AgentPersona(**sample_persona_data)
        assert persona.name == "Alex Rivera"
        assert persona.title == "Chief of Staff"
        assert persona.role == "Manage executive operations"
        assert "proactive" in persona.personality
        assert persona.communication_style == "executive"
        assert persona.reports_to == "ceo"
        assert len(persona.tools_allowlist) == 3

    def test_create_minimal_persona(self):
        persona = AgentPersona(name="Min")
        assert persona.name == "Min"
        assert persona.title == ""
        assert persona.personality == []
        assert persona.tools_allowlist == []

    def test_extra_fields_allowed(self):
        persona = AgentPersona(name="Test", custom_field="value")
        assert persona.custom_field == "value"

    def test_defaults(self):
        persona = AgentPersona(name="Default")
        assert persona.communication_style == "professional"
        assert persona.reports_to is None
        assert persona.tools_denylist == []


# ---------------------------------------------------------------------------
#  Loading from YAML file
# ---------------------------------------------------------------------------


class TestLoadPersona:
    """Test loading personas from YAML files."""

    def test_load_valid_yaml(self, persona_yaml_file):
        persona = load_persona(persona_yaml_file)
        assert persona is not None
        assert persona.name == "Alex Rivera"
        assert persona.title == "Chief of Staff"

    def test_load_nonexistent_file(self, tmp_path):
        result = load_persona(tmp_path / "nonexistent.yaml")
        assert result is None

    def test_load_invalid_yaml(self, tmp_path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("{{not valid yaml", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_persona(bad_file)

    def test_load_non_mapping_yaml(self, tmp_path):
        list_file = tmp_path / "list.yaml"
        list_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a mapping"):
            load_persona(list_file)

    def test_load_auto_name_from_filename(self, tmp_path):
        filepath = tmp_path / "growth-analyst.yaml"
        filepath.write_text(yaml.dump({"title": "Analyst"}), encoding="utf-8")
        persona = load_persona(filepath)
        assert persona is not None
        assert persona.name == "Growth Analyst"


# ---------------------------------------------------------------------------
#  Loading from dict (embedded in agent YAML)
# ---------------------------------------------------------------------------


class TestLoadPersonaFromDict:
    """Test loading persona from a dict."""

    def test_load_full_dict(self, sample_persona_data):
        persona = load_persona_from_dict(sample_persona_data)
        assert persona is not None
        assert persona.name == "Alex Rivera"

    def test_load_empty_dict(self):
        result = load_persona_from_dict({})
        assert result is None

    def test_load_none(self):
        result = load_persona_from_dict(None)
        assert result is None

    def test_load_string_key(self):
        persona = load_persona_from_dict("exec-assistant")
        assert persona is not None
        assert persona.name == "exec-assistant"
        assert persona.role == "exec-assistant"

    def test_auto_name(self):
        persona = load_persona_from_dict({"title": "PM", "role": "Manager"})
        assert persona is not None
        assert persona.name == "Agent"


# ---------------------------------------------------------------------------
#  Persona-to-Prompt conversion
# ---------------------------------------------------------------------------


class TestPersonaToPrompt:
    """Test converting persona to prompt injection text."""

    def test_full_prompt(self, sample_persona):
        prompt = persona_to_prompt(sample_persona)
        assert "## Agent Persona: Alex Rivera" in prompt
        assert "Chief of Staff" in prompt
        assert "proactive" in prompt
        assert "project management" in prompt
        assert "executive" in prompt
        assert "Surface blockers" in prompt
        assert "Reports to:" in prompt

    def test_minimal_prompt(self):
        persona = AgentPersona(name="Bot")
        prompt = persona_to_prompt(persona)
        assert "## Agent Persona: Bot" in prompt
        assert "professional" in prompt  # default communication_style

    def test_prompt_excludes_empty_fields(self):
        persona = AgentPersona(name="Simple", title="", role="")
        prompt = persona_to_prompt(persona)
        assert "**Title:**" not in prompt
        assert "**Role:**" not in prompt

    def test_prompt_includes_background(self, sample_persona):
        prompt = persona_to_prompt(sample_persona)
        assert "backbone of operations" in prompt


# ---------------------------------------------------------------------------
#  Persona resolution
# ---------------------------------------------------------------------------


class TestResolvePersona:
    """Test the resolve_persona() resolution chain."""

    def test_resolve_embedded_dict(self, sample_persona_data):
        """Embedded persona dict in agent def takes priority."""

        class MockAgent:
            key = "assistant"
            persona = sample_persona_data

        persona = resolve_persona(MockAgent())
        assert persona is not None
        assert persona.name == "Alex Rivera"

    def test_resolve_companion_file(self, tmp_path, sample_persona_data):
        """Companion .persona.yaml file is used when no embedded dict."""
        companion = tmp_path / "assistant.persona.yaml"
        companion.write_text(yaml.dump(sample_persona_data), encoding="utf-8")

        class MockAgent:
            key = "assistant"
            persona = ""  # Empty string — not a dict

        persona = resolve_persona(MockAgent(), agents_dir=tmp_path)
        assert persona is not None
        assert persona.name == "Alex Rivera"

    def test_resolve_fallback_none(self, tmp_path):
        """No persona found → returns None."""

        class MockAgent:
            key = "assistant"
            persona = ""

        persona = resolve_persona(MockAgent(), agents_dir=tmp_path)
        assert persona is None

    def test_resolve_no_agents_dir(self):
        """No agents_dir → skips companion file check."""

        class MockAgent:
            key = "assistant"
            persona = ""

        persona = resolve_persona(MockAgent())
        assert persona is None


# ---------------------------------------------------------------------------
#  Prompt builder integration
# ---------------------------------------------------------------------------


class TestPromptBuilderPersonaIntegration:
    """Test persona layer injection into the prompt builder."""

    def test_persona_layer_in_prompt(self, tmp_path, sample_persona):
        from realize_core.prompt.builder import build_system_prompt

        prompt = build_system_prompt(
            kb_path=tmp_path,
            system_config={},
            system_key="test",
            agent_key="assistant",
            persona_override=sample_persona,
        )
        assert "Agent Persona: Alex Rivera" in prompt
        assert "Chief of Staff" in prompt

    def test_no_persona_no_layer(self, tmp_path):
        from realize_core.prompt.builder import build_system_prompt

        prompt = build_system_prompt(
            kb_path=tmp_path,
            system_config={},
            system_key="test",
            agent_key="assistant",
            persona_override=None,
        )
        assert "Agent Persona" not in prompt

    def test_persona_priority_prevents_trimming(self, sample_persona):
        """Persona layer has priority 8 — should survive budget trimming."""
        from realize_core.prompt.builder import _get_layer_priority

        persona_prompt = persona_to_prompt(sample_persona)
        priority = _get_layer_priority(persona_prompt)
        assert priority == 8


# ---------------------------------------------------------------------------
#  Sample persona files validation
# ---------------------------------------------------------------------------


class TestSamplePersonas:
    """Verify that the bundled sample persona YAMLs are valid."""

    PERSONA_DIR = Path(__file__).resolve().parent.parent / "templates" / "personas"

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "templates" / "personas").exists(),
        reason="Sample personas directory not found",
    )
    def test_sample_personas_load(self):
        persona_files = list(self.PERSONA_DIR.glob("*.yaml"))
        assert len(persona_files) >= 3, f"Expected >= 3 sample personas, found {len(persona_files)}"

        for pf in persona_files:
            persona = load_persona(pf)
            assert persona is not None, f"Failed to load {pf.name}"
            assert persona.name, f"Persona in {pf.name} has no name"
            assert len(persona.personality) > 0, f"Persona in {pf.name} has no personality traits"
            assert len(persona.expertise) > 0, f"Persona in {pf.name} has no expertise"
