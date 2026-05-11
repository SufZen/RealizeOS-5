"""Tests for the MCP operational tool family (Story 4).

Covers:

* Registry — ops tools register under ``ops``, gated by ``mcp.expose_ops``.
* Scope — list_* are read; run_/trigger_/approve_/dismiss_/reject_ are editor.
* Workflow execution — wraps execute_skill() in-process.
* Evolution gap analysis — wraps run_gap_analysis().
* Approval queue listing — wraps the SQL query in approvals.py.
* Dispatcher integration — scope enforcement, family gating.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from realize_api.dependencies import CurrentUser


@pytest.fixture
def fresh_registry():
    from realize_core.mcp_server import registry as registry_mod

    registry_mod.reset_for_tests()
    yield registry_mod.get_registry()
    registry_mod.reset_for_tests()


def _user(role: str = "owner") -> CurrentUser:
    return CurrentUser(user_id="test-user", role=role)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestOpsRegistry:
    def test_ops_family_registered(self, fresh_registry):
        names = {t.name for t in fresh_registry.all()}
        expected = {
            "list_workflows",
            "run_workflow",
            "trigger_skill",
            "run_evolution",
            "list_suggestions",
            "approve_suggestion",
            "dismiss_suggestion",
            "list_approvals",
            "approve_request",
            "reject_request",
        }
        assert expected <= names

    def test_ops_hidden_when_expose_ops_false(self, fresh_registry):
        from realize_core.mcp_server.config import McpConfig

        cfg = McpConfig(
            enabled=True,
            expose_kb=False,
            expose_ops=False,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        visible = {t.name for t in fresh_registry.visible_tools(cfg)}
        assert "run_workflow" not in visible
        assert "list_workflows" not in visible

    def test_ops_scopes(self, fresh_registry):
        scopes = {t.name: t.scope for t in fresh_registry.all() if t.family == "ops"}
        assert scopes["list_workflows"] == "read"
        assert scopes["list_suggestions"] == "read"
        assert scopes["list_approvals"] == "read"
        assert scopes["run_workflow"] == "editor"
        assert scopes["trigger_skill"] == "editor"
        assert scopes["approve_suggestion"] == "editor"
        assert scopes["dismiss_suggestion"] == "editor"
        assert scopes["run_evolution"] == "editor"


# ---------------------------------------------------------------------------
# list_workflows
# ---------------------------------------------------------------------------


class TestListWorkflows:
    @pytest.mark.asyncio
    async def test_returns_all_skills(self):
        from realize_core.mcp_server.tools.ops_tools import list_workflows

        fake = [
            {"name": "daily_brief", "_version": 2, "triggers": ["brief"], "system_key": "personal"},
            {"name": "weekly_review", "_version": 1, "triggers": ["review"], "system_key": ""},
        ]
        with patch("realize_core.skills.detector.get_all_skills", return_value=fake):
            result = await list_workflows({}, SimpleNamespace(), _user())
        assert result["total"] == 2
        names = [w["name"] for w in result["workflows"]]
        assert names == ["daily_brief", "weekly_review"]

    @pytest.mark.asyncio
    async def test_system_filter(self):
        from realize_core.mcp_server.tools.ops_tools import list_workflows

        fake = [
            {"name": "a", "system_key": "personal"},
            {"name": "b", "system_key": "arena"},
            {"name": "c", "system_key": ""},  # global — should match any system
        ]
        with patch("realize_core.skills.detector.get_all_skills", return_value=fake):
            result = await list_workflows({"system_key": "arena"}, SimpleNamespace(), _user())
        names = [w["name"] for w in result["workflows"]]
        assert "b" in names
        assert "c" in names
        assert "a" not in names


# ---------------------------------------------------------------------------
# run_workflow / trigger_skill
# ---------------------------------------------------------------------------


class TestRunWorkflow:
    @pytest.mark.asyncio
    async def test_validation_missing_name(self):
        from realize_core.mcp_server.tools.ops_tools import run_workflow

        result = await run_workflow({"input_text": "hi"}, SimpleNamespace(), _user())
        assert result["code"] == "MCP_VALIDATION"

    @pytest.mark.asyncio
    async def test_validation_missing_input(self):
        from realize_core.mcp_server.tools.ops_tools import run_workflow

        result = await run_workflow({"name": "x"}, SimpleNamespace(), _user())
        assert result["code"] == "MCP_VALIDATION"

    @pytest.mark.asyncio
    async def test_not_found(self):
        from realize_core.mcp_server.tools.ops_tools import run_workflow

        with patch("realize_core.skills.detector.get_skill_by_name", return_value=None):
            result = await run_workflow({"name": "missing", "input_text": "hi"}, SimpleNamespace(), _user())
        assert result["code"] == "MCP_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_executes_skill_with_state(self):
        from realize_core.mcp_server.tools.ops_tools import run_workflow

        skill = {"name": "daily_brief", "system_key": "personal"}
        state = SimpleNamespace(
            systems={"personal": {"name": "Personal"}},
            shared_config={"identity": "shared/identity.md"},
            kb_path="/tmp/kb",
        )
        with (
            patch(
                "realize_core.skills.detector.get_skill_by_name",
                return_value=skill,
            ),
            patch(
                "realize_core.skills.executor.execute_skill",
                new=AsyncMock(return_value="brief output"),
            ) as exec_mock,
        ):
            result = await run_workflow(
                {"name": "daily_brief", "input_text": "Run the brief"},
                state,
                _user(),
            )

        assert result["output"] == "brief output"
        assert result["system_key"] == "personal"
        # Verify execute_skill received the in-process state
        kwargs = exec_mock.call_args.kwargs
        assert kwargs["skill"] is skill
        assert kwargs["user_message"] == "Run the brief"
        assert kwargs["system_config"] == {"name": "Personal"}
        assert kwargs["channel"] == "mcp"


# ---------------------------------------------------------------------------
# run_evolution
# ---------------------------------------------------------------------------


class TestRunEvolution:
    @pytest.mark.asyncio
    async def test_wraps_gap_analysis(self):
        from realize_core.mcp_server.tools.ops_tools import run_evolution

        fake_suggestions = [{"id": "s1", "title": "Add tool X"}]
        with patch(
            "realize_core.evolution.gap_detector.run_gap_analysis",
            new=AsyncMock(return_value=fake_suggestions),
        ) as mock:
            result = await run_evolution({"days": 14}, SimpleNamespace(), _user())
        mock.assert_awaited_once_with(days=14)
        assert result["count"] == 1
        assert result["suggestions"] == fake_suggestions

    @pytest.mark.asyncio
    async def test_invalid_days(self):
        from realize_core.mcp_server.tools.ops_tools import run_evolution

        result = await run_evolution({"days": 999}, SimpleNamespace(), _user())
        assert result["code"] == "MCP_VALIDATION"


# ---------------------------------------------------------------------------
# Dispatcher integration — scope + family gating
# ---------------------------------------------------------------------------


class TestDispatchOps:
    @pytest.mark.asyncio
    async def test_viewer_cannot_run_workflow(self, fresh_registry):
        from realize_core.mcp_server.auth import bind_user, reset_user
        from realize_core.mcp_server.config import McpConfig
        from realize_core.mcp_server.server import _dispatch

        cfg = McpConfig(
            enabled=True,
            expose_kb=False,
            expose_ops=True,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        token = bind_user(CurrentUser(user_id="v", role="viewer"))
        try:
            out = await _dispatch(
                fresh_registry,
                cfg,
                SimpleNamespace(),
                "run_workflow",
                {"name": "x", "input_text": "y"},
            )
        finally:
            reset_user(token)
        body = json.loads(out[0].text)
        assert body["code"] == "MCP_INSUFFICIENT_SCOPE"

    @pytest.mark.asyncio
    async def test_ops_blocked_when_family_disabled(self, fresh_registry):
        from realize_core.mcp_server.config import McpConfig
        from realize_core.mcp_server.server import _dispatch

        cfg = McpConfig(
            enabled=True,
            expose_kb=False,
            expose_ops=False,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        out = await _dispatch(fresh_registry, cfg, SimpleNamespace(), "run_workflow", {})
        body = json.loads(out[0].text)
        assert body["code"] == "MCP_TOOL_DISABLED"
