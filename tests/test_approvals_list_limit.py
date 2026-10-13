"""The approvals list is bounded, and the Decided tab gets what was decided most recently.

``GET /api/approvals`` used to return the whole queue for ``?status=`` (the
Decided tab), oldest decisions mixed in by creation time. Now every list is
capped by ``limit`` (default 50, at most 500) and ``?status=decided`` lists
approved, rejected and answered items, most recently decided first. The old
filters answer as before.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from realize_core.db.schema import get_connection, init_schema, set_db_path
from realize_core.governance.gates import create_approval_request


@pytest.fixture(autouse=True)
def db(tmp_path):
    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


def _client() -> TestClient:
    from fastapi import FastAPI
    from realize_api.routes import approvals

    app = FastAPI()
    app.include_router(approvals.router, prefix="/api")
    return TestClient(app)


def _held(**kwargs) -> str:
    return create_approval_request("acme", "writer", "send_email", expires_minutes=60, **kwargs)


def _settle(approval_id: str, status: str, decided_at: str, created_at: str) -> None:
    """Store a decision directly, with chosen stamps (decision order differs from creation order)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE approval_queue SET status = ?, decided_at = ?, created_at = ?, decided_by = 'dana' WHERE id = ?",
            (status, decided_at, created_at, approval_id),
        )
        conn.commit()
    finally:
        conn.close()


def _ids(resp) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [a["id"] for a in resp.json()["approvals"]]


class TestDecided:
    def test_decided_lists_settled_items_most_recently_decided_first(self):
        old_request, new_request, answered, still_held = _held(), _held(), _held(), _held()
        # Created first but decided last, and the other way round.
        _settle(old_request, "approved", "2026-10-13T12:00:00.000000Z", "2026-10-01T09:00:00.000000Z")
        _settle(new_request, "rejected", "2026-10-11T12:00:00.000000Z", "2026-10-10T09:00:00.000000Z")
        _settle(answered, "answered", "2026-10-12T12:00:00.000000Z", "2026-10-05T09:00:00.000000Z")

        ids = _ids(_client().get("/api/approvals?status=decided&limit=50"))

        assert ids == [old_request, answered, new_request]
        assert still_held not in ids

    def test_one_decided_status_also_comes_by_decision_time(self):
        first, second = _held(), _held()
        _settle(first, "approved", "2026-10-13T12:00:00.000000Z", "2026-10-01T09:00:00.000000Z")
        _settle(second, "approved", "2026-10-12T12:00:00.000000Z", "2026-10-10T09:00:00.000000Z")

        assert _ids(_client().get("/api/approvals?status=approved")) == [first, second]

    def test_decided_is_capped_by_limit(self):
        ids = [_held() for _ in range(5)]
        for i, approval_id in enumerate(ids):
            _settle(approval_id, "approved", f"2026-10-1{i}T12:00:00.000000Z", "2026-10-01T09:00:00.000000Z")

        listed = _ids(_client().get("/api/approvals?status=decided&limit=2"))

        assert listed == [ids[4], ids[3]]


class TestLimit:
    def test_default_limit_is_50(self):
        for _ in range(55):
            _held()
        assert len(_ids(_client().get("/api/approvals?status=pending"))) == 50

    def test_limit_caps_and_keeps_newest_first(self):
        first, second, third = _held(), _held(), _held()
        conn = get_connection()
        try:
            for approval_id, stamp in ((first, "01"), (second, "02"), (third, "03")):
                conn.execute(
                    "UPDATE approval_queue SET created_at = ? WHERE id = ?",
                    (f"2026-10-{stamp}T09:00:00.000000Z", approval_id),
                )
            conn.commit()
        finally:
            conn.close()

        assert _ids(_client().get("/api/approvals?status=pending&limit=2")) == [third, second]

    @pytest.mark.parametrize("limit", [0, -1, 501])
    def test_limit_outside_1_to_500_is_refused(self, limit):
        assert _client().get(f"/api/approvals?limit={limit}").status_code == 422

    def test_500_is_allowed(self):
        _held()
        assert len(_ids(_client().get("/api/approvals?limit=500"))) == 1


class TestUnchangedContract:
    def test_empty_status_still_lists_everything(self):
        held, settled = _held(), _held()
        _settle(settled, "rejected", "2026-10-13T12:00:00.000000Z", "2026-10-01T09:00:00.000000Z")

        assert set(_ids(_client().get("/api/approvals?status="))) == {held, settled}

    def test_default_is_still_pending_only(self):
        held, settled = _held(), _held()
        _settle(settled, "approved", "2026-10-13T12:00:00.000000Z", "2026-10-01T09:00:00.000000Z")

        assert _ids(_client().get("/api/approvals")) == [held]
