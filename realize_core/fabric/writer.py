"""
FABRIC Entity Writer.

Writes FabricEntity objects back to markdown files with YAML frontmatter.
Ensures round-trip fidelity: parse → write → parse produces identical entities.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from realize_core.fabric.entity import FabricEntity


def write_entity(entity: FabricEntity, path: Path | None = None) -> Path:
    """
    Write a FabricEntity to a markdown file.

    Args:
        entity: The entity to write.
        path: Target path (defaults to entity.path).

    Returns:
        The path the file was written to.

    Raises:
        ValueError: If no path is available.
    """
    target = path or entity.path
    if target is None:
        raise ValueError("No path specified for entity write")

    content = entity_to_markdown(entity)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return target


def entity_to_markdown(entity: FabricEntity) -> str:
    """
    Serialize a FabricEntity to markdown string with YAML frontmatter.

    Preserves all frontmatter fields from the original parse,
    updating core fields from the entity's attributes.
    """
    # Start with existing frontmatter, then overlay entity fields
    fm = dict(entity.frontmatter)

    # Core identity (always write)
    if entity.id:
        fm["id"] = entity.id
    if entity.type:
        fm["type"] = entity.type
    if entity.title:
        fm["title"] = entity.title
    if entity.slug:
        fm["slug"] = entity.slug
    if entity.venture:
        fm["venture"] = entity.venture

    # Tags (if present)
    if entity.tags:
        fm["tags"] = entity.tags

    # Provenance
    if entity.source:
        fm["source"] = entity.source
    if entity.created_by:
        fm["created_by"] = entity.created_by
    if entity.created_at:
        fm["created_at"] = entity.created_at.isoformat()
    if entity.last_modified_at:
        fm["last_modified_at"] = entity.last_modified_at.isoformat()
    if entity.last_modified_by:
        fm["last_modified_by"] = entity.last_modified_by

    # Trust signals
    if entity.confidence < 1.0:
        fm["confidence"] = entity.confidence
    if entity.verified:
        fm["verified"] = entity.verified
    if entity.verified_by:
        fm["verified_by"] = entity.verified_by
    if entity.last_verified_at:
        fm["last_verified_at"] = entity.last_verified_at.isoformat()

    # Build markdown
    parts = []

    if fm:
        yaml_str = yaml.dump(
            fm,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ).rstrip("\n")
        parts.append(f"---\n{yaml_str}\n---\n")

    if entity.body:
        parts.append(entity.body)

    return "\n".join(parts) if parts else ""
