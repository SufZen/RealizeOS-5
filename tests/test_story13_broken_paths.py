"""STORY-13 — regression tests for code paths that referenced things that don't exist."""

from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# realize_core.engine (channels/base.py imported a missing module)
# ---------------------------------------------------------------------------


@pytest.fixture
def engine_env(monkeypatch):
    """Patch config loading and the core handler used by realize_core.engine."""
    import realize_core.base_handler as bh
    import realize_core.config as cfg

    systems = {"acme": {"name": "Acme"}}
    monkeypatch.setattr(cfg, "load_config", lambda *a, **k: {"features": {"activity_log": True}})
    monkeypatch.setattr(cfg, "build_systems_dict", lambda *a, **k: systems)
    handler = mock.AsyncMock(return_value="hello from acme")
    monkeypatch.setattr(bh, "process_message", handler)
    return systems, handler


class TestEngineEntryPoint:
    @pytest.mark.asyncio
    async def test_single_venture_resolved_and_features_passed(self, engine_env):
        from realize_core.engine import process_message

        _, handler = engine_env
        reply = await process_message(user_id="u1", text="hi", channel="telegram")

        assert reply == "hello from acme"
        kwargs = handler.call_args.kwargs
        assert kwargs["system_key"] == "acme"
        assert kwargs["message"] == "hi"
        assert kwargs["channel"] == "telegram"
        assert kwargs["features"]["activity_log"] is True
        assert kwargs["all_systems"] == {"acme": {"name": "Acme"}}

    @pytest.mark.asyncio
    async def test_ambiguous_venture_asks_user(self, engine_env):
        from realize_core.engine import process_message

        systems, handler = engine_env
        systems["beta"] = {"name": "Beta"}
        reply = await process_message(user_id="u1", text="hi")

        assert "acme" in reply
        assert "beta" in reply
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_ventures_configured(self, engine_env):
        from realize_core.engine import process_message

        systems, handler = engine_env
        systems.clear()
        reply = await process_message(user_id="u1", text="hi")

        assert "no ventures" in reply.lower()
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_channel_handle_incoming_reaches_engine(self, engine_env):
        from realize_core.channels.api import APIChannel
        from realize_core.channels.base import IncomingMessage

        out = await APIChannel().handle_incoming(IncomingMessage(user_id="u1", text="hi", system_key="acme"))

        assert out.text == "hello from acme"
        assert out.channel == "api"


# ---------------------------------------------------------------------------
# workflows: prompt node called a non-existent router.route_and_query
# ---------------------------------------------------------------------------


class TestWorkflowPromptNode:
    @pytest.mark.asyncio
    async def test_prompt_node_routes_through_route_to_llm(self, monkeypatch):
        from realize_core.llm import router
        from realize_core.workflows import NodeType, WorkflowContext, WorkflowNode, WorkflowRunner

        llm = mock.AsyncMock(return_value="summary text")
        monkeypatch.setattr(router, "route_to_llm", llm)

        node = WorkflowNode(
            id="p",
            node_type=NodeType.PROMPT,
            config={"prompt": "Summarize {topic}", "task_type": "simple"},
        )
        result = await WorkflowRunner()._run_prompt(node, WorkflowContext("wf", variables={"topic": "Q3"}))

        assert result == {"output": "summary text"}
        kwargs = llm.call_args.kwargs
        assert kwargs["messages"] == [{"role": "user", "content": "Summarize Q3"}]
        assert kwargs["task_type"] == "simple"


# ---------------------------------------------------------------------------
# settings: MCP status read hub._connections (attribute is `servers`)
# ---------------------------------------------------------------------------


def test_settings_tools_lists_mcp_servers(monkeypatch):
    import realize_core.tools.mcp as mcp_mod
    from realize_api.main import create_app

    fake_hub = SimpleNamespace(
        servers={"files": SimpleNamespace(enabled=True, connected=True, tools=[{"name": "read"}, {"name": "write"}])}
    )
    monkeypatch.setattr(mcp_mod, "get_mcp_hub", lambda: fake_hub)

    resp = TestClient(create_app()).get("/api/tools")

    assert resp.status_code == 200
    assert {"name": "files", "enabled": True, "connected": True, "tools_count": 2} in resp.json()["mcp_servers"]


# ---------------------------------------------------------------------------
# DB-backed fixes: reports column, webhook activity rows
# ---------------------------------------------------------------------------


@pytest.fixture
def op_db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    db_path = tmp_path / "ops.db"
    set_db_path(db_path)
    init_schema(db_path)
    yield db_path
    set_db_path(None)


@pytest.mark.asyncio
async def test_weekly_review_counts_approval_decisions(op_db, tmp_path):
    from realize_core.db.schema import get_connection
    from realize_core.scheduler.reports import generate_weekly_review

    conn = get_connection()
    conn.execute(
        "INSERT INTO approval_queue (id, venture_key, agent_key, action_type, status, decided_at) "
        "VALUES ('a1', 'acme', 'w', 'send', 'approved', strftime('%Y-%m-%dT%H:%M:%f','now'))"
    )
    conn.commit()
    conn.close()

    report = await generate_weekly_review({}, tmp_path, features={"approval_gates": True})

    assert "## Approvals" in report
    assert "Approved: 1" in report


def _webhook_client(secret: str = "") -> TestClient:
    from realize_api.main import create_app

    app = create_app()
    app.state.config = {"features": {"webhook_secret": secret}} if secret else {"features": {}}
    return TestClient(app)


def test_webhook_logs_activity_row(op_db):
    from realize_core.db.schema import get_connection

    resp = _webhook_client().post("/api/webhooks/github", json={"action": "opened"})
    assert resp.status_code == 200

    conn = get_connection()
    rows = conn.execute("SELECT actor_type, actor_id, action FROM activity_events").fetchall()
    conn.close()
    assert ("system", "webhook:github", "webhook_received") in [tuple(r) for r in rows]


class TestWebhookAuth:
    """With auth on, only HMAC-signed deliveries bypass the API key."""

    @pytest.fixture(autouse=True)
    def _auth_on(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("REALIZE_API_KEY", "test-key")
        monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)

    def test_signed_delivery_accepted_without_api_key(self):
        body = json.dumps({"action": "opened"}).encode()
        sig = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()

        resp = _webhook_client("s3cret").post(
            "/api/webhooks/github", content=body, headers={"X-Webhook-Signature": sig}
        )
        assert resp.status_code == 200

    def test_bad_signature_rejected(self):
        resp = _webhook_client("s3cret").post(
            "/api/webhooks/github", content=b"{}", headers={"X-Webhook-Signature": "nope"}
        )
        assert resp.status_code == 401

    def test_without_secret_requires_api_key(self):
        resp = _webhook_client().post("/api/webhooks/github", json={})
        assert resp.status_code == 401

    def test_events_listing_never_public(self):
        resp = _webhook_client("s3cret").get("/api/webhooks/events")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /chat passed neither features nor all_systems
# ---------------------------------------------------------------------------


def test_chat_passes_features_and_hides_errors(monkeypatch):
    import realize_core.base_handler as bh
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = {"acme": {"name": "Acme"}}
    app.state.config = {"features": {"activity_log": True}}
    handler = mock.AsyncMock(return_value="ok")
    monkeypatch.setattr(bh, "process_message", handler)
    client = TestClient(app)

    resp = client.post("/api/chat", json={"message": "hi", "system_key": "acme", "user_id": "u1"})
    assert resp.status_code == 200
    kwargs = handler.call_args.kwargs
    assert kwargs["features"]["activity_log"] is True
    assert kwargs["all_systems"] == {"acme": {"name": "Acme"}}

    handler.side_effect = RuntimeError("secret internal detail /etc/passwd")
    resp = client.post("/api/chat", json={"message": "hi", "system_key": "acme", "user_id": "u1"})
    assert resp.status_code == 500
    assert "secret internal detail" not in resp.text
