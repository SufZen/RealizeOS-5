"""STORY-18 — venture-scoped users and views (brief item 4)."""

from __future__ import annotations

import json
import textwrap

import pytest
from fastapi.testclient import TestClient

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
      - email: adam@acme.io
        role: admin
        ventures: [acme]
        password_hash: "$2b$12$adam"
      - email: broken@acme.io
        role: operator
        ventures: acme
        password_hash: "$2b$12$broken"
    """
)

SYSTEMS = {
    "acme": {"name": "Acme Tower", "agents": {}},
    "globex": {"name": "Globex Fund", "agents": {}},
}


@pytest.fixture
def users_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "users.yaml").write_text(USERS_YAML, encoding="utf-8")
    return tmp_path / "users.yaml"


@pytest.fixture
def op_db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "realize_data.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


def _client(user_id: str | None = None, role: str = "owner", scopes: list[str] | None = None) -> TestClient:
    """An app whose requests carry the principal the auth middleware would set."""
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = dict(SYSTEMS)
    app.state.config = {"features": {}}

    if user_id is not None:

        @app.middleware("http")
        async def as_principal(request, call_next):
            request.state.user_id = user_id
            request.state.role = role
            request.state.scopes = scopes or []
            return await call_next(request)

    return TestClient(app)


# ---------------------------------------------------------------------------
# users.yaml + scope resolution
# ---------------------------------------------------------------------------


class TestUsersAndScope:
    def test_users_yaml_ventures_and_roles(self, users_file):
        from realize_core.security.users import get_user, list_users

        assert get_user("dana@acme.io").ventures == ("acme",)
        assert get_user("dana@acme.io").role == "operator"
        assert get_user("owner@realization.co.il").ventures == ()
        # A malformed scope never becomes "every venture": the user is skipped.
        assert "broken@acme.io" not in {u.email for u in list_users()}

    def test_allowed_ventures(self, users_file):
        from realize_core.security.venture_scope import allowed_ventures

        assert allowed_ventures(None) is None
        assert allowed_ventures("owner@realization.co.il") is None
        assert allowed_ventures("api-key") is None
        assert allowed_ventures("dana@acme.io") == {"acme"}
        # Token scopes narrow further; they never widen a user's list.
        assert allowed_ventures("api-key", ["venture:globex"]) == {"globex"}
        assert allowed_ventures("dana@acme.io", ["venture:globex"]) == frozenset()

    @pytest.mark.parametrize(
        ("method", "path", "permission"),
        [
            ("GET", "/api/ventures", None),
            ("POST", "/api/auth/logout", None),
            ("POST", "/api/chat", "agents:execute"),
            ("POST", "/api/chat/stream", "agents:execute"),
            ("DELETE", "/api/conversations/acme/u1", "agents:execute"),
            ("POST", "/api/approvals/a1/approve", "pipeline:approve"),
            ("POST", "/api/dreams/p1/reject", "pipeline:approve"),
            ("DELETE", "/api/ventures/acme", "system:delete"),
            ("POST", "/api/ventures", "system:manage"),
            ("PUT", "/api/settings/features", "system:manage"),
            ("POST", "/api/agents/reload", "system:manage"),
            ("POST", "/api/ventures/acme/kb/file", "system:write"),
            ("POST", "/api/some-future-route", "system:write"),
            ("POST", "/mcp/messages/abc", "system:write"),  # policy table; the guard skips non-/api paths
        ],
    )
    def test_required_permission(self, method, path, permission):
        from realize_core.security.venture_scope import required_permission

        assert required_permission(method, path) == permission

    def test_session_reports_ventures(self, users_file, monkeypatch):
        from realize_core.security import session_store

        record = session_store.SessionRecord(
            session_id="s1",
            user_id="dana@acme.io",
            role="operator",
            csrf_token="c",
            created_at="",
            last_seen_at="",
            expires_at="",
            ip_address="",
            user_agent="",
            remember_me=False,
        )
        monkeypatch.setattr(session_store, "get_session", lambda _sid: record)
        client = _client()
        client.cookies.set(session_store.SESSION_COOKIE_NAME, "s1")
        assert client.get("/api/auth/session").json()["ventures"] == ["acme"]


# ---------------------------------------------------------------------------
# Reads: scoped users see their ventures only
# ---------------------------------------------------------------------------


class TestScopedReads:
    def test_listings_show_only_allowed_ventures(self, users_file):
        client = _client("dana@acme.io", "operator")
        assert [v["key"] for v in client.get("/api/ventures").json()["ventures"]] == ["acme"]
        assert [s["key"] for s in client.get("/api/systems").json()["systems"]] == ["acme"]
        assert [v["key"] for v in client.get("/api/dashboard").json()["ventures"]] == ["acme"]
        assert set(client.get("/api/status").json()["systems"]) == {"acme"}

    def test_other_venture_by_path_or_query_is_forbidden(self, users_file):
        client = _client("dana@acme.io", "operator")
        assert client.get("/api/systems/globex").status_code == 403
        assert client.get("/api/ventures/globex/activity").status_code == 403
        assert client.get("/api/approvals?venture_key=globex").status_code == 403
        assert client.get("/api/systems/acme").status_code == 200

    def test_ventures_named_in_write_bodies_are_checked(self, users_file):
        client = _client("dana@acme.io", "operator")
        assert client.post("/api/chat", json={"message": "hi", "system_key": "globex"}).status_code == 403
        assert client.post("/api/missions", json={"title": "t", "goal": "g", "venture": "globex"}).status_code == 403
        resp = client.post("/api/skills/install", json={"skill_id": "x", "venture_key": "globex"})
        assert resp.status_code == 403
        # A path naming an allowed venture can't smuggle another one in the query.
        assert client.get("/api/systems/acme?venture_key=globex").status_code == 403

    def test_cross_venture_areas_need_a_named_venture(self, users_file):
        client = _client("dana@acme.io", "operator")
        assert client.get("/api/fabric/entities").status_code == 403
        assert client.get("/api/fabric/entities?venture=acme").status_code != 403
        # Edits addressed by id alone can't be limited to a venture.
        assert client.delete("/api/fabric/entities/ent-1?venture=acme").status_code == 403
        assert client.delete("/api/workflows/payment-check").status_code == 403

    def test_unscoped_and_auth_off_see_everything(self, users_file):
        for client in (_client("owner@realization.co.il", "owner"), _client()):
            keys = {v["key"] for v in client.get("/api/ventures").json()["ventures"]}
            assert keys == {"acme", "globex"}

    def test_approvals_and_activity_are_filtered(self, users_file, op_db):
        from realize_core.activity.store import query_events
        from realize_core.db.schema import get_connection

        conn = get_connection(op_db)
        for i, venture in enumerate(["acme", "globex"]):
            conn.execute(
                "INSERT INTO approval_queue (id, venture_key, agent_key, action_type) VALUES (?, ?, 'a', 'x')",
                (f"apv-{venture}", venture),
            )
            conn.execute(
                "INSERT INTO activity_events (id, venture_key, actor_type, actor_id, action) "
                "VALUES (?, ?, 'system', 's', 'tick')",
                (f"ev-{i}", venture),
            )
        conn.commit()
        conn.close()

        client = _client("dana@acme.io", "operator")
        ids = [a["id"] for a in client.get("/api/approvals").json()["approvals"]]
        assert ids == ["apv-acme"]
        # Deciding on another venture's approval looks like it doesn't exist.
        assert client.post("/api/approvals/apv-globex/reject", json={}).status_code == 404

        assert [e["venture_key"] for e in query_events(venture_keys={"acme"})] == ["acme"]
        assert query_events(venture_keys=set()) == []
        recent = client.get("/api/dashboard").json()["recent_activity"]
        assert {e["venture_key"] for e in recent} == {"acme"}

    def test_agents_from_other_ventures_hidden(self, users_file, tmp_path):
        from realize_api.main import create_app
        from realize_core.agents.registry import AgentRegistry
        from realize_core.agents.schema import V1AgentDef

        kb = tmp_path / "kb"
        registry = AgentRegistry()
        for venture, key in (("acme", "pm"), ("globex", "cfo")):
            agent_dir = kb / f"systems/{venture}/A-agents"
            agent_dir.mkdir(parents=True)
            (agent_dir / f"{key}.md").write_text(f"# {key}", encoding="utf-8")
            registry.register(V1AgentDef(key=key, name=key, file_path=str(agent_dir / f"{key}.md")))

        app = create_app()
        app.state.systems = dict(SYSTEMS)
        app.state.kb_path = kb
        app.state.agent_registry = registry

        @app.middleware("http")
        async def as_dana(request, call_next):
            request.state.user_id = "dana@acme.io"
            request.state.role = "operator"
            return await call_next(request)

        client = TestClient(app)
        assert [a["key"] for a in client.get("/api/agents").json()["agents"]] == ["pm"]
        assert client.get("/api/agents/cfo").status_code == 404


# ---------------------------------------------------------------------------
# Writes: RBAC per route, global changes need an unscoped owner/admin
# ---------------------------------------------------------------------------


class TestWrites:
    def test_viewer_is_read_only(self, users_file):
        client = _client("vic@acme.io", "viewer")
        assert client.post("/api/chat", json={"message": "hi", "system_key": "acme"}).status_code == 403
        assert client.post("/api/ventures/acme/kb/file", json={}).status_code == 403
        assert client.get("/api/ventures").status_code == 200

    def test_operator_cannot_change_global_settings(self, users_file):
        client = _client("dana@acme.io", "operator")
        assert client.put("/api/settings/features", content="not json").status_code == 403

    def test_scoped_admin_cannot_change_what_every_venture_shares(self, users_file):
        client = _client("adam@acme.io", "admin")
        resp = client.put("/api/settings/features", content="not json")
        assert resp.status_code == 403
        assert "every venture" in resp.json()["detail"]

    def test_unscoped_admin_passes_the_gate(self, users_file):
        client = _client("api-key", "owner")
        # Past the access check, the malformed body is what fails.
        assert client.put("/api/settings/features", content="not json").status_code == 422


# ---------------------------------------------------------------------------
# MCP: the same scope, fail-closed for tools that span every venture
# ---------------------------------------------------------------------------


async def _call(name: str, args: dict, scopes: list[str]):
    from realize_api.dependencies import CurrentUser
    from realize_core.mcp_server import registry as registry_mod
    from realize_core.mcp_server.auth import bind_user, reset_user
    from realize_core.mcp_server.config import McpConfig
    from realize_core.mcp_server.server import _dispatch

    cfg = McpConfig(
        enabled=True,
        expose_kb=True,
        expose_ops=True,
        allow_admin=False,
        audit_full_payload=False,
        bearer_token_override="",
    )
    token = bind_user(CurrentUser(user_id="agent-7", role="editor", scopes=scopes))
    try:
        app_state = type("S", (), {"systems": dict(SYSTEMS), "config": {"features": {}}, "kb_path": None})()
        registry_mod.reset_for_tests()
        out = await _dispatch(registry_mod.get_registry(), cfg, app_state, name, args)
    finally:
        reset_user(token)
    return json.loads(out[0].text)


class TestMcp:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("name", "args"),
        [
            ("get_system", {"system_key": "globex"}),
            ("kb_search", {"query": "budget"}),
            ("run_evolution", {}),
            ("list_suggestions", {}),
        ],
    )
    async def test_scoped_caller_refused(self, name, args):
        out = await _call(name, args, ["venture:acme"])
        assert out["code"] == "MCP_FORBIDDEN"

    @pytest.mark.asyncio
    async def test_scoped_caller_sees_own_ventures(self):
        out = await _call("list_systems", {}, ["venture:acme"])
        assert [s["key"] for s in out["systems"]] == ["acme"]
        out = await _call("get_system", {"system_key": "acme"}, ["venture:acme"])
        assert out.get("code") != "MCP_FORBIDDEN"

    @pytest.mark.asyncio
    async def test_unscoped_caller_unchanged(self):
        out = await _call("list_systems", {}, [])
        assert {s["key"] for s in out["systems"]} == {"acme", "globex"}


def test_guard_covers_rest_api_only(users_file):
    """MCP transport paths are not REST routes; MCP applies scope per tool instead."""
    import asyncio
    from types import SimpleNamespace

    from realize_api.dependencies import enforce_access

    request = SimpleNamespace(
        state=SimpleNamespace(user_id="vic@acme.io", role="viewer", scopes=[]),
        url=SimpleNamespace(path="/mcp/messages/abc"),
        method="POST",
    )
    asyncio.run(enforce_access(request))  # no 403 for a viewer's MCP message
