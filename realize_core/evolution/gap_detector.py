"""
Gap Detection: Analyze interaction logs to find capability gaps.

Identifies:
1. Unhandled requests — no tool or skill matched action intents
2. Repeated patterns — same type of request done ad-hoc 3+ times
3. Failed tool calls — tools that error repeatedly
4. Low satisfaction — corrections, retries, negative feedback

Outputs structured "evolution suggestions" to the suggestions table.
"""
import json
import logging
from collections import Counter
from datetime import datetime

from realize_core.evolution.analytics import get_recent_interactions, _get_conn

logger = logging.getLogger(__name__)


async def run_gap_analysis(days: int = 7) -> list[dict]:
    """
    Analyze recent interactions and generate evolution suggestions.

    Returns list of suggestion dicts.
    """
    suggestions = []
    interactions = get_recent_interactions(limit=200)
    if not interactions:
        return suggestions

    suggestions.extend(_detect_unhandled_requests(interactions))
    suggestions.extend(_detect_repeated_patterns(interactions))
    suggestions.extend(_detect_tool_failures(interactions))
    suggestions.extend(_detect_low_satisfaction(interactions))

    if suggestions:
        _store_suggestions(suggestions)
        logger.info(f"Gap analysis complete: {len(suggestions)} suggestions generated")

    return suggestions


def _detect_unhandled_requests(interactions: list[dict]) -> list[dict]:
    """Find interactions where the system likely couldn't fulfill the request."""
    suggestions = []
    unhandled = []

    for ix in interactions:
        if ix.get("error"):
            unhandled.append(ix["message_preview"])
            continue
        tools = json.loads(ix.get("tools_used", "[]"))
        if not tools and not ix.get("skill_name") and ix.get("intent") in ("research", "act"):
            unhandled.append(ix["message_preview"])

    if len(unhandled) >= 3:
        samples = unhandled[:10]
        suggestions.append({
            "type": "unhandled_requests",
            "title": f"{len(unhandled)} potentially unhandled requests",
            "description": (
                f"Found {len(unhandled)} requests that may not have been fully addressed. "
                f"Samples: {'; '.join(t[:60] for t in samples[:3])}"
            ),
            "action_data": {"samples": samples},
        })

    return suggestions


def _detect_repeated_patterns(interactions: list[dict]) -> list[dict]:
    """Find repeated ad-hoc requests that could become skills."""
    suggestions = []
    adhoc_types = Counter()
    adhoc_samples = {}

    for ix in interactions:
        if not ix.get("skill_name") and ix.get("task_type"):
            task_type = ix["task_type"]
            adhoc_types[task_type] += 1
            if task_type not in adhoc_samples:
                adhoc_samples[task_type] = []
            if len(adhoc_samples[task_type]) < 5:
                adhoc_samples[task_type].append(ix["message_preview"])

    for task_type, count in adhoc_types.most_common(5):
        if count >= 3:
            suggestions.append({
                "type": "repeated_pattern",
                "title": f"'{task_type}' requested {count} times without a skill",
                "description": (
                    f"The task type '{task_type}' was triggered {count} times "
                    f"without matching any skill. Consider creating a skill for this."
                ),
                "action_data": {"task_type": task_type, "count": count,
                                "samples": adhoc_samples.get(task_type, [])},
            })

    return suggestions


def _detect_tool_failures(interactions: list[dict]) -> list[dict]:
    """Find tools that fail repeatedly."""
    suggestions = []
    error_tools = Counter()
    for ix in interactions:
        if ix.get("error"):
            for tool in json.loads(ix.get("tools_used", "[]")):
                error_tools[tool] += 1

    for tool, count in error_tools.most_common(3):
        if count >= 2:
            suggestions.append({
                "type": "tool_failure",
                "title": f"Tool '{tool}' failed {count} times",
                "description": f"The tool '{tool}' has encountered errors {count} times. Check configuration.",
                "action_data": {"tool": tool, "error_count": count},
            })

    return suggestions


def _detect_low_satisfaction(interactions: list[dict]) -> list[dict]:
    """Find areas with low satisfaction signals."""
    suggestions = []
    low_sat = Counter()
    for ix in interactions:
        if ix.get("satisfaction_signal") in ("retry", "correction", "negative"):
            low_sat[ix["system_key"]] += 1

    for system, count in low_sat.most_common(3):
        if count >= 3:
            suggestions.append({
                "type": "low_satisfaction",
                "title": f"{system}: {count} negative satisfaction signals",
                "description": (
                    f"System '{system}' received {count} negative signals. "
                    f"Review recent interactions for improvement areas."
                ),
                "action_data": {"system_key": system, "signal_count": count},
            })

    return suggestions


def _store_suggestions(suggestions: list[dict]):
    """Store evolution suggestions in the database."""
    with _get_conn() as conn:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for s in suggestions:
            conn.execute("""
                INSERT INTO evolution_suggestions
                (timestamp, suggestion_type, title, description, action_data, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            """, (now, s["type"], s["title"], s["description"],
                  json.dumps(s.get("action_data", {}))))


def get_pending_suggestions() -> list[dict]:
    """Get all pending evolution suggestions."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM evolution_suggestions WHERE status = 'pending' ORDER BY timestamp DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_suggestion(suggestion_id: int, status: str = "approved"):
    """Mark a suggestion as approved, dismissed, or applied."""
    with _get_conn() as conn:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE evolution_suggestions SET status = ?, resolved_at = ? WHERE id = ?",
            (status, now, suggestion_id),
        )


def format_suggestions_overview(suggestions: list[dict]) -> str:
    """Format suggestions for display."""
    if not suggestions:
        return "No pending evolution suggestions. The system is running well."
    lines = [f"**Evolution Suggestions ({len(suggestions)}):**\n"]
    for s in suggestions:
        icon = {"unhandled_requests": "?", "repeated_pattern": "->",
                "tool_failure": "!", "low_satisfaction": "~"}.get(s["suggestion_type"], "*")
        lines.append(f"  {icon} **#{s['id']}** [{s['suggestion_type']}]\n"
                     f"    {s['title']}\n    _{s['description'][:120]}_")
    return "\n".join(lines)
