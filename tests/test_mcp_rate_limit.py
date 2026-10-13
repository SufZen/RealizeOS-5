"""Per-principal rate limits on MCP tool calls.

The HTTP rate limiter lets /mcp stream through (buffering would break the
transports), so the dispatcher limits each tools/call per principal: an
agent token has its own bucket, a stdio session its own, people
``user:<id>``. A limited call gets ``MCP_RATE_LIMITED``, is audit-logged,
and the connection carries on.
"""

from __future__ import annotations

import json
import textwrap
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from realize_api.dependencies import CurrentUser

API_KEY = "test-api-key-1234567890abcdef"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

USERS_YAML = textwrap.dedent(
    """
    users:
      - email: owner@realization.co.il
        role: owner
        password_hash: "$2b$12$owner"
      - email: dana@acme.io
        role: operator
        ventures: [acme]
        password_hash: "$2b$12$dana"
      - email: vic@acme.io
        role: viewer
        ventures: [acme]
        password_hash: "$2b$12$vic"
    """
)

SYSTEMS = {"acme": {"name": "Acme Tower", "agents": {}}, "globex": {"name": "Globex Fund", "agents": {}}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """users.yaml, a migrated DB, two ventures, and a fresh tool registry."""
    from realize_core.db.migrations import run_migrations
    from realize_core.db.schema import init_schema, set_db_path
    from realize_core.mcp_server import registry as registry_mod

    monkeypatch.chdir(tmp_path)
    (tmp_path / "users.yaml").write_text(USERS_YAML, encoding="utf-8")
    db = tmp_path / "ops.db"
    init_schema(db)
    run_migrations(db)
    set_db_path(db)
    registry_mod.reset_for_tests()
    state = SimpleNamespace(systems=dict(SYSTEMS), kb_path=tmp_path, shared_config={}, config={"features": {}})
    yield SimpleNamespace(path=tmp_path, state=state)
    registry_mod.reset_for_tests()
    set_db_path(None)


def _config(**overrides):
    from realize_core.mcp_server.config import McpConfig

    values = {
        "enabled": True,
        "expose_kb": True,
        "expose_ops": True,
        "allow_admin": True,
        "audit_full_payload": False,
        "bearer_token_override": "",
    }
    values.update(overrides)
    return McpConfig(**values)


def _agent(user: str = "dana@acme.io", ventures=("acme",)) -> CurrentUser:
    """An agent token's principal, as the auth middleware sets it."""
    from realize_core.security.agent_tokens import create_token, resolve_token

    _token, secret = create_token(name="claude-acme", user_email=user, ventures=list(ventures))
    principal = resolve_token(secret)
    return CurrentUser(user_id=principal.user_id, role=principal.role, scopes=principal.scopes)


def _stdio(user: str = "dana@acme.io") -> CurrentUser:
    """A local stdio session's caller, as the stdio entry point binds it."""
    from realize_core.security.agent_tokens import STDIO_SCOPE

    return CurrentUser(user_id=user, role="operator", scopes=[STDIO_SCOPE, "venture:acme"])


async def _call(state, user, name: str, args: dict | None = None, cfg=None) -> dict:
    from realize_core.mcp_server.auth import bind_user, reset_user
    from realize_core.mcp_server.registry import get_registry
    from realize_core.mcp_server.server import _dispatch

    token = bind_user(user)
    try:
        out = await _dispatch(get_registry(), cfg or _config(), state, name, args or {})
    finally:
        reset_user(token)
    return json.loads(out[0].text)


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------


class TestRateLimitConfig:
    def test_unset_uses_the_api_limit(self, monkeypatch):
        from realize_core.mcp_server.config import mcp_config_from_env
        from realize_core.mcp_server.rate_limit import limit_per_minute

        monkeypatch.delenv("MCP_RATE_LIMIT_PER_MINUTE", raising=False)
        cfg = mcp_config_from_env({})
        assert cfg.rate_limit_per_minute is None
        monkeypatch.setattr("realize_core.config.API_RATE_LIMIT_PER_MINUTE", 77)
        assert limit_per_minute(cfg.rate_limit_per_minute) == 77

    def test_env_wins_over_yaml(self, monkeypatch):
        from realize_core.mcp_server.config import mcp_config_from_env

        monkeypatch.delenv("MCP_RATE_LIMIT_PER_MINUTE", raising=False)
        assert mcp_config_from_env({"mcp": {"rate_limit_per_minute": 40}}).rate_limit_per_minute == 40
        monkeypatch.setenv("MCP_RATE_LIMIT_PER_MINUTE", "12")
        assert mcp_config_from_env({"mcp": {"rate_limit_per_minute": 40}}).rate_limit_per_minute == 12

    @pytest.mark.parametrize("raw", ["0", "-5", "lots", "1.5"])
    def test_a_bad_value_falls_back_to_the_api_limit_never_to_none(self, monkeypatch, raw):
        from realize_core.mcp_server.config import mcp_config_from_env

        monkeypatch.setenv("MCP_RATE_LIMIT_PER_MINUTE", raw)
        assert mcp_config_from_env({}).rate_limit_per_minute is None


class TestRateLimitBuckets:
    def test_keys_match_the_http_limiter(self):
        from realize_core.mcp_server.rate_limit import principal_key
        from realize_core.security.agent_tokens import STDIO_SCOPE

        token_user = CurrentUser(user_id="agent:0123456789ab", role="operator", scopes=["agent:0123456789ab"])
        assert principal_key(token_user) == "agent:0123456789ab"
        stdio = CurrentUser(user_id="dana@acme.io", role="operator", scopes=[STDIO_SCOPE])
        assert principal_key(stdio) == "agent:stdio:dana@acme.io"
        assert principal_key(CurrentUser(user_id="dana@acme.io", role="operator")) == "user:dana@acme.io"
        request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"), headers={})
        anonymous = CurrentUser(user_id="anonymous", role="owner")
        assert principal_key(anonymous, request) == "ip:203.0.113.9"
        assert principal_key(anonymous) == "ip:anonymous"  # no request (stdio, tests)

    def test_a_claimed_agent_scope_without_a_token_is_a_person(self):
        from realize_core.mcp_server.rate_limit import principal_key

        # Only a verified token or the stdio entry point makes a caller an agent.
        user = CurrentUser(user_id="dana@acme.io", role="operator", scopes=["agent:forged"])
        assert principal_key(user) == "user:dana@acme.io"


@pytest.mark.asyncio
class TestRateLimitDispatch:
    async def test_limited_call_is_refused_audited_and_others_keep_going(self, world, monkeypatch):
        from realize_core.security import audit

        events: list[dict] = []
        monkeypatch.setattr(audit, "get_audit_logger", lambda: SimpleNamespace(log=lambda **kw: events.append(kw)))
        cfg = _config(rate_limit_per_minute=2)
        dana = CurrentUser(user_id="dana@acme.io", role="operator", scopes=[])

        assert (await _call(world.state, dana, "realize_health", cfg=cfg))["status"] == "ok"
        assert (await _call(world.state, dana, "realize_health", cfg=cfg))["status"] == "ok"
        limited = await _call(world.state, dana, "realize_health", cfg=cfg)
        assert limited["code"] == "MCP_RATE_LIMITED"
        assert limited["retry_after_seconds"] == 60

        [event] = [e for e in events if e["outcome"] == "rate_limited"]
        assert event["user_id"] == "dana@acme.io"
        assert event["action"] == "mcp.realize_health"
        assert event["channel"] == "mcp"
        assert event["metadata"]["bucket"] == "user:dana@acme.io"

        # Someone else has their own bucket.
        owner = CurrentUser(user_id="owner@realization.co.il", role="owner", scopes=[])
        assert (await _call(world.state, owner, "realize_health", cfg=cfg))["status"] == "ok"

    async def test_refused_and_unknown_calls_count_too(self, world):
        cfg = _config(rate_limit_per_minute=2)
        viewer = CurrentUser(user_id="vic@acme.io", role="viewer", scopes=[])

        assert (await _call(world.state, viewer, "no_such_tool", cfg=cfg))["code"] == "MCP_TOOL_NOT_FOUND"
        assert (await _call(world.state, viewer, "run_evolution", cfg=cfg))["code"] == "MCP_INSUFFICIENT_SCOPE"
        assert (await _call(world.state, viewer, "realize_health", cfg=cfg))["code"] == "MCP_RATE_LIMITED"

    async def test_an_agent_token_has_its_own_bucket_apart_from_its_person(self, world):
        cfg = _config(rate_limit_per_minute=1)
        agent = _agent()
        person = CurrentUser(user_id="dana@acme.io", role="operator", scopes=[])

        assert (await _call(world.state, agent, "realize_health", cfg=cfg))["status"] == "ok"
        assert (await _call(world.state, agent, "realize_health", cfg=cfg))["code"] == "MCP_RATE_LIMITED"
        # The person the agent acts for is not slowed down by it, nor is another agent.
        assert (await _call(world.state, person, "realize_health", cfg=cfg))["status"] == "ok"
        assert (await _call(world.state, _agent(), "realize_health", cfg=cfg))["status"] == "ok"
        # And a stdio session of the same person has its own bucket too.
        assert (await _call(world.state, _stdio(), "realize_health", cfg=cfg))["status"] == "ok"
        assert (await _call(world.state, _stdio(), "realize_health", cfg=cfg))["code"] == "MCP_RATE_LIMITED"

    async def test_the_bucket_frees_after_the_window(self, world, monkeypatch):
        from realize_core.utils import rate_limiter

        clock = {"now": 1_000.0}
        monkeypatch.setattr(rate_limiter.time, "time", lambda: clock["now"])
        cfg = _config(rate_limit_per_minute=1)
        dana = CurrentUser(user_id="dana@acme.io", role="operator", scopes=[])

        assert (await _call(world.state, dana, "realize_health", cfg=cfg))["status"] == "ok"
        assert (await _call(world.state, dana, "realize_health", cfg=cfg))["code"] == "MCP_RATE_LIMITED"
        clock["now"] += 61
        assert (await _call(world.state, dana, "realize_health", cfg=cfg))["status"] == "ok"


def test_rate_limit_over_streamable_http_keeps_the_session_working(world, monkeypatch):
    """Over /mcp a limited tools/call is a normal JSON-RPC result; tools/list still answers."""
    from realize_api.main import create_app
    from realize_core.security.agent_tokens import create_token

    monkeypatch.setenv("REALIZE_API_KEY", API_KEY)
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
    _token, secret = create_token(name="claude-acme", user_email="dana@acme.io", ventures=["acme"])
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {secret}"}

    def rpc(client, method: str, params: dict, rpc_id: int):
        body = {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}
        r = client.post("/mcp", headers=headers, content=json.dumps(body))
        assert r.status_code == 200, r.text
        return r.json()["result"]

    with TestClient(create_app()) as client:
        client.app.state.systems = dict(SYSTEMS)
        client.app.state.config = {"features": {}}
        call = {"name": "realize_health", "arguments": {}}
        texts = [json.loads(rpc(client, "tools/call", call, i)["content"][0]["text"]) for i in range(3)]
        assert [t.get("code") for t in texts] == [None, None, "MCP_RATE_LIMITED"]
        # Listing isn't a tool call: it keeps working while the agent waits.
        assert rpc(client, "tools/list", {}, 9)["tools"]
        # The API key (a person's integration) has its own bucket.
        key_headers = {**MCP_HEADERS, "X-API-Key": API_KEY}
        body = {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": call}
        r = client.post("/mcp", headers=key_headers, content=json.dumps(body))
        assert json.loads(r.json()["result"]["content"][0]["text"])["status"] == "ok"
