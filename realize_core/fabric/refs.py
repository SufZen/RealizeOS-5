"""
FABRIC Reference Extraction.

Extracts entity references from three mechanisms:
1. Wikilinks: [[entity-id]]
2. Inline XML refs: <type ref="entity-id"/>
3. Frontmatter refs: structured field values matching ID patterns
"""

from __future__ import annotations

import re

# --- Wikilink pattern: [[entity-id]] or [[entity-id|display text]] ---
_WIKILINK_RE = re.compile(r"\[\[([a-zA-Z0-9][a-zA-Z0-9._-]*)\s*(?:\|[^\]]+)?\]\]")

# --- XML ref pattern: <type ref="entity-id"/> or <type ref="entity-id">...</type> ---
_XML_REF_RE = re.compile(r'<\w+\s+ref="([a-zA-Z0-9][a-zA-Z0-9._-]*)"(?:\s*/>|[^>]*>[^<]*</\w+>)')

# --- Entity ID patterns (for frontmatter value scanning) ---
_ENTITY_ID_PATTERNS = [
    re.compile(r"^dec-\d{4}-\d{2}-[a-z0-9-]+(?:-\d+)?$"),  # decision
    re.compile(r"^m-\d{4}-\d{2}-\d{2}-[a-z0-9-]+(?:-\d+)?$"),  # mission
    re.compile(r"^contact-[a-z0-9-]+$"),  # contact
    re.compile(r"^commitment-\d{4}-\d{2}-[a-z0-9-]+(?:-\d+)?$"),  # commitment
    re.compile(r"^insight-\d{4}-\d{2}-[a-z0-9-]+(?:-\d+)?$"),  # insight
    re.compile(r"^risk-\d{4}-\d{2}-[a-z0-9-]+(?:-\d+)?$"),  # risk
    re.compile(r"^action-[a-z0-9-]+$"),  # action
]

# Frontmatter keys known to contain entity references
_REF_KEYS = {
    "reviewers",
    "ventures",
    "supersedes",
    "superseded_by",
    "followups",
    "related_risks",
    "related_decisions",
    "related_mission",
    "source_mission",
    "source_references",
    "related_actions",
    "renegotiated_to",
    "evidence",
    "produced_entities",
    "by",
    "to",
    "owner",
    "parent_mission",
    "partners",
}


def extract_refs(frontmatter: dict, body: str) -> list[str]:
    """
    Extract all entity references from frontmatter and body.

    Returns a deduplicated list of entity IDs referenced.
    """
    refs: set[str] = set()

    # 1. Wikilinks from body
    for match in _WIKILINK_RE.finditer(body):
        refs.add(match.group(1))

    # 2. XML refs from body
    for match in _XML_REF_RE.finditer(body):
        refs.add(match.group(1))

    # 3. Frontmatter refs (known keys + ID pattern scanning)
    _extract_frontmatter_refs(frontmatter, refs)

    return sorted(refs)


def _extract_frontmatter_refs(data: dict, refs: set[str]) -> None:
    """Recursively scan frontmatter for entity ID references."""
    for key, value in data.items():
        if key in (
            "id",
            "type",
            "title",
            "slug",
            "source",
            "created_by",
            "last_modified_by",
            "verified_by",
            "content_hash",
        ):
            continue  # Skip self-referential fields

        if isinstance(value, str):
            if key in _REF_KEYS or _looks_like_entity_id(value):
                refs.add(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and (key in _REF_KEYS or _looks_like_entity_id(item)):
                    refs.add(item)
        elif isinstance(value, dict):
            _extract_frontmatter_refs(value, refs)


def _looks_like_entity_id(value: str) -> bool:
    """Check if a string matches any known entity ID pattern."""
    return any(pattern.fullmatch(value) for pattern in _ENTITY_ID_PATTERNS)
