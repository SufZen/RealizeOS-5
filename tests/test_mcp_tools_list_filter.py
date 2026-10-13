"""tools/list leaves out the tools a caller would be refused.

Outside agents (agent tokens and stdio sessions) don't see tools their rules
refuse, RBAC roles don't see tools their permissions don't cover, MCP-only
roles keep the scope check, and a venture-limited caller doesn't see tools
that span every venture. Pilot accounts stay confined. Calls to a hidden
tool are still refused.
"""

from __future__ import annotations

import json
import textwrap
from types import SimpleNamespace

import pytest
from realize_api.dependencies import CurrentUser

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


def _listed(user, cfg=None) -> set[str]:
    from realize_core.mcp_server.registry import get_registry
    from realize_core.mcp_server.server import callable_tools

    return {t.name for t in callable_tools(get_registry(), cfg or _config(), user)}


# ---------------------------------------------------------------------------
# tools/list hides what the caller would be refused
# ---------------------------------------------------------------------------


class TestToolsListHidesRefusedTools:
    def test_an_agent_token_sees_only_tools_it_may_call_or_have_held(self, world):
        from realize_core.security.agent_access import ALLOW, HOLD, MCP_TOOL_RULES

        names = _listed(_agent())
        assert {"run_workflow", "trigger_skill"} <= names  # held writes stay listed
        assert {"realize_chat", "list_approvals", "kb_search"} <= names
        refused = {
            "approve_request",
            "reject_request",
            "approve_suggestion",
            "dismiss_suggestion",
            "run_evolution",
            "create_venture",
            "delete_venture",
            "update_setting",
            "reload_agents",
        }
        assert not names & refused
        # Tools spanning every venture are hidden from a venture-scoped agent.
        assert not names & {"realize_status", "kb_get_document", "list_suggestions"}
        assert all(MCP_TOOL_RULES.get(n) in (ALLOW, HOLD) for n in names)

    def test_a_stdio_session_is_filtered_like_an_agent_token(self, world):
        names = _listed(_stdio())
        assert "run_workflow" in names
        assert not names & {"approve_request", "delete_venture", "update_setting"}

    def test_rbac_roles_see_only_their_permissions(self, world):
        viewer = _listed(CurrentUser(user_id="vic@acme.io", role="viewer", scopes=[]))
        assert "list_agents" in viewer
        assert not viewer & {"realize_chat", "run_workflow", "approve_request", "delete_venture"}

        operator = _listed(CurrentUser(user_id="dana@acme.io", role="operator", scopes=[]))
        assert {"realize_chat", "run_workflow"} <= operator
        assert not operator & {"run_evolution", "delete_venture", "update_setting"}

        owner = _listed(CurrentUser(user_id="owner@realization.co.il", role="owner", scopes=[]))
        assert {"delete_venture", "approve_request", "run_evolution"} <= owner

    def test_mcp_only_roles_keep_the_scope_check(self, world):
        read = _listed(CurrentUser(user_id="u", role="read", scopes=[]))
        assert "list_agents" in read
        assert "clear_history" not in read  # needs editor
        assert "clear_history" in _listed(CurrentUser(user_id="u", role="editor", scopes=[]))

    def test_a_venture_limited_person_doesnt_see_tools_that_span_every_venture(self, world):
        dana = CurrentUser(user_id="dana@acme.io", role="operator", scopes=["venture:acme"])
        names = _listed(dana)
        assert {"list_agents", "list_ventures", "realize_health"} <= names
        assert not names & {"realize_status", "kb_get_document", "list_suggestions"}

    def test_pilot_accounts_keep_their_confinement(self, world):
        from realize_core.wedge.pilot import PILOT_TOOLS

        (world.path / "users.yaml").write_text(
            USERS_YAML + '  - email: pilot@example.com\n    role: operator\n    pilot: true\n    password_hash: "x"\n',
            encoding="utf-8",
        )
        pilot = CurrentUser(user_id="pilot@example.com", role="operator", scopes=[])
        names = _listed(pilot, _config(tools=None))
        assert "realize_health" in names
        assert names <= PILOT_TOOLS
        assert "list_agents" in _listed(CurrentUser(user_id="dana@acme.io", role="operator", scopes=[]))

    @pytest.mark.asyncio
    async def test_hidden_tools_are_still_refused_when_called(self, world):
        agent = _agent()
        assert "approve_request" not in _listed(agent)
        out = await _call(world.state, agent, "approve_request", {"approval_id": "x"})
        assert out["code"] == "MCP_AGENT_CANNOT_DECIDE"
        out = await _call(world.state, agent, "delete_venture", {"key": "acme", "confirm": True})
        assert out["code"] == "MCP_AGENT_REFUSED"
        viewer = CurrentUser(user_id="vic@acme.io", role="viewer", scopes=[])
        out = await _call(world.state, viewer, "run_workflow", {"name": "x", "input_text": "y"})
        assert out["code"] == "MCP_INSUFFICIENT_SCOPE"

    @pytest.mark.asyncio
    async def test_every_listed_tool_passes_the_callers_static_checks(self, world):
        """No drift: what tools/list offers is never refused before the arguments are looked at."""
        from realize_core.mcp_server import venture_guard
        from realize_core.mcp_server.registry import get_registry
        from realize_core.mcp_server.server import caller_refusal

        callers = [
            _agent(),
            _stdio(),
            CurrentUser(user_id="vic@acme.io", role="viewer", scopes=["venture:acme"]),
            CurrentUser(user_id="dana@acme.io", role="operator", scopes=["venture:acme"]),
            CurrentUser(user_id="owner@realization.co.il", role="owner", scopes=[]),
        ]
        for user in callers:
            allowed = venture_guard.caller_ventures(user)
            for tool in get_registry().visible_tools(_config()):
                listed = tool.name in _listed(user)
                refused = caller_refusal(tool, user) is not None or (
                    allowed is not None
                    and "spans every venture" in (venture_guard.check_call(tool.name, {}, allowed) or "")
                )
                assert listed != refused, (user.user_id, tool.name)

    def test_the_mcp_server_lists_through_the_same_filter(self, world):
        """The SDK handler (what clients get on tools/list) uses callable_tools."""
        import anyio
        import mcp.types as mcp_types
        from realize_core.mcp_server.auth import bind_user, reset_user
        from realize_core.mcp_server.server import build_mcp_server

        server = build_mcp_server(app_state=world.state, mcp_config=_config())
        handler = server.request_handlers[mcp_types.ListToolsRequest]
        token = bind_user(_agent())
        try:
            result = anyio.run(handler, mcp_types.ListToolsRequest(method="tools/list"))
        finally:
            reset_user(token)
        names = {t.name for t in result.root.tools}
        assert "run_workflow" in names
        assert "approve_request" not in names
