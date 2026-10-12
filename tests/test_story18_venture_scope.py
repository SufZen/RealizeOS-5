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

    def _session_for(self, monkeypatch, user_id: str, role: str):
        from realize_core.security import session_store

        record = session_store.SessionRecord(
            session_id="s1",
            user_id=user_id,
            role=role,
            csrf_token="c",
            created_at="",
            last_seen_at="",
            expires_at="",
            ip_address="",
            user_agent="",
            remember_me=False,
        )
        revoked: list[str] = []
        monkeypatch.setattr(session_store, "get_session", lambda _sid: record)
        monkeypatch.setattr(session_store, "revoke_session", lambda sid: revoked.append(sid))
        client = _client()
        client.cookies.set(session_store.SESSION_COOKIE_NAME, "s1")
        return client, revoked

    def test_session_of_a_removed_user_is_signed_out(self, users_file, monkeypatch):
        """Codex audit F20: introspection re-checks users.yaml like protected requests do."""
        client, revoked = self._session_for(monkeypatch, "gone@acme.io", "operator")
        assert client.get("/api/auth/session").json() == {"authenticated": False}
        assert revoked == ["s1"]

    def test_session_reports_the_current_role(self, users_file, monkeypatch):
        # Signed in as an operator; users.yaml now says viewer.
        client, _ = self._session_for(monkeypatch, "vic@acme.io", "operator")
        assert client.get("/api/auth/session").json()["role"] == "viewer"


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


# ---------------------------------------------------------------------------
# Security review follow-ups
# ---------------------------------------------------------------------------


def _app_as(user_id: str, role: str):
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = dict(SYSTEMS)
    app.state.config = {"features": {}}

    @app.middleware("http")
    async def as_principal(request, call_next):
        request.state.user_id = user_id
        request.state.role = role
        request.state.scopes = []
        return await call_next(request)

    return app


class TestReviewFollowUps:
    @pytest.mark.parametrize(
        "headers",
        [{}, {"Content-Type": "APPLICATION/JSON"}, {"Content-Type": "application/vnd.api+json"}],
        ids=["no-content-type", "uppercase", "json-suffix"],
    )
    def test_body_parsed_like_fastapi(self, users_file, headers):
        client = _client("dana@acme.io", "operator")
        body = json.dumps({"message": "hi", "system_key": "globex"})
        assert client.post("/api/chat", content=body, headers=headers).status_code == 403

    def test_nested_and_non_text_venture_values_refused(self, users_file):
        client = _client("dana@acme.io", "operator")
        nested = {"entity_type": "note", "title": "t", "venture": "acme", "frontmatter": {"venture": "globex"}}
        assert client.post("/api/fabric/entities", json=nested).status_code == 403
        listed = {"message": "hi", "system_key": ["globex"]}
        assert client.post("/api/chat", json=listed).status_code == 403

    def test_repeated_query_values_all_checked(self, users_file):
        client = _client("dana@acme.io", "operator")
        assert client.get("/api/approvals?venture_key=acme&venture_key=globex").status_code == 403

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/api/settings/features"),
            ("GET", "/api/shared/file?path=identity.md"),
            ("GET", "/api/tools"),
            ("POST", "/api/pipelines/execute"),
        ],
    )
    def test_system_wide_areas_closed_to_scoped_users(self, users_file, method, path):
        client = _client("dana@acme.io", "operator")
        resp = client.request(method, path, json={} if method == "POST" else None)
        assert resp.status_code == 403
        assert "every venture" in resp.json()["detail"]

    def test_entity_by_id_checks_the_entitys_own_venture(self, users_file):
        class FakeSynapse:
            def get(self, entity_id, depth=0):
                entities = {
                    "ent-a": {"id": "ent-a", "venture": "acme"},
                    "ent-g": {"id": "ent-g", "venture": "globex"},
                }
                entity = dict(entities[entity_id])
                if depth:
                    entity["neighbors"] = [{"id": "ent-g", "venture": "globex"}, {"id": "ent-a2", "venture": "acme"}]
                return entity

        app = _app_as("dana@acme.io", "operator")
        app.state.synapse = FakeSynapse()
        client = TestClient(app)
        assert client.get("/api/fabric/entities/ent-g?venture=acme").status_code == 404
        entity = client.get("/api/fabric/entities/ent-a?venture=acme&depth=1").json()["entity"]
        assert [n["id"] for n in entity["neighbors"]] == ["ent-a2"]

    def test_frontmatter_cannot_relabel_an_entity(self, users_file):
        client = _client("api-key", "owner")
        body = {"entity_type": "note", "title": "t", "venture": "acme", "frontmatter": {"venture": "globex"}}
        resp = client.post("/api/fabric/entities", json=body)
        assert resp.status_code == 400
        assert "set by the server" in resp.json()["detail"]

    def test_workflow_detail_and_create_respect_scope(self, users_file, monkeypatch):
        from realize_core.skills import detector

        # A skill loaded from globex's YAML: its dict has no system_key.
        monkeypatch.setattr(detector, "_loaded_skills", {"globex": [{"name": "globex-report"}]})
        client = _client("dana@acme.io", "operator")
        assert client.get("/api/workflows/globex-report").status_code == 404
        assert client.get("/api/workflows").json()["workflows"] == []
        # A venture-limited user can't create a global skill.
        body = {"name": "x", "system_key": "", "steps": [{"id": "s1", "type": "agent"}]}
        assert client.post("/api/workflows", json=body).status_code == 403

    def test_mcp_skill_tools_check_the_skills_venture(self, monkeypatch):
        from realize_core.mcp_server.venture_guard import check_call
        from realize_core.skills import detector

        # YAML skills don't carry their venture: the owner is where they were loaded.
        owners = {"globex-report": ("globex", {"name": "globex-report"}), "summarize": ("_default", {})}
        monkeypatch.setattr(detector, "find_skill", lambda name: owners.get(name))
        allowed = frozenset({"acme"})
        args = {"system_key": "acme", "input_text": "go"}
        assert check_call("run_workflow", {**args, "name": "globex-report"}, allowed) == "Workflow not found"
        assert check_call("trigger_skill", {**args, "name": "nope"}, allowed) == "Workflow not found"
        assert check_call("run_workflow", {**args, "name": "summarize"}, allowed) is None
        assert check_call("get_system", {"system_key": ["acme"]}, allowed) is not None

    @pytest.mark.asyncio
    async def test_mcp_skill_runs_as_the_caller(self, monkeypatch):
        from realize_api.dependencies import CurrentUser
        from realize_core.mcp_server.tools.ops_tools import run_workflow
        from realize_core.skills import detector, executor

        seen: dict = {}

        async def fake_execute(**kwargs):
            seen.update(kwargs)
            return "done"

        monkeypatch.setattr(detector, "get_skill_by_name", lambda name: {"name": name, "system_key": "acme"})
        monkeypatch.setattr(executor, "execute_skill", fake_execute)
        await run_workflow(
            {"name": "s", "input_text": "go", "system_key": "acme", "user_id": "boss@acme.io"},
            app_state=None,
            user=CurrentUser(user_id="dana@acme.io", role="editor"),
        )
        assert seen["user_id"] == "dana@acme.io"


@pytest.mark.asyncio
async def test_mcp_chat_context_limited_to_callers_ventures(monkeypatch):
    """Cross-system context must not pull in ventures the MCP caller can't see."""
    from realize_api.dependencies import CurrentUser
    from realize_core import base_handler
    from realize_core.mcp_server.tools.chat_tools import realize_chat

    seen: dict = {}

    async def fake_process(**kwargs):
        seen.update(kwargs)
        return "ok"

    monkeypatch.setattr(base_handler, "process_message", fake_process)
    app_state = type("S", (), {"systems": dict(SYSTEMS), "config": {"features": {}}, "kb_path": None})()
    user = CurrentUser(user_id="agent-7", role="editor", scopes=["venture:acme"])

    await realize_chat({"message": "hi", "system_key": "acme"}, app_state=app_state, user=user)

    assert set(seen["all_systems"]) == {"acme"}


def test_migration_008_lets_every_role_sign_in(tmp_path):
    """An operator's session used to violate user_sessions' role CHECK (500 on login)."""
    import importlib
    import sqlite3

    m006 = importlib.import_module("realize_core.migration.versions.006_user_sessions")
    m008 = importlib.import_module("realize_core.migration.versions.008_session_roles")

    conn = sqlite3.connect(tmp_path / "sessions.db")
    m006.up(conn)
    insert = "INSERT INTO user_sessions (session_id, csrf_token, user_id, role, expires_at) VALUES (?, 'c', ?, ?, 'x')"
    conn.execute(insert, ("s-owner", "owner@x", "owner"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, ("s-op", "dana@x", "operator"))

    m008.up(conn)
    m008.up(conn)  # idempotent
    conn.execute(insert, ("s-op", "dana@x", "operator"))
    conn.execute(insert, ("s-user", "uri@x", "user"))
    assert {r[0] for r in conn.execute("SELECT session_id FROM user_sessions")} == {"s-owner", "s-op", "s-user"}

    m008.down(conn)
    assert {r[0] for r in conn.execute("SELECT session_id FROM user_sessions")} == {"s-owner"}
    conn.close()


def test_operator_session_can_be_created(tmp_path, monkeypatch):
    """End to end through the migration engine: create_session accepts the new roles."""
    from realize_core.db.schema import set_db_path
    from realize_core.migration.engine import MigrationEngine
    from realize_core.security import session_store

    db = tmp_path / "realize_data.db"
    set_db_path(db)
    try:
        MigrationEngine(db_path=db).migrate_up()
        record = session_store.create_session(user_id="dana@acme.io", role="operator")
        assert session_store.get_session(record.session_id).role == "operator"
    finally:
        set_db_path(None)


# ---------------------------------------------------------------------------
# Independent review (Codex) F1-F5: adversarial checks through the real app
# ---------------------------------------------------------------------------


def _kb_app(tmp_path, user_id="agent-7", role="operator", scopes=("venture:acme",)):
    """An app over a real temp KB with two ventures, as a scoped principal."""
    from realize_api.main import create_app

    kb = tmp_path / "kb"
    for venture in ("acme", "globex"):
        brain = kb / "systems" / venture / "B-brain"
        brain.mkdir(parents=True)
        (brain / "private.md").write_text(f"{venture} confidential", encoding="utf-8")
    app = create_app()
    app.state.systems = {
        "acme": {"name": "Acme", "agents": {}, "system_dir": "systems/acme"},
        "globex": {"name": "Globex", "agents": {}, "system_dir": "systems/globex"},
    }
    app.state.kb_path = kb
    app.state.config = {"features": {}}

    @app.middleware("http")
    async def as_principal(request, call_next):
        request.state.user_id = user_id
        request.state.role = role
        request.state.scopes = list(scopes)
        return await call_next(request)

    return TestClient(app), kb


class TestKbFilesBelongToTheVenture:
    """F1: a permitted venture URL must not reach another venture's files."""

    def test_sibling_venture_file_is_refused_for_every_operation(self, tmp_path):
        client, kb = _kb_app(tmp_path)
        other = "systems/globex/B-brain/private.md"
        url = "/api/ventures/acme/kb/file"

        assert client.get(url, params={"path": other}).status_code == 403
        assert client.put(url, json={"path": other, "content": "x"}).status_code == 403
        assert client.post(url, json={"path": "systems/globex/B-brain/new.md", "content": "x"}).status_code == 403
        assert client.delete(url, params={"path": other}).status_code == 403
        assert (kb / other).read_text(encoding="utf-8") == "globex confidential"
        assert not (kb / "systems/globex/B-brain/new.md").exists()

    def test_own_files_still_work(self, tmp_path):
        client, _ = _kb_app(tmp_path)
        resp = client.get("/api/ventures/acme/kb/file", params={"path": "systems/acme/B-brain/private.md"})
        assert resp.status_code == 200
        assert resp.json()["content"] == "acme confidential"

    @pytest.mark.parametrize(
        "path",
        [
            "systems/acme/../globex/B-brain/private.md",
            "systems\\globex\\B-brain\\private.md",
            "shared/identity.md",
        ],
        ids=["dot-dot", "backslashes", "outside-ventures"],
    )
    def test_traversal_and_other_roots_refused(self, tmp_path, path):
        client, _ = _kb_app(tmp_path)
        assert client.get("/api/ventures/acme/kb/file", params={"path": path}).status_code in (400, 403)

    def test_absolute_path_refused(self, tmp_path):
        client, kb = _kb_app(tmp_path)
        absolute = str((kb / "systems/globex/B-brain/private.md").resolve())
        assert client.get("/api/ventures/acme/kb/file", params={"path": absolute}).status_code in (400, 403)

    def test_symlink_escape_refused(self, tmp_path):
        import os

        client, kb = _kb_app(tmp_path)
        link = kb / "systems/acme/B-brain/link.md"
        try:
            os.symlink(kb / "systems/globex/B-brain/private.md", link)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not available here")
        resp = client.get("/api/ventures/acme/kb/file", params={"path": "systems/acme/B-brain/link.md"})
        assert resp.status_code == 403


class TestFabricUsesTheRealScopeParameter:
    """F2: an alias the handler ignores must not satisfy the guard."""

    class FakeSynapse:
        def __init__(self):
            self.calls = []

        def toc(self, venture=None):
            self.calls.append(venture)
            return [{"id": "e1", "venture": venture or "globex"}]

    @pytest.mark.parametrize("alias", ["system_key", "venture_key"])
    def test_alias_is_refused(self, tmp_path, alias):
        client, _ = _kb_app(tmp_path)
        synapse = self.FakeSynapse()
        client.app.state.synapse = synapse
        assert client.get(f"/api/fabric/toc?{alias}=acme").status_code == 403
        assert synapse.calls == []

    def test_venture_parameter_scopes_the_query(self, tmp_path):
        client, _ = _kb_app(tmp_path)
        synapse = self.FakeSynapse()
        client.app.state.synapse = synapse
        assert client.get("/api/fabric/toc?venture=acme").status_code == 200
        assert synapse.calls == ["acme"]


class TestSessionsFollowTheUsersFile:
    """F3: a removed or malformed user never widens an existing session."""

    @pytest.fixture
    def authed(self, users_file, monkeypatch):
        from realize_core.security import session_store

        monkeypatch.setenv("REALIZE_API_KEY", "test-key-not-secret")
        revoked: list[str] = []
        monkeypatch.setattr(session_store, "revoke_session", lambda sid: revoked.append(sid) or True)
        monkeypatch.setattr(session_store, "touch_session", lambda sid: None)

        def client_for(user_id, stored_role):
            from realize_api.main import create_app

            record = session_store.SessionRecord(
                session_id="s1",
                user_id=user_id,
                role=stored_role,
                csrf_token="c",
                created_at="",
                last_seen_at="",
                expires_at="",
                ip_address="",
                user_agent="",
                remember_me=False,
            )
            monkeypatch.setattr(session_store, "get_session", lambda _sid: record)
            app = create_app()
            app.state.systems = dict(SYSTEMS)
            app.state.config = {"features": {}}
            client = TestClient(app)
            client.cookies.set(session_store.SESSION_COOKIE_NAME, "s1")
            return client

        return client_for, revoked

    def test_removed_user_loses_the_session(self, authed):
        client_for, revoked = authed
        client = client_for("ghost@acme.io", "owner")
        assert client.get("/api/ventures").status_code == 401
        assert revoked == ["s1"]

    def test_current_role_applies_not_the_stored_one(self, authed):
        client_for, _ = authed
        client = client_for("vic@acme.io", "owner")  # stored as owner, now a viewer
        resp = client.post("/api/chat", json={"message": "hi", "system_key": "acme"}, headers={"X-Realize-CSRF": "c"})
        assert resp.status_code == 403

    def test_scoped_user_still_scoped(self, authed):
        client_for, _ = authed
        client = client_for("dana@acme.io", "operator")
        assert [v["key"] for v in client.get("/api/ventures").json()["ventures"]] == ["acme"]


@pytest.mark.parametrize("ventures", ["[]", '""', "0", "null"])
def test_present_but_empty_ventures_skips_the_user(tmp_path, monkeypatch, ventures):
    from realize_core.security.users import get_user

    monkeypatch.chdir(tmp_path)
    (tmp_path / "users.yaml").write_text(
        f'users:\n  - email: eve@acme.io\n    role: operator\n    ventures: {ventures}\n    password_hash: "$2b$12$x"\n',
        encoding="utf-8",
    )
    assert get_user("eve@acme.io") is None


def test_unreadable_users_file_means_no_sessions(users_file, monkeypatch):
    """A broken users.yaml loads no users, so every dashboard session fails closed."""
    from realize_core.security.users import get_user

    users_file.write_text("users: [this is: not valid", encoding="utf-8")
    assert get_user("dana@acme.io") is None


class TestPipelinesClosedToScopedUsers:
    """F4: pipeline definitions and runs aren't venture-scoped yet."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [("GET", "/api/pipelines"), ("POST", "/api/pipelines"), ("POST", "/api/pipelines/test")],
    )
    def test_refused(self, tmp_path, method, path):
        client, _ = _kb_app(tmp_path)
        resp = client.request(method, path, json={"name": "x", "venture_key": "acme", "steps": []})
        assert resp.status_code == 403

    def test_unscoped_owner_keeps_access(self, tmp_path):
        client, _ = _kb_app(tmp_path, user_id="api-key", role="owner", scopes=())
        assert client.get("/api/pipelines").status_code == 200


class TestMcpUsesRestPermissions:
    """F5: one permission model for REST and MCP."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("role", "tool", "allowed"),
        [
            ("operator", "list_systems", True),
            ("user", "list_systems", True),
            ("viewer", "list_systems", True),
            ("viewer", "realize_chat", False),
            ("user", "approve_request", False),
            ("viewer", "clear_history", False),
        ],
    )
    async def test_role_matrix(self, role, tool, allowed):
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
        args = {
            "list_systems": {},
            "realize_chat": {"message": "hi", "system_key": "acme"},
            "approve_request": {"approval_id": "apv-1"},
            "clear_history": {"system_key": "acme", "user_id": "u1"},
        }[tool]
        registry_mod.reset_for_tests()
        token = bind_user(CurrentUser(user_id="u1", role=role, scopes=[]))
        try:
            app_state = type("S", (), {"systems": dict(SYSTEMS), "config": {"features": {}}, "kb_path": None})()
            out = await _dispatch(registry_mod.get_registry(), cfg, app_state, tool, args)
        finally:
            reset_user(token)
        text = out[0].text
        refused = "MCP_INSUFFICIENT_SCOPE" in text
        assert refused is (not allowed), text[:200]


# ---------------------------------------------------------------------------
# Codex audit F02/F03: global collections and public status
# ---------------------------------------------------------------------------


class TestGlobalCollectionsRespectScope:
    def test_routing_analytics_hide_other_ventures(self, users_file):
        from realize_api.routes import routing

        routing._routing_analytics.clear()
        routing._routing_analytics.extend(
            [
                {
                    "system_key": "globex",
                    "message_preview": "GLOBEX PRIVATE BID 900000",
                    "selected_agent": "writer",
                    "scores": {},
                },
                {"system_key": "acme", "message_preview": "acme note", "selected_agent": "writer", "scores": {}},
            ]
        )
        try:
            dana = _client("dana@acme.io", "operator")
            body = dana.get("/api/routing/analytics").json()
            assert [e["system_key"] for e in body["entries"]] == ["acme"]
            assert "GLOBEX" not in json.dumps(body)
            assert dana.get("/api/routing/agents/writer/stats").json()["total_routes"] == 1

            owner = _client("owner@realization.co.il", "owner")
            assert owner.get("/api/routing/analytics").json()["total"] == 2
        finally:
            routing._routing_analytics.clear()

    @pytest.mark.parametrize("path", ["/api/webhooks/events", "/api/llm/usage", "/api/llm/routing"])
    def test_unowned_global_diagnostics_closed_to_scoped_users(self, users_file, path):
        assert _client("dana@acme.io", "operator").get(path).status_code == 403
        assert _client("owner@realization.co.il", "owner").get(path).status_code == 200


def test_anonymous_status_is_refused(tmp_path, monkeypatch):
    """With auth on, /api/status must not list ventures or agents to anyone anonymous."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REALIZE_API_KEY", "test-api-key-1234567890abcdef")
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = dict(SYSTEMS)
    resp = TestClient(app).get("/api/status")
    assert resp.status_code == 401
    assert "Globex" not in resp.text


class TestVentureSkillsScope:
    """Security review of the K-1 fix: a venture's skills are only listed to callers who may see it."""

    def test_rest_skills_of_another_venture_are_refused(self, users_file, monkeypatch):
        from realize_core.skills import detector

        monkeypatch.setattr(detector, "_loaded_skills", {"globex": [{"name": "globex-secret-skill"}]})
        resp = _client("dana@acme.io", "operator").get("/api/systems/globex/skills")
        assert resp.status_code in (403, 404)
        assert "globex-secret-skill" not in resp.text

    def test_rest_skills_of_own_venture_are_listed(self, users_file, monkeypatch):
        from realize_core.skills import detector

        monkeypatch.setattr(detector, "_loaded_skills", {"acme": [{"name": "acme-skill"}]})
        body = _client("dana@acme.io", "operator").get("/api/systems/acme/skills").json()
        assert [s["name"] for s in body["skills"]] == ["acme-skill"]

    def test_unknown_venture_is_404_not_default_skills(self, users_file):
        resp = _client("owner@realization.co.il", "owner").get("/api/systems/nope/skills")
        assert resp.status_code == 404

    async def test_mcp_list_skills_checks_the_venture(self, monkeypatch):
        from realize_core.mcp_server.venture_guard import check_call

        denial = check_call("list_skills", {"system_key": "globex"}, frozenset({"acme"}))
        assert denial is not None
