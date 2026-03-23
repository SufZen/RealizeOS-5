"""
Schema migration engine for RealizeOS.

Provides versioned, reversible database migrations with:
- Version tracking via ``migration_history`` table
- Forward (up) and reverse (down) migration support
- Rollback by N steps
- Transaction safety — each migration runs in its own transaction
- Auto-discovery of version modules from the ``versions/`` package

Each migration is a Python module in ``realize_core/migration/versions/``
with the naming convention ``NNN_description.py`` (e.g. ``001_baseline.py``).

Every version module must export:
- ``VERSION: int`` — unique version number (must match filename prefix)
- ``DESCRIPTION: str`` — human-readable summary
- ``up(conn: sqlite3.Connection) -> None`` — forward migration
- ``down(conn: sqlite3.Connection) -> None`` — reverse migration
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MigrationVersion:
    """Metadata for a discovered migration module."""

    version: int
    description: str
    module_name: str

    def load(self):
        """Import and return the migration module."""
        return importlib.import_module(self.module_name)


@dataclass(frozen=True)
class MigrationRecord:
    """A row from the migration history table."""

    version: int
    description: str
    direction: str  # 'up' or 'down'
    applied_at: str  # ISO-8601 timestamp


# ---------------------------------------------------------------------------
# SQL for migration bookkeeping
# ---------------------------------------------------------------------------

_MIGRATION_META_SQL = """
CREATE TABLE IF NOT EXISTS migration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL CHECK(direction IN ('up', 'down')),
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_migration_history_version
    ON migration_history(version);
"""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MigrationEngine:
    """
    Schema migration runner with version tracking, up/down, and rollback.

    Args:
        db_path: Path to the SQLite database file.
                 If ``None``, uses the default from ``realize_core.db.schema``.
        versions_package: Dotted import path to the versions sub-package.
                          Defaults to ``realize_core.migration.versions``.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        versions_package: str = "realize_core.migration.versions",
    ) -> None:
        self._db_path = db_path
        self._versions_package = versions_package
        self._ensure_meta_table()

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Open a connection to the migration database."""
        if self._db_path is not None:
            path = self._db_path
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path), timeout=10)
        else:
            # Fall back to the shared DB helper
            from realize_core.db.schema import get_connection

            conn = get_connection()
            return conn

        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_meta_table(self) -> None:
        """Create the ``migration_history`` table if it doesn't exist."""
        conn = self._get_connection()
        try:
            conn.executescript(_MIGRATION_META_SQL)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Version discovery
    # ------------------------------------------------------------------

    def discover_versions(self) -> list[MigrationVersion]:
        """
        Scan the versions package and return all available migrations,
        sorted by version number ascending.

        Each module must export ``VERSION`` (int) and ``DESCRIPTION`` (str).
        """
        versions: list[MigrationVersion] = []

        try:
            pkg = importlib.import_module(self._versions_package)
        except ImportError as exc:
            logger.error("Failed to import versions package %s: %s", self._versions_package, exc)
            return versions

        for finder, name, _ in pkgutil.iter_modules(pkg.__path__):
            full_name = f"{self._versions_package}.{name}"
            try:
                mod = importlib.import_module(full_name)
                ver = getattr(mod, "VERSION", None)
                desc = getattr(mod, "DESCRIPTION", "")
                if ver is None:
                    logger.warning("Module %s missing VERSION — skipping", full_name)
                    continue
                versions.append(
                    MigrationVersion(
                        version=int(ver),
                        description=desc,
                        module_name=full_name,
                    )
                )
            except Exception as exc:
                logger.error("Failed to inspect module %s: %s", full_name, exc)

        versions.sort(key=lambda v: v.version)
        return versions

    # ------------------------------------------------------------------
    # Version tracking
    # ------------------------------------------------------------------

    def get_current_version(self) -> int:
        """
        Return the current effective schema version.

        Walks the migration history to compute the net state:
        ``up`` increments, ``down`` decrements.  The result is the
        highest version that has been applied and **not** rolled back.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute("SELECT version, direction FROM migration_history ORDER BY id").fetchall()
        finally:
            conn.close()

        applied: set[int] = set()
        for row in rows:
            ver = row["version"] if isinstance(row, sqlite3.Row) else row[0]
            direction = row["direction"] if isinstance(row, sqlite3.Row) else row[1]
            if direction == "up":
                applied.add(ver)
            else:
                applied.discard(ver)

        return max(applied) if applied else 0

    def get_applied_versions(self) -> set[int]:
        """Return the set of currently-applied version numbers."""
        conn = self._get_connection()
        try:
            rows = conn.execute("SELECT version, direction FROM migration_history ORDER BY id").fetchall()
        finally:
            conn.close()

        applied: set[int] = set()
        for row in rows:
            ver = row["version"] if isinstance(row, sqlite3.Row) else row[0]
            direction = row["direction"] if isinstance(row, sqlite3.Row) else row[1]
            if direction == "up":
                applied.add(ver)
            else:
                applied.discard(ver)

        return applied

    def get_migration_history(self) -> list[MigrationRecord]:
        """Return the full ordered migration history."""
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT version, description, direction, applied_at FROM migration_history ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

        return [
            MigrationRecord(
                version=row["version"] if isinstance(row, sqlite3.Row) else row[0],
                description=row["description"] if isinstance(row, sqlite3.Row) else row[1],
                direction=row["direction"] if isinstance(row, sqlite3.Row) else row[2],
                applied_at=row["applied_at"] if isinstance(row, sqlite3.Row) else row[3],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Forward migration
    # ------------------------------------------------------------------

    def migrate_up(self, target_version: int | None = None) -> list[int]:
        """
        Apply all pending ``up`` migrations, in order, up to
        *target_version* (inclusive).  If *target_version* is ``None``,
        migrates to the latest available version.

        Returns:
            List of version numbers that were applied.

        Raises:
            RuntimeError: If a migration's ``up()`` function fails.
        """
        available = self.discover_versions()
        if not available:
            logger.info("No migration versions discovered")
            return []

        if target_version is None:
            target_version = available[-1].version

        applied = self.get_applied_versions()
        pending = [v for v in available if v.version not in applied and v.version <= target_version]

        if not pending:
            logger.debug("No pending migrations (current=%d, target=%d)", self.get_current_version(), target_version)
            return []

        applied_versions: list[int] = []

        for migration in pending:
            mod = migration.load()
            up_fn = getattr(mod, "up", None)
            if up_fn is None:
                raise RuntimeError(f"Migration {migration.module_name} missing up() function")

            conn = self._get_connection()
            try:
                logger.info("Applying migration v%d (%s)...", migration.version, migration.description)
                up_fn(conn)
                conn.execute(
                    "INSERT INTO migration_history (version, description, direction) VALUES (?, ?, 'up')",
                    (migration.version, migration.description),
                )
                conn.commit()
                applied_versions.append(migration.version)
                logger.info("Migration v%d applied successfully", migration.version)
            except Exception as exc:
                conn.rollback()
                logger.error("Migration v%d FAILED — rolled back: %s", migration.version, exc)
                raise RuntimeError(f"Migration v{migration.version} failed: {exc}") from exc
            finally:
                conn.close()

        return applied_versions

    # ------------------------------------------------------------------
    # Reverse migration
    # ------------------------------------------------------------------

    def migrate_down(self, target_version: int) -> list[int]:
        """
        Roll back applied migrations, in reverse order, until
        the current version equals *target_version*.

        Args:
            target_version: The version to roll back **to** (exclusive —
                            this version will remain applied).  Use ``0``
                            to roll back everything.

        Returns:
            List of version numbers that were rolled back.

        Raises:
            RuntimeError: If a migration's ``down()`` function fails.
            ValueError: If *target_version* exceeds the current version.
        """
        current = self.get_current_version()
        if target_version >= current:
            logger.debug("Target version %d >= current %d — nothing to roll back", target_version, current)
            return []

        available = {v.version: v for v in self.discover_versions()}
        applied = self.get_applied_versions()

        # Versions to roll back, in descending order
        to_rollback = sorted(
            [v for v in applied if v > target_version],
            reverse=True,
        )

        rolled_back: list[int] = []

        for ver in to_rollback:
            migration = available.get(ver)
            if migration is None:
                raise RuntimeError(f"Cannot roll back version {ver}: migration module not found")

            mod = migration.load()
            down_fn = getattr(mod, "down", None)
            if down_fn is None:
                raise RuntimeError(f"Migration {migration.module_name} missing down() function")

            conn = self._get_connection()
            try:
                logger.info("Rolling back migration v%d (%s)...", ver, migration.description)
                down_fn(conn)
                conn.execute(
                    "INSERT INTO migration_history (version, description, direction) VALUES (?, ?, 'down')",
                    (ver, migration.description),
                )
                conn.commit()
                rolled_back.append(ver)
                logger.info("Migration v%d rolled back successfully", ver)
            except Exception as exc:
                conn.rollback()
                logger.error("Rollback of v%d FAILED: %s", ver, exc)
                raise RuntimeError(f"Rollback of v{ver} failed: {exc}") from exc
            finally:
                conn.close()

        return rolled_back

    def rollback(self, steps: int = 1) -> list[int]:
        """
        Undo the last *steps* applied migrations.

        Convenience wrapper over :meth:`migrate_down` that computes the
        target version from the current applied set.

        Args:
            steps: Number of migrations to undo.

        Returns:
            List of version numbers that were rolled back.
        """
        if steps < 1:
            return []

        applied = sorted(self.get_applied_versions())
        if not applied:
            logger.debug("No applied migrations to roll back")
            return []

        # Determine target: the version we want to keep
        remaining = applied[:-steps] if steps < len(applied) else []
        target = remaining[-1] if remaining else 0

        return self.migrate_down(target_version=target)

    # ------------------------------------------------------------------
    # Status / info
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """
        Return a summary of the migration state.

        Keys:
            current_version, available_versions, applied_versions,
            pending_versions, history_count
        """
        available = self.discover_versions()
        applied = self.get_applied_versions()
        available_nums = {v.version for v in available}
        pending = sorted(available_nums - applied)

        return {
            "current_version": self.get_current_version(),
            "available_versions": sorted(available_nums),
            "applied_versions": sorted(applied),
            "pending_versions": pending,
            "history_count": len(self.get_migration_history()),
        }
