"""
Memory consolidation — extract key facts from daily conversations.

Runs nightly (or on-demand) to:
1. Gather all conversations from the past period
2. Use LLM to extract structured facts, decisions, and action items
3. Store as permanent memories in the memory DB
4. Optionally write summaries to KB files (insights/learning-log.md)
"""
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


async def consolidate_memories(
    system_key: str = "",
    days: int = 1,
    kb_path: Path = None,
    system_config: dict = None,
) -> dict:
    """
    Extract key facts from recent conversations and store as memories.

    Args:
        system_key: Venture key (empty = all ventures)
        days: How many days back to look
        kb_path: Root KB path (for writing summaries to files)
        system_config: Venture config (for finding insights dir)

    Returns:
        {facts_extracted, memories_stored, summary}
    """
    from realize_core.memory.conversation import get_history_with_timestamps

    # Gather recent conversations
    conversations = []
    try:
        history = get_history_with_timestamps(system_key or "default", "api-user")
        if not history:
            history = get_history_with_timestamps(system_key or "default", "dashboard-user")

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for msg in history:
            ts = msg.get("timestamp", "")
            if ts:
                try:
                    msg_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if msg_time >= cutoff:
                        conversations.append(msg)
                except (ValueError, TypeError):
                    conversations.append(msg)
            else:
                conversations.append(msg)
    except Exception as e:
        logger.warning(f"Failed to load conversations: {e}")

    if not conversations:
        return {"facts_extracted": 0, "memories_stored": 0, "summary": "No recent conversations to consolidate."}

    # Build conversation text for LLM
    conv_text = ""
    for msg in conversations[-50:]:  # Limit to last 50 messages
        role = msg.get("role", "unknown")
        content = msg.get("content", "")[:500]
        conv_text += f"[{role}]: {content}\n"

    # Use LLM to extract facts
    facts = await _extract_facts_with_llm(conv_text, system_key)

    if not facts:
        return {"facts_extracted": 0, "memories_stored": 0, "summary": "No notable facts extracted."}

    # Store facts as memories
    stored = 0
    try:
        from realize_core.memory.store import store_memory
        for fact in facts:
            store_memory(
                system_key=system_key or "shared",
                category=fact.get("category", "fact"),
                content=fact.get("content", ""),
                tags=fact.get("tags", []),
            )
            stored += 1
    except Exception as e:
        logger.warning(f"Failed to store memories: {e}")

    # Write daily summary to insights dir if configured
    summary_text = _format_summary(facts, system_key, days)
    if kb_path and system_config:
        _write_to_insights(summary_text, kb_path, system_config)

    return {
        "facts_extracted": len(facts),
        "memories_stored": stored,
        "summary": summary_text,
    }


async def _extract_facts_with_llm(conv_text: str, system_key: str) -> list[dict]:
    """Use LLM to extract structured facts from conversation text."""
    prompt = f"""Analyze these conversations and extract key facts, decisions, and action items.

Return a JSON array of objects, each with:
- "content": the fact/decision/action (one sentence)
- "category": one of "fact", "decision", "action_item", "preference", "learning"
- "tags": list of relevant tags

Only extract genuinely useful information. Skip small talk and pleasantries.

Conversations:
{conv_text}

Return ONLY a JSON array, no other text."""

    try:
        from realize_core.llm.router import route_to_llm
        response = await route_to_llm(
            system_prompt="You are a fact extraction assistant. Return only valid JSON.",
            messages=[{"role": "user", "content": prompt}],
            task_type="simple",
            system_key=system_key,
        )

        import json
        # Try to parse JSON from response
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        facts = json.loads(text)
        if isinstance(facts, list):
            return facts[:20]  # Cap at 20 facts
    except Exception as e:
        logger.warning(f"LLM fact extraction failed: {e}")

    return []


def _format_summary(facts: list[dict], system_key: str, days: int) -> str:
    """Format facts into a readable summary."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [f"## Consolidation Summary — {date_str}"]
    if system_key:
        lines.append(f"Venture: {system_key}")
    lines.append(f"Period: last {days} day(s)")
    lines.append(f"Facts extracted: {len(facts)}")
    lines.append("")

    categories = {}
    for fact in facts:
        cat = fact.get("category", "other")
        categories.setdefault(cat, []).append(fact["content"])

    for cat, items in categories.items():
        lines.append(f"### {cat.replace('_', ' ').title()}")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def _write_to_insights(summary: str, kb_path: Path, system_config: dict):
    """Append consolidation summary to the learning log."""
    insights_dir = system_config.get("insights_dir", "")
    if not insights_dir:
        return

    log_path = kb_path / insights_dir / "learning-log.md"
    try:
        existing = ""
        if log_path.exists():
            existing = log_path.read_text(encoding="utf-8")

        if not existing:
            existing = "# Learning Log\n\nAuto-generated insights from memory consolidation.\n\n"

        # Append new summary at the top (after header)
        header_end = existing.find("\n\n", existing.find("\n")) + 2
        if header_end < 2:
            header_end = len(existing)

        updated = existing[:header_end] + summary + "\n---\n\n" + existing[header_end:]
        log_path.write_text(updated, encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to write to insights: {e}")
