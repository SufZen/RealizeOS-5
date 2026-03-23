"""Tests for Sprint 8 — governance gates, approval queue API.

Covers:
- Gate detection (is_gated)
- Approval request creation
- Approve/reject flow
- Pending approval queries
- API endpoints for approvals
"""

import pytest
from realize_core.activity.bus import _recent_events, _subscribers
from realize_core.db.schema import init_schema, set_db_path
from realize_core.governance.gates import (
    approve_request,
    create_approval_request,
    get_pending_approvals,
    is_gated,
    reject_request,
)


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    db_path = tmp_path / "test_gov.db"
    set_db_path(db_path)
    init_schema(db_path)
    _subscribers.clear()
    _recent_events.clear()
    yield db_path
    _subscribers.clear()
    _recent_events.clear()
    set_db_path(None)


# ---------------------------------------------------------------------------
# Gate detection
# ---------------------------------------------------------------------------


class TestGateDetection:
    def test_gated_when_enabled(self):
        features = {"approval_gates": True, "governance": {"gates": {"send_email": True}}}
        assert is_gated("send_email", features) is True

    def test_not_gated_when_disabled(self):
        features = {"approval_gates": True, "governance": {"gates": {"send_email": False}}}
        assert is_gated("send_email", features) is False

    def test_not_gated_when_feature_off(self):
        features = {"approval_gates": False}
        assert is_gated("send_email", features) is False

    def test_not_gated_for_unknown_action(self):
        features = {"approval_gates": True}
        assert is_gated("unknown_action", features) is False

    def test_mapped_actions(self):
        features = {"approval_gates": True, "governance": {"gates": {"send_email": True}}}
        assert is_gated("send_gmail", features) is True
        assert is_gated("create_draft", features) is True


# ---------------------------------------------------------------------------
# Approval lifecycle
# ---------------------------------------------------------------------------


class TestApprovalLifecycle:
    def test_create_approval(self, setup_db):
        aid = create_approval_request("v1", "writer", "send_email", {"to": "test@example.com"}, db_path=setup_db)
        assert aid is not None

        pending = get_pending_approvals(db_path=setup_db)
        assert len(pending) == 1
        assert pending[0]["id"] == aid
        assert pending[0]["status"] == "pending"

    def test_approve(self, setup_db):
        aid = create_approval_request("v1", "writer", "send_email", db_path=setup_db)
        result = approve_request(aid, decision_note="Looks good", db_path=setup_db)
        assert result is not None
        assert result["status"] == "approved"
        assert result["decision_note"] == "Looks good"

        pending = get_pending_approvals(db_path=setup_db)
        assert len(pending) == 0

    def test_reject(self, setup_db):
        aid = create_approval_request("v1", "writer", "publish_content", db_path=setup_db)
        result = reject_request(aid, decision_note="Not ready", db_path=setup_db)
        assert result is not None
        assert result["status"] == "rejected"

    def test_approve_nonexistent(self, setup_db):
        result = approve_request("fake-id", db_path=setup_db)
        assert result is None

    def test_double_approve_fails(self, setup_db):
        aid = create_approval_request("v1", "writer", "send_email", db_path=setup_db)
        approve_request(aid, db_path=setup_db)
        result = approve_request(aid, db_path=setup_db)
        assert result is None

    def test_filter_by_venture(self, setup_db):
        create_approval_request("v1", "writer", "send_email", db_path=setup_db)
        create_approval_request("v2", "analyst", "publish_content", db_path=setup_db)

        v1 = get_pending_approvals(venture_key="v1", db_path=setup_db)
        assert len(v1) == 1
        assert v1[0]["venture_key"] == "v1"


# ---------------------------------------------------------------------------
# Approval API
# ---------------------------------------------------------------------------


class TestApprovalAPI:
    @pytest.fixture
    def client(self, setup_db):
        try:
            from fastapi import FastAPI
        except ImportError:
            pytest.skip("FastAPI not installed")

        from fastapi.testclient import TestClient
        from realize_api.routes import approvals

        app = FastAPI()
        app.include_router(approvals.router, prefix="/api")
        return TestClient(app)

    def test_list_pending(self, client, setup_db):
        create_approval_request("v1", "writer", "send_email", db_path=setup_db)
        res = client.get("/api/approvals")
        assert res.status_code == 200
        assert len(res.json()["approvals"]) == 1

    def test_approve_via_api(self, client, setup_db):
        aid = create_approval_request("v1", "writer", "send_email", db_path=setup_db)
        res = client.post(f"/api/approvals/{aid}/approve", json={"decision_note": "OK"})
        assert res.status_code == 200
        assert res.json()["status"] == "approved"

    def test_reject_via_api(self, client, setup_db):
        aid = create_approval_request("v1", "writer", "publish_content", db_path=setup_db)
        res = client.post(f"/api/approvals/{aid}/reject", json={"decision_note": "Not yet"})
        assert res.status_code == 200
        assert res.json()["status"] == "rejected"

    def test_approve_not_found(self, client):
        res = client.post("/api/approvals/fake-id/approve")
        assert res.status_code == 404

    def test_filter_by_venture(self, client, setup_db):
        create_approval_request("v1", "w", "send_email", db_path=setup_db)
        create_approval_request("v2", "a", "publish_content", db_path=setup_db)

        res = client.get("/api/approvals?venture_key=v1")
        assert len(res.json()["approvals"]) == 1
