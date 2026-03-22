"""
Simple migration system for RealizeOS operational database.

Migrations are functions registered in MIGRATIONS dict, keyed by version number.
On startup, any unapplied migrations are run in order.
"""
import logging
import sqlite3
from pathlib import Path

from realize_core.db.schema import get_connection, init_schema

logger = logging.getLogger(__name__)

# Registry of migrations: version -> callable(conn)
# Version 1 is the initial schema (handled by init_schema).
# Add future migrations here as version 2, 3, etc.
MIGRATIONS: dict[int, callable] = {}


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version from the database."""
    try:
        row = conn.execute(
            "SELECT MAX(version) as v FROM schema_version"
        ).fetchone()
        return row["v"] if row and row["v"] else 0
    except sqlite3.OperationalError:
        return 0


def run_migrations(db_path: Path = None):
    """
    Run all pending migrations.

    1. Ensures base schema exists (version 1)
    2. Checks current version
    3. Applies any migrations with version > current
    """
    init_schema(db_path)
    conn = get_connection(db_path)

    try:
        current = get_current_version(conn)
        pending = {v: fn for v, fn in MIGRATIONS.items() if v > current}

        if not pending:
            logger.debug(f"Database at version {current}, no migrations needed")
            return

        for version in sorted(pending.keys()):
            logger.info(f"Running migration v{version}...")
            try:
                pending[version](conn)
                conn.execute(
                    "INSERT INTO schema_version(version) VALUES (?)",
                    (version,),
                )
                conn.commit()
                logger.info(f"Migration v{version} complete")
            except Exception as e:
                conn.rollback()
                logger.error(f"Migration v{version} failed: {e}")
                raise
    finally:
        conn.close()
