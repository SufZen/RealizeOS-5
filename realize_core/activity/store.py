"""
Activity Event Store: read/query layer for persisted activity events.
"""
import logging

from realize_core.db.schema import get_connection

logger = logging.getLogger(__name__)


def query_events(
    venture_key: str = None,
    actor_id: str = None,
    action: str = None,
    limit: int = 50,
    offset: int = 0,
    db_path=None,
) -> list[dict]:
    """
    Query activity events with optional filters.

    Returns events newest-first.
    """
    conn = get_connection(db_path)
    try:
        clauses = []
        params = []

        if venture_key:
            clauses.append("venture_key = ?")
            params.append(venture_key)
        if actor_id:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if action:
            clauses.append("action = ?")
            params.append(action)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM activity_events {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def count_events(venture_key: str = None, db_path=None) -> int:
    """Count total events, optionally filtered by venture."""
    conn = get_connection(db_path)
    try:
        if venture_key:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM activity_events WHERE venture_key = ?",
                (venture_key,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) as c FROM activity_events").fetchone()
        return row["c"]
    finally:
        conn.close()
