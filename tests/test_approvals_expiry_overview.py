"""Codex audit 2026-10-13 — N11 (expired approvals), N12 (Overview agent total), role hints.

Covers:
- An expired approval is listed as ``expired`` (never as decidable ``pending``),
  in REST, MCP and the briefing query.
- A decision on an expired or already-decided item gets 409 with the reason
  and the item's real state; nothing runs. A missing item stays 404.
- Two concurrent decisions: exactly one wins, the other learns who decided.
- ``/api/dashboard`` counts configured agents, including those with no
  runtime-state row (a fresh install), and keeps the summary consistent.
- ``/api/auth/session`` reports the role's permissions so the dashboard can
  hide controls the role can't use.
"""

from __future__ import annotations

import asyncio
import textwrap

import pytest
from fastapi.testclient import TestClient
from realize_core.db.schema import init_schema, set_db_path
from realize_core.governance.gates import create_approval_request


@pytest.fixture(autouse=True)
def db(tmp_path):
    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


def _approvals_client() -> TestClient:
    from fastapi import FastAPI
    from realize_api.routes import approvals

    app = FastAPI()
    app.include_router(approvals.router, prefix="/api")
    return TestClient(app)


def _held(expires_minutes: int = 60, **kwargs) -> str:
    return create_approval_request("acme", "writer", "send_email", expires_minutes=expires_minutes, **kwargs)


# ---------------------------------------------------------------------------
# N11 — expiry in the list
# ---------------------------------------------------------------------------


class TestExpiredInList:
    def test_expired_item_is_not_pending(self):
        live, lapsed = _held(), _held(expires_minutes=-1)
        client = _approvals_client()

        pending = client.get("/api/approvals?status=pending").json()["approvals"]
        assert [a["id"] for a in pending] == [live]
        assert pending[0]["status"] == "pending"
        assert pending[0]["expired"] is False

        expired = client.get("/api/approvals?status=expired").json()["approvals"]
        assert [a["id"] for a in expired] == [lapsed]
        assert expired[0]["status"] == "expired"
        assert expired[0]["expired"] is True

    def test_all_statuses_report_effective_status(self):
        live, lapsed = _held(), _held(expires_minutes=-1)
        rows = {a["id"]: a for a in _approvals_client().get("/api/approvals?status=").json()["approvals"]}
        assert rows[live]["status"] == "pending"
        assert rows[lapsed]["status"] == "expired"
        assert rows[lapsed]["expired"] is True

    def test_default_list_is_pending_only(self):
        _held(expires_minutes=-1)
        assert _approvals_client().get("/api/approvals").json()["approvals"] == []

    def test_briefing_query_skips_expired(self):
        from realize_core.governance.gates import get_pending_approvals

        live = _held()
        _held(expires_minutes=-1)
        assert [p["id"] for p in get_pending_approvals()] == [live]
        assert [p["id"] for p in get_pending_approvals("acme")] == [live]
        assert get_pending_approvals("globex") == []

    def test_mcp_list_matches_rest(self):
        from realize_api.dependencies import CurrentUser
        from realize_core.mcp_server.tools.ops_tools import list_approvals

        live, lapsed = _held(), _held(expires_minutes=-1)
        user = CurrentUser(user_id="owner", role="owner")
        pending = asyncio.run(list_approvals({}, None, user))["approvals"]
        assert [a["id"] for a in pending] == [live]
        one = asyncio.run(list_approvals({"approval_id": lapsed}, None, user))["approvals"]
        assert one[0]["status"] == "expired"
        assert one[0]["expired"] is True


# ---------------------------------------------------------------------------
# N11 — refused decisions explain themselves
# ---------------------------------------------------------------------------


class TestRefusedDecisions:
    def test_expired_decision_is_409_with_reason(self):
        lapsed = _held(expires_minutes=-1, action_name="send_email", params={"to": "x@y.z"})
        client = _approvals_client()
        for verb in ("approve", "reject"):
            resp = client.post(f"/api/approvals/{lapsed}/{verb}", json={})
            assert resp.status_code == 409
            body = resp.json()
            assert body["reason"] == "expired"
            assert "expired" in body["detail"]
            assert body["approval"]["status"] == "expired"
            assert body["approval"]["executed_at"] is None  # nothing ran

    def test_already_decided_names_the_decider(self):
        from realize_core.governance.gates import approve_request

        aid = _held()
        approve_request(aid, decided_by="dana@acme.io", channel="dashboard")
        resp = _approvals_client().post(f"/api/approvals/{aid}/reject", json={})
        assert resp.status_code == 409
        body = resp.json()
        assert body["reason"] == "already_decided"
        assert "dana@acme.io" in body["detail"]
        assert body["approval"]["status"] == "approved"
        assert body["approval"]["decided_by"] == "dana@acme.io"

    def test_missing_item_stays_404(self):
        resp = _approvals_client().post("/api/approvals/nope/approve", json={})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Approval not found or not pending"

    def test_concurrent_decisions_one_wins(self):
        """Two people decide at once: one decision lands, the other is told."""
        from realize_core.governance.gates import decide_approval

        aid = _held()

        async def both():
            return await asyncio.gather(
                decide_approval(aid, approve=True, decided_by="a@x", channel="dashboard"),
                decide_approval(aid, approve=False, decided_by="b@x", channel="dashboard"),
            )

        results = asyncio.run(both())
        assert sum(r is not None for r in results) == 1
        winner = next(r for r in results if r is not None)["approval"]
        resp = _approvals_client().post(f"/api/approvals/{aid}/approve", json={})
        assert resp.status_code == 409
        assert resp.json()["approval"]["status"] == winner["status"]
        assert resp.json()["approval"]["decided_by"] == winner["decided_by"]


class TestApprovalStatusHelpers:
    def test_effective_status_never_changes_the_row(self):
        from realize_core.governance.approval_status import with_effective_status

        row = {"id": "a", "status": "pending", "expires_at": "2000-01-01T00:00:00.000000Z"}
        view = with_effective_status(row, "2026-01-01T00:00:00.000000Z")
        assert view["status"] == "expired"
        assert view["expired"] is True
        assert row["status"] == "pending"
        assert with_effective_status({"status": "pending", "expires_at": None}, "z")["expired"] is False
        assert with_effective_status({"status": "approved", "expires_at": "0"}, "z")["status"] == "approved"


# ---------------------------------------------------------------------------
# N12 — Overview agent total
# ---------------------------------------------------------------------------


SYSTEMS = {
    "acme": {"name": "Acme", "agents": {"writer": "a.md", "analyst": "b.md"}},
    "globex": {"name": "Globex", "agents": {"cfo": "c.md", "ops": "d.md"}},
}


def _dashboard_client(tmp_path) -> TestClient:
    from fastapi import FastAPI
    from realize_api.routes import dashboard

    app = FastAPI()
    app.include_router(dashboard.router, prefix="/api")
    app.state.systems = dict(SYSTEMS)
    app.state.kb_path = tmp_path
    app.state.config = {"features": {}}
    return TestClient(app)


def _set_state(venture: str, agent: str, status: str) -> None:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO agent_states (agent_key, venture_key, status) VALUES (?, ?, ?)",
            (agent, venture, status),
        )
        conn.commit()
    finally:
        conn.close()


class TestOverviewAgentTotal:
    def test_fresh_install_counts_configured_agents(self, tmp_path):
        data = _dashboard_client(tmp_path).get("/api/dashboard").json()
        assert data["venture_count"] == 2
        assert data["agent_total"] == 4
        assert data["agent_total"] == sum(v["agent_count"] for v in data["ventures"])
        # Agents with no runtime row have never run: idle, not missing.
        assert data["agent_summary"] == {"idle": 4, "running": 0, "paused": 0, "error": 0}

    def test_runtime_states_stay_consistent_with_the_total(self, tmp_path):
        _set_state("acme", "writer", "running")
        _set_state("globex", "cfo", "error")
        _set_state("acme", "retired-agent", "running")  # no longer configured
        data = _dashboard_client(tmp_path).get("/api/dashboard").json()
        assert data["agent_total"] == 4
        assert data["agent_summary"] == {"idle": 2, "running": 1, "paused": 0, "error": 1}
        assert sum(data["agent_summary"].values()) == data["agent_total"]


# ---------------------------------------------------------------------------
# Role hints for the dashboard
# ---------------------------------------------------------------------------


USERS_YAML = textwrap.dedent(
    """
    users:
      - email: owner@acme.io
        role: owner
        password_hash: "$2b$12$owner"
      - email: vic@acme.io
        role: viewer
        ventures: [acme]
        password_hash: "$2b$12$vic"
    """
)


class TestRolePermissions:
    def test_role_permissions(self):
        from realize_core.security.venture_scope import has_permission, role_permissions

        assert role_permissions("viewer") == ["agents:read", "system:read"]
        assert "pipeline:approve" in role_permissions("operator")
        assert "system:manage" not in role_permissions("operator")
        assert role_permissions("nobody") == []
        assert role_permissions(None) == []
        for role in ("owner", "admin", "operator", "user", "viewer", "guest"):
            for permission in ("pipeline:approve", "system:write", "system:manage", "system:delete"):
                assert (permission in role_permissions(role)) == has_permission(role, permission)

    @pytest.mark.parametrize(
        ("email", "can_approve"),
        [("owner@acme.io", True), ("vic@acme.io", False)],
    )
    def test_session_reports_permissions(self, tmp_path, monkeypatch, email, can_approve):
        from realize_api.main import create_app
        from realize_core.security import session_store

        monkeypatch.chdir(tmp_path)
        (tmp_path / "users.yaml").write_text(USERS_YAML, encoding="utf-8")
        record = session_store.SessionRecord(
            session_id="s1",
            user_id=email,
            role="owner",  # the role at sign-in; users.yaml decides now
            csrf_token="c",
            created_at="",
            last_seen_at="",
            expires_at="",
            ip_address="",
            user_agent="",
            remember_me=False,
        )
        monkeypatch.setattr(session_store, "get_session", lambda _sid: record)
        client = TestClient(create_app())
        client.cookies.set(session_store.SESSION_COOKIE_NAME, "s1")
        body = client.get("/api/auth/session").json()
        assert ("pipeline:approve" in body["permissions"]) is can_approve
