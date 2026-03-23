"""Tests for realize_core.config — YAML config loading and system building.

Covers:
- Basic config loading and system building
- Environment variable interpolation
- Missing config file defaults
- Invalid YAML handling
- Agent auto-discovery
"""

import os
from pathlib import Path


def _write_config(tmp_dir: Path, content: str) -> Path:
    config_path = tmp_dir / "realize-os.yaml"
    config_path.write_text(content)
    return config_path


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_load_config_basic(self, tmp_path):
        """Test loading a basic config."""
        _write_config(
            tmp_path,
            """
name: "Test Business"
systems:
  - key: test
    name: "Test System"
    directory: systems/test
""",
        )
        from realize_core.config import load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        assert config["name"] == "Test Business"
        assert len(config["systems"]) == 1
        assert config["systems"][0]["key"] == "test"

    def test_load_config_multiple_systems(self, tmp_path):
        """Test loading config with multiple systems."""
        _write_config(
            tmp_path,
            """
name: "Multi System"
systems:
  - key: alpha
    name: "Alpha"
    directory: systems/alpha
  - key: beta
    name: "Beta"
    directory: systems/beta
  - key: gamma
    name: "Gamma"
    directory: systems/gamma
""",
        )
        from realize_core.config import load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        assert len(config["systems"]) == 3

    def test_missing_config_returns_defaults(self, tmp_path):
        """Missing config file should return a default config dict."""
        from realize_core.config import load_config

        config = load_config(str(tmp_path / "nonexistent.yaml"))
        assert "name" in config
        assert "systems" in config
        assert isinstance(config["systems"], list)

    def test_config_with_features(self, tmp_path):
        """Config with features section loads correctly."""
        _write_config(
            tmp_path,
            """
name: "Feature Test"
systems: []
features:
  review_pipeline: true
  auto_memory: false
  proactive_mode: true
""",
        )
        from realize_core.config import load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        assert config["features"]["review_pipeline"] is True
        assert config["features"]["auto_memory"] is False

    def test_config_with_shared_section(self, tmp_path):
        """Config with shared section loads correctly."""
        _write_config(
            tmp_path,
            """
name: "Shared Test"
systems: []
shared:
  identity: shared/identity.md
  preferences: shared/user-preferences.md
""",
        )
        from realize_core.config import load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        assert config["shared"]["identity"] == "shared/identity.md"


# ---------------------------------------------------------------------------
# Environment variable interpolation
# ---------------------------------------------------------------------------


class TestEnvVarInterpolation:
    def test_env_var_resolved(self, tmp_path):
        """${VAR} is resolved from environment."""
        os.environ["TEST_API_KEY_CONFIG"] = "test-key-123"
        _write_config(
            tmp_path,
            """
name: "Env Test"
llm:
  api_key: "${TEST_API_KEY_CONFIG}"
systems:
  - key: test
    name: "Test"
    directory: systems/test
""",
        )
        from realize_core.config import load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        assert config["llm"]["api_key"] == "test-key-123"
        del os.environ["TEST_API_KEY_CONFIG"]

    def test_missing_env_var_resolves_to_empty(self, tmp_path):
        """${NONEXISTENT_VAR} resolves to empty string."""
        # Ensure the var doesn't exist
        os.environ.pop("DEFINITELY_NOT_SET_XYZ", None)
        _write_config(
            tmp_path,
            """
name: "Missing Env"
settings:
  key: "${DEFINITELY_NOT_SET_XYZ}"
systems: []
""",
        )
        from realize_core.config import load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        assert config["settings"]["key"] == ""

    def test_multiple_env_vars_in_one_file(self, tmp_path):
        """Multiple ${VAR} references in one config file."""
        os.environ["TEST_HOST"] = "localhost"
        os.environ["TEST_PORT"] = "8080"
        _write_config(
            tmp_path,
            """
name: "Multi Env"
server:
  host: "${TEST_HOST}"
  port: "${TEST_PORT}"
systems: []
""",
        )
        from realize_core.config import load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        assert config["server"]["host"] == "localhost"
        assert config["server"]["port"] == "8080"
        del os.environ["TEST_HOST"]
        del os.environ["TEST_PORT"]


# ---------------------------------------------------------------------------
# System dict building
# ---------------------------------------------------------------------------


class TestBuildSystemsDict:
    def test_build_systems_dict(self, tmp_path):
        """Test building the systems lookup dict."""
        _write_config(
            tmp_path,
            """
name: "Multi System"
systems:
  - key: alpha
    name: "Alpha"
    directory: systems/alpha
  - key: beta
    name: "Beta"
    directory: systems/beta
""",
        )
        from realize_core.config import build_systems_dict, load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        systems = build_systems_dict(config)
        assert "alpha" in systems
        assert "beta" in systems
        assert systems["alpha"]["name"] == "Alpha"

    def test_systems_dict_has_fabric_paths(self, tmp_path):
        """Each system should have FABRIC directory paths."""
        _write_config(
            tmp_path,
            """
name: "FABRIC Test"
systems:
  - key: test
    name: "Test"
    directory: systems/test
""",
        )
        from realize_core.config import build_systems_dict, load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        systems = build_systems_dict(config)
        test_sys = systems["test"]
        assert "foundations" in test_sys
        assert "agents_dir" in test_sys
        assert "brain_dir" in test_sys
        assert "routines_dir" in test_sys

    def test_agent_auto_discovery(self, tmp_path):
        """Agents are auto-discovered from A-agents/ directory."""
        # Create agent files
        agents_dir = tmp_path / "systems" / "test" / "A-agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "orchestrator.md").write_text("# Orchestrator")
        (agents_dir / "writer.md").write_text("# Writer")
        (agents_dir / "_README.md").write_text("# Agents readme")

        _write_config(
            tmp_path,
            """
name: "Discovery Test"
systems:
  - key: test
    name: "Test"
    directory: systems/test
""",
        )
        from realize_core.config import build_systems_dict, load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        systems = build_systems_dict(config, kb_path=tmp_path)
        agents = systems["test"]["agents"]
        assert "orchestrator" in agents
        assert "writer" in agents
        # _README.md should be excluded
        assert "_README" not in agents

    def test_empty_agents_dir(self, tmp_path):
        """Empty agents directory returns empty dict."""
        agents_dir = tmp_path / "systems" / "test" / "A-agents"
        agents_dir.mkdir(parents=True)

        _write_config(
            tmp_path,
            """
name: "Empty Agents"
systems:
  - key: test
    name: "Test"
    directory: systems/test
""",
        )
        from realize_core.config import build_systems_dict, load_config

        config = load_config(str(tmp_path / "realize-os.yaml"))
        systems = build_systems_dict(config, kb_path=tmp_path)
        assert systems["test"]["agents"] == {}
