"""STORY-14 — integrations registered as registry tools, governed by the trust ladder."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def fresh_registry(monkeypatch):
    """A clean global ToolRegistry for each test."""
    import realize_core.tools.tool_registry as tr

    monkeypatch.setattr(tr, "_registry", None)
    return tr.get_tool_registry()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_integrations_registered(self, fresh_registry):
        fresh_registry.auto_discover()

        names = set(fresh_registry.status_summary()["tools"])
        assert {"web", "google_workspace", "google_sheets", "clickup", "mcp"} <= names
        for action in ("gmail_search", "drive_upload", "sheets_append", "clickup_create_task", "web_fetch"):
            assert fresh_registry.get_tool_for_action(action) is not None, action

    def test_read_write_classification(self, fresh_registry):
        fresh_registry.auto_discover()

        assert fresh_registry.is_destructive("sheets_append") is True
        assert fresh_registry.is_destructive("gmail_send") is True
        assert fresh_registry.is_destructive("sheets_read") is False
        assert fresh_registry.is_destructive("gmail_search") is False
        assert fresh_registry.is_destructive("no_such_action") is None

    def test_app_startup_populates_registry(self, fresh_registry, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        from realize_api.main import create_app

        monkeypatch.chdir(tmp_path)
        with TestClient(create_app()):
            assert fresh_registry.get_tool_for_action("sheets_read") is not None


# ---------------------------------------------------------------------------
# FunctionMapTool adapter
# ---------------------------------------------------------------------------


def _tool(func, writes=()):
    from realize_core.tools.base_tool import ToolCategory
    from realize_core.tools.function_tool import FunctionMapTool

    return FunctionMapTool(
        name="t",
        description="test",
        category=ToolCategory.CUSTOM,
        schemas=[{"name": "act", "description": "d", "input_schema": {"type": "object", "properties": {}}}],
        functions={"act": func},
        write_actions=writes,
    )


class TestFunctionMapTool:
    @pytest.mark.asyncio
    async def test_success_renders_readable_json(self):
        async def act(**_):
            return {"פרויקט": "מגדל", "budget": 1200000}

        result = await _tool(act).execute("act", {})
        assert result.success
        assert "מגדל" in result.output  # not \\u-escaped
        assert result.data == {"פרויקט": "מגדל", "budget": 1200000}

    @pytest.mark.asyncio
    async def test_in_band_error_becomes_failure(self):
        async def act(**_):
            return {"error": "Spreadsheet not found"}

        result = await _tool(act).execute("act", {})
        assert not result.success
        assert result.error == "Spreadsheet not found"

    @pytest.mark.asyncio
    async def test_bad_arguments_reported_to_model(self):
        async def act(spreadsheet_id: str):
            return {}

        result = await _tool(act).execute("act", {"wrong": 1})
        assert not result.success
        assert "Invalid parameters" in result.error

    def test_output_truncated(self):
        from realize_core.tools.function_tool import MAX_OUTPUT_CHARS, render_output

        assert len(render_output("x" * (MAX_OUTPUT_CHARS + 500))) < MAX_OUTPUT_CHARS + 50

    def test_write_flag_from_write_actions(self):
        async def act(**_):
            return {}

        assert _tool(act, writes={"act"}).get_write_actions() == {"act"}


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


class TestAvailability:
    def test_google_needs_stored_tokens(self, tmp_path, monkeypatch):
        from realize_core.tools.google_auth import has_stored_credentials

        monkeypatch.setenv("GOOGLE_OAUTH_TOKENS_PATH", str(tmp_path / "missing.json"))
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "nodata"))
        assert has_stored_credentials() is False

        token = tmp_path / "tokens.json"
        token.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_OAUTH_TOKENS_PATH", str(token))
        assert has_stored_credentials() is True

    def test_clickup_needs_api_key(self, monkeypatch):
        from realize_core.tools.pm_tools import get_tool

        monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
        assert get_tool().is_available() is False
        monkeypatch.setenv("CLICKUP_API_KEY", "pk_test")
        assert get_tool().is_available() is True


# ---------------------------------------------------------------------------
# MCP bridge
# ---------------------------------------------------------------------------


class _FakeServer:
    def __init__(self, tools, connected=True):
        self._tools = tools
        self.connected = connected

    def describe_tools(self):
        return self._tools


@pytest.fixture
def fake_mcp(monkeypatch):
    import realize_core.tools.mcp as mcp_mod

    calls = []

    async def call_tool(name, args):
        calls.append((name, args))
        return "Error: boom" if name.endswith("explode") else f"ran {name}"

    server = _FakeServer(
        [
            ({"name": "mcp__files__read", "description": "read", "input_schema": {"type": "object"}}, True),
            ({"name": "mcp__files__delete", "description": "delete", "input_schema": {"type": "object"}}, False),
            ({"name": "mcp__files__explode", "description": "x", "input_schema": {"type": "object"}}, True),
        ]
    )
    hub = SimpleNamespace(servers={"files": server}, call_tool=call_tool)
    monkeypatch.setattr(mcp_mod, "get_mcp_hub", lambda: hub)
    return server, calls


class TestMCPBridge:
    @pytest.mark.asyncio
    async def test_actions_resolved_dynamically(self, fresh_registry, fake_mcp):
        from realize_core.tools.mcp_bridge_tool import MCPBridgeTool

        fresh_registry.register(MCPBridgeTool())

        result = await fresh_registry.execute("mcp__files__read", {"path": "a"})
        assert result.success
        assert result.output == "ran mcp__files__read"
        assert fresh_registry.is_destructive("mcp__files__read") is False
        assert fresh_registry.is_destructive("mcp__files__delete") is True

    @pytest.mark.asyncio
    async def test_in_band_error(self, fresh_registry, fake_mcp):
        from realize_core.tools.mcp_bridge_tool import MCPBridgeTool

        fresh_registry.register(MCPBridgeTool())
        result = await fresh_registry.execute("mcp__files__explode", {})
        assert not result.success

    def test_unavailable_when_no_server_connected(self, fake_mcp):
        from realize_core.tools.mcp_bridge_tool import MCPBridgeTool

        server, _ = fake_mcp
        server.connected = False
        tool = MCPBridgeTool()
        assert tool.is_available() is False
        assert tool.get_schemas() == []


# ---------------------------------------------------------------------------
# Trust ladder alignment
# ---------------------------------------------------------------------------


class TestTrustLadder:
    @pytest.mark.parametrize(
        "action",
        [
            "sheets_append",
            "sheets_create",
            "drive_upload",
            "gmail_reply",
            "clickup_create_task",
            "drive_set_permissions",
        ],
    )
    def test_business_writes_need_approval_at_default_level(self, action):
        from realize_core.governance.trust_ladder import TrustDecision, check_trust

        assert check_trust(action, {}) is TrustDecision.APPROVE

    def test_unknown_read_is_auto_unknown_write_needs_approval(self):
        from realize_core.governance.trust_ladder import TrustDecision, check_trust

        assert check_trust("mcp__x__list", {}, is_destructive=False) is TrustDecision.AUTO
        assert check_trust("mcp__x__delete", {}, is_destructive=True) is TrustDecision.APPROVE
        assert check_trust("mcp__x__delete", {"trust": {"level": 1}}, is_destructive=True) is TrustDecision.BLOCK
        assert check_trust("mcp__x__delete", {"trust": {"level": 5}}, is_destructive=True) is TrustDecision.AUTO

    @pytest.mark.asyncio
    async def test_gate_holds_unmapped_mcp_write(self, fresh_registry, fake_mcp):
        from realize_core.governance.tool_gate import ToolGate
        from realize_core.tools.mcp_bridge_tool import MCPBridgeTool

        _, calls = fake_mcp
        fresh_registry.register(MCPBridgeTool())
        fresh_registry.set_gate(ToolGate(config={}))

        held = await fresh_registry.execute("mcp__files__delete", {"path": "contract.pdf"})
        assert held.metadata.get("requires_human") is True
        assert calls == []  # never executed

        read = await fresh_registry.execute("mcp__files__read", {"path": "a"})
        assert read.success
        assert calls == [("mcp__files__read", {"path": "a"})]


@pytest.mark.asyncio
async def test_legacy_two_arg_gate_still_holds(fresh_registry, fake_mcp):
    """A gate implementing the original decide(action, params) must not fail open."""
    from realize_core.governance.tool_gate import GateDecision, GateOutcome
    from realize_core.tools.mcp_bridge_tool import MCPBridgeTool

    class LegacyGate:
        def decide(self, action_name, params):
            return GateDecision(GateOutcome.NEEDS_APPROVAL, action_name, request_id="r1")

    _, calls = fake_mcp
    fresh_registry.register(MCPBridgeTool())
    fresh_registry.set_gate(LegacyGate())

    result = await fresh_registry.execute("mcp__files__read", {})
    assert result.metadata.get("request_id") == "r1"
    assert calls == []
