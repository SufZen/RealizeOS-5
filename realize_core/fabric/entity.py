"""
FabricEntity — The core data structure for all FABRIC knowledge entities.

Every piece of knowledge in RealizeOS (decisions, missions, contacts, insights,
commitments, documents, learnings) is a FabricEntity backed by a markdown file
with YAML frontmatter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class FabricEntity:
    """
    A single FABRIC entity parsed from a markdown file.

    Attributes:
        id: Stable immutable ID (e.g., "dec-2026-05-pricing-001").
        type: Entity type (e.g., "decision", "mission", "contact").
        title: Human-readable title.
        slug: URL-safe identifier (changeable, unlike id).
        venture: Venture key this entity belongs to ("_brand" for global).
        path: Filesystem path to the source markdown file.
        frontmatter: Full parsed YAML frontmatter as a dict.
        body: Markdown body content (everything after frontmatter).
        tags: Tags from frontmatter + inline extraction.
        refs: Entity IDs referenced by this entity.
        source: Origin: "manual" | "agent-generated" | "imported" | "dreaming".
        created_by: Actor ID (e.g., "user-asaf", "agent-maria").
        created_at: Creation timestamp.
        last_modified_at: Last modification timestamp.
        last_modified_by: Actor who last modified.
        confidence: Agent-generated content confidence (0.0-1.0); users = 1.0.
        verified: Whether a human has reviewed this entity.
        content_hash: SHA-256 of the raw file content (for change detection).
    """

    # Core identity
    id: str = ""
    type: str = ""
    title: str = ""
    slug: str = ""
    venture: str = ""

    # File backing
    path: Path | None = None
    frontmatter: dict = field(default_factory=dict)
    body: str = ""

    # Graph data
    tags: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)

    # Provenance
    source: str = "manual"
    created_by: str = ""
    created_at: datetime | None = None
    last_modified_at: datetime | None = None
    last_modified_by: str = ""

    # Trust signals
    confidence: float = 1.0
    verified: bool = False
    verified_by: str = ""
    last_verified_at: datetime | None = None

    # Caching
    content_hash: str = ""

    @property
    def is_agent_generated(self) -> bool:
        """Check if this entity was created by an agent."""
        return self.source in ("agent-generated", "dreaming")

    @property
    def fabric_layer(self) -> str:
        """Infer FABRIC layer from file path."""
        if self.path is None:
            return ""
        parts = self.path.parts
        for part in parts:
            if part.startswith("F-"):
                return "foundations"
            if part.startswith("A-"):
                return "agents"
            if part.startswith("B-"):
                return "brain"
            if part.startswith("R-"):
                return "routines"
            if part.startswith("I-"):
                return "insights"
            if part.startswith("C-"):
                return "creations"
        return ""

    def summary_for_toc(self) -> dict:
        """Return L1 TOC entry for Synapse."""
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "slug": self.slug,
            "venture": self.venture,
            "tags": self.tags,
            "refs": self.refs,
            "layer": self.fabric_layer,
            "source": self.source,
            "confidence": self.confidence,
            "verified": self.verified,
        }

    def __repr__(self) -> str:
        return f"FabricEntity(id={self.id!r}, type={self.type!r}, title={self.title!r})"
