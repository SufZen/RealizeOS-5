"""
Nightly self-evaluation — the system reviews its own performance.

Runs as a scheduled job to:
1. Analyze today's interactions (response quality, tool usage, errors)
2. Identify patterns (repeated questions, failed requests, slow responses)
3. Generate improvement suggestions -> feeds into evolution inbox
4. Track performance trends over time
"""
import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


async def run_nightly_evaluation(
    systems: dict,
    features: dict = None,
) -> dict:
    """
    Run a nightly self-evaluation of system performance.

    Returns:
        {
            total_events: int,
            errors_found: int,
            suggestions: list[dict],
            summary: str,
        }
    """
    features = features or {}
    now = datetime.now(UTC)
    (now - timedelta(hours=24)).isoformat()
    results = {
        "total_events": 0,
        "errors_found": 0,
        "suggestions": [],
        "summary": "",
    }

    # 1. Gather today's activity events
    events = []
    if features.get("activity_log"):
        try:
            from realize_core.activity.store import query_events
            events = query_events(limit=200)
            results["total_events"] = len(events)
        except Exception as e:
            logger.warning(f"Failed to load events: {e}")

    # 2. Analyze error events
    error_events = [e for e in events if e.get("action", "").endswith("_error") or "error" in e.get("details", "").lower()]
    results["errors_found"] = len(error_events)

    if error_events:
        results["suggestions"].append({
            "type": "error_pattern",
            "priority": "high",
            "title": f"{len(error_events)} errors detected today",
            "description": _summarize_errors(error_events),
            "source": "nightly_review",
        })

    # 3. Detect repeated unanswered patterns
    from collections import Counter
    action_counts = Counter(e.get("action", "") for e in events)

    # Check for high skill_not_found rates
    skill_misses = action_counts.get("skill_not_found", 0)
    if skill_misses >= 3:
        results["suggestions"].append({
            "type": "skill_gap",
            "priority": "medium",
            "title": f"Skill not found {skill_misses} times",
            "description": "Users are requesting capabilities that don't match existing skills. Consider creating new skills for these patterns.",
            "source": "nightly_review",
        })

    # 4. Check agent utilization imbalance
    agent_actions = Counter(e.get("actor_id", "") for e in events if e.get("actor_type") == "agent")
    if agent_actions:
        most_used = agent_actions.most_common(1)[0]
        total_agent_events = sum(agent_actions.values())
        if most_used[1] > total_agent_events * 0.7 and len(agent_actions) > 2:
            results["suggestions"].append({
                "type": "routing_imbalance",
                "priority": "low",
                "title": f"Agent '{most_used[0]}' handles {most_used[1]}/{total_agent_events} events",
                "description": "One agent is handling most of the work. Consider improving routing rules to better distribute tasks.",
                "source": "nightly_review",
            })

    # 5. Check LLM usage patterns
    llm_events = [e for e in events if e.get("action") == "llm_called"]
    if llm_events:
        models_used = Counter()
        for e in llm_events:
            details = e.get("details", "")
            if "gemini" in details.lower():
                models_used["gemini"] += 1
            elif "claude" in details.lower():
                models_used["claude"] += 1
            else:
                models_used["other"] += 1

    # 6. Generate summary
    results["summary"] = _build_summary(results, events, systems)

    # 7. Store suggestions in evolution system
    if results["suggestions"]:
        try:
            from realize_core.evolution.gap_detector import _store_suggestions
            formatted = []
            for s in results["suggestions"]:
                formatted.append({
                    "type": s["type"],
                    "priority": s["priority"],
                    "description": f"{s['title']}: {s['description']}",
                    "source": "nightly_review",
                })
            _store_suggestions(formatted)
            logger.info(f"Nightly review: stored {len(formatted)} suggestions")
        except Exception as e:
            logger.warning(f"Failed to store suggestions: {e}")

    return results


def _summarize_errors(error_events: list[dict]) -> str:
    """Create a human-readable error summary."""
    from collections import Counter
    error_actions = Counter(e.get("action", "unknown") for e in error_events)
    parts = [f"{action} ({count}x)" for action, count in error_actions.most_common(5)]
    return "Error types: " + ", ".join(parts)


def _build_summary(results: dict, events: list, systems: dict) -> str:
    """Build a human-readable summary."""
    lines = [
        f"Nightly Review -- {datetime.now().strftime('%Y-%m-%d')}",
        f"Events processed: {results['total_events']}",
        f"Errors detected: {results['errors_found']}",
        f"Suggestions generated: {len(results['suggestions'])}",
        f"Ventures active: {len(systems)}",
    ]

    if results["suggestions"]:
        lines.append("\nKey findings:")
        for s in results["suggestions"]:
            lines.append(f"  [{s['priority'].upper()}] {s['title']}")

    return "\n".join(lines)
