"""
Tests for Phase 2-3 hardening: security scanner enhancements, storage factory,
security middleware, and DB migration v2.
"""

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ===========================================================================
# Security Scanner — extended checks
# ===========================================================================


class TestSecurityScanner:
    """Test the enhanced run_security_scan function."""

    def test_scan_returns_all_keys(self):
        from realize_core.security.scanner import run_security_scan

        result = run_security_scan(Path("."))
        assert "passed" in result
        assert "warnings" in result
        assert "critical" in result
        assert "total" in result
        assert "checks" in result
        assert "scanned_at" in result

    def test_scan_checks_are_list(self):
        from realize_core.security.scanner import run_security_scan

        result = run_security_scan(Path("."))
        assert isinstance(result["checks"], list)
        assert len(result["checks"]) > 0

    def test_check_structure(self):
        from realize_core.security.scanner import run_security_scan

        result = run_security_scan(Path("."))
        for check in result["checks"]:
            assert "name" in check
            assert "status" in check
            assert "detail" in check
            assert check["status"] in ("pass", "warn", "critical")

    def test_total_matches_sum(self):
        from realize_core.security.scanner import run_security_scan

        result = run_security_scan(Path("."))
        assert result["total"] == result["passed"] + result["warnings"] + result["critical"]

    def test_scan_with_explicit_config(self):
        from realize_core.security.scanner import run_security_scan

        config = {
            "kb_path": "/tmp/fake_kb",
            "api_key": "test-key-12345",
        }
        result = run_security_scan(Path("."), config)
        assert result["total"] > 0

    def test_scan_jwt_check_exists(self):
        from realize_core.security.scanner import run_security_scan

        result = run_security_scan(Path("."))
        check_names = [c["name"] for c in result["checks"]]
        assert any("JWT" in n for n in check_names)

    def test_scan_audit_check_exists(self):
        from realize_core.security.scanner import run_security_scan

        result = run_security_scan(Path("."))
        check_names = [c["name"] for c in result["checks"]]
        assert any("Audit" in n for n in check_names)

    def test_scan_middleware_check_exists(self):
        from realize_core.security.scanner import run_security_scan

        result = run_security_scan(Path("."))
        check_names = [c["name"] for c in result["checks"]]
        assert any("middleware" in n.lower() for n in check_names)

    def test_scan_with_jwt_enabled(self):
        from realize_core.security.scanner import run_security_scan

        with patch.dict(os.environ, {"REALIZE_JWT_ENABLED": "true", "REALIZE_JWT_SECRET": "a" * 64}):
            result = run_security_scan(Path("."))
            jwt_checks = [c for c in result["checks"] if "JWT" in c["name"]]
            assert len(jwt_checks) >= 1
            assert jwt_checks[0]["status"] == "pass"

    def test_scan_with_weak_jwt_secret(self):
        from realize_core.security.scanner import run_security_scan

        with patch.dict(os.environ, {"REALIZE_JWT_ENABLED": "true", "REALIZE_JWT_SECRET": "weak"}):
            result = run_security_scan(Path("."))
            jwt_checks = [c for c in result["checks"] if "JWT" in c["name"]]
            assert len(jwt_checks) >= 1
            assert jwt_checks[0]["status"] in ("warn", "critical")

    def test_scan_with_audit_dir(self):
        from realize_core.security.scanner import run_security_scan

        with tempfile.TemporaryDirectory() as d:
            with patch.dict(os.environ, {"REALIZE_AUDIT_LOG_DIR": d}):
                result = run_security_scan(Path("."))
                audit_checks = [c for c in result["checks"] if "Audit" in c["name"]]
                assert len(audit_checks) >= 1
                assert audit_checks[0]["status"] == "pass"

    def test_scan_without_audit_dir(self):
        from realize_core.security.scanner import run_security_scan

        env = os.environ.copy()
        env.pop("REALIZE_AUDIT_LOG_DIR", None)
        with patch.dict(os.environ, env, clear=True):
            result = run_security_scan(Path("."))
            audit_checks = [c for c in result["checks"] if "Audit" in c["name"]]
            assert len(audit_checks) >= 1
            assert audit_checks[0]["status"] == "warn"


# ===========================================================================
# Storage Factory
# ===========================================================================


class TestStorageFactory:
    """Test the storage provider factory singleton system."""

    def _reset(self):
        """Reset factory singletons between tests."""
        import realize_core.storage.factory as f

        f._primary = None
        f._sync_manager = None

    def test_get_storage_provider_default_local(self):
        from realize_core.storage.factory import get_storage_provider

        self._reset()
        with tempfile.TemporaryDirectory() as d:
            config = {"provider": "local", "local_root": d}
            provider = get_storage_provider(config)
            assert provider is not None
            assert "local" in str(type(provider)).lower()
        self._reset()

    def test_get_storage_provider_singleton(self):
        from realize_core.storage.factory import get_storage_provider

        self._reset()
        with tempfile.TemporaryDirectory() as d:
            config = {"provider": "local", "local_root": d}
            p1 = get_storage_provider(config)
            p2 = get_storage_provider()  # no config → returns cached
            assert p1 is p2
        self._reset()

    def test_reconfigure_creates_fresh(self):
        from realize_core.storage.factory import get_storage_provider, reconfigure

        self._reset()
        with tempfile.TemporaryDirectory() as d:
            config = {"provider": "local", "local_root": d}
            p1 = get_storage_provider(config)
            p2 = reconfigure(config)
            assert p1 is not p2
        self._reset()

    def test_get_sync_manager_returns_none_when_local(self):
        from realize_core.storage.factory import get_sync_manager

        self._reset()
        # Default config is local, sync returns None
        manager = get_sync_manager()
        assert manager is None
        self._reset()

    def test_unknown_provider_falls_back_to_local(self):
        from realize_core.storage.factory import get_storage_provider

        self._reset()
        p = get_storage_provider({"provider": "azure"})
        assert "local" in str(type(p)).lower()
        self._reset()


# ===========================================================================
# DB Migration v2
# ===========================================================================


class TestMigrationV2:
    """Test the v2 migration — storage_sync_log table + indexes."""

    def test_migration_registered(self):
        from realize_core.db.migrations import MIGRATIONS

        assert 2 in MIGRATIONS

    def test_migration_creates_sync_log_table(self):
        from realize_core.db.migrations import MIGRATIONS

        conn = sqlite3.connect(":memory:")
        # Create prerequisite tables
        conn.execute("""
            CREATE TABLE activity_events (
                id TEXT PRIMARY KEY,
                entity_type TEXT, entity_id TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE approval_queue (
                id TEXT PRIMARY KEY,
                status TEXT, expires_at TEXT
            )
        """)
        conn.commit()

        # Run v2 migration
        MIGRATIONS[2](conn)

        # Verify table exists
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='storage_sync_log'")
        assert cursor.fetchone() is not None

    def test_migration_creates_indexes(self):
        from realize_core.db.migrations import MIGRATIONS

        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE activity_events (
                id TEXT PRIMARY KEY, entity_type TEXT, entity_id TEXT, created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE approval_queue (
                id TEXT PRIMARY KEY, status TEXT, expires_at TEXT
            )
        """)
        conn.commit()

        MIGRATIONS[2](conn)

        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        index_names = [row[0] for row in cursor.fetchall()]
        assert "idx_sync_log_status" in index_names
        assert "idx_sync_log_file_key" in index_names
        assert "idx_activity_created_at" in index_names
        assert "idx_activity_entity" in index_names
        assert "idx_approval_expires" in index_names

    def test_migration_idempotent(self):
        from realize_core.db.migrations import MIGRATIONS

        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE activity_events (
                id TEXT PRIMARY KEY, entity_type TEXT, entity_id TEXT, created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE approval_queue (
                id TEXT PRIMARY KEY, status TEXT, expires_at TEXT
            )
        """)
        conn.commit()

        # Run twice — should not raise
        MIGRATIONS[2](conn)
        MIGRATIONS[2](conn)

    def test_sync_log_insert(self):
        from realize_core.db.migrations import MIGRATIONS

        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE activity_events (
                id TEXT PRIMARY KEY, entity_type TEXT, entity_id TEXT, created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE approval_queue (
                id TEXT PRIMARY KEY, status TEXT, expires_at TEXT
            )
        """)
        conn.commit()
        MIGRATIONS[2](conn)

        # Insert a record
        conn.execute("""
            INSERT INTO storage_sync_log (id, sync_type, source_backend, target_backend, file_key, status)
            VALUES ('test-1', 'push', 'local', 's3', 'doc.txt', 'completed')
        """)
        conn.commit()

        row = conn.execute("SELECT * FROM storage_sync_log WHERE id = 'test-1'").fetchone()
        assert row is not None

    def test_sync_log_status_constraint(self):
        from realize_core.db.migrations import MIGRATIONS

        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE activity_events (
                id TEXT PRIMARY KEY, entity_type TEXT, entity_id TEXT, created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE approval_queue (
                id TEXT PRIMARY KEY, status TEXT, expires_at TEXT
            )
        """)
        conn.commit()
        MIGRATIONS[2](conn)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("""
                INSERT INTO storage_sync_log (id, sync_type, source_backend, target_backend, file_key, status)
                VALUES ('bad-1', 'push', 'local', 's3', 'doc.txt', 'invalid_status')
            """)


# ===========================================================================
# FastAPI app creation
# ===========================================================================


class TestAppCreation:
    """Verify the full app wires up correctly."""

    def test_app_creates_successfully(self):
        from realize_api.main import create_app

        app = create_app()
        assert len(app.routes) >= 120

    def test_app_has_security_routes(self):
        from realize_api.main import create_app

        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/security/scan" in paths or any("/security/" in p for p in paths)

    def test_app_has_auth_routes(self):
        from realize_api.main import create_app

        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("/auth/" in p for p in paths)

    def test_app_has_storage_sync_routes(self):
        from realize_api.main import create_app

        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("sync" in p for p in paths)
