"""
Migration engine for RealizeOS schema management.

Provides versioned, reversible database migrations with up/down support,
rollback capability, and transaction safety.

Usage:
    from realize_core.migration.engine import MigrationEngine

    engine = MigrationEngine(db_path=Path("realize_data.db"))
    engine.migrate_up()       # Apply all pending migrations
    engine.rollback(steps=1)  # Undo the last migration
"""
from realize_core.migration.engine import MigrationEngine

__all__ = ["MigrationEngine"]
