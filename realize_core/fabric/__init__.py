"""
FABRIC Entity System — The Heart of RealizeOS.

Provides the structured knowledge graph layer: entity parsing, CRUD,
schema validation, reference extraction, and ID generation.

All FABRIC content is markdown-first, git-versioned, and portable.
"""

from realize_core.fabric.entity import FabricEntity
from realize_core.fabric.parser import parse_entity, parse_frontmatter
from realize_core.fabric.writer import write_entity
from realize_core.fabric.id_gen import generate_id
from realize_core.fabric.validator import validate_entity
from realize_core.fabric.refs import extract_refs
from realize_core.fabric.tags import extract_tags

__all__ = [
    "FabricEntity",
    "parse_entity",
    "parse_frontmatter",
    "write_entity",
    "generate_id",
    "validate_entity",
    "extract_refs",
    "extract_tags",
]
