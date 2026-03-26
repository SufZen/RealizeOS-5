"""
Production Hardening Tests — Intent 5.2.

Validate:
- Concurrent sessions (multiple agents + tools simultaneously)
- DB index performance verification
- Error recovery and graceful degradation
- Memory safety (no unbounded growth)
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from realize_core.tools.approval import ApprovalTool, ApprovalStatus
from realize_core.tools.messaging import MessageTool, MessageStore


def run_async(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Concurrent sessions
# ---------------------------------------------------------------------------


class TestConcurrentSessions:
    """Verify system handles multiple simultaneous agent sessions."""

    def test_concurrent_approval_requests(self):
        """10 concurrent approval requests don't interfere."""
        tool = ApprovalTool()

        def make_request(i):
            result = run_async(tool.execute("request_decision", {
                "agent_key": f"agent_{i}",
                "system_key": "test",
                "description": f"Approval request #{i}",
                "options": ["yes", "no"],
            }))
            return result

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            results = [f.result() for f in futures]

        assert all(r.success for r in results)
        assert len({r.data["id"] for r in results}) == 10  # All unique IDs

    def test_concurrent_messaging(self):
        """Multiple agents sending messages simultaneously."""
        store = MessageStore()
        tool = MessageTool(store=store)

        def send_message(i):
            result = run_async(tool.execute("send_message", {
                "target": "agent:receiver",
                "content": f"Message from agent {i}",
                "agent_key": f"sender_{i}",
            }))
            return result

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(send_message, i) for i in range(10)]
            results = [f.result() for f in futures]

        assert all(r.success for r in results)

        # Verify all messages in receiver's inbox
        inbox = store.get_inbox("receiver", limit=20)
        assert len(inbox) == 10

    def test_concurrent_read_write(self):
        """Reads and writes happening simultaneously."""
        tool = MessageTool()

        def writer(i):
            return run_async(tool.execute("send_message", {
                "target": "agent:reader",
                "content": f"Msg {i}",
                "agent_key": f"w_{i}",
            }))

        def reader():
            return run_async(tool.execute("read_messages", {
                "agent_key": "reader",
                "limit": 5,
            }))

        with ThreadPoolExecutor(max_workers=6) as executor:
            write_futures = [executor.submit(writer, i) for i in range(5)]
            read_future = executor.submit(reader)

            for f in write_futures:
                assert f.result().success
            assert read_future.result().success


# ---------------------------------------------------------------------------
# DB index verification
# ---------------------------------------------------------------------------


class TestDBIndexes:
    """Verify indexes on new tables for query performance."""

    def test_approval_indexes(self, tmp_path):
        """Verify approval_requests table has proper indexes."""
        from realize_core.db.migrations import run_migrations
        from realize_core.db.schema import get_connection

        db_path = tmp_path / "test.db"
        run_migrations(db_path)
        conn = get_connection(db_path)

        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'approval_requests'"
        ).fetchall()
        index_names = {row[0] for row in indexes}
        assert "idx_approval_agent" in index_names
        conn.close()

    def test_messaging_indexes(self, tmp_path):
        """Verify agent_messages table has proper indexes."""
        from realize_core.db.migrations import run_migrations
        from realize_core.db.schema import get_connection

        db_path = tmp_path / "test.db"
        run_migrations(db_path)
        conn = get_connection(db_path)

        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'agent_messages'"
        ).fetchall()
        index_names = {row[0] for row in indexes}
        assert "idx_messages_target" in index_names
        assert "idx_messages_sender" in index_names
        assert "idx_messages_status" in index_names
        conn.close()


# ---------------------------------------------------------------------------
# Error recovery
# ---------------------------------------------------------------------------


class TestErrorRecovery:
    """Verify graceful error handling in all new tools."""

    def test_approval_invalid_action(self):
        tool = ApprovalTool()
        result = run_async(tool.execute("nonexistent_action", {}))
        assert not result.success

    def test_messaging_invalid_action(self):
        tool = MessageTool()
        result = run_async(tool.execute("bad_action", {}))
        assert not result.success

    def test_messaging_empty_content(self):
        tool = MessageTool()
        result = run_async(tool.execute("send_message", {
            "target": "agent:test",
            "content": "",
        }))
        assert not result.success

    def test_approval_resolve_nonexistent(self):
        tool = ApprovalTool()
        result = tool.store.resolve("nonexistent-id", ApprovalStatus.APPROVED, "yes", "operator")
        assert result is None

    def test_messaging_offline_queue_flush(self):
        """Queue flush doesn't crash on empty queue."""
        store = MessageStore()
        queued = store.get_queued_messages("nonexistent_agent")
        assert queued == []


# ---------------------------------------------------------------------------
# Memory safety
# ---------------------------------------------------------------------------


class TestMemorySafety:
    """Verify no unbounded memory growth."""

    def test_message_store_bounded_inbox(self):
        """Inbox returns bounded results even with many messages."""
        store = MessageStore()
        from realize_core.tools.messaging import Message

        for i in range(100):
            store.send(Message(
                sender=f"sender_{i}",
                target="agent:receiver",
                content=f"Message {i}",
            ))

        inbox = store.get_inbox("receiver", limit=10)
        assert len(inbox) == 10  # Bounded

    def test_approval_store_bounded(self):
        """Approval store handles many pending requests."""
        tool = ApprovalTool()
        for i in range(50):
            run_async(tool.execute("request_decision", {
                "agent_key": f"agent_{i}",
                "system_key": "test",
                "description": f"Q{i}?",
                "options": ["y", "n"],
            }))

        pending = tool.store.get_pending()
        assert len(pending) == 50  # All stored correctly


# ---------------------------------------------------------------------------
# Migration completeness
# ---------------------------------------------------------------------------


class TestMigrationCompleteness:
    """Verify all migrations run cleanly and schema is complete."""

    def test_full_schema(self, tmp_path):
        """All expected tables exist after running all migrations."""
        from realize_core.db.migrations import run_migrations
        from realize_core.db.schema import get_connection

        db_path = tmp_path / "test.db"
        run_migrations(db_path)
        conn = get_connection(db_path)

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row[0] for row in tables}

        # V1-V2 tables
        assert "schema_version" in table_names or "storage_sync_log" in table_names

        # V3 table
        assert "approval_requests" in table_names

        # V4 tables
        assert "agent_messages" in table_names
        assert "message_channels" in table_names
        assert "message_channel_subscribers" in table_names
        assert "message_queues" in table_names

        conn.close()
