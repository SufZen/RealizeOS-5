"""
Tests for the agent loader — V1 (.md) and V2 (.yaml) format loading.
"""

import textwrap
from pathlib import Path

import pytest
from realize_core.agents.loader import (
    detect_format,
    load_agent,
    load_agents_from_directory,
)
from realize_core.agents.schema import V1AgentDef, V2AgentDef

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_agents_dir(tmp_path: Path) -> Path:
    """Create a temp directory with sample V1 and V2 agent files."""
    agents_dir = tmp_path / "A-agents"
    agents_dir.mkdir()

    # V1 markdown agent
    (agents_dir / "writer.md").write_text(
        textwrap.dedent("""\
        # Writer Agent

        ## Role
        Content creator and copywriter.

        ## Personality
        - Creative but disciplined
        - Adapts to venture voice

        ## Core Capabilities
        - Blog posts, articles
        - Social media posts
        - Email drafts

        ## Operating Rules
        1. Always read venture-voice.md before writing
        2. Ask about target audience
        3. Produce a draft, then offer to iterate
    """),
        encoding="utf-8",
    )

    # V2 YAML agent
    (agents_dir / "orchestrator.yaml").write_text(
        textwrap.dedent("""\
        name: Orchestrator
        key: orchestrator
        version: "2"
        description: Coordinates all agents and delegates tasks.
        scope: Overall venture coordination
        persona: pm
        inputs:
          - user_message
          - venture_context
        outputs:
          - response
          - delegation_plan
        tools:
          - delegate
          - task_create
        critical_rules:
          - Never act without user confirmation on high-impact tasks
        communication_style: professional
        guardrails:
          - name: no-autonomous-actions
            description: Always confirm before external actions
            enforcement: strict
        pipeline_stages:
          - name: plan
            agent_key: orchestrator
            description: Create execution plan
          - name: execute
            agent_key: writer
            description: Execute the plan
    """),
        encoding="utf-8",
    )

    # Skip file (starts with _)
    (agents_dir / "_README.md").write_text("# Agents directory\n", encoding="utf-8")

    return agents_dir


@pytest.fixture
def v1_file(tmp_agents_dir: Path) -> Path:
    return tmp_agents_dir / "writer.md"


@pytest.fixture
def v2_file(tmp_agents_dir: Path) -> Path:
    return tmp_agents_dir / "orchestrator.yaml"


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


class TestDetectFormat:
    def test_md_is_v1(self):
        assert detect_format("writer.md") == "v1"

    def test_yaml_is_v2(self):
        assert detect_format("agent.yaml") == "v2"

    def test_yml_is_v2(self):
        assert detect_format("agent.yml") == "v2"

    def test_unknown_format(self):
        assert detect_format("agent.json") == "unknown"


# ---------------------------------------------------------------------------
# V1 Loader
# ---------------------------------------------------------------------------


class TestV1Loader:
    def test_loads_v1_agent(self, v1_file: Path):
        agent = load_agent(v1_file)
        assert isinstance(agent, V1AgentDef)
        assert agent.key == "writer"
        assert agent.version == "1"

    def test_extracts_name(self, v1_file: Path):
        agent = load_agent(v1_file)
        assert agent.name == "Writer"

    def test_extracts_role(self, v1_file: Path):
        agent = load_agent(v1_file)
        assert "Content creator" in agent.role

    def test_extracts_capabilities(self, v1_file: Path):
        agent = load_agent(v1_file)
        assert len(agent.capabilities) >= 3
        assert any("Blog" in c for c in agent.capabilities)

    def test_extracts_operating_rules(self, v1_file: Path):
        agent = load_agent(v1_file)
        assert len(agent.operating_rules) >= 3
        assert any("audience" in r.lower() for r in agent.operating_rules)

    def test_stores_raw_content(self, v1_file: Path):
        agent = load_agent(v1_file)
        assert "## Role" in agent.raw_content

    def test_stores_file_path(self, v1_file: Path):
        agent = load_agent(v1_file)
        assert agent.file_path == str(v1_file)


# ---------------------------------------------------------------------------
# V2 Loader
# ---------------------------------------------------------------------------


class TestV2Loader:
    def test_loads_v2_agent(self, v2_file: Path):
        agent = load_agent(v2_file)
        assert isinstance(agent, V2AgentDef)
        assert agent.key == "orchestrator"
        assert agent.version == "2"

    def test_parses_scope(self, v2_file: Path):
        agent = load_agent(v2_file)
        assert "coordination" in agent.scope.lower()

    def test_parses_persona(self, v2_file: Path):
        agent = load_agent(v2_file)
        assert agent.persona == "pm"

    def test_parses_io(self, v2_file: Path):
        agent = load_agent(v2_file)
        assert "user_message" in agent.inputs
        assert "response" in agent.outputs

    def test_parses_tools(self, v2_file: Path):
        agent = load_agent(v2_file)
        assert "delegate" in agent.tools

    def test_parses_critical_rules(self, v2_file: Path):
        agent = load_agent(v2_file)
        assert len(agent.critical_rules) >= 1

    def test_parses_guardrails(self, v2_file: Path):
        agent = load_agent(v2_file)
        assert len(agent.guardrails) == 1
        assert agent.guardrails[0].enforcement == "strict"

    def test_parses_pipeline_stages(self, v2_file: Path):
        agent = load_agent(v2_file)
        assert agent.has_pipeline
        assert len(agent.pipeline_stages) == 2
        assert agent.stage_agent_keys == ["orchestrator", "writer"]

    def test_stores_file_path(self, v2_file: Path):
        agent = load_agent(v2_file)
        assert agent.file_path == str(v2_file)


# ---------------------------------------------------------------------------
# Directory loading
# ---------------------------------------------------------------------------


class TestDirectoryLoader:
    def test_loads_all_agents(self, tmp_agents_dir: Path):
        agents = load_agents_from_directory(tmp_agents_dir)
        assert len(agents) == 2  # writer.md + orchestrator.yaml

    def test_skips_underscore_files(self, tmp_agents_dir: Path):
        agents = load_agents_from_directory(tmp_agents_dir)
        keys = [a.key for a in agents]
        assert "_README" not in keys

    def test_mixed_v1_v2(self, tmp_agents_dir: Path):
        agents = load_agents_from_directory(tmp_agents_dir)
        v1_count = sum(1 for a in agents if isinstance(a, V1AgentDef))
        v2_count = sum(1 for a in agents if isinstance(a, V2AgentDef))
        assert v1_count == 1
        assert v2_count == 1

    def test_empty_directory(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        agents = load_agents_from_directory(empty)
        assert agents == []

    def test_nonexistent_directory(self, tmp_path: Path):
        agents = load_agents_from_directory(tmp_path / "nope")
        assert agents == []


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestLoaderErrors:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_agent(Path("/nonexistent/agent.md"))

    def test_unsupported_format(self, tmp_path: Path):
        bad = tmp_path / "agent.json"
        bad.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            load_agent(bad)

    def test_invalid_yaml(self, tmp_path: Path):
        bad = tmp_path / "broken.yaml"
        bad.write_text("{{{{invalid yaml", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_agent(bad)

    def test_yaml_not_dict(self, tmp_path: Path):
        bad = tmp_path / "list.yaml"
        bad.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a mapping"):
            load_agent(bad)

    def test_v2_key_derived_from_filename(self, tmp_path: Path):
        """V2 agent without explicit key should derive from filename."""
        nokey = tmp_path / "my-agent.yaml"
        nokey.write_text("name: My Agent\nversion: '2'\n", encoding="utf-8")
        agent = load_agent(nokey)
        assert agent.key == "my_agent"
