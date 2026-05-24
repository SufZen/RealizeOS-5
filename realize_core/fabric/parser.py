"""
FABRIC Markdown Parser.

Parses markdown files with YAML frontmatter into FabricEntity objects.
Handles all three reference mechanisms (wikilinks, XML refs, frontmatter refs)
and extracts tags from both frontmatter and inline XML.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path

import yaml

from realize_core.fabric.entity import FabricEntity
from realize_core.fabric.refs import extract_refs
from realize_core.fabric.tags import extract_tags

logger = logging.getLogger(__name__)

# Regex for YAML frontmatter block: starts and ends with ---
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n?",
    re.DOTALL,
)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Extract YAML frontmatter and body from markdown content.

    Returns:
        Tuple of (frontmatter_dict, body_text). If no frontmatter found,
        returns ({}, full_content).
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    try:
        fm = yaml.safe_load(match.group(1))
        if not isinstance(fm, dict):
            logger.warning("Frontmatter is not a dict, treating as empty")
            return {}, content
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse frontmatter YAML: {e}")
        return {}, content

    body = content[match.end() :]
    return fm, body


def parse_entity(
    path: Path,
    venture: str = "",
    content: str | None = None,
) -> FabricEntity:
    """
    Parse a markdown file into a FabricEntity.

    Args:
        path: Path to the markdown file.
        venture: Venture key (inferred from path if empty).
        content: File content (read from path if None).

    Returns:
        Populated FabricEntity.
    """
    if content is None:
        content = path.read_text(encoding="utf-8")

    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    frontmatter, body = parse_frontmatter(content)

    # Infer venture from path if not provided
    if not venture:
        venture = _infer_venture(path)

    # Extract core fields from frontmatter
    entity_id = frontmatter.get("id", "")
    entity_type = frontmatter.get("type", "")
    title = frontmatter.get("title", "")
    slug = frontmatter.get("slug", "")

    # If no title in frontmatter, use filename
    if not title:
        title = path.stem.replace("-", " ").replace("_", " ").title()

    # If no slug, derive from filename
    if not slug:
        slug = path.stem.lower()

    # Extract provenance
    source = frontmatter.get("source", "manual")
    created_by = frontmatter.get("created_by", "")
    created_at = _parse_datetime(frontmatter.get("created_at"))
    last_modified_at = _parse_datetime(frontmatter.get("last_modified_at"))
    last_modified_by = frontmatter.get("last_modified_by", "")

    # Trust signals
    confidence = float(frontmatter.get("confidence", 1.0))
    verified = bool(frontmatter.get("verified", False))
    verified_by = frontmatter.get("verified_by", "")
    last_verified_at = _parse_datetime(frontmatter.get("last_verified_at"))

    # Extract tags and refs from both frontmatter and body
    tags = extract_tags(frontmatter, body)
    refs = extract_refs(frontmatter, body)

    return FabricEntity(
        id=entity_id,
        type=entity_type,
        title=title,
        slug=slug,
        venture=venture or frontmatter.get("venture", ""),
        path=path,
        frontmatter=frontmatter,
        body=body,
        tags=tags,
        refs=refs,
        source=source,
        created_by=created_by,
        created_at=created_at,
        last_modified_at=last_modified_at,
        last_modified_by=last_modified_by,
        confidence=confidence,
        verified=verified,
        verified_by=verified_by,
        last_verified_at=last_verified_at,
        content_hash=content_hash,
    )


def _infer_venture(path: Path) -> str:
    """Infer venture key from file path (e.g., systems/my-biz/... → my-biz)."""
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "systems" and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def _parse_datetime(value) -> datetime | None:
    """Parse a datetime value from frontmatter (str or datetime)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try ISO 8601 formats
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None
