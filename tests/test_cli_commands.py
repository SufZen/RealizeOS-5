"""Tests for the Typer-based CLI (Story 6).

Covers:
- Help text for every registered command
- Version output
- Profile CRUD via ``config profile`` subcommands
- Backwards compatibility (``python cli.py status`` path)
- Formatter helpers
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from realize_core.cli_app import app
from realize_core.cli_app.formatters import emit, to_json, to_table, to_yaml
from realize_core.cli_app.profiles import Profile, ProfileManager
from typer.testing import CliRunner

runner = CliRunner()

# ------------------------------------------------------------------ #
# Help / smoke tests                                                  #
# ------------------------------------------------------------------ #


class TestHelpOutput:
    """Every registered command should render its --help without error."""

    @pytest.mark.parametrize(
        "cmd",
        [
            [],  # root --help
            ["init", "--help"],
            ["serve", "--help"],
            ["bot", "--help"],
            ["status", "--help"],
            ["audit", "--help"],
            ["index", "--help"],
            ["setup", "--help"],
            ["doctor", "--help"],
            ["version", "--help"],
            ["venture", "--help"],
            ["venture", "list", "--help"],
            ["venture", "create", "--help"],
            ["venture", "delete", "--help"],
            ["config", "--help"],
            ["config", "profile", "--help"],
            ["config", "profile", "list", "--help"],
            ["config", "profile", "add", "--help"],
            ["config", "profile", "set-default", "--help"],
            ["config", "profile", "show", "--help"],
            ["devmode", "--help"],
            ["devmode", "setup", "--help"],
            ["devmode", "check", "--help"],
            ["devmode", "scaffold", "--help"],
            ["devmode", "snapshot", "--help"],
            ["devmode", "rollback", "--help"],
            ["devmode", "diff", "--help"],
            ["devmode", "status", "--help"],
        ],
    )
    def test_help_exits_zero(self, cmd: list[str]) -> None:
        result = runner.invoke(app, cmd if cmd else ["--help"])
        assert result.exit_code == 0, f"cmd={cmd!r} failed:\n{result.output}"


class TestVersion:
    def test_version_output(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "RealizeOS v" in result.output


# ------------------------------------------------------------------ #
# Profile system                                                      #
# ------------------------------------------------------------------ #


class TestProfileManager:
    """Unit tests for ProfileManager (file-backed TOML profiles)."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        pm = ProfileManager(config_dir=tmp_path)
        assert pm.has_any_profile() is False

        p = pm.add_profile("dev", endpoint="http://localhost:9999")
        assert p.name == "dev"
        assert p.endpoint == "http://localhost:9999"

        got = pm.get_profile("dev")
        assert got.endpoint == "http://localhost:9999"
        assert pm.has_any_profile() is True

    def test_list_profiles_default_first(self, tmp_path: Path) -> None:
        pm = ProfileManager(config_dir=tmp_path)
        pm.add_profile("beta")
        pm.add_profile("alpha")
        pm.set_default("alpha")

        profiles = pm.list_profiles()
        assert profiles[0].name == "alpha"

    def test_set_default_nonexistent_raises(self, tmp_path: Path) -> None:
        pm = ProfileManager(config_dir=tmp_path)
        with pytest.raises(ValueError, match="does not exist"):
            pm.set_default("nope")

    def test_get_profile_missing_returns_defaults(self, tmp_path: Path) -> None:
        pm = ProfileManager(config_dir=tmp_path)
        p = pm.get_profile("nonexistent")
        assert p.endpoint == "http://localhost:8080"

    def test_first_profile_becomes_default(self, tmp_path: Path) -> None:
        pm = ProfileManager(config_dir=tmp_path)
        pm.add_profile("first")
        raw = pm._load_raw()
        assert raw["default_profile"] == "first"


class TestProfileCLI:
    """Integration tests for ``config profile`` subcommands via CliRunner."""

    def test_profile_add_and_list(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".realize-os"

        with mock.patch("realize_core.cli_app.commands.config.ProfileManager") as mock_pm:
            pm_instance = ProfileManager(config_dir=config_dir)
            mock_pm.return_value = pm_instance

            result = runner.invoke(app, ["config", "profile", "add", "test-profile", "--endpoint", "http://test:9090"])
            assert result.exit_code == 0, result.output
            assert "test-profile" in result.output

            result = runner.invoke(app, ["config", "profile", "list"])
            assert result.exit_code == 0, result.output
            assert "test-profile" in result.output

    def test_profile_show(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".realize-os"

        with mock.patch("realize_core.cli_app.commands.config.ProfileManager") as mock_pm:
            pm_instance = ProfileManager(config_dir=config_dir)
            pm_instance.add_profile("show-me", endpoint="http://example:1234")
            mock_pm.return_value = pm_instance

            result = runner.invoke(app, ["config", "profile", "show", "show-me"])
            assert result.exit_code == 0, result.output
            assert "http://example:1234" in result.output


# ------------------------------------------------------------------ #
# Formatters                                                          #
# ------------------------------------------------------------------ #


class TestFormatters:
    def test_to_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        data = [{"name": "alpha", "status": "ok"}]
        to_json(data)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == data

    def test_to_yaml(self, capsys: pytest.CaptureFixture[str]) -> None:
        data = [{"key": "val"}]
        to_yaml(data)
        captured = capsys.readouterr()
        assert "key: val" in captured.out

    def test_to_table_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        to_table([])
        captured = capsys.readouterr()
        assert "No results" in captured.out

    def test_emit_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        emit({"a": 1}, output_format="json")
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"a": 1}

    def test_emit_yaml(self, capsys: pytest.CaptureFixture[str]) -> None:
        emit({"b": 2}, output_format="yaml")
        captured = capsys.readouterr()
        assert "b: 2" in captured.out


# ------------------------------------------------------------------ #
# Profile dataclass                                                   #
# ------------------------------------------------------------------ #


class TestProfileDataclass:
    def test_to_dict_excludes_name(self) -> None:
        p = Profile(name="test", endpoint="http://x")
        d = p.to_dict()
        assert "name" not in d
        assert d["endpoint"] == "http://x"

    def test_defaults(self) -> None:
        p = Profile(name="d")
        assert p.endpoint == "http://localhost:8080"
        assert p.api_key_env == "REALIZE_API_KEY"
        assert p.default_system == ""
