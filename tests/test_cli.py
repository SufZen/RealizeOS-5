"""Tests for realize_core.cli — CLI entry point."""

import tempfile
from pathlib import Path

from realize_core.cli import cmd_init, main


class TestCmdInit:
    def test_scaffolds_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = cmd_init(tmpdir, "full", "test-project")
            assert result == 0

            # Check directories were created
            assert (Path(tmpdir) / "config").is_dir()
            assert (Path(tmpdir) / "skills").is_dir()
            assert (Path(tmpdir) / "workflows").is_dir()
            assert (Path(tmpdir) / "docs" / "dev-process" / "active").is_dir()
            assert (Path(tmpdir) / "channels").is_dir()  # Full tier only

    def test_creates_workspace_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_init(tmpdir, "full", "my-project")
            ws = Path(tmpdir) / "config" / "workspace.yaml"
            assert ws.exists()
            content = ws.read_text()
            assert "my-project" in content
            assert "full" in content

    def test_creates_env_example(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_init(tmpdir, "full", "test")
            env = Path(tmpdir) / ".env.example"
            assert env.exists()
            content = env.read_text()
            assert "ANTHROPIC_API_KEY" in content

    def test_creates_claude_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_init(tmpdir, "full", "my-proj")
            claude_md = Path(tmpdir) / "CLAUDE.md"
            assert claude_md.exists()
            content = claude_md.read_text()
            assert "my-proj" in content

    def test_lite_tier_no_channels_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_init(tmpdir, "lite", "lite-project")
            assert not (Path(tmpdir) / "channels").is_dir()  # Lite = no channels dir
            assert (Path(tmpdir) / "config").is_dir()  # But still has config

    def test_idempotent(self):
        """Running init twice should not overwrite existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_init(tmpdir, "full", "first")
            ws = Path(tmpdir) / "config" / "workspace.yaml"
            original = ws.read_text()

            cmd_init(tmpdir, "full", "second")
            assert ws.read_text() == original  # Not overwritten


class TestMainCLI:
    def test_no_args_shows_help(self, capsys):
        result = main([])
        assert result == 0

    def test_init_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = main(["init", tmpdir, "--name", "cli-test"])
            assert result == 0
            assert (Path(tmpdir) / "config" / "workspace.yaml").exists()

    def test_status_command(self, capsys):
        result = main(["status"])
        assert result == 0
        captured = capsys.readouterr()
        assert "RealizeOS Status" in captured.out
