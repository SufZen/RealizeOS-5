"""
Tests for the Migration Engine (realize_core/migration/engine.py).

Covers:
- Engine initialization and meta table creation
- Version discovery from modules
- Forward migration (migrate_up)
- Reverse migration (migrate_down)
- Rollback by N steps
- Idempotency (applying twice is safe)
- Transaction rollback on migration failure
- Migration history tracking
- Status reporting
"""

import sqlite3
import sys
import types

import pytest

# ---------------------------------------------------------------------------
# Helpers — create fake migration modules for isolated testing
# ---------------------------------------------------------------------------


def _make_version_module(
    name: str,
    version: int,
    description: str = "",
    up_sql: str = "",
    down_sql: str = "",
    up_raises: bool = False,
    down_raises: bool = False,
) -> types.ModuleType:
    """Build a synthetic migration module with up/down functions."""
    mod = types.ModuleType(name)
    mod.VERSION = version
    mod.DESCRIPTION = description

    def up(conn: sqlite3.Connection) -> None:
        if up_raises:
            raise RuntimeError(f"Simulated failure in migration v{version} up()")
        if up_sql:
            conn.executescript(up_sql)

    def down(conn: sqlite3.Connection) -> None:
        if down_raises:
            raise RuntimeError(f"Simulated failure in migration v{version} down()")
        if down_sql:
            conn.executescript(down_sql)

    mod.up = up
    mod.down = down
    return mod


@pytest.fixture
def fake_versions_package(tmp_path):
    """
    Create a temporary Python package with two migration modules.

    Yields a tuple of (package_dotted_name, list_of_modules).
    """
    pkg_name = "test_migration_versions"
    pkg_dir = tmp_path / pkg_name
    pkg_dir.mkdir()

    # Write __init__.py
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    # Write 001_baseline.py
    (pkg_dir / "001_baseline.py").write_text(
        "import sqlite3\n"
        "VERSION = 1\n"
        'DESCRIPTION = "Baseline test tables"\n'
        "\n"
        "def up(conn: sqlite3.Connection) -> None:\n"
        '    conn.executescript("""\n'
        "        CREATE TABLE IF NOT EXISTS test_users (\n"
        "            id INTEGER PRIMARY KEY,\n"
        "            name TEXT NOT NULL\n"
        "        );\n"
        '    """)\n'
        "\n"
        "def down(conn: sqlite3.Connection) -> None:\n"
        '    conn.executescript("DROP TABLE IF EXISTS test_users;")\n',
        encoding="utf-8",
    )

    # Write 002_add_email.py
    (pkg_dir / "002_add_email.py").write_text(
        "import sqlite3\n"
        "VERSION = 2\n"
        'DESCRIPTION = "Add email column to test_users"\n'
        "\n"
        "def up(conn: sqlite3.Connection) -> None:\n"
        '    conn.execute("ALTER TABLE test_users ADD COLUMN email TEXT;")\n'
        "\n"
        "def down(conn: sqlite3.Connection) -> None:\n"
        "    # SQLite doesn't support DROP COLUMN before 3.35\n"
        "    # Recreate the table without the email column\n"
        '    conn.executescript("""\n'
        "        CREATE TABLE test_users_backup AS SELECT id, name FROM test_users;\n"
        "        DROP TABLE test_users;\n"
        "        ALTER TABLE test_users_backup RENAME TO test_users;\n"
        '    """)\n',
        encoding="utf-8",
    )

    # Add parent dir to sys.path so the package is importable
    sys.path.insert(0, str(tmp_path))
    yield pkg_name

    # Cleanup
    sys.path.remove(str(tmp_path))
    # Remove cached modules
    for key in list(sys.modules):
        if key.startswith(pkg_name):
            del sys.modules[key]


@pytest.fixture
def engine(tmp_path, fake_versions_package):
    """Create a MigrationEngine with an isolated temp DB and fake versions."""
    from realize_core.migration.engine import MigrationEngine

    db_path = tmp_path / "test_migrate.db"
    return MigrationEngine(db_path=db_path, versions_package=fake_versions_package)


# ---------------------------------------------------------------------------
# Tests — Initialization
# ---------------------------------------------------------------------------


class TestEngineInit:
    def test_creates_migration_history_table(self, engine, tmp_path):
        """Engine init should create the migration_history table."""
        db_path = tmp_path / "test_migrate.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        tables = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "migration_history" in tables

    def test_initial_version_is_zero(self, engine):
        """Before any migrations, current version should be 0."""
        assert engine.get_current_version() == 0

    def test_initial_applied_versions_empty(self, engine):
        """Before any migrations, no versions should be applied."""
        assert engine.get_applied_versions() == set()


# ---------------------------------------------------------------------------
# Tests — Version Discovery
# ---------------------------------------------------------------------------


class TestDiscoverVersions:
    def test_discovers_two_versions(self, engine):
        """Should find both 001_baseline and 002_add_email."""
        versions = engine.discover_versions()
        assert len(versions) == 2
        assert versions[0].version == 1
        assert versions[1].version == 2

    def test_versions_sorted(self, engine):
        """Versions should be sorted ascending."""
        versions = engine.discover_versions()
        nums = [v.version for v in versions]
        assert nums == sorted(nums)

    def test_version_descriptions(self, engine):
        """Version descriptions should match module definitions."""
        versions = engine.discover_versions()
        # First version
        assert "Baseline" in versions[0].description
        # Second version
        assert "email" in versions[1].description.lower()

    def test_load_returns_module(self, engine):
        """MigrationVersion.load() should return a module with up/down."""
        versions = engine.discover_versions()
        mod = versions[0].load()
        assert hasattr(mod, "up")
        assert hasattr(mod, "down")
        assert callable(mod.up)
        assert callable(mod.down)


# ---------------------------------------------------------------------------
# Tests — Migrate Up
# ---------------------------------------------------------------------------


class TestMigrateUp:
    def test_migrate_up_all(self, engine, tmp_path):
        """migrate_up() with no target applies all pending migrations."""
        applied = engine.migrate_up()
        assert applied == [1, 2]
        assert engine.get_current_version() == 2

    def test_migrate_up_to_version_1(self, engine):
        """migrate_up(target_version=1) applies only v1."""
        applied = engine.migrate_up(target_version=1)
        assert applied == [1]
        assert engine.get_current_version() == 1

    def test_migrate_up_remaining(self, engine):
        """After applying v1, migrate_up() applies only v2."""
        engine.migrate_up(target_version=1)
        applied = engine.migrate_up()
        assert applied == [2]
        assert engine.get_current_version() == 2

    def test_migrate_up_idempotent(self, engine):
        """Calling migrate_up() twice returns [] the second time."""
        engine.migrate_up()
        second = engine.migrate_up()
        assert second == []
        assert engine.get_current_version() == 2

    def test_tables_created_after_up(self, engine, tmp_path):
        """After migrate_up, the test_users table should exist with email column."""
        engine.migrate_up()
        db_path = tmp_path / "test_migrate.db"
        conn = sqlite3.connect(str(db_path))
        # Insert a row with email to verify both migrations applied
        conn.execute("INSERT INTO test_users (name, email) VALUES ('Alice', 'a@b.com')")
        conn.commit()
        row = conn.execute("SELECT name, email FROM test_users").fetchone()
        conn.close()
        assert row[0] == "Alice"
        assert row[1] == "a@b.com"


# ---------------------------------------------------------------------------
# Tests — Migrate Down
# ---------------------------------------------------------------------------


class TestMigrateDown:
    def test_migrate_down_to_v1(self, engine, tmp_path):
        """migrate_down(1) should undo v2 but keep v1."""
        engine.migrate_up()
        rolled = engine.migrate_down(target_version=1)
        assert rolled == [2]
        assert engine.get_current_version() == 1

        # test_users should still exist but without email column
        db_path = tmp_path / "test_migrate.db"
        conn = sqlite3.connect(str(db_path))
        cols = [info[1] for info in conn.execute("PRAGMA table_info(test_users)").fetchall()]
        conn.close()
        assert "name" in cols
        assert "email" not in cols

    def test_migrate_down_to_zero(self, engine, tmp_path):
        """migrate_down(0) should undo all migrations."""
        engine.migrate_up()
        rolled = engine.migrate_down(target_version=0)
        assert sorted(rolled) == [1, 2]
        assert engine.get_current_version() == 0

        # test_users table should not exist
        db_path = tmp_path / "test_migrate.db"
        conn = sqlite3.connect(str(db_path))
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "test_users" not in tables

    def test_migrate_down_noop_when_at_target(self, engine):
        """migrate_down to current version does nothing."""
        engine.migrate_up(target_version=1)
        rolled = engine.migrate_down(target_version=1)
        assert rolled == []
        assert engine.get_current_version() == 1

    def test_migrate_down_noop_when_above_current(self, engine):
        """migrate_down to a version higher than current does nothing."""
        engine.migrate_up(target_version=1)
        rolled = engine.migrate_down(target_version=5)
        assert rolled == []


# ---------------------------------------------------------------------------
# Tests — Rollback
# ---------------------------------------------------------------------------


class TestRollback:
    def test_rollback_one_step(self, engine):
        """rollback(1) undoes the last applied migration."""
        engine.migrate_up()
        rolled = engine.rollback(steps=1)
        assert rolled == [2]
        assert engine.get_current_version() == 1

    def test_rollback_two_steps(self, engine):
        """rollback(2) undoes the last two migrations."""
        engine.migrate_up()
        rolled = engine.rollback(steps=2)
        assert sorted(rolled) == [1, 2]
        assert engine.get_current_version() == 0

    def test_rollback_more_than_applied(self, engine):
        """rollback(10) when only 2 applied should roll back both."""
        engine.migrate_up()
        rolled = engine.rollback(steps=10)
        assert sorted(rolled) == [1, 2]
        assert engine.get_current_version() == 0

    def test_rollback_zero_does_nothing(self, engine):
        """rollback(0) should be a no-op."""
        engine.migrate_up()
        rolled = engine.rollback(steps=0)
        assert rolled == []
        assert engine.get_current_version() == 2

    def test_rollback_on_empty_db(self, engine):
        """rollback on empty DB returns empty list."""
        rolled = engine.rollback(steps=1)
        assert rolled == []


# ---------------------------------------------------------------------------
# Tests — Migration Failure
# ---------------------------------------------------------------------------


class TestMigrationFailure:
    def test_up_failure_rolls_back_transaction(self, tmp_path):
        """If up() raises, the transaction is aborted and version not recorded."""
        from realize_core.migration.engine import MigrationEngine

        # Create a version package with a failing migration
        pkg_name = "test_fail_versions"
        pkg_dir = tmp_path / pkg_name
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "001_works.py").write_text(
            "import sqlite3\n"
            "VERSION = 1\n"
            'DESCRIPTION = "Works fine"\n'
            "def up(conn):\n"
            '    conn.execute("CREATE TABLE ok_table (id INTEGER PRIMARY KEY);")\n'
            "def down(conn):\n"
            '    conn.execute("DROP TABLE IF EXISTS ok_table;")\n',
            encoding="utf-8",
        )
        (pkg_dir / "002_fails.py").write_text(
            "VERSION = 2\n"
            'DESCRIPTION = "This one fails"\n'
            "def up(conn):\n"
            '    raise RuntimeError("Intentional failure")\n'
            "def down(conn):\n"
            "    pass\n",
            encoding="utf-8",
        )

        sys.path.insert(0, str(tmp_path))
        try:
            db_path = tmp_path / "fail_test.db"
            engine = MigrationEngine(db_path=db_path, versions_package=pkg_name)

            with pytest.raises(RuntimeError, match="Intentional failure"):
                engine.migrate_up()

            # v1 should be applied, v2 should not
            assert engine.get_current_version() == 1
            assert 2 not in engine.get_applied_versions()
        finally:
            sys.path.remove(str(tmp_path))
            for key in list(sys.modules):
                if key.startswith(pkg_name):
                    del sys.modules[key]


# ---------------------------------------------------------------------------
# Tests — Migration History
# ---------------------------------------------------------------------------


class TestMigrationHistory:
    def test_history_records_up(self, engine):
        """History should record each up migration."""
        engine.migrate_up()
        history = engine.get_migration_history()
        assert len(history) == 2
        assert all(r.direction == "up" for r in history)
        assert history[0].version == 1
        assert history[1].version == 2

    def test_history_records_down(self, engine):
        """History should record down (rollback) operations too."""
        engine.migrate_up()
        engine.rollback(steps=1)
        history = engine.get_migration_history()
        # 2 ups + 1 down = 3 records
        assert len(history) == 3
        assert history[2].direction == "down"
        assert history[2].version == 2

    def test_history_has_timestamps(self, engine):
        """All history records should have non-empty applied_at."""
        engine.migrate_up()
        history = engine.get_migration_history()
        for record in history:
            assert record.applied_at
            assert "T" in record.applied_at  # ISO-8601 format


# ---------------------------------------------------------------------------
# Tests — Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_before_migrations(self, engine):
        """Status before any migration shows version 0 and pending."""
        status = engine.status()
        assert status["current_version"] == 0
        assert status["available_versions"] == [1, 2]
        assert status["applied_versions"] == []
        assert status["pending_versions"] == [1, 2]

    def test_status_after_full_migration(self, engine):
        """After full migration, no pending versions."""
        engine.migrate_up()
        status = engine.status()
        assert status["current_version"] == 2
        assert status["applied_versions"] == [1, 2]
        assert status["pending_versions"] == []

    def test_status_after_partial_migration(self, engine):
        """After partial migration, shows correct pending."""
        engine.migrate_up(target_version=1)
        status = engine.status()
        assert status["current_version"] == 1
        assert status["applied_versions"] == [1]
        assert status["pending_versions"] == [2]


# ---------------------------------------------------------------------------
# Tests — Round-trip (up → down → up)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_up_down_up_cycle(self, engine, tmp_path):
        """Full cycle: up → down → up should leave DB in correct state."""
        # Up to latest
        engine.migrate_up()
        assert engine.get_current_version() == 2

        # Down to zero
        engine.migrate_down(target_version=0)
        assert engine.get_current_version() == 0

        # Back up to latest
        engine.migrate_up()
        assert engine.get_current_version() == 2

        # Verify table works
        db_path = tmp_path / "test_migrate.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO test_users (name, email) VALUES ('Bob', 'b@b.com')")
        conn.commit()
        row = conn.execute("SELECT name, email FROM test_users").fetchone()
        conn.close()
        assert row[0] == "Bob"
        assert row[1] == "b@b.com"

    def test_selective_rollback_and_reapply(self, engine):
        """Rollback v2, then reapply it."""
        engine.migrate_up()
        engine.rollback(steps=1)
        assert engine.get_current_version() == 1

        applied = engine.migrate_up()
        assert applied == [2]
        assert engine.get_current_version() == 2


# ---------------------------------------------------------------------------
# Tests — Real migration modules (001_baseline, 002_v5_tables)
# ---------------------------------------------------------------------------


class TestRealMigrations:
    """Test the actual migration modules in realize_core/migration/versions/."""

    @pytest.fixture
    def real_engine(self, tmp_path):
        from realize_core.migration.engine import MigrationEngine

        db_path = tmp_path / "real_migrate.db"
        return MigrationEngine(
            db_path=db_path,
            versions_package="realize_core.migration.versions",
        )

    @pytest.fixture
    def latest_version(self, real_engine):
        """Discover the latest available migration version dynamically."""
        versions = real_engine.discover_versions()
        return max(v.version for v in versions)

    def test_real_discover_versions(self, real_engine):
        """Should discover 001_baseline and 002_v5_tables."""
        versions = real_engine.discover_versions()
        nums = [v.version for v in versions]
        assert 1 in nums
        assert 2 in nums

    def test_real_migrate_up_all(self, real_engine, tmp_path, latest_version):
        """Applying all real migrations creates expected tables."""
        applied = real_engine.migrate_up()
        assert 1 in applied
        assert 2 in applied
        assert real_engine.get_current_version() == latest_version

        db_path = tmp_path / "real_migrate.db"
        conn = sqlite3.connect(str(db_path))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()

        # Baseline tables
        assert "activity_events" in tables
        assert "agent_states" in tables
        assert "approval_queue" in tables

        # V5 tables
        assert "skill_executions" in tables
        assert "pipeline_runs" in tables
        assert "routing_decisions" in tables
        assert "storage_sync_log" in tables

    def test_real_rollback_v5_keeps_baseline(self, real_engine, tmp_path, latest_version):
        """Rolling back the last migration keeps all earlier tables."""
        real_engine.migrate_up()
        real_engine.rollback(steps=1)

        assert real_engine.get_current_version() == latest_version - 1

        db_path = tmp_path / "real_migrate.db"
        conn = sqlite3.connect(str(db_path))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()

        # Baseline should remain
        assert "activity_events" in tables
        assert "agent_states" in tables

    def test_real_full_roundtrip(self, real_engine, latest_version):
        """Up all → down all → up all should succeed."""
        real_engine.migrate_up()
        assert real_engine.get_current_version() == latest_version

        real_engine.migrate_down(target_version=0)
        assert real_engine.get_current_version() == 0

        real_engine.migrate_up()
        assert real_engine.get_current_version() == latest_version
