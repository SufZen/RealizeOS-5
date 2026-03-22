"""Tests for realize_core.scheduler.lifecycle — agent status management.

Covers:
- Status get/set operations
- Status transitions (idle → running → idle, error)
- Record creation on first status set
- is_paused check
- Invalid status rejection
"""
import pytest
from realize_core.db.schema import init_schema, set_db_path
from realize_core.scheduler.lifecycle import (
    get_agent_status,
    is_paused,
    mark_error,
    mark_idle,
    mark_running,
    set_agent_status,
)


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    """Initialize a fresh test database for each test."""
    db_path = tmp_path / "test_lifecycle.db"
    set_db_path(db_path)
    init_schema(db_path)
    yield db_path
    set_db_path(None)


# ---------------------------------------------------------------------------
# Basic operations
# ---------------------------------------------------------------------------

class TestAgentStatusOperations:
    def test_set_creates_record(self, setup_db):
        set_agent_status("writer", "v1", "idle", db_path=setup_db)
        status = get_agent_status("writer", "v1", db_path=setup_db)
        assert status is not None
        assert status["status"] == "idle"

    def test_get_nonexistent_returns_none(self, setup_db):
        assert get_agent_status("nonexistent", "v1", db_path=setup_db) is None

    def test_update_existing(self, setup_db):
        set_agent_status("writer", "v1", "idle", db_path=setup_db)
        set_agent_status("writer", "v1", "running", db_path=setup_db)
        status = get_agent_status("writer", "v1", db_path=setup_db)
        assert status["status"] == "running"

    def test_invalid_status_raises(self, setup_db):
        with pytest.raises(ValueError):
            set_agent_status("writer", "v1", "invalid", db_path=setup_db)


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

class TestStatusTransitions:
    def test_idle_to_running(self, setup_db):
        mark_idle("writer", "v1", db_path=setup_db)
        mark_running("writer", "v1", db_path=setup_db)
        status = get_agent_status("writer", "v1", db_path=setup_db)
        assert status["status"] == "running"
        assert status["last_run_at"] is not None

    def test_running_to_idle(self, setup_db):
        mark_running("writer", "v1", db_path=setup_db)
        mark_idle("writer", "v1", db_path=setup_db)
        status = get_agent_status("writer", "v1", db_path=setup_db)
        assert status["status"] == "idle"
        assert status["last_error"] is None

    def test_running_to_error(self, setup_db):
        mark_running("writer", "v1", db_path=setup_db)
        mark_error("writer", "v1", "Connection timeout", db_path=setup_db)
        status = get_agent_status("writer", "v1", db_path=setup_db)
        assert status["status"] == "error"
        assert status["last_error"] == "Connection timeout"

    def test_error_clears_on_idle(self, setup_db):
        mark_error("writer", "v1", "Some error", db_path=setup_db)
        mark_idle("writer", "v1", db_path=setup_db)
        status = get_agent_status("writer", "v1", db_path=setup_db)
        assert status["status"] == "idle"
        assert status["last_error"] is None

    def test_updated_at_changes(self, setup_db):
        mark_idle("writer", "v1", db_path=setup_db)
        s1 = get_agent_status("writer", "v1", db_path=setup_db)
        mark_running("writer", "v1", db_path=setup_db)
        s2 = get_agent_status("writer", "v1", db_path=setup_db)
        assert s2["updated_at"] >= s1["updated_at"]


# ---------------------------------------------------------------------------
# Pause check
# ---------------------------------------------------------------------------

class TestIsPaused:
    def test_not_paused(self, setup_db):
        mark_idle("writer", "v1", db_path=setup_db)
        assert is_paused("writer", "v1", db_path=setup_db) is False

    def test_paused(self, setup_db):
        set_agent_status("writer", "v1", "paused", db_path=setup_db)
        assert is_paused("writer", "v1", db_path=setup_db) is True

    def test_nonexistent_not_paused(self, setup_db):
        assert is_paused("nonexistent", "v1", db_path=setup_db) is False


# ---------------------------------------------------------------------------
# Multi-venture isolation
# ---------------------------------------------------------------------------

class TestMultiVenture:
    def test_same_agent_different_ventures(self, setup_db):
        mark_running("writer", "v1", db_path=setup_db)
        mark_idle("writer", "v2", db_path=setup_db)

        s1 = get_agent_status("writer", "v1", db_path=setup_db)
        s2 = get_agent_status("writer", "v2", db_path=setup_db)

        assert s1["status"] == "running"
        assert s2["status"] == "idle"
