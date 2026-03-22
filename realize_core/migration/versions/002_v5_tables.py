"""
Migration 002 — V5 operational tables.

Adds new tables required by RealizeOS V5 features:

- ``skill_executions``   — tracks each skill run for analytics
- ``pipeline_runs``      — tracks agent pipeline executions
- ``routing_decisions``  — records LLM routing choices for observability
- ``storage_sync_log``   — tracks background storage sync operations

These tables support the V5 Skills System, Pipeline Builder,
Routing Analytics, and Storage Sync features (Sprints 2–4).
"""
import sqlite3

VERSION = 2
DESCRIPTION = "V5 tables — skill_executions, pipeline_runs, routing_decisions, storage_sync_log"


def up(conn: sqlite3.Connection) -> None:
    """Create new V5 operational tables."""
    conn.executescript("""
        -- Skill Executions: track every skill invocation for analytics
        CREATE TABLE IF NOT EXISTS skill_executions (
            id TEXT PRIMARY KEY,
            venture_key TEXT NOT NULL,
            skill_key TEXT NOT NULL,
            skill_format TEXT NOT NULL DEFAULT 'yaml'
                CHECK(skill_format IN ('yaml', 'skill_md')),
            trigger_method TEXT NOT NULL DEFAULT 'keyword'
                CHECK(trigger_method IN ('keyword', 'semantic', 'explicit', 'pipeline')),
            trigger_score REAL,
            agent_key TEXT,
            input_message TEXT,
            output_summary TEXT,
            status TEXT NOT NULL DEFAULT 'running'
                CHECK(status IN ('running', 'completed', 'failed', 'cancelled')),
            error_message TEXT,
            duration_ms INTEGER,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            completed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_skill_exec_venture
            ON skill_executions(venture_key, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_skill_exec_skill
            ON skill_executions(skill_key, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_skill_exec_status
            ON skill_executions(status, created_at DESC);


        -- Pipeline Runs: track agent pipeline executions
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id TEXT PRIMARY KEY,
            venture_key TEXT NOT NULL,
            pipeline_name TEXT NOT NULL,
            initiator_agent TEXT,
            status TEXT NOT NULL DEFAULT 'running'
                CHECK(status IN ('running', 'completed', 'failed',
                                 'cancelled', 'awaiting_approval')),
            current_stage TEXT,
            stages_completed INTEGER NOT NULL DEFAULT 0,
            stages_total INTEGER NOT NULL DEFAULT 0,
            context TEXT,
            result TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            completed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_pipeline_runs_venture
            ON pipeline_runs(venture_key, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status
            ON pipeline_runs(status, created_at DESC);


        -- Routing Decisions: record LLM routing for observability
        CREATE TABLE IF NOT EXISTS routing_decisions (
            id TEXT PRIMARY KEY,
            venture_key TEXT NOT NULL,
            agent_key TEXT,
            task_classification TEXT,
            selected_provider TEXT NOT NULL,
            selected_model TEXT NOT NULL,
            routing_reason TEXT,
            alternatives TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            latency_ms INTEGER,
            cost_estimate REAL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
        );

        CREATE INDEX IF NOT EXISTS idx_routing_venture
            ON routing_decisions(venture_key, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_routing_provider
            ON routing_decisions(selected_provider, created_at DESC);


        -- Storage Sync Log: track background sync operations
        CREATE TABLE IF NOT EXISTS storage_sync_log (
            id TEXT PRIMARY KEY,
            sync_type TEXT NOT NULL
                CHECK(sync_type IN ('upload', 'download', 'delete', 'full_sync')),
            source_backend TEXT NOT NULL,
            target_backend TEXT NOT NULL,
            file_key TEXT NOT NULL,
            file_size_bytes INTEGER,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'in_progress', 'completed',
                                 'failed', 'skipped')),
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            completed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_sync_log_status
            ON storage_sync_log(status, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_sync_log_file
            ON storage_sync_log(file_key, created_at DESC);
    """)


def down(conn: sqlite3.Connection) -> None:
    """Drop all V5 tables (destructive — use only in dev/test)."""
    conn.executescript("""
        DROP TABLE IF EXISTS skill_executions;
        DROP TABLE IF EXISTS pipeline_runs;
        DROP TABLE IF EXISTS routing_decisions;
        DROP TABLE IF EXISTS storage_sync_log;
    """)
