"""Data models for profession and market packs (spec 010)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

Layer = Literal["firm", "market", "profession", "core"]

#: Order in which layers win: earlier entries override later ones.
LAYER_ORDER: tuple[Layer, ...] = ("firm", "market", "profession", "core")

#: Item types the resolver understands (spec 010 §3.1).
ITEM_TYPES = ("term", "rule", "document", "skill", "agent", "trust", "measure", "default")

#: Trust levels a pack or firm override may name, from least to most strict.
TRUST_STRICTNESS: dict[str, int] = {"auto": 0, "approve": 1, "block": 2}

VERIFICATION_NAMES = {
    0: "general knowledge",
    1: "drafted",
    2: "reviewed",
    3: "maintained",
    4: "field-proven",
}


@dataclass(frozen=True)
class Resolved:
    """A value resolved through the cascade, with where it came from."""

    value: Any
    layer: Layer
    pack_id: str | None = None
    verification: int | None = None
    source: str | None = None

    def label(self) -> str:
        """Short provenance label, e.g. ``market il@0.1.0 · verification 1 (drafted)``."""
        parts = [self.layer]
        if self.pack_id:
            parts.append(self.pack_id)
        text = " ".join(parts)
        if self.verification is not None:
            text += f" · verification {self.verification} ({VERIFICATION_NAMES.get(self.verification, '?')})"
        return text


@dataclass
class RuleCard:
    """A sourced, dated market or profession fact (spec 010 §4.5)."""

    id: str
    statement: str
    source: str
    as_of: str
    body: str = ""
    applies_to: dict[str, Any] = field(default_factory=dict)
    review_by: str | None = None
    verification: int = 1
    verified_by: str | None = None
    reviewed_at: str | None = None
    path: Path | None = None

    def effective_level(self, pack_level: int | None, today: date | None = None) -> int:
        """Lowest of the card's and the pack's level; an expired review drops it to 1."""
        level = self.verification if pack_level is None else min(self.verification, pack_level)
        if self.review_by:
            try:
                if date.fromisoformat(str(self.review_by)) < (today or date.today()):
                    level = min(level, 1)
            except ValueError:
                level = min(level, 1)
        return level


@dataclass
class Pack:
    """A loaded pack: manifest plus its indexed content."""

    id: str
    kind: Literal["profession", "market", "firm"]
    version: str
    root: Path
    title: str = ""
    languages: list[str] = field(default_factory=list)
    defaults: dict[str, Any] = field(default_factory=dict)
    verification_level: int | None = None
    #: The manifest's ``verification`` block, with the recorded approval state on top.
    verification: dict[str, Any] = field(default_factory=dict)
    #: The approval-recorded verification state applied to this pack, if any (audit N04).
    verification_state: dict[str, Any] | None = None
    limits: list[str] = field(default_factory=list)
    requires: dict[str, Any] = field(default_factory=dict)
    terms: dict[str, dict[str, Any]] = field(default_factory=dict)  # casefolded term -> entry
    rules: dict[str, RuleCard] = field(default_factory=dict)
    documents: dict[str, Path] = field(default_factory=dict)
    skills: dict[str, Path] = field(default_factory=dict)
    #: Agent definitions (``A-agents/*.md``), keyed like venture agents (file stem, ``-`` → ``_``).
    agents: dict[str, Path] = field(default_factory=dict)
    #: The team routing guide (``A-agents/_README.md``), when the pack has one.
    agents_readme: Path | None = None
    #: ``skill-settings.yaml``: per skill id, extra ``triggers`` and (firm layer only) ``variables``.
    skill_settings: dict[str, dict[str, Any]] = field(default_factory=dict)
    trust: dict[str, str] = field(default_factory=dict)
    measures: dict[str, dict[str, Any]] = field(default_factory=dict)
    schemas: dict[str, dict[str, Any]] = field(default_factory=dict)
    disabled: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)

    @property
    def ref(self) -> str:
        """``id@version`` reference used in provenance."""
        return f"{self.id}@{self.version}"
