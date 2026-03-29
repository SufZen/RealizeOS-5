"""
Session Startup Brief — Auto-generated situational context at session start.

Generates a brief (< 500 tokens) summarizing:
- Recent activity (last 24h from audit log)
- Pending tasks
- Pending approvals
- Recent KB changes

The brief is prepended to the first message of each session and cached
for the session duration to avoid regeneration on subsequent messages.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Maximum tokens for the brief
MAX_BRIEF_TOKENS = 500
_CHARS_PER_TOKEN = 3.5


def generate_session_brief(
    system_key: str,
    db_path: str | None = None,
    pending_tasks: list[dict[str, Any]] | None = None,
    pending_approvals: list[dict[str, Any]] | None = None,
    recent_kb_changes: list[dict[str, Any]] | None = None,
    recent_audit_entries: list[dict[str, Any]] | None = None,
    lookback_hours: int = 24,
) -> str:
    """
    Generate a situational brief for the start of an agent session.

    Produces a concise summary that orients the agent on what's happening
    in the venture. Sections with no items are omitted to save tokens.

    Args:
        system_key: Venture/system identifier.
        db_path: Path to SQLite database (for querying audit log).
        pending_tasks: List of pending task dicts (title, priority, due_date).
        pending_approvals: List of pending approval dicts (type, requested_by, created_at).
        recent_kb_changes: List of recent KB change dicts (file, action, timestamp).
        recent_audit_entries: List of recent audit log entries (action, details, timestamp).
        lookback_hours: Hours to look back for recent activity.

    Returns:
        Formatted brief string, empty if nothing to report.
    """
    sections: list[str] = []

    # Section 1: Recent Activity (from audit log or provided entries)
    activity_section = _build_activity_section(recent_audit_entries, db_path, system_key, lookback_hours)
    if activity_section:
        sections.append(activity_section)

    # Section 2: Pending Tasks
    tasks_section = _build_tasks_section(pending_tasks)
    if tasks_section:
        sections.append(tasks_section)

    # Section 3: Pending Approvals
    approvals_section = _build_approvals_section(pending_approvals)
    if approvals_section:
        sections.append(approvals_section)

    # Section 4: Recent KB Changes
    kb_section = _build_kb_changes_section(recent_kb_changes)
    if kb_section:
        sections.append(kb_section)

    if not sections:
        return ""

    brief = "## Session Brief\n" + "\n\n".join(sections)

    # Enforce token budget
    max_chars = int(MAX_BRIEF_TOKENS * _CHARS_PER_TOKEN)
    if len(brief) > max_chars:
        brief = brief[:max_chars] + "\n\n[...brief truncated]"

    return brief


def _build_activity_section(
    entries: list[dict[str, Any]] | None,
    db_path: str | None,
    system_key: str,
    lookback_hours: int,
) -> str:
    """Build the recent activity section."""
    items = entries or []

    # If no entries provided, try querying the database
    if not items and db_path:
        items = _query_recent_audit(db_path, system_key, lookback_hours)

    if not items:
        return ""

    lines = [f"**Recent Activity ({lookback_hours}h)**"]
    for entry in items[:5]:  # Limit to 5 most recent
        action = entry.get("action", "unknown")
        details = entry.get("details", "")
        timestamp = entry.get("timestamp", "")
        if timestamp and isinstance(timestamp, str):
            # Show only time portion for brevity
            try:
                ts = datetime.fromisoformat(timestamp)
                timestamp = ts.strftime("%H:%M")
            except (ValueError, TypeError):
                pass
        line = f"- [{timestamp}] {action}"
        if details:
            line += f": {details[:80]}"
        lines.append(line)

    if len(entries or []) > 5:
        lines.append(f"- ...and {len(entries or []) - 5} more")

    return "\n".join(lines)


def _build_tasks_section(tasks: list[dict[str, Any]] | None) -> str:
    """Build the pending tasks section."""
    if not tasks:
        return ""

    lines = [f"**Pending Tasks ({len(tasks)})**"]
    for task in tasks[:5]:
        title = task.get("title", "Untitled")
        priority = task.get("priority", "")
        due = task.get("due_date", "")
        line = f"- {title}"
        if priority:
            line += f" [{priority}]"
        if due:
            line += f" (due: {due})"
        lines.append(line)

    if len(tasks) > 5:
        lines.append(f"- ...and {len(tasks) - 5} more")

    return "\n".join(lines)


def _build_approvals_section(approvals: list[dict[str, Any]] | None) -> str:
    """Build the pending approvals section."""
    if not approvals:
        return ""

    lines = [f"**Pending Approvals ({len(approvals)})**"]
    for approval in approvals[:3]:
        approval_type = approval.get("type", "decision")
        requested_by = approval.get("requested_by", "")
        description = approval.get("description", "")
        line = f"- {approval_type}"
        if requested_by:
            line += f" from {requested_by}"
        if description:
            line += f": {description[:60]}"
        lines.append(line)

    return "\n".join(lines)


def _build_kb_changes_section(changes: list[dict[str, Any]] | None) -> str:
    """Build the recent KB changes section."""
    if not changes:
        return ""

    lines = ["**Recent KB Updates**"]
    for change in changes[:3]:
        file_path = change.get("file", "")
        action = change.get("action", "modified")
        lines.append(f"- {action}: {file_path}")

    return "\n".join(lines)


def _query_recent_audit(
    db_path: str,
    system_key: str,
    lookback_hours: int,
) -> list[dict[str, Any]]:
    """
    Query the audit log table for recent entries.

    Gracefully returns an empty list if the table doesn't exist
    or the query fails.
    """
    try:
        import sqlite3

        cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
        cutoff_str = cutoff.isoformat()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT action, details, timestamp
            FROM audit_log
            WHERE system_key = ?
              AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT 5
            """,
            (system_key, cutoff_str),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.debug("Audit log query skipped: %s", e)
        return []


# ---------------------------------------------------------------------------
# Session-level caching
# ---------------------------------------------------------------------------

_brief_cache: dict[str, str] = {}


def get_or_generate_brief(
    session_id: str,
    system_key: str,
    **kwargs,
) -> str:
    """
    Get a cached brief or generate a new one for this session.

    Each session gets at most one brief generation. Subsequent calls
    within the same session return the cached version.

    Args:
        session_id: Unique session identifier.
        system_key: Venture identifier.
        **kwargs: Additional args passed to generate_session_brief.

    Returns:
        Session brief string (may be empty if nothing to report).
    """
    cache_key = f"{session_id}:{system_key}"
    if cache_key in _brief_cache:
        return _brief_cache[cache_key]

    brief = generate_session_brief(system_key=system_key, **kwargs)
    _brief_cache[cache_key] = brief
    return brief


def clear_brief_cache():
    """Clear the session brief cache (useful for testing)."""
    _brief_cache.clear()
