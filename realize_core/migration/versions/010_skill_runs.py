"""
Migration 010 — Durable resume points for paused skills (v5.15, audit F10/F17).

A skill paused at a human step or a held tool step is stored in ``skill_runs``
(one row per paused run, linked to its approval item) instead of a per-user
in-memory dict, so a second paused skill no longer overwrites the first and a
restart no longer loses it. The resume store also creates the table on first
use; this migration records it in the schema history.
"""

import sqlite3

VERSION = 10
DESCRIPTION = "skill_runs: durable resume points for paused skills (v5.15)"


def up(conn: sqlite3.Connection) -> None:
    """Create skill_runs (idempotent)."""
    from realize_core.skills.resume_store import DDL

    conn.executescript(DDL)


def down(conn: sqlite3.Connection) -> None:
    """Drop skill_runs (paused skills are lost)."""
    conn.executescript("DROP TABLE IF EXISTS skill_runs;")
