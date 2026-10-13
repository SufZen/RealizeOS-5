"""Audit N01: only a global pack maintainer decides a shared pack's verification.

A ``pack_verify`` approval sits in one venture's queue, but what it changes is
shared by every venture using the pack. A venture-scoped operator who can see
the row used to be able to approve it. Now every entry point (REST, MCP and a
direct ``decide_approval`` call) needs an owner with access to every venture,
and a refused attempt leaves the item pending and the pack unchanged.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from realize_api.dependencies import CurrentUser
from realize_core.governance.gates import (
    ApprovalForbiddenError,
    Decider,
    approve_request,
    create_approval_request,
    decide_approval,
    reject_request,
)
from realize_core.packs import load_pack, state
from realize_core.packs.verify import request_verification

PACKS = Path(__file__).parent.parent / "packs"

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
      - email: adam@realization.co.il
        role: admin
        password_hash: "$2b$12$adam"
      - email: olga@acme.io
        role: owner
        ventures: [acme]
        password_hash: "$2b$12$olga"
    """
)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """users.yaml, an operational DB and a copy of the Portugal pack as the shipped packs."""
    from realize_core.db.schema import init_schema, set_db_path
    from realize_core.packs import loader

    monkeypatch.chdir(tmp_path)
    (tmp_path / "users.yaml").write_text(USERS_YAML, encoding="utf-8")
    db = tmp_path / "realize_data.db"
    set_db_path(db)
    init_schema(db)
    root = tmp_path / "packs"
    shutil.copytree(PACKS / "market" / "pt", root / "market" / "pt", ignore=shutil.ignore_patterns("reviews"))
    monkeypatch.setattr(loader, "default_packs_root", lambda: root)
    yield root
    set_db_path(None)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _row(approval_id: str) -> dict:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        return dict(conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone())
    finally:
        conn.close()


def _queue(level: int = 2) -> str:
    return request_verification("acme", kind="market", pack_id="pt", level=level, reviewer="Ana Silva, advogada")


def _client(user_id: str, role: str, scopes: list[str] | None = None) -> TestClient:
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = {"acme": {"name": "Acme"}, "globex": {"name": "Globex"}}
    app.state.config = {"features": {}}

    @app.middleware("http")
    async def as_principal(request, call_next):
        request.state.user_id = user_id
        request.state.role = role
        request.state.scopes = scopes or []
        return await call_next(request)

    return TestClient(app)


def _unchanged(setup: Path, before: dict[str, bytes], approval_id: str) -> None:
    assert _row(approval_id)["status"] == "pending"
    assert _snapshot(setup) == before
    assert not state.state_path().exists()
    assert load_pack(setup / "market" / "pt").verification_level == 1


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_scoped_operator_gets_403_and_nothing_changes(setup, action):
    before = _snapshot(setup)
    approval_id = _queue()
    client = _client("dana@acme.io", "operator")
    assert client.get("/api/approvals").json()["approvals"][0]["id"] == approval_id  # the row is visible

    resp = client.post(f"/api/approvals/{approval_id}/{action}", json={})

    assert resp.status_code == 403
    assert "only an owner with access to every venture" in resp.json()["detail"]
    _unchanged(setup, before, approval_id)


@pytest.mark.parametrize(
    ("user", "role"),
    [("adam@realization.co.il", "admin"), ("olga@acme.io", "owner")],
    ids=["unrestricted-admin", "venture-scoped-owner"],
)
def test_admin_and_scoped_owner_are_not_pack_maintainers(setup, user, role):
    before = _snapshot(setup)
    approval_id = _queue()
    assert _client(user, role).post(f"/api/approvals/{approval_id}/approve", json={}).status_code == 403
    _unchanged(setup, before, approval_id)


def test_token_narrowed_to_one_venture_is_not_a_pack_maintainer(setup):
    approval_id = _queue()
    client = _client("owner@realization.co.il", "owner", scopes=["venture:acme"])
    assert client.post(f"/api/approvals/{approval_id}/approve", json={}).status_code == 403
    assert _row(approval_id)["status"] == "pending"


def test_owner_approves_and_the_outcome_is_stored(setup):
    before = _snapshot(setup)
    approval_id = _queue()

    resp = _client("owner@realization.co.il", "owner").post(f"/api/approvals/{approval_id}/approve", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["execution"]["executed"] is True
    assert body["execution"]["success"] is True
    assert body["execution"]["error"] is None
    assert set(body["execution"]) == {"executed", "success", "output", "error"}
    # The response row carries the stored outcome, like the queue does afterwards.
    assert body["execution_status"] == "succeeded"
    row = _row(approval_id)
    assert row["execution_status"] == "succeeded"
    assert row["executed_at"]
    assert json.loads(row["result_json"]) == {"output": body["execution"]["output"]}
    assert row["error"] is None
    pack = load_pack(setup / "market" / "pt")
    assert pack.verification_level == 2
    assert pack.verification["approved_by"] == "owner@realization.co.il"
    assert pack.verification["approval_id"] == approval_id
    assert _snapshot(setup) == before  # pack files untouched


def test_owner_rejects(setup):
    before = _snapshot(setup)
    approval_id = _queue()
    resp = _client("owner@realization.co.il", "owner").post(f"/api/approvals/{approval_id}/reject", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["execution"] is None
    assert _snapshot(setup) == before
    assert not state.state_path().exists()


def test_local_dev_mode_is_the_owner(setup):
    """With auth off there is no principal; the local operator is the owner, as everywhere in the API."""
    from realize_api.main import create_app

    approval_id = _queue()
    app = create_app()
    app.state.systems = {"acme": {"name": "Acme"}}
    app.state.config = {"features": {}}
    resp = TestClient(app).post(f"/api/approvals/{approval_id}/approve", json={})
    assert resp.status_code == 200
    assert resp.json()["execution"]["success"] is True


def test_scoped_operator_still_decides_venture_items(setup):
    """Only global items need a maintainer; the operator's own venture queue works as before."""
    approval_id = create_approval_request("acme", "writer", "agent_decision", {"summary": "Go ahead?"})
    resp = _client("dana@acme.io", "operator").post(f"/api/approvals/{approval_id}/approve", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", ["approve_request", "reject_request"])
def test_mcp_scoped_operator_gets_forbidden(setup, tool):
    from realize_core.mcp_server.tools import ops_tools

    before = _snapshot(setup)
    approval_id = _queue()
    handler = getattr(ops_tools, tool)
    out = asyncio.run(handler({"approval_id": approval_id}, None, CurrentUser("dana@acme.io", "operator", [])))
    assert out["code"] == "MCP_FORBIDDEN"
    assert "only an owner" in out["error"]
    _unchanged(setup, before, approval_id)


def test_mcp_owner_approves(setup):
    from realize_core.mcp_server.tools import ops_tools

    approval_id = _queue()
    owner = CurrentUser("owner@realization.co.il", "owner", [])
    out = asyncio.run(ops_tools.approve_request({"approval_id": approval_id}, None, owner))
    assert out["status"] == "approved"
    assert out["executed"] is True
    assert out["success"] is True
    assert _row(approval_id)["decision_channel"] == "mcp"
    assert load_pack(setup / "market" / "pt").verification_level == 2


def test_mcp_dispatcher_refuses_an_outside_agent_before_the_handler(setup, monkeypatch):
    """Outside agents never decide; the dispatcher refuses them (STORY-37) and the gate would too."""
    from realize_core.security.agent_access import CODE_PEOPLE_DECIDE, tool_refusal

    assert tool_refusal("approve_request")[0] == CODE_PEOPLE_DECIDE
    approval_id = _queue()
    agent = Decider(user_id="agent:tok1", role="owner", allowed_ventures=None, is_agent=True)
    with pytest.raises(ApprovalForbiddenError, match="outside agent"):
        asyncio.run(decide_approval(approval_id, True, decider=agent))
    assert _row(approval_id)["status"] == "pending"


# ---------------------------------------------------------------------------
# Direct callers
# ---------------------------------------------------------------------------


def test_decide_approval_without_a_decider_fails_closed(setup):
    before = _snapshot(setup)
    approval_id = _queue()
    with pytest.raises(ApprovalForbiddenError):
        asyncio.run(decide_approval(approval_id, True, decided_by="someone"))
    with pytest.raises(ApprovalForbiddenError):
        asyncio.run(decide_approval(approval_id, False, decided_by="someone"))
    _unchanged(setup, before, approval_id)


def test_low_level_approve_and_reject_cannot_decide_a_global_item(setup):
    approval_id = _queue()
    assert approve_request(approval_id, decided_by="owner") is None
    assert reject_request(approval_id, decided_by="owner") is None
    assert _row(approval_id)["status"] == "pending"


def test_decider_properties():
    assert Decider("o", "owner", None).is_global_maintainer
    assert Decider("o", "OWNER", None).is_global_maintainer
    assert not Decider("o", "owner", frozenset({"acme"})).is_global_maintainer
    assert not Decider("o", "owner", frozenset()).is_global_maintainer
    assert not Decider("o", "admin", None).is_global_maintainer
    assert not Decider("o", "operator", None).is_global_maintainer
    assert not Decider("agent:x", "owner", None, is_agent=True).is_global_maintainer
    assert not Decider("o", None, None).is_global_maintainer
