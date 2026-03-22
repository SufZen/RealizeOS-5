"""
Scheduled reports — morning briefing, weekly review, daily activity log.

These are pre-built scheduled jobs that aggregate data across the system
and produce summaries. They can be triggered by cron schedules or on-demand
via the dashboard.
"""
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


async def generate_morning_briefing(
    systems: dict,
    kb_path: Path,
    features: dict = None,
) -> str:
    """
    Generate a morning briefing covering all ventures.

    Includes:
    - Pending approvals
    - Agent activity summary (last 24h)
    - Upcoming scheduled tasks
    - Recent evolution suggestions
    - Quick status of each venture
    """
    features = features or {}
    sections = []
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %B %d, %Y")

    sections.append(f"# Morning Briefing — {date_str}\n")

    # 1. Pending approvals
    if features.get("approval_gates"):
        try:
            from realize_core.governance.gates import get_pending_approvals
            pending = get_pending_approvals()
            if pending:
                sections.append(f"## Pending Approvals ({len(pending)})")
                for p in pending[:5]:
                    sections.append(f"- **{p.get('action', 'unknown')}** by {p.get('actor_id', '?')} "
                                   f"in {p.get('venture_key', '?')}")
            else:
                sections.append("## Approvals\nNo pending approvals.")
        except Exception:
            pass

    # 2. Activity summary (last 24h)
    if features.get("activity_log"):
        try:
            from realize_core.activity.store import query_events, count_events
            yesterday = (now - timedelta(hours=24)).isoformat()
            total = count_events(since=yesterday)
            sections.append(f"## Activity (last 24h)\n{total} events recorded.")

            # Per-venture breakdown
            for sys_key in systems:
                count = count_events(venture_key=sys_key, since=yesterday)
                if count > 0:
                    sections.append(f"- **{sys_key}**: {count} events")
        except Exception:
            pass

    # 3. Agent status overview
    if features.get("agent_lifecycle"):
        try:
            from realize_core.db.schema import get_connection
            conn = get_connection()
            rows = conn.execute(
                "SELECT venture_key, status, COUNT(*) as cnt FROM agent_states GROUP BY venture_key, status"
            ).fetchall()
            conn.close()

            if rows:
                sections.append("## Agent Status")
                status_map = {}
                for row in rows:
                    vk = row[0]
                    status_map.setdefault(vk, {})[row[1]] = row[2]
                for vk, statuses in status_map.items():
                    parts = [f"{s}: {c}" for s, c in statuses.items()]
                    sections.append(f"- **{vk}**: {', '.join(parts)}")
        except Exception:
            pass

    # 4. Venture quick status
    sections.append("## Ventures")
    for sys_key, sys_conf in systems.items():
        agent_count = len(sys_conf.get("agents", {}))
        sections.append(f"- **{sys_conf.get('name', sys_key)}** — {agent_count} agents")

    sections.append(f"\n---\n*Generated at {now.strftime('%H:%M UTC')}*")
    return "\n".join(sections)


async def generate_weekly_review(
    systems: dict,
    kb_path: Path,
    features: dict = None,
) -> str:
    """
    Generate a weekly review covering the past 7 days.

    Includes:
    - Total activity count per venture
    - Top actions performed
    - Approval decisions made
    - Evolution suggestions status
    - Memory consolidation summary
    """
    features = features or {}
    sections = []
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()

    sections.append(f"# Weekly Review — Week of {(now - timedelta(days=7)).strftime('%B %d')}\n")

    # Activity totals
    if features.get("activity_log"):
        try:
            from realize_core.activity.store import query_events, count_events
            total = count_events(since=week_ago)
            sections.append(f"## Activity Summary\n{total} total events this week.")

            for sys_key in systems:
                count = count_events(venture_key=sys_key, since=week_ago)
                if count > 0:
                    sections.append(f"- **{sys_key}**: {count} events")

            # Top actions
            events = query_events(limit=200)
            from collections import Counter
            action_counts = Counter(e.get("action", "unknown") for e in events)
            if action_counts:
                sections.append("\n### Top Actions")
                for action, cnt in action_counts.most_common(5):
                    sections.append(f"- {action}: {cnt}")
        except Exception:
            pass

    # Approvals made
    if features.get("approval_gates"):
        try:
            from realize_core.db.schema import get_connection
            conn = get_connection()
            approved = conn.execute(
                "SELECT COUNT(*) FROM approval_queue WHERE status = 'approved' AND updated_at > ?",
                (week_ago,),
            ).fetchone()[0]
            rejected = conn.execute(
                "SELECT COUNT(*) FROM approval_queue WHERE status = 'rejected' AND updated_at > ?",
                (week_ago,),
            ).fetchone()[0]
            conn.close()
            sections.append(f"\n## Approvals\n- Approved: {approved}\n- Rejected: {rejected}")
        except Exception:
            pass

    sections.append(f"\n---\n*Generated at {now.strftime('%Y-%m-%d %H:%M UTC')}*")
    return "\n".join(sections)


async def generate_daily_log(
    systems: dict,
    features: dict = None,
) -> str:
    """
    Generate a daily activity log (silent job — no user notification).

    Returns a structured summary of all events from the past 24 hours.
    """
    features = features or {}
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(hours=24)).isoformat()

    sections = [f"# Daily Log — {now.strftime('%Y-%m-%d')}\n"]

    if features.get("activity_log"):
        try:
            from realize_core.activity.store import query_events
            events = query_events(limit=100)
            sections.append(f"Total events: {len(events)}")

            for event in events[:20]:
                ts = event.get("created_at", "")[:19]
                action = event.get("action", "?")
                actor = event.get("actor_id", "?")
                venture = event.get("venture_key", "?")
                sections.append(f"- [{ts}] {venture}/{actor}: {action}")
        except Exception:
            pass

    return "\n".join(sections)
