"""
Interaction Analytics: Track every request with metadata.

Stores interaction data in SQLite for analysis by the gap detector
and prompt refiner. Lightweight — just logs, doesn't block the response.
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_conn():
    """Get a SQLite connection from the memory store."""
    from realize_core.memory.store import db_connection

    return db_connection()


def init_analytics_tables():
    """Create analytics tables if they don't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interaction_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id TEXT NOT NULL,
                system_key TEXT NOT NULL,
                agent_key TEXT DEFAULT '',
                skill_name TEXT DEFAULT '',
                task_type TEXT DEFAULT '',
                tools_used TEXT DEFAULT '[]',
                intent TEXT DEFAULT '',
                message_preview TEXT DEFAULT '',
                response_length INTEGER DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                satisfaction_signal TEXT DEFAULT '',
                error TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_interaction_ts
            ON interaction_log(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_interaction_system
            ON interaction_log(system_key, timestamp)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evolution_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                suggestion_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                action_data TEXT DEFAULT '{}',
                status TEXT DEFAULT 'pending',
                resolved_at TEXT DEFAULT ''
            )
        """)
    logger.info("Analytics tables initialized")


def log_interaction(
    user_id: str,
    system_key: str,
    message: str,
    response_length: int = 0,
    latency_ms: int = 0,
    agent_key: str = "",
    skill_name: str = "",
    task_type: str = "",
    tools_used: list[str] = None,
    intent: str = "",
    error: str = "",
):
    """Log an interaction to the analytics table. Non-blocking."""
    try:
        with _get_conn() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            preview = message[:200] if message else ""
            conn.execute(
                """
                INSERT INTO interaction_log
                (timestamp, user_id, system_key, agent_key, skill_name, task_type,
                 tools_used, intent, message_preview, response_length, latency_ms, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    now,
                    str(user_id),
                    system_key,
                    agent_key,
                    skill_name,
                    task_type,
                    json.dumps(tools_used or []),
                    intent,
                    preview,
                    response_length,
                    latency_ms,
                    error,
                ),
            )
    except Exception as e:
        logger.debug(f"Analytics log failed (non-fatal): {e}")


def log_satisfaction(user_id: str, signal: str):
    """Update the most recent interaction with a satisfaction signal."""
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                UPDATE interaction_log SET satisfaction_signal = ?
                WHERE user_id = ? AND id = (
                    SELECT id FROM interaction_log WHERE user_id = ?
                    ORDER BY timestamp DESC LIMIT 1
                )
            """,
                (signal, str(user_id), str(user_id)),
            )
    except Exception as e:
        logger.debug(f"Satisfaction log failed (non-fatal): {e}")


def get_interaction_stats(system_key: str = None, days: int = 7) -> dict:
    """Get interaction statistics for the last N days."""
    with _get_conn() as conn:
        where = "WHERE timestamp > datetime('now', ?)"
        params = [f"-{days} days"]
        if system_key:
            where += " AND system_key = ?"
            params.append(system_key)

        stats = {}
        row = conn.execute(f"SELECT COUNT(*) as total FROM interaction_log {where}", params).fetchone()
        stats["total_interactions"] = row["total"]

        rows = conn.execute(
            f"SELECT system_key, COUNT(*) as count FROM interaction_log {where} GROUP BY system_key", params
        ).fetchall()
        stats["by_system"] = {r["system_key"]: r["count"] for r in rows}

        rows = conn.execute(
            f"SELECT task_type, COUNT(*) as count FROM interaction_log {where} AND task_type != '' "
            f"GROUP BY task_type ORDER BY count DESC LIMIT 10",
            params,
        ).fetchall()
        stats["by_task_type"] = {r["task_type"]: r["count"] for r in rows}

        rows = conn.execute(
            f"SELECT skill_name, COUNT(*) as count FROM interaction_log {where} AND skill_name != '' "
            f"GROUP BY skill_name ORDER BY count DESC LIMIT 10",
            params,
        ).fetchall()
        stats["skills_triggered"] = {r["skill_name"]: r["count"] for r in rows}

        error_row = conn.execute(
            f"SELECT COUNT(*) as count FROM interaction_log {where} AND error != ''", params
        ).fetchone()
        stats["error_count"] = error_row["count"]

        rows = conn.execute(
            f"SELECT satisfaction_signal, COUNT(*) as count FROM interaction_log {where} "
            f"AND satisfaction_signal != '' GROUP BY satisfaction_signal",
            params,
        ).fetchall()
        stats["satisfaction"] = {r["satisfaction_signal"]: r["count"] for r in rows}

    return stats


def get_recent_interactions(system_key: str = None, limit: int = 50) -> list[dict]:
    """Get the most recent interactions for analysis."""
    with _get_conn() as conn:
        if system_key:
            rows = conn.execute(
                "SELECT * FROM interaction_log WHERE system_key = ? ORDER BY timestamp DESC LIMIT ?",
                (system_key, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM interaction_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]
