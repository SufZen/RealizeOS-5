"""
Tests for Agent-to-Agent Messaging Bus — Intent 4.1.

Covers:
- Message model (creation, serialization, target parsing)
- MessageStore (send, inbox, queuing, channels, conversations)
- MessageTool (send_message, read_messages, list_conversations, create_channel)
- Offline delivery queue
- Migration v4
"""

from __future__ import annotations

import asyncio

import pytest

from realize_core.tools.messaging import (
    Channel,
    Message,
    MessageStatus,
    MessageStore,
    MessageTarget,
    MessageTool,
    get_tool,
)
from realize_core.tools.base_tool import ToolCategory


def run_async(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Message model
# ---------------------------------------------------------------------------


class TestMessage:
    def test_create(self):
        msg = Message(sender="writer", target="agent:analyst", content="Status update")
        assert msg.sender == "writer"
        assert msg.target_type == MessageTarget.AGENT
        assert msg.target_id == "analyst"
        assert msg.status == MessageStatus.SENT

    def test_human_target(self):
        msg = Message(sender="writer", target="human:default", content="Need input")
        assert msg.target_type == MessageTarget.HUMAN
        assert msg.target_id == "default"

    def test_channel_target(self):
        msg = Message(sender="writer", target="channel:team-updates", content="Hello")
        assert msg.target_type == MessageTarget.CHANNEL
        assert msg.target_id == "team-updates"

    def test_bare_target(self):
        msg = Message(sender="writer", target="analyst", content="Direct")
        assert msg.target_type == MessageTarget.AGENT
        assert msg.target_id == "analyst"

    def test_serialization_roundtrip(self):
        msg = Message(sender="writer", target="agent:analyst", content="Status")
        d = msg.to_dict()
        restored = Message.from_dict(d)
        assert restored.id == msg.id
        assert restored.sender == msg.sender
        assert restored.target == msg.target
        assert restored.content == msg.content


# ---------------------------------------------------------------------------
# MessageStore
# ---------------------------------------------------------------------------


class TestMessageStore:
    @pytest.fixture
    def store(self):
        return MessageStore()

    def test_send_to_agent(self, store):
        msg = Message(sender="writer", target="agent:analyst", content="Review this")
        result = store.send(msg)
        assert result.status == MessageStatus.QUEUED

    def test_send_to_human(self, store):
        msg = Message(sender="writer", target="human:default", content="Need approval")
        result = store.send(msg)
        assert result.status == MessageStatus.DELIVERED

    def test_inbox(self, store):
        store.send(Message(sender="writer", target="agent:analyst", content="msg1"))
        store.send(Message(sender="dev", target="agent:analyst", content="msg2"))
        store.send(Message(sender="writer", target="agent:dev", content="wrong target"))

        inbox = store.get_inbox("analyst")
        assert len(inbox) == 2
        assert all(m.target_id == "analyst" for m in inbox)

    def test_mark_read(self, store):
        msg = Message(sender="writer", target="agent:analyst", content="Read me")
        store.send(msg)
        inbox = store.get_inbox("analyst")
        assert len(inbox) == 1
        assert store.mark_read(inbox[0].id) is True
        assert inbox[0].status == MessageStatus.READ

    def test_unread_only(self, store):
        msg1 = Message(sender="writer", target="agent:analyst", content="Msg 1")
        msg2 = Message(sender="dev", target="agent:analyst", content="Msg 2")
        store.send(msg1)
        store.send(msg2)
        store.mark_read(msg1.id)
        unread = store.get_inbox("analyst", unread_only=True)
        assert len(unread) == 1
        assert unread[0].sender == "dev"

    def test_offline_queue(self, store):
        msg = Message(sender="writer", target="agent:analyst", content="Offline msg")
        store.send(msg)
        queued = store.get_queued_messages("analyst")
        assert len(queued) == 1
        assert queued[0].status == MessageStatus.DELIVERED
        assert queued[0].delivered_at is not None
        # Queue should be empty after flush
        assert len(store.get_queued_messages("analyst")) == 0

    def test_channel_creation(self, store):
        channel = store.create_channel("team-updates", "agency", "writer")
        assert channel.name == "team-updates"
        assert "writer" in channel.subscribers

    def test_channel_idempotent(self, store):
        ch1 = store.create_channel("team", "agency", "writer")
        ch2 = store.create_channel("team", "agency", "dev")
        assert ch1.id == ch2.id  # Same channel returned

    def test_channel_broadcast(self, store):
        store.create_channel("updates", "agency", "writer")
        store.subscribe_to_channel("updates", "agency", "analyst")
        store.subscribe_to_channel("updates", "agency", "dev")

        msg = Message(sender="writer", target="channel:updates", content="Broadcast!")
        store.send(msg)

        analyst_inbox = store.get_inbox("analyst")
        dev_inbox = store.get_inbox("dev")
        writer_inbox = store.get_inbox("writer")  # Sender excluded

        assert len(analyst_inbox) == 1
        assert len(dev_inbox) == 1
        assert len(writer_inbox) == 0

    def test_conversations(self, store):
        store.send(Message(sender="writer", target="agent:analyst", content="Hello"))
        store.send(Message(sender="writer", target="agent:analyst", content="Follow up"))
        store.send(Message(sender="dev", target="agent:analyst", content="Build done"))

        convos = store.get_conversations("analyst")
        assert len(convos) == 2
        writer_convo = next(c for c in convos if c["with"] == "writer")
        assert writer_convo["count"] == 2


# ---------------------------------------------------------------------------
# MessageTool
# ---------------------------------------------------------------------------


class TestMessageTool:
    @pytest.fixture
    def tool(self):
        return MessageTool()

    def test_properties(self, tool):
        assert tool.name == "messaging"
        assert tool.category == ToolCategory.COMMUNICATION
        assert tool.is_available()

    def test_schemas(self, tool):
        schemas = tool.get_schemas()
        assert len(schemas) == 4
        names = {s.name for s in schemas}
        assert names == {"send_message", "read_messages", "list_conversations", "create_channel"}

    def test_send_message(self, tool):
        result = run_async(tool.execute("send_message", {
            "target": "agent:analyst",
            "content": "Status update",
            "agent_key": "writer",
            "system_key": "agency",
        }))
        assert result.success
        assert "Message sent" in result.output

    def test_send_missing_fields(self, tool):
        result = run_async(tool.execute("send_message", {}))
        assert not result.success

    def test_read_messages(self, tool):
        # Send then read
        run_async(tool.execute("send_message", {
            "target": "agent:analyst",
            "content": "Read me",
            "agent_key": "writer",
        }))
        result = run_async(tool.execute("read_messages", {"agent_key": "analyst"}))
        assert result.success
        assert "1 message(s)" in result.output

    def test_list_conversations(self, tool):
        run_async(tool.execute("send_message", {
            "target": "agent:analyst",
            "content": "Hello",
            "agent_key": "writer",
        }))
        result = run_async(tool.execute("list_conversations", {"agent_key": "analyst"}))
        assert result.success
        assert "1 conversation(s)" in result.output

    def test_create_channel(self, tool):
        result = run_async(tool.execute("create_channel", {
            "name": "team-updates",
            "agent_key": "writer",
            "system_key": "agency",
        }))
        assert result.success
        assert "Channel 'team-updates' created" in result.output

    def test_create_channel_missing_name(self, tool):
        result = run_async(tool.execute("create_channel", {}))
        assert not result.success

    def test_unknown_action(self, tool):
        result = run_async(tool.execute("unknown", {}))
        assert not result.success


# ---------------------------------------------------------------------------
# Factory & migration
# ---------------------------------------------------------------------------


class TestFactory:
    def test_get_tool(self):
        tool = get_tool()
        assert isinstance(tool, MessageTool)

    def test_registry_integration(self):
        from realize_core.tools.tool_registry import ToolRegistry
        registry = ToolRegistry()
        tool = get_tool()
        assert registry.register(tool) is True
        assert registry.get_tool("messaging") is not None


class TestMigrationV4:
    def test_migration_registered(self):
        from realize_core.db.migrations import MIGRATIONS
        assert 4 in MIGRATIONS

    def test_tables_created(self, tmp_path):
        import sqlite3
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version VALUES (3)")
        conn.commit()
        from realize_core.db.migrations import MIGRATIONS
        MIGRATIONS[4](conn)
        conn.commit()

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in tables}
        assert "agent_messages" in table_names
        assert "message_channels" in table_names
        assert "message_channel_subscribers" in table_names
        assert "message_queues" in table_names
        conn.close()
