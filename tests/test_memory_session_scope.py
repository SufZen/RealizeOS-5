"""Security review S1/S2: memories and creative sessions stay within the caller's reach.

S1 — ``GET /api/memory/search`` without ``venture`` searched every venture's
memories, so an agent token limited to ``acme`` (or a person limited to
``acme``) read ``globex``'s. It now searches only the caller's ventures, and
``/api/memory/stats`` (LLM usage, not split by venture) is a system area.
The Dream Inbox counts next to the list are scoped the same way.

S2 — ``GET /api/systems/{key}/sessions/{user_id}`` let an outside agent read
its person's creative session, which the MCP ``get_session`` tool refuses.
Both now apply the same own-conversation rule.
"""

from __future__ import annotations

import textwrap
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

API_KEY = "test-api-key-1234567890abcdef"

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
    """
)

SYSTEMS = {
    "acme": {"name": "Acme Tower", "agents": {}},
    "globex": {"name": "Globex Fund", "agents": {}},
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """users.yaml, a migrated operational DB, a memory DB with both ventures' memories, empty session caches."""
    from realize_core import config
    from realize_core.db.migrations import run_migrations
    from realize_core.db.schema import init_schema, set_db_path
    from realize_core.memory import store
    from realize_core.migration.engine import MigrationEngine
    from realize_core.pipeline import session

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "KB_PATH", tmp_path)
    (tmp_path / "users.yaml").write_text(USERS_YAML, encoding="utf-8")
    ops = tmp_path / "ops.db"
    init_schema(ops)
    run_migrations(ops)
    MigrationEngine(db_path=ops).migrate_up()
    set_db_path(ops)

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "memory.db")
    store.init_db()
    store.store_memory("acme", "decision", "Pelican tower: acme chose the steel frame")
    store.store_memory("globex", "decision", "Pelican fund: globex sold the bridge stake for 4M")
    monkeypatch.setattr(session, "_sessions", type(session._sessions)())
    monkeypatch.setattr(session, "_hydrated_users", set())
    yield tmp_path
    set_db_path(None)


def _app():
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = dict(SYSTEMS)
    app.state.config = {"features": {}}
    return app


@pytest.fixture
def api(env, monkeypatch):
    """The API with auth on (API key), as agent tokens need."""
    monkeypatch.setenv("REALIZE_API_KEY", API_KEY)
    monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
    app = _app()
    return SimpleNamespace(client=TestClient(app), app=app)


def _as(user_id: str, role: str, monkeypatch) -> TestClient:
    """A client (auth off) whose requests carry this principal, as the auth middleware would set it."""
    monkeypatch.delenv("REALIZE_API_KEY", raising=False)
    monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
    app = _app()

    @app.middleware("http")
    async def as_principal(request, call_next):
        request.state.user_id = user_id
        request.state.role = role
        request.state.scopes = []
        return await call_next(request)

    return TestClient(app)


def _agent_token(user: str = "dana@acme.io", ventures=("acme",)) -> dict:
    from realize_core.security.agent_tokens import create_token

    _, secret = create_token(name="claude-desktop-acme", user_email=user, ventures=list(ventures))
    return {"Authorization": f"Bearer {secret}"}


def _ventures(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {row["system_key"] for row in response.json()["results"]}


# ---------------------------------------------------------------------------
# S1 — memory search and stats
# ---------------------------------------------------------------------------


class TestMemorySearch:
    def test_an_agent_token_finds_only_its_ventures_memories(self, api):
        headers = _agent_token()
        r = api.client.get("/api/memory/search", params={"q": "pelican"}, headers=headers)
        assert _ventures(r) == {"acme"}
        assert "globex" not in r.text
        assert "bridge stake" not in r.text
        named = api.client.get("/api/memory/search", params={"q": "pelican", "venture": "globex"}, headers=headers)
        assert named.status_code == 403

    def test_a_venture_limited_person_finds_only_their_ventures_memories(self, env, monkeypatch):
        dana = _as("dana@acme.io", "operator", monkeypatch)
        r = dana.get("/api/memory/search", params={"q": "pelican"})
        assert _ventures(r) == {"acme"}
        assert "bridge stake" not in r.text
        assert dana.get("/api/memory/search", params={"q": "pelican", "venture": "globex"}).status_code == 403
        assert _ventures(dana.get("/api/memory/search", params={"q": "pelican", "venture": "acme"})) == {"acme"}

    def test_an_unrestricted_owner_finds_every_ventures_memories(self, api, monkeypatch):
        r = api.client.get("/api/memory/search", params={"q": "pelican"}, headers={"X-API-Key": API_KEY})
        assert _ventures(r) == {"acme", "globex"}
        owner = _as("owner@realization.co.il", "owner", monkeypatch)
        assert _ventures(owner.get("/api/memory/search", params={"q": "pelican"})) == {"acme", "globex"}
        assert _ventures(owner.get("/api/memory/search", params={"q": "pelican", "venture": "globex"})) == {"globex"}

    def test_the_limit_counts_only_memories_the_caller_may_see(self, env, monkeypatch):
        """Scoping is in the query: other ventures' rows can't crowd out the caller's."""
        from realize_core.memory import store

        for i in range(30):
            store.store_memory("globex", f"learning-{i}", f"Pelican note {i}: globex item {i * 7919}")
        r = _as("dana@acme.io", "operator", monkeypatch).get("/api/memory/search", params={"q": "pelican"})
        assert _ventures(r) == {"acme"}
        assert len(r.json()["results"]) == 1

    def test_stats_are_a_system_area(self, api, monkeypatch):
        assert api.client.get("/api/memory/stats", headers=_agent_token()).status_code == 403
        assert _as("dana@acme.io", "operator", monkeypatch).get("/api/memory/stats").status_code == 403
        assert _as("owner@realization.co.il", "owner", monkeypatch).get("/api/memory/stats").status_code == 200

    def test_store_search_by_allowed_set(self, env):
        from realize_core.memory.store import search_memories

        assert {m["system_key"] for m in search_memories("pelican", system_keys={"acme"})} == {"acme"}
        assert search_memories("pelican", system_keys=frozenset()) == []
        assert {m["system_key"] for m in search_memories("pelican")} == {"acme", "globex"}
        assert search_memories("pelican", system_key="globex", system_keys={"acme"}) == []


def test_dream_inbox_counts_cover_only_the_callers_ventures(env, monkeypatch):
    from realize_core.dreaming.inbox import DreamInbox
    from realize_core.dreaming.policy import DreamProposal

    inbox = DreamInbox(env / "dream-inbox.jsonl")
    for venture in ("acme", "globex", "globex", ""):
        inbox.submit(DreamProposal(cycle_type="curator", action="annotate_entity", venture=venture, title="x"))

    def stats(client: TestClient) -> dict:
        client.app.state.dream_inbox = inbox
        r = client.get("/api/dreams", params={"status": ""})
        assert r.status_code == 200, r.text
        return r.json()

    dana = stats(_as("dana@acme.io", "operator", monkeypatch))
    assert dana["count"] == 1
    assert dana["stats"]["total"] == 1
    owner = stats(_as("owner@realization.co.il", "owner", monkeypatch))
    assert owner["stats"]["total"] == 4


# ---------------------------------------------------------------------------
# S2 — creative sessions over REST
# ---------------------------------------------------------------------------


@pytest.fixture
def dana_session(env):
    from realize_core.pipeline.session import create_session

    return create_session("acme", "dana@acme.io", "Tower brochure", "content", ["writer", "reviewer"])


class TestSessionRoute:
    URL = "/api/systems/acme/sessions/dana@acme.io"

    def test_an_agent_cannot_read_its_persons_session(self, api, dana_session):
        r = api.client.get(self.URL, headers=_agent_token())
        assert r.status_code == 403
        assert "Tower brochure" not in r.text

    def test_the_person_reads_their_own_session(self, env, dana_session, monkeypatch):
        r = _as("dana@acme.io", "operator", monkeypatch).get(self.URL)
        assert r.status_code == 200, r.text
        assert r.json()["session"]["id"] == dana_session.id
        assert r.json()["session"]["brief"] == "Tower brochure"

    def test_a_person_cannot_read_someone_elses_session(self, env, dana_session, monkeypatch):
        from realize_core.pipeline.session import create_session

        create_session("acme", "owner@realization.co.il", "Board memo", "content", ["writer"])
        r = _as("dana@acme.io", "operator", monkeypatch).get("/api/systems/acme/sessions/owner@realization.co.il")
        assert r.status_code == 403
        assert "Board memo" not in r.text

    def test_owners_and_the_api_key_may_name_another_user(self, api, dana_session, monkeypatch):
        assert api.client.get(self.URL, headers={"X-API-Key": API_KEY}).json()["session"]["id"] == dana_session.id
        owner = _as("owner@realization.co.il", "owner", monkeypatch)
        assert owner.get(self.URL).json()["session"]["id"] == dana_session.id

    def test_rest_and_mcp_apply_the_same_rule(self, env, dana_session):
        """The REST route and the MCP get_session tool share may_access_conversation."""
        import asyncio

        from realize_core.mcp_server.tools.chat_tools import get_session

        agent = SimpleNamespace(user_id="agent:abc", role="operator", scopes=["agent:abc", "venture:acme"])
        out = asyncio.run(get_session({"system_key": "acme", "user_id": "dana@acme.io"}, None, agent))
        assert out["code"] == "MCP_FORBIDDEN"
