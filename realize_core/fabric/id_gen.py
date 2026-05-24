"""
FABRIC Stable Entity ID Generator.

Generates immutable IDs for FABRIC entities following the format:
    <type-prefix>-<yyyy-mm>-<slug>-<seq>

Examples:
    dec-2026-05-pricing-001
    m-2026-05-20-find-properties-001
    contact-meirav
    commitment-2026-05-send-rationale-001
    insight-2026-05-funnel-pattern-001
"""

from __future__ import annotations

import re
from datetime import datetime

# Type prefix mapping
_TYPE_PREFIXES = {
    "decision": "dec",
    "mission": "m",
    "contact": "contact",
    "commitment": "commitment",
    "insight": "insight",
    "risk": "risk",
    "action": "action",
    "document": "doc",
    "learning": "learn",
}

_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9]+")


def generate_id(
    entity_type: str,
    slug: str,
    seq: int = 1,
    date: datetime | None = None,
) -> str:
    """
    Generate a stable FABRIC entity ID.

    Args:
        entity_type: Entity type (e.g., "decision", "mission", "contact").
        slug: Human-readable slug (e.g., "pricing-model").
        seq: Sequence number for disambiguation (default 1).
        date: Date for the ID (defaults to now).

    Returns:
        Formatted ID string.
    """
    date = date or datetime.now()
    prefix = _TYPE_PREFIXES.get(entity_type, entity_type[:3])

    # Clean slug: lowercase, alphanumeric + hyphens only
    clean_slug = _SLUG_CLEAN_RE.sub("-", slug.lower()).strip("-")
    if not clean_slug:
        clean_slug = "unnamed"

    # Truncate slug to keep IDs reasonable
    if len(clean_slug) > 40:
        clean_slug = clean_slug[:40].rstrip("-")

    # Contact IDs don't include date
    if entity_type == "contact":
        return f"{prefix}-{clean_slug}"

    # Mission IDs include full date
    if entity_type == "mission":
        date_str = date.strftime("%Y-%m-%d")
        return f"{prefix}-{date_str}-{clean_slug}-{seq:03d}"

    # All other types: year-month
    date_str = date.strftime("%Y-%m")
    return f"{prefix}-{date_str}-{clean_slug}-{seq:03d}"


def parse_id_type(entity_id: str) -> str:
    """
    Infer entity type from its ID prefix.

    Returns empty string if unrecognized.
    """
    _prefix_to_type = {v: k for k, v in _TYPE_PREFIXES.items()}

    parts = entity_id.split("-")
    if not parts:
        return ""

    # Try exact prefix match
    prefix = parts[0]
    return _prefix_to_type.get(prefix, "")
