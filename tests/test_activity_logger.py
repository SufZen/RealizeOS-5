"""Tests for realize_core.activity — event logging, store, and bus.

Covers:
- Fire-and-forget event logging to SQLite
- Event bus publish/subscribe
- Activity store query/filter/count
- Integration with agent lifecycle
"""

import pytest
from realize_core.activity.bus import (
    _recent_events,
    _subscribers,
    get_recent_events,
    publish_event,
    subscribe,
    unsubscribe,
)
from realize_core.activity.logger import log_event
from realize_core.activity.store import count_events, query_events
from realize_core.db.schema import get_connection, init_schema, set_db_path


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    """Initialize a fresh test database for each test."""
    db_path = tmp_path / "test_activity.db"
    set_db_path(db_path)
    init_schema(db_path)
    yield db_path
    set_db_path(None)


@pytest.fixture(autouse=True)
def clear_bus():
    """Clear bus state between tests."""
    _subscribers.clear()
    _recent_events.clear()
    yield
    _subscribers.clear()
    _recent_events.clear()


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------


class TestLogEvent:
    def test_logs_to_sqlite(self, setup_db):
        event_id = log_event(
            venture_key="v1",
            actor_type="agent",
            actor_id="writer",
            action="llm_called",
            entity_type="task",
            entity_id="content",
            details='{"tokens": 100}',
        )
        assert event_id is not None

        conn = get_connection(setup_db)
        row = conn.execute("SELECT * FROM activity_events WHERE id = ?", (event_id,)).fetchone()
        conn.close()

        assert row is not None
        assert row["venture_key"] == "v1"
        assert row["action"] == "llm_called"

    def test_publishes_to_bus(self):
        received = []
        subscribe(lambda e: received.append(e))

        log_event(
            venture_key="v1",
            actor_type="user",
            actor_id="u1",
            action="message_received",
        )

        assert len(received) == 1
        assert received[0]["action"] == "message_received"

    def test_never_raises(self, tmp_path):
        """Logging should never raise, even if DB is broken."""
        set_db_path(tmp_path / "nonexistent_dir" / "db.sqlite")
        # Should not raise
        result = log_event(
            venture_key="v1",
            actor_type="agent",
            actor_id="x",
            action="test",
        )
        # May return an ID even if persistence failed
        assert result is not None or result is None  # just verify no exception


# ---------------------------------------------------------------------------
# Event store (query layer)
# ---------------------------------------------------------------------------


class TestActivityStore:
    def test_query_all(self, setup_db):
        for i in range(5):
            log_event(
                venture_key="v1",
                actor_type="agent",
                actor_id="writer",
                action=f"action_{i}",
            )

        events = query_events(db_path=setup_db)
        assert len(events) == 5

    def test_query_by_venture(self, setup_db):
        log_event(venture_key="v1", actor_type="agent", actor_id="w", action="a")
        log_event(venture_key="v2", actor_type="agent", actor_id="w", action="b")

        v1 = query_events(venture_key="v1", db_path=setup_db)
        assert len(v1) == 1
        assert v1[0]["venture_key"] == "v1"

    def test_query_by_actor(self, setup_db):
        log_event(venture_key="v1", actor_type="agent", actor_id="writer", action="a")
        log_event(venture_key="v1", actor_type="agent", actor_id="analyst", action="b")

        writer_events = query_events(actor_id="writer", db_path=setup_db)
        assert len(writer_events) == 1

    def test_query_by_action(self, setup_db):
        log_event(venture_key="v1", actor_type="agent", actor_id="w", action="llm_called")
        log_event(venture_key="v1", actor_type="user", actor_id="u", action="message_received")

        llm = query_events(action="llm_called", db_path=setup_db)
        assert len(llm) == 1

    def test_query_with_limit(self, setup_db):
        for i in range(10):
            log_event(venture_key="v1", actor_type="agent", actor_id="w", action="a")

        events = query_events(limit=3, db_path=setup_db)
        assert len(events) == 3

    def test_count_events(self, setup_db):
        for i in range(7):
            log_event(venture_key="v1", actor_type="agent", actor_id="w", action="a")
        log_event(venture_key="v2", actor_type="agent", actor_id="w", action="b")

        assert count_events(db_path=setup_db) == 8
        assert count_events(venture_key="v1", db_path=setup_db) == 7


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------


class TestEventBus:
    def test_subscribe_receives_events(self):
        received = []
        subscribe(lambda e: received.append(e))
        publish_event({"action": "test"})
        assert len(received) == 1

    def test_unsubscribe(self):
        received = []

        def cb(e):
            return received.append(e)

        subscribe(cb)
        publish_event({"action": "first"})
        unsubscribe(cb)
        publish_event({"action": "second"})
        assert len(received) == 1

    def test_recent_events_buffer(self):
        for i in range(5):
            publish_event({"id": str(i), "action": f"a{i}"})

        recent = get_recent_events(limit=3)
        assert len(recent) == 3
        assert recent[0]["id"] == "4"  # newest first

    def test_multiple_subscribers(self):
        r1, r2 = [], []
        subscribe(lambda e: r1.append(e))
        subscribe(lambda e: r2.append(e))
        publish_event({"action": "test"})
        assert len(r1) == 1
        assert len(r2) == 1
