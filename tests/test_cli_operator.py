"""Tests for Story 7 — operator CLI commands (chat, ask, kb, workflow, skill, evolution).

All new commands talk to a running RealizeOS API instance via HTTP.
We mock the HTTP client to avoid needing a live server.
"""

from __future__ import annotations

from unittest import mock

import pytest
from realize_core.cli_app import app
from typer.testing import CliRunner

runner = CliRunner()


# ------------------------------------------------------------------ #
# Help / smoke tests for new commands                                  #
# ------------------------------------------------------------------ #


class TestNewCommandHelp:
    """Every new Story-7 command should render its --help without error."""

    @pytest.mark.parametrize(
        "cmd",
        [
            ["chat", "--help"],
            ["ask", "--help"],
            ["kb", "--help"],
            ["kb", "search", "--help"],
            ["kb", "get", "--help"],
            ["kb", "reindex", "--help"],
            ["workflow", "--help"],
            ["workflow", "list", "--help"],
            ["workflow", "run", "--help"],
            ["skill", "--help"],
            ["skill", "list", "--help"],
            ["skill", "trigger", "--help"],
            ["evolution", "--help"],
            ["evolution", "run", "--help"],
            ["evolution", "suggestions", "--help"],
            ["evolution", "approve", "--help"],
            ["evolution", "dismiss", "--help"],
        ],
    )
    def test_help_exits_zero(self, cmd: list[str]) -> None:
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0, f"cmd={cmd!r} failed:\n{result.output}"


# ------------------------------------------------------------------ #
# Chat / Ask commands                                                  #
# ------------------------------------------------------------------ #


class TestChatCommand:
    @mock.patch("realize_core.cli_app.commands.chat.api_post")
    def test_chat_table_output(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"response": "Hello from RealizeOS!"}
        result = runner.invoke(app, ["chat", "hello"])
        assert result.exit_code == 0
        assert "Hello from RealizeOS!" in result.output

    @mock.patch("realize_core.cli_app.commands.chat.api_post")
    def test_chat_with_system_and_agent(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"response": "OK"}
        result = runner.invoke(app, ["chat", "test", "--system", "arena", "--agent", "writer"])
        assert result.exit_code == 0
        call_body = mock_post.call_args[1]["json_body"]
        assert call_body["system_key"] == "arena"
        assert call_body["agent_key"] == "writer"

    @mock.patch("realize_core.cli_app.commands.chat.api_post")
    def test_chat_json_format(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"response": "test", "session_id": "abc"}
        result = runner.invoke(app, ["--format", "json", "chat", "hello"])
        assert result.exit_code == 0
        assert '"response"' in result.output


class TestAskCommand:
    @mock.patch("realize_core.cli_app.commands.ask.api_post")
    def test_ask_basic(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"response": "42"}
        result = runner.invoke(app, ["ask", "what is the answer?"])
        assert result.exit_code == 0
        assert "42" in result.output


# ------------------------------------------------------------------ #
# KB commands                                                          #
# ------------------------------------------------------------------ #


class TestKBCommands:
    @mock.patch("realize_core.cli_app.commands.kb.api_get")
    def test_kb_search(self, mock_get: mock.MagicMock) -> None:
        mock_get.return_value = {"results": [{"title": "doc1", "score": 0.9}]}
        result = runner.invoke(app, ["--format", "json", "kb", "search", "investment"])
        assert result.exit_code == 0
        assert "doc1" in result.output

    @mock.patch("realize_core.cli_app.commands.kb.api_get")
    def test_kb_get(self, mock_get: mock.MagicMock) -> None:
        mock_get.return_value = {"id": "d1", "content": "hello world"}
        result = runner.invoke(app, ["--format", "json", "kb", "get", "d1"])
        assert result.exit_code == 0
        assert "hello world" in result.output

    @mock.patch("realize_core.cli_app.commands.kb.api_post")
    def test_kb_reindex(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"message": "Reindexed 15 documents."}
        result = runner.invoke(app, ["kb", "reindex"])
        assert result.exit_code == 0
        assert "Reindex" in result.output


# ------------------------------------------------------------------ #
# Workflow commands                                                    #
# ------------------------------------------------------------------ #


class TestWorkflowCommands:
    @mock.patch("realize_core.cli_app.commands.workflow.api_get")
    def test_workflow_list(self, mock_get: mock.MagicMock) -> None:
        mock_get.return_value = [{"name": "onboard", "status": "active"}]
        result = runner.invoke(app, ["--format", "json", "workflow", "list"])
        assert result.exit_code == 0
        assert "onboard" in result.output

    @mock.patch("realize_core.cli_app.commands.workflow.api_post")
    def test_workflow_run(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"status": "completed", "output": "done"}
        result = runner.invoke(app, ["--format", "json", "workflow", "run", "onboard"])
        assert result.exit_code == 0
        assert "completed" in result.output

    @mock.patch("realize_core.cli_app.commands.workflow.api_post")
    def test_workflow_run_with_input(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"status": "ok"}
        result = runner.invoke(app, ["workflow", "run", "test", "--input", '{"key": "val"}'])
        assert result.exit_code == 0
        call_body = mock_post.call_args[1]["json_body"]
        assert call_body["input"] == {"key": "val"}

    @mock.patch("realize_core.cli_app.commands.workflow.api_post")
    def test_workflow_run_invalid_json(self, mock_post: mock.MagicMock) -> None:
        result = runner.invoke(app, ["workflow", "run", "test", "--input", "not-json"])
        assert result.exit_code == 1


# ------------------------------------------------------------------ #
# Skill commands                                                       #
# ------------------------------------------------------------------ #


class TestSkillCommands:
    @mock.patch("realize_core.cli_app.commands.skill.api_get")
    def test_skill_list(self, mock_get: mock.MagicMock) -> None:
        mock_get.return_value = [{"name": "daily-digest"}]
        result = runner.invoke(app, ["--format", "json", "skill", "list"])
        assert result.exit_code == 0
        assert "daily-digest" in result.output

    @mock.patch("realize_core.cli_app.commands.skill.api_post")
    def test_skill_trigger(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"status": "triggered"}
        result = runner.invoke(app, ["--format", "json", "skill", "trigger", "daily-digest"])
        assert result.exit_code == 0
        assert "triggered" in result.output


# ------------------------------------------------------------------ #
# Evolution commands                                                   #
# ------------------------------------------------------------------ #


class TestEvolutionCommands:
    @mock.patch("realize_core.cli_app.commands.evolution.api_post")
    def test_evolution_run(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"suggestions_created": 3}
        result = runner.invoke(app, ["--format", "json", "evolution", "run"])
        assert result.exit_code == 0
        assert "3" in result.output

    @mock.patch("realize_core.cli_app.commands.evolution.api_get")
    def test_evolution_suggestions(self, mock_get: mock.MagicMock) -> None:
        mock_get.return_value = [{"id": "s1", "status": "pending"}]
        result = runner.invoke(app, ["--format", "json", "evolution", "suggestions"])
        assert result.exit_code == 0
        assert "pending" in result.output

    @mock.patch("realize_core.cli_app.commands.evolution.api_get")
    def test_evolution_suggestions_filtered(self, mock_get: mock.MagicMock) -> None:
        mock_get.return_value = []
        result = runner.invoke(app, ["--format", "json", "evolution", "suggestions", "--status", "approved"])
        assert result.exit_code == 0
        params = mock_get.call_args[1]["params"]
        assert params["status"] == "approved"

    @mock.patch("realize_core.cli_app.commands.evolution.api_post")
    def test_evolution_approve(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"message": "Approved."}
        result = runner.invoke(app, ["evolution", "approve", "s1"])
        assert result.exit_code == 0
        assert "Approved" in result.output or "approved" in result.output

    @mock.patch("realize_core.cli_app.commands.evolution.api_post")
    def test_evolution_dismiss(self, mock_post: mock.MagicMock) -> None:
        mock_post.return_value = {"message": "Dismissed."}
        result = runner.invoke(app, ["evolution", "dismiss", "s2"])
        assert result.exit_code == 0
        assert "Dismissed" in result.output or "dismissed" in result.output


# ------------------------------------------------------------------ #
# HTTP client helper                                                   #
# ------------------------------------------------------------------ #


class TestHTTPClient:
    @mock.patch("realize_core.cli_app.http_client.ProfileManager")
    def test_api_client_sets_api_key_header(self, mock_pm_cls: mock.MagicMock) -> None:
        from realize_core.cli_app.profiles import Profile

        mock_pm = mock_pm_cls.return_value
        mock_pm.get_profile.return_value = Profile(name="test", endpoint="http://test:9090", api_key_env="TEST_KEY")

        import os

        with mock.patch.dict(os.environ, {"TEST_KEY": "secret123"}):
            from realize_core.cli_app.http_client import api_client

            client = api_client("test")
            assert client.headers.get("x-api-key") == "secret123"
            client.close()
