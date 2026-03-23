"""
Auto-Prompt Refinement: Improve agent prompts based on feedback.

When the gap detector finds low satisfaction or corrections, this module
analyzes the pattern and suggests prompt improvements. Changes are tracked
with version history for easy rollback.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from realize_core.evolution.analytics import _get_conn

logger = logging.getLogger(__name__)

REFINE_PROMPT = """You are improving an AI agent's system prompt based on user feedback patterns.

Current agent prompt:
---
{current_prompt}
---

Feedback patterns detected:
{feedback_patterns}

Based on these patterns, suggest specific, minimal changes to the prompt.
Do NOT rewrite the entire prompt. Only suggest additions or modifications
to address the feedback patterns.

Respond with a JSON object:
{{
  "changes": [
    {{
      "type": "add" | "modify",
      "location": "where in the prompt (beginning/end/after section X)",
      "content": "the text to add or the modified text",
      "reason": "why this change addresses the feedback"
    }}
  ],
  "summary": "one-line summary of all changes"
}}
"""


async def suggest_prompt_refinement(
    system_key: str,
    agent_key: str,
    feedback_patterns: list[str],
    kb_path: str = ".",
    system_config: dict = None,
) -> dict | None:
    """
    Analyze feedback patterns and suggest prompt improvements.

    Returns dict with suggested changes, or None if no changes needed.
    """
    from realize_core.llm.claude_client import call_claude

    agents = (system_config or {}).get("agents", {})
    prompt_path = agents.get(agent_key)
    if not prompt_path:
        return None

    full_path = Path(kb_path) / prompt_path
    if not full_path.exists():
        return None

    current_prompt = full_path.read_text(encoding="utf-8")
    if len(current_prompt) > 4000:
        current_prompt = current_prompt[:4000] + "\n... (truncated)"

    prompt = REFINE_PROMPT.format(
        current_prompt=current_prompt,
        feedback_patterns="\n".join(f"- {p}" for p in feedback_patterns[:10]),
    )

    try:
        response = await call_claude(
            system_prompt=prompt,
            messages=[{"role": "user", "content": "Suggest improvements."}],
            max_tokens=600,
        )

        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        result = json.loads(text)
        result["system_key"] = system_key
        result["agent_key"] = agent_key
        result["prompt_path"] = str(prompt_path)
        return result

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Prompt refinement parsing failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Prompt refinement failed: {e}")
        return None


async def apply_prompt_refinement(refinement: dict, kb_path: str = ".") -> str:
    """Apply a prompt refinement by modifying the agent's prompt file."""
    prompt_path = refinement.get("prompt_path")
    if not prompt_path:
        return "No prompt path specified."

    full_path = Path(kb_path) / prompt_path
    if not full_path.exists():
        return f"Prompt file not found: {full_path}"

    current_content = full_path.read_text(encoding="utf-8")

    # Save backup
    backup_path = full_path.with_suffix(f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    backup_path.write_text(current_content, encoding="utf-8")

    modified = current_content
    changes = refinement.get("changes", [])

    for change in changes:
        content = change.get("content", "")
        location = change.get("location", "end")
        if change.get("type") == "add":
            if "beginning" in location.lower():
                modified = content + "\n\n" + modified
            else:
                modified = modified + "\n\n" + content

    full_path.write_text(modified, encoding="utf-8")
    _log_refinement(refinement, str(backup_path))

    from realize_core.prompt.builder import clear_cache

    clear_cache()

    return (
        f"Prompt updated for {refinement.get('agent_key', '?')}. "
        f"Backup at {backup_path.name}. {len(changes)} changes applied."
    )


def _log_refinement(refinement: dict, backup_path: str):
    """Log a prompt refinement to the database."""
    try:
        with _get_conn() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT INTO evolution_suggestions
                (timestamp, suggestion_type, title, description, action_data, status)
                VALUES (?, 'prompt_refinement', ?, ?, ?, 'applied')
            """,
                (
                    now,
                    f"Prompt refined: {refinement.get('agent_key', '?')}",
                    refinement.get("summary", "Prompt updated"),
                    json.dumps({"backup": backup_path, **refinement}),
                ),
            )
    except Exception as e:
        logger.debug(f"Failed to log refinement: {e}")


def format_refinement_preview(refinement: dict) -> str:
    """Format a refinement suggestion for display."""
    agent = refinement.get("agent_key", "?")
    system = refinement.get("system_key", "?")
    summary = refinement.get("summary", "")
    changes = refinement.get("changes", [])

    lines = [f"**Prompt Refinement: {system}/{agent}**", f"_{summary}_\n"]
    for i, change in enumerate(changes, 1):
        lines.append(
            f"  {i}. [{change.get('type', '?')}] {change.get('reason', '')}\n     `{change.get('content', '')[:100]}`"
        )
    return "\n".join(lines)
