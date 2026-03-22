"""
SKILL.md loader — parse Anthropic-inspired markdown skill definitions.

SKILL.md format::

    ---
    name: skill_name
    description: What this skill does
    triggers:
      - keyword one
      - keyword two
    tags: [content, writing]
    version: "1"
    agent: writer
    ---

    # Skill Title

    Instructions for the LLM on how to execute this skill.

    ## Steps
    1. First, analyse the user's request
    2. Then produce output in the specified format

    ## Output Format
    Return the result as markdown.

The loader:
- Parses YAML frontmatter (between ``---`` markers)
- Extracts the markdown body (everything after the second ``---``)
- Returns a ``SkillMdDefinition`` dataclass
- Supports scanning directories for ``SKILL.md`` or ``*.skill.md`` files
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Pattern to match YAML frontmatter between --- markers
_FRONTMATTER_RE = re.compile(
    r"\A\s*---\s*\n(.*?)\n---\s*\n?(.*)",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SkillMdDefinition:
    """
    Parsed representation of a SKILL.md file.

    Attributes:
        name: Unique skill identifier (from frontmatter ``name``).
        description: Human-readable summary.
        triggers: List of keyword trigger phrases.
        tags: Optional categorisation tags.
        version: Skill version string.
        agent: Default agent to execute with (e.g. ``writer``).
        instructions: The full markdown body — LLM execution instructions.
        frontmatter: Raw frontmatter dict (for any extra fields).
        file_path: Absolute path to the source ``.md`` file.
    """
    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    version: str = "1"
    agent: str = "orchestrator"
    instructions: str = ""
    frontmatter: dict[str, Any] = field(default_factory=dict)
    file_path: str = ""

    @property
    def key(self) -> str:
        """Normalised key derived from the name (snake_case)."""
        return self.name.replace("-", "_").replace(" ", "_").lower()

    def to_skill_dict(self) -> dict[str, Any]:
        """
        Convert to the skill dict format used by ``detector.py`` / ``executor.py``.

        Adds ``_format: 'skill_md'`` so the executor knows to use
        the SKILL.md execution path.
        """
        return {
            "name": self.name,
            "description": self.description,
            "triggers": list(self.triggers),
            "tags": list(self.tags),
            "agent": self.agent,
            "_version": 1,
            "_format": "skill_md",
            "_instructions": self.instructions,
            "_source": self.file_path,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_skill_md(content: str, file_path: str = "") -> SkillMdDefinition | None:
    """
    Parse a SKILL.md string into a ``SkillMdDefinition``.

    Args:
        content: Raw text content of the ``.md`` file.
        file_path: Optional source file path for logging/metadata.

    Returns:
        Parsed definition, or ``None`` if the file has no valid frontmatter
        or is missing a ``name`` field.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        logger.debug("No YAML frontmatter found in %s", file_path or "<string>")
        return None

    frontmatter_raw = match.group(1)
    body = match.group(2).strip()

    try:
        import yaml
        frontmatter = yaml.safe_load(frontmatter_raw)
    except ImportError:
        logger.warning("PyYAML not installed — cannot parse SKILL.md frontmatter")
        return None
    except Exception as exc:
        logger.warning("Failed to parse YAML frontmatter in %s: %s",
                        file_path or "<string>", exc)
        return None

    if not isinstance(frontmatter, dict):
        logger.warning("Frontmatter is not a dict in %s", file_path or "<string>")
        return None

    name = frontmatter.get("name")
    if not name:
        logger.warning("SKILL.md missing 'name' in frontmatter: %s",
                        file_path or "<string>")
        return None

    # Normalise triggers — accept string or list
    raw_triggers = frontmatter.get("triggers", [])
    if isinstance(raw_triggers, str):
        raw_triggers = [raw_triggers]

    # Normalise tags
    raw_tags = frontmatter.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split(",")]

    return SkillMdDefinition(
        name=str(name),
        description=str(frontmatter.get("description", "")),
        triggers=[str(t) for t in raw_triggers],
        tags=[str(t) for t in raw_tags],
        version=str(frontmatter.get("version", "1")),
        agent=str(frontmatter.get("agent", "orchestrator")),
        instructions=body,
        frontmatter=frontmatter,
        file_path=str(file_path),
    )


def load_skill_md_file(path: Path) -> SkillMdDefinition | None:
    """
    Load and parse a single SKILL.md file.

    Args:
        path: Path to the ``.md`` file.

    Returns:
        Parsed definition, or ``None`` on failure.
    """
    try:
        content = path.read_text(encoding="utf-8")
        return parse_skill_md(content, file_path=str(path))
    except Exception as exc:
        logger.warning("Failed to read SKILL.md file %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------

def scan_skill_md_files(
    directory: Path,
    recursive: bool = True,
) -> list[SkillMdDefinition]:
    """
    Scan a directory for SKILL.md files and parse them all.

    Matched filenames:
    - ``SKILL.md`` (exact)
    - ``*.skill.md`` (convention)
    - Any ``.md`` file with YAML frontmatter containing ``name``

    Args:
        directory: Root directory to scan.
        recursive: If ``True``, scan subdirectories too.

    Returns:
        List of successfully parsed definitions.
    """
    if not directory.exists() or not directory.is_dir():
        logger.debug("Skill MD scan directory does not exist: %s", directory)
        return []

    results: list[SkillMdDefinition] = []
    glob_pattern = "**/*.md" if recursive else "*.md"

    for md_file in directory.glob(glob_pattern):
        if not md_file.is_file():
            continue

        # Skip files that are clearly not skills (READMEs, changelogs, etc.)
        name_lower = md_file.name.lower()
        if name_lower in ("readme.md", "changelog.md", "contributing.md",
                           "license.md", "_readme.md"):
            continue

        definition = load_skill_md_file(md_file)
        if definition is not None:
            results.append(definition)
            logger.debug("Loaded SKILL.md: %s from %s",
                         definition.name, md_file)

    logger.info("Scanned %s: found %d SKILL.md definitions", directory, len(results))
    return results
