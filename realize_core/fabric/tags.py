"""
FABRIC Semantic Tag Extraction.

Extracts tags from two sources:
1. Frontmatter `tags` field (explicit)
2. Inline XML semantic tags: <tag>value</tag>
"""

from __future__ import annotations

import re

# Inline XML tag pattern: <tag>value</tag>
_INLINE_TAG_RE = re.compile(r"<tag>([^<]+)</tag>", re.IGNORECASE)


def extract_tags(frontmatter: dict, body: str) -> list[str]:
    """
    Extract all tags from frontmatter and inline XML.

    Returns a deduplicated, sorted list of tags.
    """
    tags: set[str] = set()

    # 1. Frontmatter tags
    fm_tags = frontmatter.get("tags", [])
    if isinstance(fm_tags, list):
        for tag in fm_tags:
            if isinstance(tag, str) and tag.strip():
                tags.add(tag.strip().lower())
    elif isinstance(fm_tags, str):
        # Support comma-separated string
        for tag in fm_tags.split(","):
            if tag.strip():
                tags.add(tag.strip().lower())

    # 2. Inline XML tags from body
    for match in _INLINE_TAG_RE.finditer(body):
        tag_value = match.group(1).strip().lower()
        if tag_value:
            tags.add(tag_value)

    return sorted(tags)
