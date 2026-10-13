"""
Codex audit (integrity gaps): storage export.

The old export zipped the whole working directory (earlier exports and its
own ZIP included), copied live SQLite files, put .env/.credentials in a file
left on the server, and the page could only show that file's server path.
"""

import io
import sqlite3
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def kb(tmp_path, monkeypatch):
    from realize_core.db import schema

    root = tmp_path / "kb"
    (root / "systems" / "acme" / "F-foundations").mkdir(parents=True)
    (root / "systems" / "acme" / "F-foundations" / "venture-identity.md").write_text("Acme", encoding="utf-8")
    (root / "systems" / "acme" / ".cache").mkdir()
    (root / "systems" / "acme" / ".cache" / "junk").write_text("x", encoding="utf-8")
    (root / "realize-os.yaml").write_text("systems: []\n", encoding="utf-8")
    (root / ".env").write_text("ANTHROPIC_API_KEY=sk-secret\n", encoding="utf-8")
    (root / ".credentials").mkdir()
    (root / ".credentials" / "tokens.json").write_text("{}", encoding="utf-8")
    (root / "backups").mkdir()
    (root / "backups" / "previous.zip").write_bytes(b"old")

    ops = tmp_path / "data" / "realize_data.db"
    ops.parent.mkdir()
    conn = sqlite3.connect(ops)
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('kept')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "data"))
    monkeypatch.setattr("realize_core.memory.store.DB_PATH", tmp_path / "data" / "memory.db")
    schema.set_db_path(ops)
    yield root
    schema.set_db_path(None)


def test_export_downloads_the_brain_without_secrets(kb):
    from realize_api.routes import storage_settings

    app = FastAPI()
    app.include_router(storage_settings.router, prefix="/api")
    app.state.kb_path = kb

    res = TestClient(app).post("/api/storage/export")

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    names = set(zipfile.ZipFile(io.BytesIO(res.content)).namelist())
    assert "realize-os.yaml" in names
    assert "systems/acme/F-foundations/venture-identity.md" in names
    assert "data/realize_data.db" in names
    assert not any(n.startswith((".env", ".credentials", "backups", "systems/acme/.cache")) for n in names)
    assert not any(n.endswith(".zip") for n in names)

    # The database is a usable snapshot.
    snap = zipfile.ZipFile(io.BytesIO(res.content)).read("data/realize_data.db")
    path = kb / "check.db"
    path.write_bytes(snap)
    assert sqlite3.connect(path).execute("SELECT v FROM t").fetchone() == ("kept",)

    # Nothing is left behind next to the data.
    assert sorted(p.name for p in (kb / "backups").iterdir()) == ["previous.zip"]


def _storage_client(tmp_path, monkeypatch):
    from realize_api.routes import storage_settings

    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(storage_settings.router, prefix="/api")
    return TestClient(app)


def test_saved_storage_config_is_applied_and_keeps_masked_keys(tmp_path, monkeypatch):
    """Saving reconfigures the live provider; a masked key sent back keeps the stored one."""
    import json

    from realize_core.storage import factory

    applied: list[dict] = []
    monkeypatch.setattr(factory, "reconfigure", lambda cfg: applied.append(cfg))
    (tmp_path / ".storage-config.json").write_text(
        json.dumps({"provider": "s3", "s3_access_key": "AKIAREALKEY1234", "s3_secret_key": "realsecret9876"}),
        encoding="utf-8",
    )
    client = _storage_client(tmp_path, monkeypatch)

    masked = client.get("/api/storage/config").json()["config"]
    res = client.put("/api/storage/config", json={**masked, "s3_bucket": "acme-brain"})

    assert res.status_code == 200
    saved = json.loads((tmp_path / ".storage-config.json").read_text(encoding="utf-8"))
    assert saved["s3_access_key"] == "AKIAREALKEY1234"
    assert saved["s3_secret_key"] == "realsecret9876"
    assert applied[-1]["s3_bucket"] == "acme-brain"


def test_unusable_storage_config_is_refused_and_not_saved(tmp_path, monkeypatch):

    from realize_core.storage import factory

    calls: list[dict] = []

    def reconfigure(cfg):
        calls.append(cfg)
        if cfg.get("provider") == "s3":
            raise ImportError("boto3 is not installed")

    monkeypatch.setattr(factory, "reconfigure", reconfigure)
    client = _storage_client(tmp_path, monkeypatch)

    res = client.put("/api/storage/config", json={"provider": "s3", "s3_bucket": "b"})

    assert res.status_code == 400
    assert not (tmp_path / ".storage-config.json").exists()
    assert calls[-1].get("provider", "local") == "local"  # the previous setup was put back


def test_export_leaves_sign_in_sessions_and_deleted_rows_out(kb, tmp_path):
    """A session cookie in the ZIP could sign in to the running server; deleted rows must not linger either."""
    from realize_api.routes import storage_settings

    ops = tmp_path / "data" / "realize_data.db"
    conn = sqlite3.connect(ops)
    conn.execute("CREATE TABLE user_sessions (session_id TEXT PRIMARY KEY, csrf_token TEXT, user_id TEXT)")
    conn.execute("INSERT INTO user_sessions VALUES ('live-session-cookie-value', 'live-csrf-value', 'owner@x')")
    conn.execute("INSERT INTO t VALUES ('erased-row-value')")
    conn.commit()
    conn.execute("DELETE FROM t WHERE v = 'erased-row-value'")
    conn.commit()
    conn.close()

    app = FastAPI()
    app.include_router(storage_settings.router, prefix="/api")
    app.state.kb_path = kb
    res = TestClient(app).post("/api/storage/export")

    assert res.status_code == 200
    snap = zipfile.ZipFile(io.BytesIO(res.content)).read("data/realize_data.db")
    for value in (b"live-session-cookie-value", b"live-csrf-value", b"erased-row-value"):
        assert value not in snap
    path = tmp_path / "snap.db"
    path.write_bytes(snap)
    check = sqlite3.connect(path)
    assert check.execute("SELECT COUNT(*) FROM user_sessions").fetchone() == (0,)
    assert check.execute("SELECT v FROM t").fetchall() == [("kept",)]
    check.close()
    # The live database keeps its sessions: only the snapshot is cleaned.
    live = sqlite3.connect(ops)
    assert live.execute("SELECT COUNT(*) FROM user_sessions").fetchone() == (1,)
    live.close()
