"""
Skill Creator — meta-skill for creating new skills conversationally.

Allows users to describe what they want, and generates either a
YAML skill or a SKILL.md file.  The creator:

1. Takes a natural-language description of the desired skill
2. Uses an LLM to generate the skill definition
3. Saves it to the venture's skills directory
4. Returns the path and a preview of the created skill

Usage::

    from realize_core.skills.creator import create_skill

    result = await create_skill(
        description="A content review pipeline that uses the writer and reviewer agents",
        output_format="yaml",          # or "skill_md"
        skills_dir=Path("systems/my-biz/R-routines/skills"),
    )
"""
from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Type for the LLM completion callable
LLMCallable = Callable[..., Awaitable[str]]


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_YAML_CREATOR_PROMPT = """You are a skill definition generator for RealizeOS.
Generate a YAML skill definition based on the user's description.

The YAML format supports two versions:
- v1: Simple pipeline (list of agents in sequence)
- v2: Multi-step workflow with step types: agent, tool, condition, human, delegate

Respond ONLY with valid YAML, no markdown code blocks, no explanation.

Example v1:
name: content_pipeline
triggers:
  - write a post
  - create content
task_type: content
pipeline:
  - writer
  - reviewer

Example v2:
name: research_workflow
triggers:
  - research competitors
  - competitive analysis
task_type: research
steps:
  - id: search
    type: tool
    tool: web_search
    params:
      query: "{user_message}"
  - id: analyze
    type: agent
    agent: analyst
    inject_context: [search]
    prompt: "Analyze the search results and provide insights."

Available agents: orchestrator, writer, reviewer, analyst
Available tools: web_search, gmail_send, google_calendar, google_sheets
"""

_SKILL_MD_CREATOR_PROMPT = """You are a skill definition generator for RealizeOS.
Generate a SKILL.md file based on the user's description.

The SKILL.md format uses YAML frontmatter and a markdown body:

```
---
name: skill_name
description: What this skill does
triggers:
  - trigger phrase one
  - trigger phrase two
tags: [category1, category2]
agent: writer
---

# Skill Title

Detailed instructions for how the LLM should execute this skill.

## Context
Explain the context and purpose.

## Steps
1. First step
2. Second step

## Output Format
Describe the expected output format.
```

Available agents: orchestrator, writer, reviewer, analyst

Respond ONLY with the complete SKILL.md content (frontmatter + body).
Do not wrap it in code blocks.
"""


# ---------------------------------------------------------------------------
# Core creation function
# ---------------------------------------------------------------------------

async def create_skill(
    description: str,
    output_format: str = "yaml",
    skills_dir: Path | None = None,
    filename: str | None = None,
    llm_fn: LLMCallable | None = None,
) -> dict[str, Any]:
    """
    Generate a new skill from a natural-language description.

    Args:
        description: Plain English description of the desired skill.
        output_format: ``"yaml"`` or ``"skill_md"``.
        skills_dir: Directory to save the file in. If ``None``,
                     the skill definition is returned but not saved.
        filename: Optional explicit filename (without extension).
        llm_fn: Async LLM callable. If ``None``, uses the default.

    Returns:
        Dict with keys:
        - ``success`` (bool)
        - ``content`` (str) — the generated skill definition
        - ``path`` (str | None) — saved file path, or None
        - ``error`` (str | None) — error message if failed
    """
    if not description or not description.strip():
        return {"success": False, "content": "", "path": None,
                "error": "Description is empty"}

    # Resolve LLM
    if llm_fn is None:
        llm_fn = _get_default_llm()
        if llm_fn is None:
            return {"success": False, "content": "", "path": None,
                    "error": "No LLM available for skill generation"}

    # Select prompt
    if output_format == "skill_md":
        system_prompt = _SKILL_MD_CREATOR_PROMPT
    else:
        system_prompt = _YAML_CREATOR_PROMPT

    # Call LLM
    try:
        content = await llm_fn(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": description}],
        )
    except Exception as exc:
        logger.error("Skill creation LLM call failed: %s", exc)
        return {"success": False, "content": "", "path": None,
                "error": f"LLM call failed: {exc}"}

    # Clean up response — strip any markdown code block wrappers
    content = _clean_generated_content(content, output_format)

    if not content.strip():
        return {"success": False, "content": "", "path": None,
                "error": "LLM returned empty content"}

    # Extract skill name for filename
    skill_name = _extract_skill_name(content, output_format)
    if not skill_name:
        skill_name = "new_skill"

    # Save if directory provided
    saved_path = None
    if skills_dir is not None:
        saved_path = _save_skill_file(
            content=content,
            skill_name=skill_name,
            output_format=output_format,
            skills_dir=skills_dir,
            filename=filename,
        )

    return {
        "success": True,
        "content": content,
        "path": str(saved_path) if saved_path else None,
        "skill_name": skill_name,
        "format": output_format,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_default_llm() -> LLMCallable | None:
    """Attempt to import the default LLM client."""
    try:
        from realize_core.llm.claude_client import call_claude
        return call_claude
    except ImportError:
        pass
    try:
        from realize_core.llm.gemini_client import call_gemini
        return call_gemini
    except ImportError:
        pass
    return None


def _clean_generated_content(content: str, output_format: str) -> str:
    """Remove markdown code block wrappers from LLM output."""
    text = content.strip()

    # Remove ```yaml ... ``` or ```markdown ... ``` wrappers
    lang_tag = "yaml" if output_format == "yaml" else "markdown"
    patterns = [
        rf"^```{lang_tag}\s*\n(.*)\n```\s*$",
        r"^```\s*\n(.*)\n```\s*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

    return text


def _extract_skill_name(content: str, output_format: str) -> str | None:
    """Extract the skill name from generated content."""
    if output_format == "skill_md":
        # Parse from frontmatter
        try:
            from realize_core.skills.md_loader import parse_skill_md
            defn = parse_skill_md(content)
            if defn:
                return defn.key
        except ImportError:
            pass

    # YAML: look for name: field
    match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
    if match:
        name = match.group(1).strip()
        return name.replace("-", "_").replace(" ", "_").lower()

    return None


def _save_skill_file(
    content: str,
    skill_name: str,
    output_format: str,
    skills_dir: Path,
    filename: str | None = None,
) -> Path | None:
    """Save the generated skill to disk."""
    try:
        skills_dir.mkdir(parents=True, exist_ok=True)

        if filename:
            base = filename
        else:
            base = skill_name.replace("-", "_").replace(" ", "_").lower()

        if output_format == "skill_md":
            file_path = skills_dir / f"{base}.skill.md"
        else:
            file_path = skills_dir / f"{base}.yaml"

        # Don't overwrite existing files
        if file_path.exists():
            counter = 1
            while file_path.exists():
                stem = f"{base}_{counter}"
                ext = ".skill.md" if output_format == "skill_md" else ".yaml"
                file_path = skills_dir / f"{stem}{ext}"
                counter += 1

        file_path.write_text(content, encoding="utf-8")
        logger.info("Created skill file: %s", file_path)
        return file_path

    except Exception as exc:
        logger.error("Failed to save skill file: %s", exc)
        return None
