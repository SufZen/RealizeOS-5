"""
Migration 005 — Messaging tables (agent-to-agent bus).

Ported from legacy ``realize_core/db/migrations.py`` (v4).

Adds:
- ``agent_messages``   — stores all inter-agent messages
- ``message_channels`` — named broadcast channels
- ``message_channel_subscribers`` — channel membership
- ``message_queues``   — offline delivery queue
"""

import sqlite3

VERSION = 5
DESCRIPTION = "Messaging tables — agent_messages, channels, queues (ported from legacy v4)"


def up(conn: sqlite3.Connection) -> None:
    """Create messaging tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_messages (
            id TEXT PRIMARY KEY,
            sender TEXT NOT NULL,
            target TEXT NOT NULL,
            target_type TEXT NOT NULL CHECK(target_type IN ('agent', 'human', 'channel')),
            target_id TEXT NOT NULL,
            content TEXT NOT NULL,
            system_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'sent'
                CHECK(status IN ('sent', 'delivered', 'read', 'queued', 'failed')),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            delivered_at TEXT,
            read_at TEXT,
            metadata TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_messages_target
            ON agent_messages(target_type, target_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_messages_sender
            ON agent_messages(sender, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_messages_status
            ON agent_messages(status);

        CREATE TABLE IF NOT EXISTS message_channels (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            system_key TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            UNIQUE(name, system_key)
        );

        CREATE TABLE IF NOT EXISTS message_channel_subscribers (
            channel_id TEXT NOT NULL,
            agent_key TEXT NOT NULL,
            subscribed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            PRIMARY KEY (channel_id, agent_key),
            FOREIGN KEY (channel_id) REFERENCES message_channels(id)
        );

        CREATE TABLE IF NOT EXISTS message_queues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT NOT NULL,
            agent_key TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            FOREIGN KEY (message_id) REFERENCES agent_messages(id)
        );

        CREATE INDEX IF NOT EXISTS idx_queue_agent
            ON message_queues(agent_key, created_at);
    """)


def down(conn: sqlite3.Connection) -> None:
    """Drop all messaging tables."""
    conn.executescript("""
        DROP TABLE IF EXISTS message_queues;
        DROP TABLE IF EXISTS message_channel_subscribers;
        DROP TABLE IF EXISTS message_channels;
        DROP TABLE IF EXISTS agent_messages;
    """)
