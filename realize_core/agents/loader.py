"""
Agent Loader — load V1 (.md) and V2 (.yaml) agent definitions.

Supports auto-detection of format based on file extension:
- ``.md``  → V1 markdown agent (parsed into V1AgentDef)
- ``.yaml`` / ``.yml`` → V2 composable agent (parsed into V2AgentDef)

Both formats return type-safe Pydantic model instances.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from realize_core.agents.schema import V1AgentDef, V2AgentDef

logger = logging.getLogger(__name__)

AgentDef = V1AgentDef | V2AgentDef


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_agent(path: Path | str) -> AgentDef:
    """
    Load a single agent definition from a file, auto-detecting the format.

    Args:
        path: Path to an agent ``.md`` or ``.yaml`` file.

    Returns:
        A ``V1AgentDef`` or ``V2AgentDef`` depending on the file type.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file type is unsupported or content is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Agent file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".md":
        return _load_v1(path)
    elif suffix in (".yaml", ".yml"):
        return _load_v2(path)
    else:
        raise ValueError(f"Unsupported agent file type '{suffix}' for {path}. Expected .md (V1) or .yaml/.yml (V2).")


def load_agents_from_directory(directory: Path | str) -> list[AgentDef]:
    """
    Discover and load all agent definitions in a directory.

    Scans for ``.md``, ``.yaml``, and ``.yml`` files (non-recursive).
    Files starting with ``_`` are skipped (e.g. ``_README.md``).

    Args:
        directory: Path to scan for agent files.

    Returns:
        List of loaded agent definitions (V1 or V2).
    """
    directory = Path(directory)
    if not directory.is_dir():
        logger.warning("Agent directory does not exist: %s", directory)
        return []

    agents: list[AgentDef] = []
    for fpath in sorted(directory.iterdir()):
        if fpath.name.startswith("_"):
            continue
        if fpath.suffix.lower() in (".md", ".yaml", ".yml"):
            try:
                agent = load_agent(fpath)
                agents.append(agent)
                logger.debug("Loaded agent '%s' from %s", agent.key, fpath.name)
            except Exception as exc:
                logger.warning("Failed to load agent from %s: %s", fpath, exc)

    return agents


def detect_format(path: Path | str) -> str:
    """
    Detect the agent file format.

    Returns:
        ``"v1"`` for markdown, ``"v2"`` for YAML, or ``"unknown"``.
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".md":
        return "v1"
    elif suffix in (".yaml", ".yml"):
        return "v2"
    return "unknown"


# ---------------------------------------------------------------------------
# V1 Loader (Markdown)
# ---------------------------------------------------------------------------

# Regex to match markdown headers like: ## Role, ## Core Capabilities
_MD_HEADER_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _load_v1(path: Path) -> V1AgentDef:
    """Parse a V1 markdown agent file into a V1AgentDef."""
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"Empty agent file: {path}")

    # Strip YAML frontmatter if present
    fm_match = _FRONTMATTER_RE.match(content)
    if fm_match:
        content = content[fm_match.end() :]

    key = path.stem.replace("-", "_")

    # Extract name from top-level heading
    name_match = re.match(r"^#\s+(.+?)(?:\s*Agent)?\s*$", content, re.MULTILINE)
    name = name_match.group(1).strip() if name_match else key.replace("_", " ").title()

    # Parse sections by ## headers
    sections = _parse_md_sections(content)

    # Extract structured fields
    role = sections.get("role", "")
    personality = sections.get("personality", "")
    capabilities = _extract_list(sections.get("core capabilities", ""))
    operating_rules = _extract_list(sections.get("operating rules", ""))

    return V1AgentDef(
        key=key,
        name=name,
        file_path=str(path),
        raw_content=content,
        role=role,
        personality=personality,
        capabilities=capabilities,
        operating_rules=operating_rules,
    )


def _parse_md_sections(content: str) -> dict[str, str]:
    """Split markdown content into {header_lower: body} sections."""
    sections: dict[str, str] = {}
    parts = _MD_HEADER_RE.split(content)

    # parts = [preamble, header1, body1, header2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        header = parts[i].strip().lower()
        body = parts[i + 1].strip()
        sections[header] = body

    return sections


def _extract_list(text: str) -> list[str]:
    """Extract bullet/numbered list items from markdown text."""
    items = []
    for line in text.splitlines():
        line = line.strip()
        # Match: - item, * item, 1. item, 1) item
        match = re.match(r"^(?:[-*]|\d+[.)]\s*)\s*(.+)$", line)
        if match:
            items.append(match.group(1).strip())
    return items


# ---------------------------------------------------------------------------
# V2 Loader (YAML)
# ---------------------------------------------------------------------------


def _load_v2(path: Path) -> V2AgentDef:
    """Parse a V2 YAML agent file into a V2AgentDef."""
    content = path.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in agent file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Agent YAML must be a mapping, got {type(data).__name__} in {path}")

    # Derive key from filename if not specified
    if "key" not in data:
        data["key"] = path.stem.replace("-", "_")

    # Derive name from key if not specified
    if "name" not in data:
        data["name"] = data["key"].replace("_", " ").title()

    data["file_path"] = str(path)

    return V2AgentDef(**data)
