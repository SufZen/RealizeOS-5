"""STORY-37 — venture-scoped agent tokens: one outside agent sees one client's brain.

Covers the token store (create, hash at rest, revoke, expiry, users.yaml
re-checks), the auth middleware (REST and MCP accept tokens; query strings,
revoked and disabled tokens are refused), venture narrowing on REST, the
REST management endpoints, the CLI and the rate-limit bucket.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import textwrap
from datetime import timedelta
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
      - email: adam@realization.co.il
        role: admin
        password_hash: "$2b$12$adam"
      - email: dana@acme.io
        role: operator
        ventures: [acme]
        password_hash: "$2b$12$dana"
      - email: olga@acme.io
        role: operator
        ventures: [acme, globex]
        password_hash: "$2b$12$olga"
    """
)

SYSTEMS = {
    "acme": {"name": "Acme Tower", "agents": {}},
    "globex": {"name": "Globex Fund", "agents": {}},
}


def _migrated_db(path):
    from realize_core.db.migrations import run_migrations
    from realize_core.db.schema import init_schema
    from realize_core.migration.engine import MigrationEngine

    init_schema(path)
    run_migrations(path)
    MigrationEngine(db_path=path).migrate_up()
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A project folder with users.yaml and its own migrated operational DB."""
    from realize_core import config
    from realize_core.db.schema import set_db_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "KB_PATH", tmp_path)  # decision-log writes stay in the temp folder
    (tmp_path / "users.yaml").write_text(USERS_YAML, encoding="utf-8")
    set_db_path(_migrated_db(tmp_path / "ops.db"))
    yield tmp_path
    set_db_path(None)


@pytest.fixture
def audit_events(monkeypatch):
    """Capture the token store's audit events."""
    from realize_core.security import agent_tokens

    events: list[dict] = []
    monkeypatch.setattr(agent_tokens, "_audit", lambda action, user_id, **kw: events.append({"action": action, **kw}))
    return events


def _create(user: str = "dana@acme.io", ventures=("acme",), **kw):
    from realize_core.security.agent_tokens import create_token

    return create_token(name=kw.pop("name", "claude-desktop-acme"), user_email=user, ventures=list(ventures), **kw)


# ---------------------------------------------------------------------------
# Token store
# ---------------------------------------------------------------------------


class TestStore:
    def test_create_shows_secret_once_and_stores_only_a_hash(self, env):
        from realize_core.db.schema import get_connection
        from realize_core.security.agent_tokens import TOKEN_PREFIX, list_tokens

        token, secret = _create(expires_in_days=30, created_by="owner@realization.co.il")
        assert secret.startswith(f"{TOKEN_PREFIX}{token.id}_")
        assert "." not in secret  # never mistaken for a JWT
        conn = get_connection()
        try:
            row = dict(conn.execute("SELECT * FROM agent_tokens WHERE id = ?", (token.id,)).fetchone())
        finally:
            conn.close()
        assert row["token_hash"] == hashlib.sha256(secret.encode()).hexdigest()
        assert secret not in json.dumps(row)
        listed = list_tokens()[0].to_dict()
        assert listed["ventures"] == ["acme"]
        assert listed["status"] == "active"
        assert listed["principal"] == f"agent:{token.id}"
        assert "token_hash" not in listed
        assert secret not in json.dumps(listed)

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"user": "nobody@acme.io"}, "No user"),
            ({"ventures": ()}, "at least one venture"),
            ({"ventures": ("globex",)}, "can't see venture 'globex'"),
            ({"ventures": ("../etc",)}, "Invalid venture key"),
            ({"name": "bad\nname"}, "Name must be"),
            ({"expires_in_days": 0}, "between 1 and"),
            ({"user": "owner@realization.co.il", "ventures": ("nope",), "known_ventures": ["acme"]}, "Unknown venture"),
        ],
    )
    def test_create_refuses_bad_requests(self, env, kwargs, message):
        from realize_core.security.agent_tokens import AgentTokenError

        with pytest.raises(AgentTokenError, match=message):
            _create(**kwargs)

    def test_resolve_gives_a_venture_scoped_agent_principal(self, env, audit_events):
        from realize_core.security.agent_tokens import get_token, resolve_token

        token, secret = _create()
        principal = resolve_token(secret)
        assert principal is not None
        assert principal.user_id == f"agent:{token.id}"
        assert principal.role == "operator"
        assert principal.ventures == {"acme"}
        assert principal.scopes == [f"agent:{token.id}", "venture:acme"]
        assert get_token(token.id).last_used_at is not None
        assert [e["action"] for e in audit_events] == ["agent_token.create"]

    @pytest.mark.parametrize("mutate", ["secret", "id", "malformed"])
    def test_wrong_tokens_are_refused_and_audited(self, env, audit_events, mutate):
        from realize_core.security.agent_tokens import resolve_token

        token, secret = _create()
        bad = {
            "secret": secret[:-4] + ("AAAA" if not secret.endswith("AAAA") else "BBBB"),
            "id": secret.replace(token.id, "0" * 12),
            "malformed": "rzag_short",
        }[mutate]
        assert resolve_token(bad) is None
        denied = [e for e in audit_events if e["action"] == "agent_token.denied"]
        assert denied
        assert denied[-1]["metadata"]["reason"] in {"bad_secret", "unknown", "malformed"}
        assert secret not in json.dumps(audit_events)

    def test_revoke_stops_the_token_at_once(self, env, audit_events):
        from realize_core.security.agent_tokens import resolve_token, revoke_token

        token, secret = _create()
        revoked, withdrawn = revoke_token(token.id, revoked_by="owner@realization.co.il")
        assert revoked.status == "revoked"
        assert withdrawn == 0
        assert resolve_token(secret) is None
        assert revoke_token(token.id)[0].status == "revoked"  # twice is harmless
        assert revoke_token("0" * 12) is None
        assert "agent_token.revoke" in [e["action"] for e in audit_events]

    def test_expired_tokens_stop_working(self, env, monkeypatch):
        from realize_core.security import agent_tokens

        token, secret = _create(expires_in_days=1)
        assert agent_tokens.resolve_token(secret) is not None
        later = agent_tokens._now() + timedelta(days=2)
        monkeypatch.setattr(agent_tokens, "_now", lambda: later)
        assert agent_tokens.resolve_token(secret) is None
        assert agent_tokens.get_token(token.id).status == "expired"

    def test_users_yaml_is_read_again_and_narrows(self, env):
        from realize_core.security.agent_tokens import resolve_token

        _, olga_secret = _create(user="olga@acme.io", ventures=("acme", "globex"))
        _, dana_secret = _create(user="dana@acme.io", ventures=("acme",))
        assert resolve_token(olga_secret).ventures == {"acme", "globex"}

        # Olga loses globex, Dana is removed from users.yaml.
        (env / "users.yaml").write_text(
            USERS_YAML.replace("ventures: [acme, globex]", "ventures: [acme]").replace(
                '  - email: dana@acme.io\n    role: operator\n    ventures: [acme]\n    password_hash: "$2b$12$dana"\n',
                "",
            ),
            encoding="utf-8",
        )
        assert resolve_token(olga_secret).ventures == {"acme"}
        assert resolve_token(dana_secret) is None

    def test_a_token_whose_ventures_all_fall_away_stops(self, env):
        from realize_core.security.agent_tokens import resolve_token

        _, secret = _create(user="olga@acme.io", ventures=("globex",))
        (env / "users.yaml").write_text(USERS_YAML.replace("ventures: [acme, globex]", "ventures: [acme]"), "utf-8")
        assert resolve_token(secret) is None

    def test_allowed_ventures_for_agent_principals(self, env):
        from realize_core.security.venture_scope import allowed_ventures

        assert allowed_ventures("agent:0123456789ab", ["agent:0123456789ab", "venture:acme"]) == {"acme"}
        # An agent is never unrestricted: no venture scope means no venture.
        assert allowed_ventures("agent:0123456789ab", ["agent:0123456789ab"]) == frozenset()
        assert allowed_ventures("agent:0123456789ab", []) == frozenset()
        # People are unaffected.
        assert allowed_ventures("owner@realization.co.il") is None
        assert allowed_ventures("api-key") is None

    def test_agents_act_only_for_themselves(self):
        from realize_core.security.chat_access import chat_user_for, may_access_conversation

        agent = "agent:0123456789ab"
        assert chat_user_for(agent, "owner", "boss@acme.io") == agent
        assert not may_access_conversation(agent, "owner", "boss@acme.io")
        assert may_access_conversation(agent, "owner", agent)
        # People keep today's rule.
        assert chat_user_for("owner@realization.co.il", "owner", "boss@acme.io") == "boss@acme.io"
        assert chat_user_for("dana@acme.io", "operator", "boss@acme.io") == "dana@acme.io"

    def test_migration_012_up_and_down(self, tmp_path):
        import importlib

        m012 = importlib.import_module("realize_core.migration.versions.012_agent_tokens")
        conn = sqlite3.connect(tmp_path / "m.db")
        m012.up(conn)
        m012.up(conn)  # idempotent
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "agent_tokens" in tables
        m012.down(conn)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "agent_tokens" not in tables
        conn.close()


# ---------------------------------------------------------------------------
# REST: auth middleware, venture narrowing, people decide
# ---------------------------------------------------------------------------


@pytest.fixture
def api(env, monkeypatch):
    """The API with auth on (API key), two ventures and an approval in each."""
    from realize_api.main import create_app
    from realize_core.governance.gates import create_approval_request

    monkeypatch.setenv("REALIZE_API_KEY", API_KEY)
    monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
    app = create_app()
    app.state.systems = dict(SYSTEMS)
    app.state.config = {"features": {}}
    ids = {v: create_approval_request(v, "writer", "sheets_append", {"row": v}) for v in SYSTEMS}
    return SimpleNamespace(client=TestClient(app), app=app, approvals=ids)


def _bearer(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


class TestRestAccess:
    def test_agent_reads_only_its_ventures(self, api):
        _, secret = _create()
        c = api.client
        assert [v["key"] for v in c.get("/api/ventures", headers=_bearer(secret)).json()["ventures"]] == ["acme"]
        rows = c.get("/api/approvals", headers=_bearer(secret)).json()["approvals"]
        assert {r["venture_key"] for r in rows} == {"acme"}
        # Status, not other people's parameters.
        assert rows[0]["outcome"] == "pending_approval"
        assert "payload" not in rows[0]
        assert "params_json" not in rows[0]
        assert c.get("/api/approvals", params={"venture_key": "globex"}, headers=_bearer(secret)).status_code == 403
        assert c.get("/api/ventures/acme/export", headers=_bearer(secret)).status_code != 403
        assert c.get("/api/ventures/globex/export", headers=_bearer(secret)).status_code == 403
        # Also via X-API-Key.
        assert c.get("/api/ventures", headers={"X-API-Key": secret}).status_code == 200
        # Shared, every-venture areas stay closed.
        assert c.get("/api/settings/features", headers=_bearer(secret)).status_code == 403

    def test_agent_cannot_approve_or_write_over_rest(self, api):
        _, secret = _create()
        c = api.client
        r = c.post(f"/api/approvals/{api.approvals['acme']}/approve", headers=_bearer(secret))
        assert r.status_code == 403
        assert "People decide" in r.text
        r = c.post("/api/ventures/acme/kb/file", json={"path": "x.md", "content": "x"}, headers=_bearer(secret))
        assert r.status_code == 403
        assert "through MCP" in r.text
        # The person still decides.
        r = c.post(f"/api/approvals/{api.approvals['acme']}/reject", headers={"X-API-Key": API_KEY})
        assert r.status_code == 200
        assert r.json()["decided_by"] == "api-key"

    @pytest.mark.parametrize(
        ("method", "path", "rule"),
        [
            ("GET", "/api/ventures", "allow"),
            ("GET", "/api/approvals", "allow"),
            ("POST", "/api/chat", "allow"),
            ("POST", "/api/chat/stream", "allow"),
            ("DELETE", "/api/conversations/acme/agent:0123456789ab", "allow"),
            ("POST", "/api/approvals/a1/approve", "people_decide"),
            ("POST", "/api/approvals/a1/reject/", "people_decide"),
            ("POST", "/api/dreams/p1/reject", "people_decide"),
            ("POST", "/api/evolution/suggestions/s1/dismiss", "people_decide"),
            ("POST", "/api/auth/logout", "refuse"),
            ("DELETE", "/api/auth/sessions", "refuse"),
            ("POST", "/api/workflows/acme-report/test", "refuse"),
            ("PUT", "/api/fabric/entities/e1", "refuse"),
            ("POST", "/api/ventures/acme/kb/file", "refuse"),
            ("POST", "/api/agent-tokens", "refuse"),
            ("PATCH", "/api/some-future-route", "refuse"),  # deny by default
        ],
    )
    def test_rest_rules(self, method, path, rule):
        from realize_core.security.agent_access import rest_rule

        assert rest_rule(method, path) == rule

    def test_revoked_unknown_and_query_string_tokens_get_401(self, api):
        from realize_core.security.agent_tokens import revoke_token

        token, secret = _create()
        c = api.client
        assert c.get("/api/ventures", params={"api_key": secret}).status_code == 401  # never from the URL
        assert c.get("/api/ventures", headers=_bearer(secret.replace(token.id, "f" * 12))).status_code == 401
        revoke_token(token.id)
        r = c.get("/api/ventures", headers=_bearer(secret))
        assert r.status_code == 401
        assert r.json()["error"] == "invalid_token"

    def test_flag_off_stops_every_agent_token(self, api):
        _, secret = _create()
        api.app.state.config = {"features": {"agent_tokens": False}}
        assert api.client.get("/api/ventures", headers=_bearer(secret)).status_code == 401
        r = api.client.post(
            "/api/agent-tokens",
            json={"name": "x", "user": "dana@acme.io", "ventures": ["acme"]},
            headers={"X-API-Key": API_KEY},
        )
        assert r.status_code == 409
        # People are unaffected.
        assert api.client.get("/api/ventures", headers={"X-API-Key": API_KEY}).status_code == 200

    def test_people_keep_todays_access(self, api):
        rows = api.client.get("/api/approvals", headers={"X-API-Key": API_KEY}).json()["approvals"]
        assert {r["venture_key"] for r in rows} == {"acme", "globex"}
        assert all("params_json" in r for r in rows)
        assert api.client.get("/api/ventures").status_code == 401


# ---------------------------------------------------------------------------
# REST mirrors MCP: one predicate, one rule set (agent_access)
# ---------------------------------------------------------------------------

#: Each MCP tool an agent may not run directly, and its REST counterparts.
REST_COUNTERPARTS = {
    "run_workflow": [("POST", "/api/workflows/acme-report/test"), ("POST", "/api/workflows")],
    "trigger_skill": [("POST", "/api/workflows/acme-report/test")],
    "approve_request": [("POST", "/api/approvals/{acme}/approve")],
    "reject_request": [("POST", "/api/approvals/{acme}/reject")],
    "approve_suggestion": [("POST", "/api/evolution/suggestions/s1/approve")],
    "dismiss_suggestion": [("POST", "/api/evolution/suggestions/s1/dismiss")],
    "create_venture": [("POST", "/api/ventures")],
    "delete_venture": [("DELETE", "/api/ventures/acme")],
    "update_setting": [("PUT", "/api/settings/features")],
    "reload_agents": [("POST", "/api/agents/reload")],
    "run_evolution": [],  # no REST route
}


class TestRestMirrorsMcp:
    def test_every_non_allowed_tool_has_a_rest_counterpart_listed(self):
        from realize_core.security.agent_access import ALLOW, MCP_TOOL_RULES

        assert {n for n, rule in MCP_TOOL_RULES.items() if rule != ALLOW} == set(REST_COUNTERPARTS)

    @pytest.mark.parametrize("tool", sorted(REST_COUNTERPARTS))
    def test_what_mcp_holds_or_refuses_rest_refuses(self, api, tool):
        """REST has no hold path: anything MCP would hold or refuse is a 403 over REST."""
        from realize_core.security.agent_access import (
            PEOPLE_DECIDE,
            PEOPLE_DECIDE_MESSAGE,
            REST_WRITE_MESSAGE,
            tool_refusal,
            tool_rule,
        )

        _, secret = _create(user="owner@realization.co.il", ventures=("acme",))
        for method, path in REST_COUNTERPARTS[tool]:
            r = api.client.request(method, path.format(acme=api.approvals["acme"]), headers=_bearer(secret), json={})
            assert r.status_code == 403, (method, path, r.text)
            expected = PEOPLE_DECIDE_MESSAGE if tool_rule(tool) == PEOPLE_DECIDE else REST_WRITE_MESSAGE
            assert expected in r.json()["detail"]
        refusal = tool_refusal(tool)
        if tool_rule(tool) == PEOPLE_DECIDE:
            assert PEOPLE_DECIDE_MESSAGE in refusal[1]  # same words on both surfaces
        # The person's decisions are untouched.
        rows = api.client.get("/api/approvals", headers={"X-API-Key": API_KEY}).json()["approvals"]
        assert {r["status"] for r in rows} == {"pending"}

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/api/agent-tokens"),
            ("POST", "/api/agent-tokens"),
            ("DELETE", "/api/agent-tokens/0123456789ab"),
            ("DELETE", "/api/auth/sessions"),
            ("POST", "/api/auth/logout"),
            ("PUT", "/api/ventures/acme/kb/file"),
            ("POST", "/api/ventures/acme/ingest"),
        ],
    )
    def test_agents_stay_out_of_management_and_session_endpoints(self, api, method, path):
        _, secret = _create(user="owner@realization.co.il", ventures=("acme", "globex"))
        r = api.client.request(method, path, headers=_bearer(secret), json={})
        assert r.status_code == 403, r.text

    def test_same_scope_on_both_surfaces(self, env):
        """REST (get_allowed_ventures) and MCP (caller_ventures) resolve an agent's ventures the same way."""
        from realize_api.dependencies import CurrentUser, get_allowed_ventures
        from realize_core.mcp_server.venture_guard import caller_ventures
        from realize_core.security.agent_tokens import resolve_token

        _, secret = _create(user="olga@acme.io", ventures=("acme", "globex"))
        principal = resolve_token(secret)
        state = SimpleNamespace(user_id=principal.user_id, scopes=principal.scopes)
        rest = get_allowed_ventures(SimpleNamespace(state=state))
        mcp = caller_ventures(CurrentUser(principal.user_id, principal.role, principal.scopes))
        assert rest == mcp == {"acme", "globex"}


class TestIdentityComesOnlyFromTheToken:
    def test_a_jwt_claiming_an_agent_identity_is_refused(self, env, monkeypatch):
        from realize_api.main import create_app
        from realize_core.security.jwt_auth import create_token

        monkeypatch.setenv("REALIZE_API_KEY", API_KEY)
        monkeypatch.setenv("REALIZE_JWT_ENABLED", "true")
        monkeypatch.setenv("REALIZE_JWT_SECRET", "x" * 40)
        app = create_app()
        app.state.systems = dict(SYSTEMS)
        client = TestClient(app)
        forged_sub = create_token("agent:0123456789ab", role="owner", scopes=["venture:acme"])
        forged_scope = create_token("bob@acme.io", role="owner", scopes=["agent:0123456789ab", "venture:acme"])
        person = create_token("owner@realization.co.il", role="owner")
        assert client.get("/api/ventures", headers=_bearer(forged_sub)).status_code == 401
        assert client.get("/api/ventures", headers=_bearer(forged_scope)).status_code == 401
        assert client.get("/api/ventures", headers=_bearer(person)).status_code == 200
        r = client.post("/api/auth/token", json={"user_id": "agent:0123456789ab", "api_key": API_KEY})
        assert r.status_code == 400

    def test_x_user_id_header_cannot_claim_an_agent(self):
        from realize_api.dependencies import header_user_id

        assert header_user_id({"X-User-ID": "agent:0123456789ab"}) == "anonymous"
        assert header_user_id({"X-User-ID": "hermes-user-7"}) == "hermes-user-7"
        assert header_user_id({}) == "anonymous"

    def test_users_yaml_cannot_define_an_agent(self, env):
        from realize_core.security.users import get_user

        (env / "users.yaml").write_text(
            USERS_YAML + '  - email: "agent:0123456789ab"\n    role: owner\n    password_hash: "$2b$12$x"\n',
            encoding="utf-8",
        )
        assert get_user("agent:0123456789ab") is None
        assert get_user("dana@acme.io") is not None


# ---------------------------------------------------------------------------
# REST management endpoints
# ---------------------------------------------------------------------------


class TestManagementApi:
    def test_create_list_revoke(self, api):
        c = api.client
        owner = {"X-API-Key": API_KEY}
        r = c.post(
            "/api/agent-tokens",
            json={"name": "claude-acme", "user": "dana@acme.io", "ventures": ["acme"], "expires_in_days": 90},
            headers=owner,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        secret, token_id = body["token"], body["agent_token"]["id"]
        assert secret.startswith("rzag_")
        assert body["agent_token"]["created_by"] == "api-key"
        assert body["agent_token"]["expires_at"]

        listing = c.get("/api/agent-tokens", headers=owner)
        assert listing.status_code == 200
        assert secret not in listing.text
        assert [t["id"] for t in listing.json()["tokens"]] == [token_id]

        assert c.get("/api/ventures", headers=_bearer(secret)).status_code == 200
        r = c.delete(f"/api/agent-tokens/{token_id}", headers=owner)
        assert r.status_code == 200
        assert r.json()["agent_token"]["status"] == "revoked"
        assert c.get("/api/ventures", headers=_bearer(secret)).status_code == 401
        assert c.delete("/api/agent-tokens/000000000000", headers=owner).status_code == 404

    @pytest.mark.parametrize(
        ("body", "status"),
        [
            ({"name": "x", "user": "dana@acme.io", "ventures": ["globex"]}, 400),  # outside the user's ventures
            ({"name": "x", "user": "owner@realization.co.il", "ventures": ["nope"]}, 400),  # not configured
            ({"name": "x", "user": "dana@acme.io", "ventures": []}, 422),  # must name a venture
            ({"name": "x", "user": "nobody@x.io", "ventures": ["acme"]}, 400),
        ],
    )
    def test_create_validation(self, api, body, status):
        r = api.client.post("/api/agent-tokens", json=body, headers={"X-API-Key": API_KEY})
        assert r.status_code == status, r.text

    def test_an_agent_cannot_manage_tokens(self, api):
        _, secret = _create(user="owner@realization.co.il")
        c = api.client
        assert c.get("/api/agent-tokens", headers=_bearer(secret)).status_code == 403
        body = {"name": "x", "user": "owner@realization.co.il", "ventures": ["acme", "globex"]}
        assert c.post("/api/agent-tokens", json=body, headers=_bearer(secret)).status_code == 403

    def _as(self, user_id: str, role: str) -> TestClient:
        """An app (auth off) whose requests carry this principal, as the auth middleware would set it."""
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

        return TestClient(app)

    def test_only_unrestricted_owners_and_admins_manage_tokens(self, env, monkeypatch):
        monkeypatch.delenv("REALIZE_API_KEY", raising=False)
        monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
        body = {"name": "x", "user": "dana@acme.io", "ventures": ["acme"]}
        assert self._as("dana@acme.io", "operator").post("/api/agent-tokens", json=body).status_code == 403
        assert self._as("dana@acme.io", "operator").get("/api/agent-tokens").status_code == 403
        admin = self._as("adam@realization.co.il", "admin")
        assert admin.post("/api/agent-tokens", json=body).status_code == 201
        # An admin can't hand an agent the owner's role.
        owner_body = {"name": "x", "user": "owner@realization.co.il", "ventures": ["acme"]}
        assert admin.post("/api/agent-tokens", json=owner_body).status_code == 403
        assert (
            self._as("owner@realization.co.il", "owner").post("/api/agent-tokens", json=owner_body).status_code == 201
        )


# ---------------------------------------------------------------------------
# CLI and rate limiting
# ---------------------------------------------------------------------------


class TestCli:
    def test_create_list_revoke(self, env, monkeypatch):
        from realize_core.cli_app import app
        from realize_core.security.agent_tokens import list_tokens
        from typer.testing import CliRunner

        monkeypatch.setenv("REALIZE_API_KEY", API_KEY)
        runner = CliRunner()
        result = runner.invoke(
            app, ["agent-token", "create", "--name", "cursor", "--user", "olga@acme.io", "--venture", "acme,globex"]
        )
        assert result.exit_code == 0, result.output
        assert "shown only once" in result.output
        token = list_tokens()[0]
        assert token.ventures == ("acme", "globex")
        assert f"rzag_{token.id}_" in result.output

        result = runner.invoke(app, ["--format", "json", "agent-token", "list"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)[0]["id"] == token.id
        assert "rzag_" not in result.output

        result = runner.invoke(app, ["agent-token", "revoke", token.id])
        assert result.exit_code == 0, result.output
        assert list_tokens()[0].status == "revoked"

    def test_create_refuses_a_venture_outside_the_user(self, env):
        from realize_core.cli_app import app
        from typer.testing import CliRunner

        result = CliRunner().invoke(app, ["agent-token", "create", "-n", "x", "-u", "dana@acme.io", "-v", "globex"])
        assert result.exit_code == 1
        assert "can't see venture" in result.output


def test_each_agent_token_has_its_own_rate_limit_bucket():
    from realize_api.security_middleware import _rate_limit_key

    def request(**state):
        return SimpleNamespace(state=SimpleNamespace(**state), client=SimpleNamespace(host="10.0.0.1"), headers={})

    assert _rate_limit_key(request(user_id="agent:0123456789ab", agent_token_id="0123456789ab")) == "agent:0123456789ab"
    assert _rate_limit_key(request(user_id="dana@acme.io")) == "user:dana@acme.io"
