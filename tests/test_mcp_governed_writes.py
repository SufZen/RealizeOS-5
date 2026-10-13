"""STORY-37 — outside agents are governed over MCP.

One agent, one client's brain: scoped reads, held writes, a person's
approval, at-most-once execution, a restart with an unknown outcome, and
"people decide" (an agent never approves its own held write). People
(dashboard users, the API key, JWTs) keep today's behaviour.
"""

from __future__ import annotations

import json
import textwrap
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from realize_core.skills import executor as _executor
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

#: The real skill runner (the ``world`` fixture replaces it with a recorder).
_REAL_EXECUTE_SKILL = _executor.execute_skill

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

SYSTEMS = {
    "acme": {"name": "Acme Tower", "agents": {}},
    "globex": {"name": "Globex Fund", "agents": {}},
}

RUN = {"name": "acme-report", "input_text": "Monthly report for tower B", "system_key": "acme"}


def _migrated_db(path):
    from realize_core.db.migrations import run_migrations
    from realize_core.db.schema import init_schema
    from realize_core.migration.engine import MigrationEngine

    init_schema(path)
    run_migrations(path)
    MigrationEngine(db_path=path).migrate_up()
    return path


@pytest.fixture
def world(tmp_path, monkeypatch):
    """users.yaml, a migrated DB, two ventures with one skill each, and a fake skill runner."""
    from realize_core import config
    from realize_core.db.schema import set_db_path
    from realize_core.mcp_server import registry as registry_mod
    from realize_core.mcp_server.held_writes import bind_app_state
    from realize_core.skills import detector, executor

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "KB_PATH", tmp_path)  # decision-log writes stay in the temp folder
    (tmp_path / "users.yaml").write_text(USERS_YAML, encoding="utf-8")
    db = _migrated_db(tmp_path / "ops.db")
    set_db_path(db)
    registry_mod.reset_for_tests()
    monkeypatch.setattr(
        detector, "_loaded_skills", {"acme": [{"name": "acme-report"}], "globex": [{"name": "globex-report"}]}
    )

    runs: list[dict] = []

    async def fake_execute_skill(**kwargs):
        runs.append(kwargs)
        return "Report ready"

    monkeypatch.setattr(executor, "execute_skill", fake_execute_skill)
    state = SimpleNamespace(systems=dict(SYSTEMS), kb_path=tmp_path, shared_config={}, config={"features": {}})
    bind_app_state(state)
    yield SimpleNamespace(path=tmp_path, db=db, runs=runs, state=state)
    bind_app_state(None)
    registry_mod.reset_for_tests()
    set_db_path(None)


def _agent(user: str = "dana@acme.io", ventures=("acme",)):
    """An agent token's principal, as the auth middleware would set it."""
    from realize_api.dependencies import CurrentUser
    from realize_core.security.agent_tokens import create_token, resolve_token

    _token, secret = create_token(name="claude-acme", user_email=user, ventures=list(ventures))
    principal = resolve_token(secret)
    return CurrentUser(user_id=principal.user_id, role=principal.role, scopes=principal.scopes)


def _person(user_id: str = "dana@acme.io", role: str = "operator"):
    from realize_api.dependencies import CurrentUser

    return CurrentUser(user_id=user_id, role=role, scopes=[])


def _config():
    from realize_core.mcp_server.config import McpConfig

    return McpConfig(
        enabled=True,
        expose_kb=True,
        expose_ops=True,
        allow_admin=True,
        audit_full_payload=False,
        bearer_token_override="",
    )


async def _call(world, user, name: str, args: dict | None = None) -> dict:
    from realize_core.mcp_server.auth import bind_user, reset_user
    from realize_core.mcp_server.registry import get_registry
    from realize_core.mcp_server.server import _dispatch

    token = bind_user(user)
    try:
        out = await _dispatch(get_registry(), _config(), world.state, name, args or {})
    finally:
        reset_user(token)
    return json.loads(out[0].text)


def _row(approval_id: str) -> dict:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        return dict(conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone())
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The per-tool rule
# ---------------------------------------------------------------------------


def test_every_mcp_tool_has_a_rule_for_agents():
    """A new tool needs a decision before outside agents can call it."""
    from realize_core.mcp_server import registry as registry_mod
    from realize_core.security.agent_access import MCP_TOOL_RULES

    registry_mod.reset_for_tests()
    try:
        names = {tool.name for tool in registry_mod.get_registry().all()}
    finally:
        registry_mod.reset_for_tests()
    assert names - set(MCP_TOOL_RULES) == set()


@pytest.mark.parametrize("tool", ["approve_request", "reject_request", "approve_suggestion", "dismiss_suggestion"])
async def test_people_decide_an_agent_never_approves(world, tool):
    agent = _agent()
    held = await _call(world, agent, "run_workflow", RUN)
    out = await _call(world, agent, tool, {"approval_id": held["approval_id"], "suggestion_id": "s1"})
    assert out["code"] == "MCP_AGENT_CANNOT_DECIDE"
    assert _row(held["approval_id"])["status"] == "pending"
    assert world.runs == []


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("create_venture", {"key": "newco"}),
        ("delete_venture", {"venture_key": "acme", "confirm": True}),
        ("update_setting", {"features": {"agent_tools": True}}),
        ("reload_agents", {}),
        ("run_evolution", {"days": 7}),
    ],
)
async def test_agent_cannot_reach_admin_or_every_venture_tools(world, tool, args):
    out = await _call(world, _agent(), tool, args)
    assert out["code"] == "MCP_AGENT_REFUSED"


async def test_scoped_reads(world):
    agent = _agent()
    assert (await _call(world, agent, "get_system", {"system_key": "acme"}))["key"] == "acme"
    assert (await _call(world, agent, "get_system", {"system_key": "globex"}))["code"] == "MCP_FORBIDDEN"
    systems = await _call(world, agent, "list_systems")
    assert [s["key"] for s in systems["systems"]] == ["acme"]
    globex = await _call(world, agent, "run_workflow", {**RUN, "name": "globex-report"})
    assert globex["code"] == "MCP_FORBIDDEN"
    assert (await _call(world, agent, "list_approvals", {"venture_key": "globex"}))["code"] == "MCP_FORBIDDEN"


async def test_a_viewer_bound_agent_cannot_run_anything(world):
    out = await _call(world, _agent(user="vic@acme.io"), "run_workflow", RUN)
    assert out["code"] == "MCP_INSUFFICIENT_SCOPE"


# ---------------------------------------------------------------------------
# Held writes
# ---------------------------------------------------------------------------


async def test_run_workflow_is_held_and_nothing_runs(world):
    agent = _agent()
    out = await _call(world, agent, "trigger_skill", {**RUN, "user_id": "boss@acme.io"})
    assert out["status"] == "pending_approval"
    assert out["venture_key"] == "acme"
    assert world.runs == []

    row = _row(out["approval_id"])
    assert row["status"] == "pending"
    assert row["action_type"] == "mcp_write"
    assert row["action_name"] == "mcp:trigger_skill"
    assert row["requested_by"] == agent.user_id
    assert row["agent_key"] == "claude-acme"
    assert row["session_ref"] == f"acme|{agent.user_id}"
    # The agent acts as itself, whatever user it names.
    assert json.loads(row["params_json"])["user_id"] == agent.user_id


async def test_invalid_writes_are_refused_not_held(world):
    from realize_core.db.schema import get_connection

    out = await _call(world, _agent(), "run_workflow", {**RUN, "input_text": ""})
    assert out["code"] == "MCP_VALIDATION"
    conn = get_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM approval_queue WHERE action_type = 'mcp_write'").fetchone()[0] == 0
    finally:
        conn.close()


async def test_approved_write_runs_once_as_the_agent(world):
    from realize_core.governance.gates import decide_approval, execute_approved_action

    agent = _agent()
    held = await _call(world, agent, "run_workflow", RUN)
    status = await _call(world, agent, "list_approvals", {"venture_key": "acme", "approval_id": held["approval_id"]})
    assert status["approvals"][0]["outcome"] == "pending_approval"

    result = await decide_approval(
        held["approval_id"], approve=True, decided_by="owner@realization.co.il", channel="dashboard"
    )
    assert result["execution"] == {"executed": True, "success": True, "output": "Report ready", "error": None}
    assert len(world.runs) == 1
    assert world.runs[0]["user_id"] == agent.user_id
    assert world.runs[0]["system_key"] == "acme"
    assert world.runs[0]["channel"] == "mcp"

    # A second decision or dispatch does nothing.
    assert await decide_approval(held["approval_id"], approve=True, decided_by="owner@realization.co.il") is None
    assert (await execute_approved_action(held["approval_id"]))["executed"] is False
    assert len(world.runs) == 1

    row = _row(held["approval_id"])
    assert row["execution_status"] == "succeeded"
    assert row["decided_by"] == "owner@realization.co.il"

    # The agent follows its item: status and its own result, not the parameters.
    status = await _call(world, agent, "list_approvals", {"venture_key": "acme", "approval_id": held["approval_id"]})
    item = status["approvals"][0]
    assert item["outcome"] == "succeeded"
    assert item["result"] == "Report ready"
    assert "params_json" not in item
    assert "payload" not in item


async def test_approved_write_runs_its_ventures_own_copy_of_a_shared_name(world, monkeypatch):
    """Two ventures each have 'site-report' with their own sheet: globex's agent gets globex's (G-1)."""
    from realize_core.governance.gates import decide_approval
    from realize_core.skills import detector

    monkeypatch.setattr(
        detector,
        "_loaded_skills",
        {
            "acme": [{"name": "site-report", "variables": {"sheet": "acme-sheet"}}],
            "globex": [{"name": "site-report", "variables": {"sheet": "globex-sheet"}}],
        },
    )
    agent = _agent(user="owner@realization.co.il", ventures=("globex",))
    held = await _call(world, agent, "run_workflow", {**RUN, "name": "site-report", "system_key": "globex"})
    assert held["status"] == "pending_approval"
    result = await decide_approval(held["approval_id"], approve=True, decided_by="owner@realization.co.il")
    assert result["execution"]["success"] is True
    assert world.runs[0]["system_key"] == "globex"
    assert world.runs[0]["skill"]["variables"]["sheet"] == "globex-sheet"


async def test_rejected_write_never_runs(world):
    from realize_core.governance.gates import decide_approval

    agent = _agent()
    held = await _call(world, agent, "run_workflow", RUN)
    await decide_approval(held["approval_id"], approve=False, decided_by="owner@realization.co.il")
    assert world.runs == []
    status = await _call(world, agent, "list_approvals", {"venture_key": "acme", "approval_id": held["approval_id"]})
    assert status["approvals"][0]["outcome"] == "rejected"


async def test_agent_sees_status_not_contents_of_other_items(world):
    from realize_core.governance.gates import create_approval_request

    other = create_approval_request(
        "acme", "writer", "sheets_append", {"row": "secret salary"}, action_name="sheets_append", params={"x": 1}
    )
    items = (await _call(world, _agent(), "list_approvals", {"venture_key": "acme"}))["approvals"]
    item = next(i for i in items if i["id"] == other)
    assert item["outcome"] == "pending_approval"
    assert "secret salary" not in json.dumps(items)
    assert "result" not in item


async def test_no_status_lookup_across_ventures(world):
    """An approval id from another venture can't be read by naming one's own venture."""
    from realize_core.governance.gates import create_approval_request

    globex_item = create_approval_request("globex", "writer", "sheets_append", {"row": "globex only"})
    agent = _agent()
    found = await _call(world, agent, "list_approvals", {"venture_key": "acme", "approval_id": globex_item})
    assert found["approvals"] == []
    refused = await _call(world, agent, "list_approvals", {"venture_key": "globex", "approval_id": globex_item})
    assert refused["code"] == "MCP_FORBIDDEN"


async def test_an_agent_cannot_flood_the_queue(world, monkeypatch):
    from realize_core.mcp_server import held_writes

    monkeypatch.setattr(held_writes, "MAX_PENDING_PER_AGENT", 2)
    agent = _agent()
    assert (await _call(world, agent, "run_workflow", RUN))["status"] == "pending_approval"
    assert (await _call(world, agent, "run_workflow", RUN))["status"] == "pending_approval"
    assert (await _call(world, agent, "run_workflow", RUN))["code"] == "MCP_TOO_MANY_PENDING"
    # Another agent has its own allowance.
    assert (await _call(world, _agent(), "run_workflow", RUN))["status"] == "pending_approval"


async def test_deny_by_default_for_new_or_misspelt_tools(world):
    from realize_core.mcp_server.registry import MCPTool, get_registry
    from realize_core.security.agent_access import tool_rule

    async def handler(args, app_state, user):
        return {"ran": True}

    get_registry().register(
        MCPTool(name="brand_new_tool", family="ops", description="", input_schema={}, scope="read", handler=handler)
    )
    agent = _agent()
    assert (await _call(world, agent, "brand_new_tool"))["code"] == "MCP_AGENT_REFUSED"
    owner = _person("owner@realization.co.il", "owner")
    assert (await _call(world, owner, "brand_new_tool"))["ran"] is True  # people are unaffected
    assert (await _call(world, agent, "RUN_WORKFLOW", RUN))["code"] == "MCP_TOOL_NOT_FOUND"
    for variant in ("Run_Workflow", " run_workflow", "run_workflow ", "approve_request\n"):
        assert tool_rule(variant) == "refuse"


async def test_only_a_live_agent_token_can_hold_a_write(world):
    """A principal that merely looks like an agent (no token row) can't queue or run anything."""
    from realize_api.dependencies import CurrentUser

    pseudo = CurrentUser(user_id="agent:000000000000", role="owner", scopes=["agent:000000000000", "venture:acme"])
    out = await _call(world, pseudo, "run_workflow", RUN)
    assert out["code"] == "MCP_AGENT_REFUSED"
    assert (await _call(world, pseudo, "approve_request", {"approval_id": "x"}))["code"] == "MCP_AGENT_CANNOT_DECIDE"
    assert world.runs == []


async def test_only_declared_arguments_are_stored_and_run(world):
    agent = _agent()
    held = await _call(world, agent, "run_workflow", {**RUN, "approval_id": "other-item", "venture_key": "acme"})
    stored = json.loads(_row(held["approval_id"])["params_json"])
    assert set(stored) == {"name", "input_text", "system_key", "user_id"}


async def test_a_tampered_item_does_not_run(world):
    """The stored call must still name the approval's venture alone when it runs."""
    from realize_core.db.schema import get_connection
    from realize_core.governance.gates import decide_approval

    agent = _agent(user="owner@realization.co.il", ventures=("acme", "globex"))
    held = await _call(world, agent, "run_workflow", RUN)
    conn = get_connection()
    try:
        params = {**RUN, "name": "globex-report", "system_key": "globex", "user_id": agent.user_id}
        conn.execute(
            "UPDATE approval_queue SET params_json = ? WHERE id = ?", (json.dumps(params), held["approval_id"])
        )
        conn.commit()
    finally:
        conn.close()
    result = await decide_approval(held["approval_id"], approve=True, decided_by="dana@acme.io")
    assert result["execution"]["success"] is False
    assert "nothing was done" in result["execution"]["error"]
    assert world.runs == []


async def test_runs_with_the_agents_narrowed_scope_not_the_approvers(world):
    """The owner approves, but the run uses the agent's current scope: here it lost the venture."""
    from realize_core.governance.gates import decide_approval

    agent = _agent()
    held = await _call(world, agent, "run_workflow", RUN)
    (world.path / "users.yaml").write_text(USERS_YAML.replace("ventures: [acme]\n", "ventures: [globex]\n", 1), "utf-8")
    result = await decide_approval(held["approval_id"], approve=True, decided_by="owner@realization.co.il")
    assert result["execution"]["success"] is False
    assert "token" in result["execution"]["error"] or "access" in result["execution"]["error"]
    assert world.runs == []


async def test_turning_agent_tokens_off_stops_approved_writes(world):
    """features.agent_tokens off stops every token at once, also a write approved later (S4)."""
    from realize_core.governance.gates import decide_approval
    from realize_core.security.agent_tokens import live_agent

    agent = _agent()
    held = await _call(world, agent, "run_workflow", RUN)
    world.state.config = {"features": {"agent_tokens": False}}  # Settings: agent tokens off
    assert live_agent(agent.user_id) is None
    result = await decide_approval(held["approval_id"], approve=True, decided_by="owner@realization.co.il")
    assert result["execution"]["success"] is False
    assert "turned off" in result["execution"]["error"]
    assert world.runs == []

    world.state.config = {"features": {"agent_tokens": True}}
    assert live_agent(agent.user_id) is not None


async def test_list_approvals_never_leaks_other_ventures(world):
    """Even naming the venture through another argument (bypassing the input schema) shows only allowed items."""
    from realize_core.governance.gates import create_approval_request

    create_approval_request("acme", "writer", "sheets_append", {"row": "acme"})
    create_approval_request("globex", "writer", "sheets_append", {"row": "globex"})
    for user in (_agent(), _person()):
        items = (await _call(world, user, "list_approvals", {"system_key": "acme"}))["approvals"]
        assert {i["venture_key"] for i in items} == {"acme"}


async def test_restart_with_unknown_outcome_never_reruns(world):
    """The server stops after claiming an approved write and before recording its result."""
    from realize_core.db.schema import set_db_path
    from realize_core.governance import gates
    from realize_core.mcp_server import registry as registry_mod
    from realize_core.mcp_server.held_writes import bind_app_state

    agent = _agent()
    held = await _call(world, agent, "run_workflow", RUN)
    waiting = await _call(world, agent, "run_workflow", {**RUN, "input_text": "Second report"})
    gates.approve_request(held["approval_id"], decided_by="owner@realization.co.il", channel="dashboard")
    assert gates._claim_for_execution(held["approval_id"]) is not None
    # ... the process dies here.

    # Restart: fresh registry and state, same database file.
    registry_mod.reset_for_tests()
    set_db_path(None)
    set_db_path(world.db)
    bind_app_state(SimpleNamespace(**vars(world.state)))

    status = await _call(world, agent, "list_approvals", {"venture_key": "acme", "approval_id": held["approval_id"]})
    item = status["approvals"][0]
    assert item["outcome"] == "unknown_outcome"
    assert "never re-run" in item["outcome_note"]
    assert (await gates.execute_approved_action(held["approval_id"]))["executed"] is False
    assert await gates.decide_approval(held["approval_id"], approve=True) is None
    assert world.runs == []

    # The other held write is still pending after the restart and runs once when approved.
    pending = await _call(
        world, agent, "list_approvals", {"venture_key": "acme", "approval_id": waiting["approval_id"]}
    )
    assert pending["approvals"][0]["outcome"] == "pending_approval"
    await gates.decide_approval(waiting["approval_id"], approve=True, decided_by="owner@realization.co.il")
    assert [r["user_message"] for r in world.runs] == ["Second report"]


async def test_revoking_the_token_withdraws_and_blocks_its_writes(world):
    from realize_core.governance import gates
    from realize_core.security.agent_tokens import revoke_token, token_id_of

    agent = _agent()
    pending = await _call(world, agent, "run_workflow", RUN)
    approved = await _call(world, agent, "run_workflow", {**RUN, "input_text": "Approved before revoke"})
    gates.approve_request(approved["approval_id"], decided_by="owner@realization.co.il")

    _token, withdrawn = revoke_token(token_id_of(agent.user_id), revoked_by="owner@realization.co.il")
    assert withdrawn == 1
    assert _row(pending["approval_id"])["status"] == "rejected"
    assert await gates.decide_approval(pending["approval_id"], approve=True) is None

    # Approved but not yet run when the token was revoked: it must not act.
    execution = await gates.execute_approved_action(approved["approval_id"])
    assert execution["executed"] is True
    assert execution["success"] is False
    assert "revoked" in execution["error"]
    assert world.runs == []


async def _chat_held_write(registry, agent) -> str:
    """A write the governance gate holds from the agent's chat (as the tool loop would call it)."""
    from realize_core.governance.context import tool_call_context
    from realize_core.security.agent_access import acting_for_outside_agent

    with (
        acting_for_outside_agent(agent.user_id),
        tool_call_context(system_key="acme", user_id=agent.user_id, channel="mcp"),
    ):
        result = await registry.execute("ledger_append", {"row": "from chat"})
    return result.metadata["request_id"]


async def _proposal(world, agent) -> str:
    args = {"venture_key": "acme", "title": "Switch supplier", "statement": "Agreed on site."}
    return (await _call(world, agent, "log_decision", args))["approval_id"]


def _expire_token(agent) -> None:
    from realize_core.db.schema import get_connection
    from realize_core.security.agent_tokens import token_id_of

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE agent_tokens SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
            (token_id_of(agent.user_id),),
        )
        conn.commit()
    finally:
        conn.close()


async def test_revoking_withdraws_everything_the_agent_has_waiting(world, ledger):
    """Writes held from its chat and its decision proposals too, not only held MCP writes (S3)."""
    from realize_core.governance import gates
    from realize_core.security.agent_tokens import revoke_token, token_id_of

    registry, tool = ledger
    agent = _agent()
    items = [await _chat_held_write(registry, agent), await _proposal(world, agent)]
    items.append((await _call(world, agent, "run_workflow", RUN))["approval_id"])
    assert {_row(i)["requested_by"] for i in items} == {agent.user_id}

    _token, withdrawn = revoke_token(token_id_of(agent.user_id), revoked_by="owner@realization.co.il")
    assert withdrawn == 3
    for item in items:
        assert _row(item)["status"] == "rejected"
        assert await gates.decide_approval(item, approve=True, decided_by="owner@realization.co.il") is None
    assert tool.calls == []
    assert world.runs == []


async def test_an_expired_agents_items_never_run_when_approved(world, ledger):
    """A token that expired (not revoked) leaves items pending; approving one runs nothing (S3)."""
    from realize_core.governance.gates import decide_approval

    registry, tool = ledger
    (world.path / "systems" / "acme").mkdir(parents=True)  # the decision log has a folder
    agent = _agent()
    chat_held, proposal = await _chat_held_write(registry, agent), await _proposal(world, agent)
    _expire_token(agent)

    write = await decide_approval(chat_held, approve=True, decided_by="owner@realization.co.il")
    assert write["execution"]["success"] is False
    assert "expired" in write["execution"]["error"]
    assert _row(chat_held)["execution_status"] == "failed"
    assert tool.calls == []

    recorded = await decide_approval(proposal, approve=True, decided_by="owner@realization.co.il")
    assert recorded["execution"]["success"] is False
    assert recorded["decision_log"]["logged"] is False
    from realize_core.governance.decision_log import list_decisions

    # The person's decision on the write is logged; the gone agent's proposal is not recorded.
    assert proposal not in {d["approval_id"] for d in list_decisions(world.path / "systems" / "acme")}


async def test_held_write_is_audited(world, monkeypatch):
    from realize_core.security import audit

    events: list[dict] = []
    monkeypatch.setattr(audit, "get_audit_logger", lambda: SimpleNamespace(log=lambda **kw: events.append(kw)))
    agent = _agent()
    held = await _call(world, agent, "run_workflow", RUN)
    refused = await _call(world, agent, "approve_request", {"approval_id": held["approval_id"]})
    assert refused["code"] == "MCP_AGENT_CANNOT_DECIDE"
    by_action = {(e["action"], e["outcome"]): e for e in events}
    assert by_action[("mcp.run_workflow", "held")]["metadata"]["approval_id"] == held["approval_id"]
    assert by_action[("mcp.run_workflow", "held")]["user_id"] == agent.user_id
    assert ("mcp.approve_request", "denied") in by_action


# ---------------------------------------------------------------------------
# Chat can't be used to get around the hold
# ---------------------------------------------------------------------------


class LedgerTool(BaseTool):
    """A write tool the internal agent could call while answering."""

    name = "ledger"
    description = "test ledger"
    category = ToolCategory.DATA

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get_schemas(self):
        obj = {"type": "object", "properties": {}}
        return [
            ToolSchema("ledger_append", "append a row", obj, is_destructive=True),
            ToolSchema("ledger_read", "read rows", obj, is_destructive=False),
        ]

    def is_available(self):
        return True

    async def execute(self, action, params):
        self.calls.append({"action": action, **params})
        return ToolResult.ok(output="done")


@pytest.fixture
def ledger(world, monkeypatch):
    """A registry with the ledger tool and a gate at trust level 5 (writes run automatically)."""
    import realize_core.tools.tool_registry as tr
    from realize_core.governance.tool_gate import ToolGate

    monkeypatch.setattr(tr, "_registry", None)
    registry = tr.get_tool_registry()
    tool = LedgerTool()
    registry.register(tool)
    registry.set_gate(ToolGate(config={"trust": {"level": 5}}))
    return registry, tool


@pytest.fixture
def chat_calls_a_write(monkeypatch):
    """The internal agent's answer calls ledger_append (as the tool loop would)."""
    from realize_core import base_handler
    from realize_core.governance.context import tool_call_context
    from realize_core.security.agent_access import outside_agent_active
    from realize_core.tools.tool_registry import get_tool_registry

    seen: list[dict] = []

    async def fake_process(**kwargs):
        with tool_call_context(system_key=kwargs["system_key"], user_id=kwargs["user_id"], channel="mcp"):
            result = await get_tool_registry().execute("ledger_append", {"row": "x"})
        seen.append({"agent": outside_agent_active(), "result": result, "user_id": kwargs["user_id"]})
        return "ok"

    monkeypatch.setattr(base_handler, "process_message", fake_process)
    return seen


async def test_agent_chat_holds_writes_the_trust_ladder_would_run(world, ledger, chat_calls_a_write):
    registry, tool = ledger
    agent = _agent()
    await _call(world, agent, "realize_chat", {"message": "Add the row", "system_key": "acme"})
    assert chat_calls_a_write[-1]["agent"] is True
    assert chat_calls_a_write[-1]["result"].metadata.get("requires_human") is True
    assert tool.calls == []  # held, not executed
    request_id = chat_calls_a_write[-1]["result"].metadata["request_id"]
    assert _row(request_id)["requested_by"] == agent.user_id

    # A person's chat is unchanged: at trust level 5 the write runs.
    await _call(world, _person(), "realize_chat", {"message": "Add the row", "system_key": "acme"})
    assert chat_calls_a_write[-1]["agent"] is False
    assert tool.calls == [{"action": "ledger_append", "row": "x"}]


LEDGER_SKILL = {
    "name": "ledger-run",
    "_version": 2,
    "steps": [
        {"id": "record", "type": "tool", "tool": "ledger_append", "params": {"row": "{user_message}"}},
        {"id": "check", "type": "tool", "tool": "ledger_read", "params": {}},
        {"id": "total", "type": "tool", "tool": "ledger_append", "params": {"row": "total"}},
    ],
}


def _pending_ledger_writes() -> list[dict]:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM approval_queue WHERE action_name = 'ledger_append' AND status = 'pending' "
            "ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


async def test_an_approved_agent_run_still_holds_each_write(world, ledger, monkeypatch):
    """Approving an agent's held run starts it; the write it makes waits for a person again (G-3)."""
    from realize_core.governance.gates import decide_approval
    from realize_core.skills import detector

    registry, tool = ledger  # trust level 5: a person's run would write at once
    monkeypatch.setattr(_executor, "execute_skill", _REAL_EXECUTE_SKILL)
    monkeypatch.setattr(detector, "_loaded_skills", {"acme": [dict(LEDGER_SKILL)]})
    agent = _agent()
    held = await _call(world, agent, "trigger_skill", {**RUN, "name": "ledger-run", "input_text": "row 7"})

    started = await decide_approval(held["approval_id"], approve=True, decided_by="owner@realization.co.il")
    assert started["execution"]["success"] is True
    assert tool.calls == []  # the write was held, not run
    [write] = _pending_ledger_writes()
    assert write["requested_by"] == agent.user_id
    assert write["venture_key"] == "acme"

    # Approving the write runs it and the skill continues, still as the agent's run:
    # the read runs, the next write is held again.
    resumed = await decide_approval(write["id"], approve=True, decided_by="owner@realization.co.il")
    assert resumed["execution"]["success"] is True
    assert tool.calls == [{"action": "ledger_append", "row": "row 7"}, {"action": "ledger_read"}]
    [total] = _pending_ledger_writes()
    assert json.loads(total["params_json"]) == {"row": "total"}
    assert total["requested_by"] == agent.user_id

    done = await decide_approval(total["id"], approve=True, decided_by="owner@realization.co.il")
    assert done["execution"]["success"] is True
    assert tool.calls[-1] == {"action": "ledger_append", "row": "total"}
    assert done["skill_output"] is not None  # the skill ran to its end
    assert _pending_ledger_writes() == []


async def test_without_a_gate_an_agents_write_never_runs(world, monkeypatch):
    import realize_core.tools.tool_registry as tr
    from realize_core.security.agent_access import acting_for_outside_agent

    monkeypatch.setattr(tr, "_registry", None)
    registry = tr.get_tool_registry()
    tool = LedgerTool()
    registry.register(tool)
    with acting_for_outside_agent("agent:0123456789ab"):
        refused = await registry.execute("ledger_append", {"row": "x"})
        read = await registry.execute("ledger_read", {})
    assert refused.success is False
    assert read.success is True
    assert tool.calls == [{"action": "ledger_read"}]


async def test_trigger_phrases_dont_run_skills_for_agents(world, monkeypatch):
    from realize_core.skills import detector

    monkeypatch.setattr(detector, "detect_skill", lambda message, system_key: {"name": "acme-report", "_version": 2})
    agent = _agent()
    out = await _call(world, agent, "realize_chat", {"message": "monthly report please", "system_key": "acme"})
    assert "trigger_skill" in out["response"]
    assert world.runs == []
    # A person's trigger phrase still runs the skill.
    await _call(world, _person(), "realize_chat", {"message": "monthly report please", "system_key": "acme"})
    assert len(world.runs) == 1


async def test_an_agent_cannot_answer_a_paused_skills_question(world, monkeypatch):
    from realize_core import base_handler
    from realize_core.skills import detector

    calls: list = []

    async def fake_resume(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(base_handler, "_resume_paused_skill", fake_resume)
    monkeypatch.setattr(detector, "detect_skill", lambda message, system_key: {"name": "acme-report", "_version": 2})
    await _call(world, _agent(), "realize_chat", {"message": "yes, go ahead", "system_key": "acme"})
    assert calls == []
    await _call(world, _person(), "realize_chat", {"message": "yes, go ahead", "system_key": "acme"})
    assert len(calls) == 1


def test_rest_chat_and_stream_hold_an_agents_writes(world, ledger, chat_calls_a_write, monkeypatch):
    from realize_api.main import create_app
    from realize_core.security.agent_tokens import create_token

    monkeypatch.setenv("REALIZE_API_KEY", API_KEY)
    monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
    _token, secret = create_token(name="claude-acme", user_email="dana@acme.io", ventures=["acme"])
    app = create_app()
    app.state.systems = dict(SYSTEMS)
    app.state.config = {"features": {}}
    client = TestClient(app)
    body = {"message": "Add the row", "system_key": "acme"}
    agent_headers = {"Authorization": f"Bearer {secret}"}
    _registry, tool = ledger

    assert client.post("/api/chat", json=body, headers=agent_headers).status_code == 200
    with client.stream("POST", "/api/chat/stream", json=body, headers=agent_headers) as r:
        assert r.status_code == 200
        r.read()
    assert [c["agent"] for c in chat_calls_a_write] == [True, True]
    assert tool.calls == []

    assert client.post("/api/chat", json=body, headers={"X-API-Key": API_KEY}).status_code == 200
    assert chat_calls_a_write[-1]["agent"] is False
    assert len(tool.calls) == 1


# ---------------------------------------------------------------------------
# A local stdio session is an outside agent too
# ---------------------------------------------------------------------------


async def test_stdio_session_is_governed_as_an_agent(world):
    from realize_core.governance.gates import decide_approval
    from realize_core.mcp_server.stdio import resolve_stdio_user

    session = resolve_stdio_user("dana@acme.io")
    assert session.user_id == "dana@acme.io"  # the person it acts for (pilot rules, audit)
    held = await _call(world, session, "run_workflow", RUN)
    assert held["status"] == "pending_approval"
    assert world.runs == []
    row = _row(held["approval_id"])
    assert row["requested_by"] == "agent:stdio:dana@acme.io"

    refused = await _call(world, session, "approve_request", {"approval_id": held["approval_id"]})
    assert refused["code"] == "MCP_AGENT_CANNOT_DECIDE"
    assert _row(held["approval_id"])["status"] == "pending"

    # A person approves; it runs once, as the session's user, within the user's ventures.
    result = await decide_approval(held["approval_id"], approve=True, decided_by="owner@realization.co.il")
    assert result["execution"]["success"] is True
    assert [r["user_id"] for r in world.runs] == ["dana@acme.io"]
    status = await _call(world, session, "list_approvals", {"venture_key": "acme", "approval_id": held["approval_id"]})
    assert status["approvals"][0]["outcome"] == "succeeded"
    assert status["approvals"][0]["result"] == "Report ready"


async def test_stdio_owner_session_cannot_act_for_others_or_reach_admin(world, monkeypatch):
    from realize_core import base_handler
    from realize_core.mcp_server.stdio import resolve_stdio_user

    seen: dict = {}

    async def fake_process(**kwargs):
        seen.update(kwargs)
        return "ok"

    monkeypatch.setattr(base_handler, "process_message", fake_process)
    session = resolve_stdio_user("owner@realization.co.il", ["acme"])
    await _call(world, session, "realize_chat", {"message": "hi", "system_key": "acme", "user_id": "dana@acme.io"})
    assert seen["user_id"] == "owner@realization.co.il"
    assert (await _call(world, session, "update_setting", {"features": {"x": True}}))["code"] == "MCP_AGENT_REFUSED"


# ---------------------------------------------------------------------------
# Pilot accounts never act through an agent token
# ---------------------------------------------------------------------------


def test_pilot_accounts_cannot_have_or_use_agent_tokens(world):
    from realize_core.security.agent_tokens import AgentTokenError, create_token, resolve_token

    pilot_yaml = USERS_YAML + (
        "  - email: pia@acme.io\n    role: viewer\n    ventures: [acme]\n    pilot: true\n"
        '    password_hash: "$2b$12$pia"\n'
    )
    (world.path / "users.yaml").write_text(pilot_yaml, encoding="utf-8")
    with pytest.raises(AgentTokenError, match="Pilot accounts"):
        create_token(name="pia", user_email="pia@acme.io", ventures=["acme"])

    # A user who becomes a pilot after the token was issued: the token stops.
    _token, secret = create_token(name="vic", user_email="vic@acme.io", ventures=["acme"])
    assert resolve_token(secret) is not None
    (world.path / "users.yaml").write_text(
        pilot_yaml.replace(
            "  - email: vic@acme.io\n    role: viewer\n", "  - email: vic@acme.io\n    role: viewer\n    pilot: true\n"
        ),
        encoding="utf-8",
    )
    assert resolve_token(secret) is None


# ---------------------------------------------------------------------------
# Chat: the agent is the actor
# ---------------------------------------------------------------------------


async def test_agent_chats_and_reads_history_as_itself(world, monkeypatch):
    from realize_core import base_handler

    seen: dict = {}

    async def fake_process(**kwargs):
        seen.update(kwargs)
        return "ok"

    monkeypatch.setattr(base_handler, "process_message", fake_process)
    agent = _agent()
    await _call(world, agent, "realize_chat", {"message": "hi", "system_key": "acme", "user_id": "boss@acme.io"})
    assert seen["user_id"] == agent.user_id
    other = await _call(world, agent, "get_history", {"system_key": "acme", "user_id": "boss@acme.io"})
    assert other["code"] == "MCP_FORBIDDEN"
    own = await _call(world, agent, "get_history", {"system_key": "acme", "user_id": agent.user_id})
    assert own["user_id"] == agent.user_id


# ---------------------------------------------------------------------------
# People keep today's behaviour
# ---------------------------------------------------------------------------


async def test_people_run_and_decide_as_before(world):
    from realize_core.governance.gates import create_approval_request

    person = _person()
    out = await _call(world, person, "run_workflow", RUN)
    assert out["output"] == "Report ready"
    assert len(world.runs) == 1
    assert world.runs[0]["user_id"] == "dana@acme.io"

    approval = create_approval_request("acme", "writer", "agent_decision", {"question": "Go ahead?"})
    rows = (await _call(world, person, "list_approvals", {"venture_key": "acme"}))["approvals"]
    assert "payload" in rows[0]  # full rows, as before
    decided = await _call(world, person, "approve_request", {"approval_id": approval})
    assert decided["status"] == "approved"
    assert decided["decided_by"] == "dana@acme.io"


# ---------------------------------------------------------------------------
# End to end over Streamable HTTP with a real agent token
# ---------------------------------------------------------------------------


def _rpc(client: TestClient, secret: str, name: str, arguments: dict) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {secret}"}
    r = client.post("/mcp", headers=headers, content=json.dumps(body))
    assert r.status_code == 200, r.text
    return json.loads(r.json()["result"]["content"][0]["text"])


def test_one_agent_end_to_end_over_mcp(world, monkeypatch):
    from realize_api.main import create_app
    from realize_core.security.agent_tokens import create_token

    monkeypatch.setenv("REALIZE_API_KEY", API_KEY)
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
    from realize_core.skills import detector

    _token, secret = create_token(name="claude-acme", user_email="dana@acme.io", ventures=["acme"])
    world_skills = detector._loaded_skills

    with TestClient(create_app()) as client:
        client.app.state.systems = dict(SYSTEMS)
        client.app.state.config = {"features": {}}
        # Startup loads the ventures' skills from disk (5.30); this test's world defines its own.
        monkeypatch.setattr(detector, "_loaded_skills", world_skills)

        # Scoped reads.
        assert _rpc(client, secret, "get_system", {"system_key": "globex"})["code"] == "MCP_FORBIDDEN"
        # Held write.
        held = _rpc(client, secret, "run_workflow", RUN)
        assert held["status"] == "pending_approval"
        assert world.runs == []
        # The agent can't approve it, over MCP or REST.
        refused = _rpc(client, secret, "approve_request", {"approval_id": held["approval_id"]})
        assert refused["code"] == "MCP_AGENT_CANNOT_DECIDE"
        r = client.post(f"/api/approvals/{held['approval_id']}/approve", headers={"Authorization": f"Bearer {secret}"})
        assert r.status_code == 403
        # A person approves; it runs once, as the agent.
        r = client.post(f"/api/approvals/{held['approval_id']}/approve", headers={"X-API-Key": API_KEY})
        assert r.status_code == 200, r.text
        assert r.json()["execution"]["success"] is True
        assert [run["user_id"] for run in world.runs] == [held_by(secret)]
        status = _rpc(client, secret, "list_approvals", {"venture_key": "acme", "approval_id": held["approval_id"]})
        assert status["approvals"][0]["outcome"] == "succeeded"
        # A bad token gets no MCP at all.
        bad = {**MCP_HEADERS, "Authorization": "Bearer rzag_000000000000_" + "x" * 43}
        assert client.post("/mcp", headers=bad, content="{}").status_code == 401
        # Revocation applies to the very next request: nothing is cached.
        from realize_core.security.agent_tokens import revoke_token, token_id_of

        revoke_token(token_id_of(held_by(secret)))
        body = {"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {}}
        r = client.post("/mcp", headers={**MCP_HEADERS, "Authorization": f"Bearer {secret}"}, content=json.dumps(body))
        assert r.status_code == 401


def held_by(secret: str) -> str:
    """The principal id an agent token's requests carry."""
    return "agent:" + secret[len("rzag_") : len("rzag_") + 12]
