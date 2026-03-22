"""Tests for Sprint 7 — scheduler service, schedule configuration, heartbeat.

Covers:
- Schedule configuration via API (set, clear)
- Scheduled agent query
- Heartbeat skip logic (paused/running agents)
- Next run calculation
"""
import pytest
from pathlib import Path
from realize_core.db.schema import init_schema, get_connection, set_db_path
from realize_core.scheduler.lifecycle import set_agent_status, get_agent_status
from realize_core.scheduler.heartbeat import _get_scheduled_agents, _update_next_run
from realize_core.activity.bus import _subscribers, _recent_events


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    db_path = tmp_path / "test_sched.db"
    set_db_path(db_path)
    init_schema(db_path)
    _subscribers.clear()
    _recent_events.clear()
    yield db_path
    _subscribers.clear()
    _recent_events.clear()
    set_db_path(None)


# ---------------------------------------------------------------------------
# Schedule configuration
# ---------------------------------------------------------------------------

class TestScheduleConfig:
    def test_set_interval_schedule(self, setup_db):
        set_agent_status("writer", "v1", "idle", db_path=setup_db)
        conn = get_connection(setup_db)
        conn.execute(
            "UPDATE agent_states SET schedule_interval_sec = 300 WHERE agent_key = 'writer'",
        )
        conn.commit()
        conn.close()

        agents = _get_scheduled_agents(db_path=setup_db)
        assert len(agents) == 1
        assert agents[0]["agent_key"] == "writer"
        assert agents[0]["schedule_interval_sec"] == 300

    def test_set_cron_schedule(self, setup_db):
        set_agent_status("analyst", "v1", "idle", db_path=setup_db)
        conn = get_connection(setup_db)
        conn.execute(
            "UPDATE agent_states SET schedule_cron = '*/5 * * * *' WHERE agent_key = 'analyst'",
        )
        conn.commit()
        conn.close()

        agents = _get_scheduled_agents(db_path=setup_db)
        assert len(agents) == 1
        assert agents[0]["schedule_cron"] == "*/5 * * * *"

    def test_paused_agents_excluded(self, setup_db):
        set_agent_status("writer", "v1", "paused", db_path=setup_db)
        conn = get_connection(setup_db)
        conn.execute(
            "UPDATE agent_states SET schedule_interval_sec = 300 WHERE agent_key = 'writer'",
        )
        conn.commit()
        conn.close()

        agents = _get_scheduled_agents(db_path=setup_db)
        assert len(agents) == 0

    def test_no_schedule_excluded(self, setup_db):
        set_agent_status("writer", "v1", "idle", db_path=setup_db)
        agents = _get_scheduled_agents(db_path=setup_db)
        assert len(agents) == 0

    def test_update_next_run(self, setup_db):
        set_agent_status("writer", "v1", "idle", db_path=setup_db)
        _update_next_run("writer", "v1", 300, db_path=setup_db)

        state = get_agent_status("writer", "v1", db_path=setup_db)
        assert state["next_run_at"] is not None

    def test_multiple_scheduled_agents(self, setup_db):
        set_agent_status("writer", "v1", "idle", db_path=setup_db)
        set_agent_status("analyst", "v1", "idle", db_path=setup_db)
        conn = get_connection(setup_db)
        conn.execute("UPDATE agent_states SET schedule_interval_sec = 300 WHERE agent_key = 'writer'")
        conn.execute("UPDATE agent_states SET schedule_cron = '0 * * * *' WHERE agent_key = 'analyst'")
        conn.commit()
        conn.close()

        agents = _get_scheduled_agents(db_path=setup_db)
        assert len(agents) == 2


# ---------------------------------------------------------------------------
# Schedule API
# ---------------------------------------------------------------------------

class TestScheduleAPI:
    @pytest.fixture
    def client(self, setup_db, tmp_path):
        try:
            from fastapi import FastAPI
        except ImportError:
            pytest.skip("FastAPI not installed")

        from fastapi.testclient import TestClient
        from realize_api.routes import ventures

        app = FastAPI()
        app.include_router(ventures.router, prefix="/api")
        app.state.systems = {
            "v1": {
                "name": "Test", "agents": {"writer": "agents/writer.md"},
                "agents_dir": "", "foundations": "", "brain_dir": "",
                "routines_dir": "", "insights_dir": "", "creations_dir": "",
            },
        }
        app.state.kb_path = tmp_path
        return TestClient(app)

    def test_set_interval_schedule(self, client):
        res = client.put(
            "/api/ventures/v1/agents/writer/schedule",
            json={"schedule_interval_sec": 300},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["schedule_interval_sec"] == 300
        assert data["next_run_at"] is not None

    def test_set_cron_schedule(self, client):
        res = client.put(
            "/api/ventures/v1/agents/writer/schedule",
            json={"schedule_cron": "*/5 * * * *"},
        )
        assert res.status_code == 200
        assert res.json()["schedule_cron"] == "*/5 * * * *"

    def test_clear_schedule(self, client):
        client.put("/api/ventures/v1/agents/writer/schedule", json={"schedule_interval_sec": 300})
        res = client.delete("/api/ventures/v1/agents/writer/schedule")
        assert res.status_code == 200
        assert res.json()["schedule"] is None

    def test_missing_schedule_params(self, client):
        res = client.put("/api/ventures/v1/agents/writer/schedule", json={})
        assert res.status_code == 400

    def test_schedule_nonexistent_agent(self, client):
        res = client.put(
            "/api/ventures/v1/agents/fake/schedule",
            json={"schedule_interval_sec": 300},
        )
        assert res.status_code == 404
