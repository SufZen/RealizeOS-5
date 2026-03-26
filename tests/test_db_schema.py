"""Tests for realize_core.db — schema, migrations, and basic operations.

Covers:
- Schema creation (all tables, indexes)
- Insert/query activity events
- Agent state operations
- Approval queue operations
- Migration system
- Idempotent schema init
"""

import uuid

import pytest
from realize_core.db.migrations import get_current_version, run_migrations
from realize_core.db.schema import (
    get_connection,
    init_schema,
    set_db_path,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temp database and initialize schema."""
    path = tmp_path / "test_realize.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)  # Reset global


@pytest.fixture
def conn(db_path):
    """Get a connection to the test database."""
    c = get_connection(db_path)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------


class TestSchema:
    def test_tables_exist(self, conn):
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        table_names = {row["name"] for row in tables}
        assert "activity_events" in table_names
        assert "agent_states" in table_names
        assert "approval_queue" in table_names
        assert "schema_version" in table_names

    def test_schema_version_is_1(self, conn):
        row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        assert row["v"] == 1

    def test_idempotent_init(self, db_path):
        """Calling init_schema twice should not fail."""
        init_schema(db_path)
        init_schema(db_path)
        conn = get_connection(db_path)
        row = conn.execute("SELECT COUNT(*) as c FROM schema_version").fetchone()
        assert row["c"] == 1  # Only one version row
        conn.close()


# ---------------------------------------------------------------------------
# Activity events
# ---------------------------------------------------------------------------


class TestActivityEvents:
    def test_insert_and_query(self, conn):
        event_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO activity_events
               (id, venture_key, actor_type, actor_id, action, entity_type, entity_id, details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, "venture1", "agent", "writer", "skill_executed", "skill", "content_pipeline", '{"tokens": 150}'),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM activity_events WHERE id = ?", (event_id,)).fetchone()
        assert row is not None
        assert row["venture_key"] == "venture1"
        assert row["actor_type"] == "agent"
        assert row["action"] == "skill_executed"
        assert row["created_at"] is not None

    def test_query_by_venture(self, conn):
        for i in range(5):
            conn.execute(
                """INSERT INTO activity_events
                   (id, venture_key, actor_type, actor_id, action)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), "v1", "agent", "writer", f"action_{i}"),
            )
        conn.execute(
            """INSERT INTO activity_events
               (id, venture_key, actor_type, actor_id, action)
               VALUES (?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), "v2", "system", "system", "startup"),
        )
        conn.commit()

        v1_rows = conn.execute("SELECT * FROM activity_events WHERE venture_key = ?", ("v1",)).fetchall()
        assert len(v1_rows) == 5

    def test_invalid_actor_type_rejected(self, conn):
        with pytest.raises(Exception):
            conn.execute(
                """INSERT INTO activity_events
                   (id, venture_key, actor_type, actor_id, action)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), "v1", "invalid_type", "x", "test"),
            )


# ---------------------------------------------------------------------------
# Agent states
# ---------------------------------------------------------------------------


class TestAgentStates:
    def test_insert_and_query(self, conn):
        conn.execute(
            """INSERT INTO agent_states (agent_key, venture_key, status)
               VALUES (?, ?, ?)""",
            ("writer", "venture1", "idle"),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM agent_states WHERE agent_key = ? AND venture_key = ?",
            ("writer", "venture1"),
        ).fetchone()
        assert row["status"] == "idle"
        assert row["updated_at"] is not None

    def test_status_update(self, conn):
        conn.execute(
            """INSERT INTO agent_states (agent_key, venture_key, status)
               VALUES (?, ?, ?)""",
            ("writer", "v1", "idle"),
        )
        conn.commit()

        conn.execute(
            """UPDATE agent_states SET status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')
               WHERE agent_key = ? AND venture_key = ?""",
            ("running", "writer", "v1"),
        )
        conn.commit()

        row = conn.execute(
            "SELECT status FROM agent_states WHERE agent_key = ? AND venture_key = ?",
            ("writer", "v1"),
        ).fetchone()
        assert row["status"] == "running"

    def test_invalid_status_rejected(self, conn):
        with pytest.raises(Exception):
            conn.execute(
                """INSERT INTO agent_states (agent_key, venture_key, status)
                   VALUES (?, ?, ?)""",
                ("writer", "v1", "invalid_status"),
            )

    def test_composite_primary_key(self, conn):
        conn.execute(
            "INSERT INTO agent_states (agent_key, venture_key, status) VALUES (?, ?, ?)",
            ("writer", "v1", "idle"),
        )
        conn.execute(
            "INSERT INTO agent_states (agent_key, venture_key, status) VALUES (?, ?, ?)",
            ("writer", "v2", "idle"),
        )
        conn.commit()

        rows = conn.execute("SELECT * FROM agent_states WHERE agent_key = 'writer'").fetchall()
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# Approval queue
# ---------------------------------------------------------------------------


class TestApprovalQueue:
    def test_insert_and_query(self, conn):
        approval_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO approval_queue
               (id, venture_key, agent_key, action_type, payload, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (approval_id, "v1", "writer", "send_email", '{"to": "user@test.com"}', "pending"),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
        assert row["status"] == "pending"
        assert row["action_type"] == "send_email"

    def test_approve_action(self, conn):
        aid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO approval_queue
               (id, venture_key, agent_key, action_type, status)
               VALUES (?, ?, ?, ?, ?)""",
            (aid, "v1", "writer", "publish", "pending"),
        )
        conn.commit()

        conn.execute(
            """UPDATE approval_queue
               SET status = 'approved', decision_note = ?, decided_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')
               WHERE id = ?""",
            ("Looks good", aid),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM approval_queue WHERE id = ?", (aid,)).fetchone()
        assert row["status"] == "approved"
        assert row["decision_note"] == "Looks good"
        assert row["decided_at"] is not None

    def test_invalid_status_rejected(self, conn):
        with pytest.raises(Exception):
            conn.execute(
                """INSERT INTO approval_queue
                   (id, venture_key, agent_key, action_type, status)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), "v1", "w", "test", "bogus"),
            )


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


class TestMigrations:
    def test_run_migrations_idempotent(self, db_path):
        run_migrations(db_path)
        run_migrations(db_path)
        conn = get_connection(db_path)
        version = get_current_version(conn)
        assert version == 4
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'storage_sync_log'"
        ).fetchone()
        assert row is not None
        # v3 table also exists
        row_v3 = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'approval_requests'"
        ).fetchone()
        assert row_v3 is not None
        # v4 table also exists
        row_v4 = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'agent_messages'"
        ).fetchone()
        assert row_v4 is not None
        conn.close()

    def test_version_tracking(self, db_path):
        conn = get_connection(db_path)
        version = get_current_version(conn)
        assert version == 1
        conn.close()

    def test_run_migrations_creates_v2_indexes(self, db_path):
        run_migrations(db_path)
        conn = get_connection(db_path)
        index_rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
        index_names = {row["name"] for row in index_rows}
        assert "idx_sync_log_status" in index_names
        assert "idx_sync_log_file_key" in index_names
        assert "idx_activity_created_at" in index_names
        assert "idx_activity_entity" in index_names
        assert "idx_approval_expires" in index_names
        conn.close()
