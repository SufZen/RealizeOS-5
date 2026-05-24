"""Tests for Story 8 — MCP subcommands, REPL, config show/set/unset.

Tests cover:
  - MCP serve/status/token help and mock invocations
  - REPL help smoke test and slash-command handler
  - config show / set / unset with a temp realize-os.yaml
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
import yaml
from realize_core.cli_app import app
from realize_core.cli_app.commands.repl import _handle_slash
from typer.testing import CliRunner

runner = CliRunner()


# ------------------------------------------------------------------ #
# Help smoke tests for Story 8 commands                                #
# ------------------------------------------------------------------ #


class TestStory8Help:
    """Every Story-8 command should render --help without error."""

    @pytest.mark.parametrize(
        "cmd",
        [
            ["mcp", "--help"],
            ["mcp", "serve", "--help"],
            ["mcp", "status", "--help"],
            ["mcp", "token", "--help"],
            ["repl", "--help"],
            ["config", "show", "--help"],
            ["config", "set", "--help"],
            ["config", "unset", "--help"],
        ],
    )
    def test_help_exits_zero(self, cmd: list[str]) -> None:
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0, f"cmd={cmd!r} failed:\n{result.output}"


# ------------------------------------------------------------------ #
# MCP commands                                                         #
# ------------------------------------------------------------------ #


class TestMCPStatus:
    @mock.patch("realize_core.cli_app.commands.mcp.api_get")
    def test_mcp_status_json(self, mock_get: mock.MagicMock) -> None:
        mock_get.return_value = {"mcp_enabled": True, "tools": 24}
        result = runner.invoke(app, ["--format", "json", "mcp", "status"])
        assert result.exit_code == 0
        assert "mcp_enabled" in result.output


class TestMCPToken:
    @mock.patch("realize_core.cli_app.commands.mcp.api_post")
    def test_mcp_token_prints_jwt(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"access_token": "eyJhbGciOi..."}
        result = runner.invoke(app, ["mcp", "token", "--user", "admin"])
        assert result.exit_code == 0
        assert "eyJhbGciOi" in result.output


# ------------------------------------------------------------------ #
# REPL slash-command handler                                           #
# ------------------------------------------------------------------ #


class TestREPLSlashCommands:
    def test_exit(self) -> None:
        assert _handle_slash("/exit", {}) == "exit"

    def test_quit(self) -> None:
        assert _handle_slash("/quit", {}) == "exit"

    def test_clear(self) -> None:
        assert _handle_slash("/clear", {}) == "clear"

    def test_help(self) -> None:
        assert _handle_slash("/help", {}) == "help"

    def test_system_switch(self) -> None:
        result = _handle_slash("/system arena", {"current_system": None})
        assert isinstance(result, dict)
        assert result["current_system"] == "arena"

    def test_agent_switch(self) -> None:
        result = _handle_slash("/agent writer", {"current_agent": None})
        assert isinstance(result, dict)
        assert result["current_agent"] == "writer"

    def test_session_set(self) -> None:
        result = _handle_slash("/session abc123", {"session_id": None})
        assert isinstance(result, dict)
        assert result["session_id"] == "abc123"

    def test_unknown_command(self) -> None:
        assert _handle_slash("/foobar", {}) == "unknown"


# ------------------------------------------------------------------ #
# Config show / set / unset                                            #
# ------------------------------------------------------------------ #


class TestConfigShowSetUnset:
    @pytest.fixture
    def cfg_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Create a temp directory with a realize-os.yaml."""
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / "realize-os.yaml"
        cfg.write_text(yaml.dump({"mcp": {"enabled": True, "allow_admin": False}}))
        return tmp_path

    def test_config_show_all(self, cfg_dir: Path) -> None:
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "mcp" in result.output
        assert "enabled" in result.output

    def test_config_show_key(self, cfg_dir: Path) -> None:
        result = runner.invoke(app, ["config", "show", "mcp.enabled"])
        assert result.exit_code == 0
        assert "True" in result.output

    def test_config_show_missing_key(self, cfg_dir: Path) -> None:
        result = runner.invoke(app, ["config", "show", "nonexistent.key"])
        assert result.exit_code == 1

    def test_config_set_new_key(self, cfg_dir: Path) -> None:
        result = runner.invoke(app, ["config", "set", "mcp.port", "9090"])
        assert result.exit_code == 0
        assert "9090" in result.output

        # Verify persistence
        with (cfg_dir / "realize-os.yaml").open() as fh:
            data = yaml.safe_load(fh)
        assert data["mcp"]["port"] == 9090

    def test_config_set_bool(self, cfg_dir: Path) -> None:
        result = runner.invoke(app, ["config", "set", "mcp.allow_admin", "true"])
        assert result.exit_code == 0

        with (cfg_dir / "realize-os.yaml").open() as fh:
            data = yaml.safe_load(fh)
        assert data["mcp"]["allow_admin"] is True

    def test_config_set_creates_intermediates(self, cfg_dir: Path) -> None:
        result = runner.invoke(app, ["config", "set", "new.deeply.nested.key", "hello"])
        assert result.exit_code == 0

        with (cfg_dir / "realize-os.yaml").open() as fh:
            data = yaml.safe_load(fh)
        assert data["new"]["deeply"]["nested"]["key"] == "hello"

    def test_config_unset(self, cfg_dir: Path) -> None:
        result = runner.invoke(app, ["config", "unset", "mcp.allow_admin"])
        assert result.exit_code == 0
        assert "Removed" in result.output

        with (cfg_dir / "realize-os.yaml").open() as fh:
            data = yaml.safe_load(fh)
        assert "allow_admin" not in data["mcp"]

    def test_config_unset_missing(self, cfg_dir: Path) -> None:
        result = runner.invoke(app, ["config", "unset", "nonexistent.key"])
        assert result.exit_code == 1

    def test_config_show_no_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 1


# ------------------------------------------------------------------ #
# Auto-cast helper                                                     #
# ------------------------------------------------------------------ #


class TestAutoCast:
    def test_bool_true(self) -> None:
        from realize_core.cli_app.commands.config import _auto_cast

        assert _auto_cast("true") is True
        assert _auto_cast("yes") is True
        assert _auto_cast("on") is True

    def test_bool_false(self) -> None:
        from realize_core.cli_app.commands.config import _auto_cast

        assert _auto_cast("false") is False

    def test_int(self) -> None:
        from realize_core.cli_app.commands.config import _auto_cast

        assert _auto_cast("42") == 42

    def test_float(self) -> None:
        from realize_core.cli_app.commands.config import _auto_cast

        assert _auto_cast("3.14") == 3.14

    def test_null(self) -> None:
        from realize_core.cli_app.commands.config import _auto_cast

        assert _auto_cast("null") is None

    def test_string(self) -> None:
        from realize_core.cli_app.commands.config import _auto_cast

        assert _auto_cast("hello") == "hello"
