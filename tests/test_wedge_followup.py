"""Wedge funnel conversion and contact queue (audit N09, N10)."""

from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace

import pytest
from realize_core.wedge import store as wedge_store
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


def _run(user: str, market: str = "pt") -> str:
    return wedge_store.record_run(user, market=market, verification=1, items=3, without_locator=0)


# ---------------------------------------------------------------- N09: conversion counts people


def test_repeat_requests_count_one_converted_user(db):
    first, second = _run("u1"), _run("u1")
    wedge_store.request_call(first, "u1", "a@example.com")
    wedge_store.request_call(second, "u1", "a@example.com")
    row = wedge_store.funnel()[0]
    assert row["users"] == 1
    assert row["converted_users"] == 1
    assert row["calls_requested"] == 2  # volume, not conversion
    assert row["call_rate"] == 1.0  # never above 100%


@pytest.mark.parametrize(
    ("converted", "users", "abroad", "passed"),
    [
        (3, 10, True, True),  # exactly 30%
        (2, 10, True, False),  # 20%
        (3, 10, False, False),  # 30%, but nobody outside Israel
    ],
)
def test_pass_signal_threshold(db, converted, users, abroad, passed):
    for i in range(users):
        market = "pt" if (abroad and i == 0) else "il"
        run = _run(f"u{i}", market)
        if i < converted:
            wedge_store.request_call(run, f"u{i}", f"u{i}@example.com")
    summary = wedge_store.funnel_summary()
    assert summary["users"] == users
    assert summary["converted_users"] == converted
    assert summary["passed"] is passed


def test_person_in_two_markets_counts_once_overall(db):
    a, b = _run("u1", "pt"), _run("u1", "es")
    _run("u2", "il")
    wedge_store.request_call(a, "u1", "x@example.com")
    wedge_store.request_call(b, "u1", "x@example.com")
    summary = wedge_store.funnel_summary()
    assert summary["users"] == 2
    assert summary["converted_users"] == 1
    assert summary["converted_outside_home"] == 1


def test_empty_funnel_never_passes(db):
    assert wedge_store.funnel_summary()["passed"] is False


# ---------------------------------------------------------------- N10: contact queue


def test_contact_queue_one_row_per_person_until_handled(db):
    a, b = _run("u1", "pt"), _run("u1", "es")
    c = _run("u2", "pt")
    _run("u3", "pt")  # never asked
    wedge_store.request_call(a, "u1", "old@example.com")
    wedge_store.request_call(b, "u1", "new@example.com")
    wedge_store.request_call(c, "u2", "+351 900")

    queue = {r["user_id"]: r for r in wedge_store.contacts()}
    assert set(queue) == {"u1", "u2"}
    assert queue["u1"]["contact"] == "new@example.com"
    assert queue["u1"]["markets"] == ["es", "pt"]
    assert queue["u1"]["requests"] == 2
    assert queue["u1"]["handled_at"] is None

    assert wedge_store.mark_contacted("u1", "owner") == 2
    assert wedge_store.mark_contacted("u1", "owner") == 0  # nothing left to handle
    assert [r["user_id"] for r in wedge_store.contacts()] == ["u2"]
    handled = {r["user_id"]: r for r in wedge_store.contacts(include_handled=True)}
    assert handled["u1"]["handled_by"] == "owner"


def test_asking_again_puts_a_handled_person_back(db):
    run = _run("u1")
    wedge_store.request_call(run, "u1", "a@example.com")
    wedge_store.mark_contacted("u1", "owner")
    assert wedge_store.contacts() == []
    wedge_store.request_call(_run("u1"), "u1", "a@example.com")
    assert [r["user_id"] for r in wedge_store.contacts()] == ["u1"]
    assert wedge_store.funnel()[0]["converted_users"] == 1


def test_old_table_gets_follow_up_columns(tmp_path):
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.execute(
        """CREATE TABLE wedge_runs (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, market TEXT NOT NULL,
           verification INTEGER NOT NULL, items INTEGER NOT NULL, without_locator INTEGER NOT NULL,
           call_requested INTEGER NOT NULL DEFAULT 0, contact TEXT, opt_in INTEGER NOT NULL DEFAULT 0,
           created_at TEXT NOT NULL)"""
    )
    wedge_store.ensure_schema(conn)
    wedge_store.ensure_schema(conn)  # idempotent
    cols = {r[1] for r in conn.execute("PRAGMA table_info(wedge_runs)")}
    assert set(wedge_store.FOLLOW_UP_COLUMNS) <= cols
    conn.close()


def test_mcp_call_request_says_what_happened_and_notes_activity(db, monkeypatch):
    from realize_core.mcp_server.tools import wedge_tools

    events = []
    monkeypatch.setattr("realize_core.activity.logger.log_event", lambda **kw: events.append(kw))
    state = SimpleNamespace(config={"features": {"wedge": True}, "wedge": {"booking_url": "https://example.com/b"}})
    user = SimpleNamespace(user_id="guest-1")
    run = _run("guest-1")
    out = asyncio.run(wedge_tools.request_audit_call({"run_id": run, "contact": "g@example.com"}, state, user))
    assert out["status"] == "recorded"
    assert "contact queue" in out["message"]
    assert "will contact you" not in out["message"]
    assert out["booking_url"] == "https://example.com/b"
    assert events[0]["action"] == "wedge_call_requested"
    assert "g@example.com" not in str(events[0])  # the contact stays in the queue, not the feed
    assert [r["user_id"] for r in wedge_store.contacts()] == ["guest-1"]


# ---------------------------------------------------------------- CLI


def _app():
    from realize_core.cli_app import app

    return app


def test_cli_funnel_contacts_contacted(db):
    run = _run("u1", "pt")
    _run("u2", "il")
    wedge_store.request_call(run, "u1", "a@example.com")

    funnel_out = runner.invoke(_app(), ["wedge", "funnel"])
    assert funnel_out.exit_code == 0, funnel_out.output
    assert "1 of 2 users asked for a call (50%); 1 outside Israel. PASS" in funnel_out.output

    listed = runner.invoke(_app(), ["wedge", "contacts"])
    assert listed.exit_code == 0
    assert "u1" in listed.output
    assert "a@example.com" in listed.output
    assert "[waiting]" in listed.output

    done = runner.invoke(_app(), ["wedge", "contacted", "U1", "--by", "dana"])
    assert done.exit_code == 0, done.output
    assert "Nobody is waiting" in runner.invoke(_app(), ["wedge", "contacts"]).output
    again = runner.invoke(_app(), ["wedge", "contacted", "u1"])
    assert again.exit_code == 1
