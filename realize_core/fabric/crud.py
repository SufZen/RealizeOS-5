"""
FABRIC CRUD Operations.

Create, Read, Update, Delete operations for FABRIC entities.
All operations are filesystem-based with the markdown files as source of truth.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from realize_core.fabric.entity import FabricEntity
from realize_core.fabric.id_gen import generate_id
from realize_core.fabric.parser import parse_entity
from realize_core.fabric.writer import write_entity

logger = logging.getLogger(__name__)

# FABRIC layer directories
FABRIC_LAYERS = {
    "foundations": "F-foundations",
    "agents": "A-agents",
    "brain": "B-brain",
    "routines": "R-routines",
    "insights": "I-insights",
    "creations": "C-creations",
}

# Entity type → default FABRIC layer mapping
_TYPE_TO_LAYER = {
    "decision": "insights",
    "mission": "routines",
    "contact": "brain",
    "commitment": "insights",
    "insight": "insights",
    "risk": "insights",
    "action": "routines",
    "document": "creations",
    "learning": "insights",
}


def create_entity(
    venture_dir: Path,
    entity_type: str,
    title: str,
    body: str = "",
    frontmatter: dict | None = None,
    layer: str = "",
    created_by: str = "user",
    venture: str = "",
) -> FabricEntity:
    """
    Create a new FABRIC entity.

    Args:
        venture_dir: Root directory of the venture (e.g., systems/my-biz).
        entity_type: Entity type (e.g., "decision", "mission").
        title: Human-readable title.
        body: Markdown body content.
        frontmatter: Additional frontmatter fields.
        layer: FABRIC layer override (inferred from type if empty).
        created_by: Actor ID creating this entity.
        venture: Venture key (inferred from path if empty).

    Returns:
        The created FabricEntity.
    """
    frontmatter = frontmatter or {}
    venture = venture or venture_dir.name

    # Generate slug from title
    slug = title.lower().replace(" ", "-").replace("_", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    # Generate stable ID
    entity_id = generate_id(entity_type, slug)

    # Determine target layer
    if not layer:
        layer = _TYPE_TO_LAYER.get(entity_type, "brain")
    layer_dir = FABRIC_LAYERS.get(layer, f"B-brain")

    # Build path
    filename = f"{slug}.md"
    target_path = venture_dir / layer_dir / filename

    # Prevent overwrites
    if target_path.exists():
        # Add sequence number
        seq = 2
        while target_path.exists():
            target_path = venture_dir / layer_dir / f"{slug}-{seq}.md"
            seq += 1

    now = datetime.now()

    # Merge frontmatter
    full_fm = {
        "id": entity_id,
        "type": entity_type,
        "title": title,
        "slug": slug,
        "venture": venture,
        "source": "manual",
        "created_by": created_by,
        "created_at": now.isoformat(),
        **frontmatter,
    }

    entity = FabricEntity(
        id=entity_id,
        type=entity_type,
        title=title,
        slug=slug,
        venture=venture,
        path=target_path,
        frontmatter=full_fm,
        body=body,
        source="manual",
        created_by=created_by,
        created_at=now,
    )

    write_entity(entity)
    logger.info(f"Created entity {entity_id} at {target_path}")
    return entity


def read_entity(path: Path, venture: str = "") -> FabricEntity:
    """
    Read a FABRIC entity from a markdown file.

    Args:
        path: Path to the markdown file.
        venture: Venture key (inferred from path if empty).

    Returns:
        Parsed FabricEntity.
    """
    return parse_entity(path, venture=venture)


def update_entity(
    entity: FabricEntity,
    updates: dict | None = None,
    body: str | None = None,
    modified_by: str = "",
) -> FabricEntity:
    """
    Update an existing FABRIC entity.

    Args:
        entity: The entity to update.
        updates: Frontmatter fields to update.
        body: New body content (None = keep existing).
        modified_by: Actor performing the update.

    Returns:
        The updated entity.
    """
    if updates:
        entity.frontmatter.update(updates)
        # Sync core fields from frontmatter
        if "title" in updates:
            entity.title = updates["title"]
        if "type" in updates:
            entity.type = updates["type"]
        if "tags" in updates:
            entity.tags = updates["tags"]

    if body is not None:
        entity.body = body

    now = datetime.now()
    entity.last_modified_at = now
    entity.last_modified_by = modified_by
    entity.frontmatter["last_modified_at"] = now.isoformat()
    if modified_by:
        entity.frontmatter["last_modified_by"] = modified_by

    write_entity(entity)
    logger.info(f"Updated entity {entity.id}")
    return entity


def delete_entity(entity: FabricEntity) -> bool:
    """
    Delete a FABRIC entity (remove the markdown file).

    Args:
        entity: The entity to delete.

    Returns:
        True if deleted successfully.
    """
    if entity.path is None or not entity.path.exists():
        logger.warning(f"Cannot delete entity {entity.id}: file not found")
        return False

    entity.path.unlink()
    logger.info(f"Deleted entity {entity.id} at {entity.path}")
    return True


def scan_venture(venture_dir: Path, venture: str = "") -> list[FabricEntity]:
    """
    Scan a venture directory and parse all markdown entities.

    Args:
        venture_dir: Root directory of the venture.
        venture: Venture key (inferred from dir name if empty).

    Returns:
        List of all parsed entities.
    """
    venture = venture or venture_dir.name
    entities: list[FabricEntity] = []

    if not venture_dir.exists():
        logger.warning(f"Venture directory not found: {venture_dir}")
        return entities

    for md_file in venture_dir.rglob("*.md"):
        # Skip meta files
        if md_file.name.startswith("_"):
            continue
        # Skip hidden dirs
        if any(part.startswith(".") for part in md_file.relative_to(venture_dir).parts):
            continue

        try:
            entity = parse_entity(md_file, venture=venture)
            entities.append(entity)
        except Exception as e:
            logger.warning(f"Failed to parse {md_file}: {e}")

    logger.info(f"Scanned venture '{venture}': {len(entities)} entities")
    return entities
