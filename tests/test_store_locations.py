"""
Codex audit F04: durable stores must live on persisted storage.

The operational DB, KB index and Synapse used to default to the working
directory / KB root, which a container doesn't persist (and the production
image mounts read-only). Startup also hid a failed operational DB behind a
healthy liveness answer.
"""

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from realize_core import config as cfg
from realize_core.db import schema


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    work = tmp_path / "app"
    data = tmp_path / "persisted"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("DATA_PATH", str(data))
    monkeypatch.delenv("REALIZE_DB_PATH", raising=False)
    schema.set_db_path(None)
    yield work, data
    schema.set_db_path(None)


class TestPersistedPath:
    def test_new_state_goes_under_data_path(self, dirs):
        work, data = dirs
        assert cfg.persisted_path("realize_data.db", work) == data.resolve() / "realize_data.db"

    def test_existing_legacy_file_is_kept(self, dirs):
        work, _ = dirs
        (work / "realize_data.db").write_bytes(b"")
        assert cfg.persisted_path("realize_data.db", work) == work / "realize_data.db"

    def test_index_stays_next_to_a_writable_source(self, dirs):
        work, _ = dirs
        assert cfg.persisted_path("kb_index.db", work, state=False) == work / "kb_index.db"

    def test_index_moves_to_data_when_source_is_read_only(self, dirs, monkeypatch):
        work, data = dirs
        monkeypatch.setattr(os, "access", lambda path, mode: Path(path) != work)
        assert cfg.persisted_path("kb_index.db", work, state=False) == data.resolve() / "kb_index.db"

    def test_synapse_dir(self, dirs):
        work, data = dirs
        assert cfg.synapse_dir(work) == data.resolve() / "synapse"
        (work / ".synapse").mkdir()
        assert cfg.synapse_dir(work) == work / ".synapse"


class TestOperationalDbPath:
    def test_default_is_under_data_path(self, dirs):
        _, data = dirs
        assert schema.get_db_path() == data.resolve() / "realize_data.db"

    def test_existing_cwd_database_is_kept(self, dirs):
        work, _ = dirs
        (work / "realize_data.db").write_bytes(b"")
        assert schema.get_db_path().resolve() == (work / "realize_data.db").resolve()

    def test_explicit_env_wins(self, dirs, monkeypatch, tmp_path):
        work, _ = dirs
        (work / "realize_data.db").write_bytes(b"")
        monkeypatch.setenv("REALIZE_DB_PATH", str(tmp_path / "ops.db"))
        assert schema.get_db_path() == tmp_path / "ops.db"


def _health_client(store_errors: dict) -> TestClient:
    from realize_api.routes import health

    app = FastAPI()
    app.include_router(health.router, prefix="/api")
    app.state.store_errors = store_errors
    return TestClient(app)


class TestHealthReadiness:
    def test_ok(self):
        res = _health_client({}).get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_required_store_failure_is_503(self):
        res = _health_client({"operational_db": "required"}).get("/api/health")
        assert res.status_code == 503
        assert res.json() == {"status": "unavailable", "service": "realize-os", "failed": ["operational_db"]}

    def test_optional_store_failure_is_degraded(self):
        res = _health_client({"synapse": "optional"}).get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "degraded"
