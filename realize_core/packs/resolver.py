"""Run-time cascade over firm, market, profession and core layers (spec 010 §3).

Higher layers win: firm > market > profession > core. Every resolved value
carries its layer, pack reference and, for rule cards, its verification level.
With the ``packs`` feature off, only the firm and core layers are consulted,
which is the behaviour before packs existed.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from realize_core.packs import loader as _loader
from realize_core.packs.loader import discover_packs, load_firm_layer, read_venture_packs
from realize_core.packs.models import ITEM_TYPES, Pack, Resolved

logger = logging.getLogger(__name__)

#: Defaults that hold when no pack sets them.
CORE_DEFAULTS: dict[str, Any] = {"units": "metric"}

_ATTR = {
    "term": "terms",
    "rule": "rules",
    "document": "documents",
    "skill": "skills",
    "trust": "trust",
    "measure": "measures",
    "default": "defaults",
}


def _version_ok(pack: Pack, wanted: str) -> bool:
    return not wanted or wanted == pack.version


class PackResolver:
    """Resolve items for one venture through the layer cascade."""

    def __init__(
        self,
        venture_dir: Path,
        *,
        enabled: bool,
        packs_root: Path | None = None,
        available: dict[tuple[str, str], Pack] | None = None,
    ):
        self.venture_dir = Path(venture_dir)
        self.enabled = enabled
        self.firm = load_firm_layer(self.venture_dir)
        self.layers: list[tuple[str, Pack]] = [("firm", self.firm)]
        self.missing: list[str] = []
        if enabled:
            available = (
                available if available is not None else discover_packs(packs_root or _loader.default_packs_root())
            )
            wanted = read_venture_packs(self.venture_dir)
            for kind in ("market", "profession"):
                for entry in wanted[kind]:
                    pack = available.get((kind, entry["id"]))
                    if pack is None or not _version_ok(pack, entry["version"]):
                        ref = f"{kind}/{entry['id']}@{entry['version'] or '*'}"
                        self.missing.append(ref)
                        logger.warning("Venture %s enables %s, which is not installed", self.venture_dir.name, ref)
                        continue
                    self.layers.append((kind, pack))

    # -- queries ------------------------------------------------------------

    @property
    def packs(self) -> list[Pack]:
        """Enabled packs (market and profession), highest layer first."""
        return [p for layer, p in self.layers if layer != "firm"]

    def _is_disabled(self, key: str) -> bool:
        return key in self.firm.disabled

    def resolve(self, item_type: str, key: str) -> Resolved | None:
        """Resolve one item by key; the highest layer that defines it wins."""
        if item_type not in ITEM_TYPES:
            raise ValueError(f"Unknown item type '{item_type}'")
        lookup = key.casefold() if item_type == "term" else key
        if self._is_disabled(key):
            return None
        for layer, pack in self.layers:
            items = getattr(pack, _ATTR[item_type])
            if lookup in items:
                return self._wrap(item_type, items[lookup], layer, pack)
        if item_type == "default" and key in CORE_DEFAULTS:
            return Resolved(value=CORE_DEFAULTS[key], layer="core")
        return None

    def list(self, item_type: str) -> dict[str, Resolved]:
        """Every item of a type across layers, highest layer winning per key."""
        if item_type not in ITEM_TYPES:
            raise ValueError(f"Unknown item type '{item_type}'")
        out: dict[str, Resolved] = {}
        if item_type == "default":
            out.update({k: Resolved(value=v, layer="core") for k, v in CORE_DEFAULTS.items()})
        for layer, pack in reversed(self.layers):
            for key, value in getattr(pack, _ATTR[item_type]).items():
                out[key] = self._wrap(item_type, value, layer, pack)
        for key in list(out):
            if self._is_disabled(key):
                del out[key]
        return out

    def glossary_lookup(self, term: str) -> Resolved | None:
        """Map a local term to its core family and kind."""
        return self.resolve("term", term)

    def terms_in(self, text: str, limit: int = 20) -> list[Resolved]:
        """Glossary terms that appear in ``text`` (case-insensitive)."""
        folded = text.casefold()
        hits = [r for key, r in self.list("term").items() if key and key in folded]
        return hits[:limit]

    def summary(self) -> dict[str, Any]:
        """JSON-friendly description of the enabled layers."""
        return {
            "enabled": self.enabled,
            "packs": [
                {
                    "id": p.id,
                    "kind": p.kind,
                    "version": p.version,
                    "title": p.title,
                    "verification": p.verification_level,
                    "limits": p.limits,
                    "warnings": p.warnings,
                }
                for p in self.packs
            ],
            "missing": self.missing,
            "firm_overrides": bool(self.firm.root.is_dir()),
        }

    # -- helpers ------------------------------------------------------------

    def _wrap(self, item_type: str, value: Any, layer: str, pack: Pack) -> Resolved:
        pack_ref = None if layer == "firm" else pack.ref
        if item_type == "rule":
            return Resolved(
                value=value,
                layer=layer,  # type: ignore[arg-type]
                pack_id=pack_ref,
                verification=value.effective_level(pack.verification_level),
                source=value.source,
            )
        source = str(value) if isinstance(value, Path) else None
        verification = pack.verification_level if layer == "market" else None
        return Resolved(value=value, layer=layer, pack_id=pack_ref, verification=verification, source=source)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Cached access per venture
# ---------------------------------------------------------------------------

_cache: dict[tuple[str, bool, str], tuple[float, PackResolver]] = {}
_lock = threading.Lock()


def _stamp(venture_dir: Path, packs_root: Path) -> float:
    """Latest modification time of anything the resolver reads."""
    newest = 0.0
    candidates = [venture_dir / "packs.yaml", venture_dir / "F-foundations" / "overrides", packs_root]
    for base in candidates:
        if not base.exists():
            continue
        paths = [base] if base.is_file() else [base, *base.rglob("*")]
        for path in paths:
            try:
                newest = max(newest, path.stat().st_mtime)
            except OSError:
                continue
    return newest


def get_resolver(venture_dir: Path, *, enabled: bool, packs_root: Path | None = None) -> PackResolver:
    """A cached resolver for a venture, rebuilt when any pack or override file changes."""
    venture_dir = Path(venture_dir)
    root = packs_root or _loader.default_packs_root()
    key = (str(venture_dir.resolve()), enabled, str(root))
    stamp = _stamp(venture_dir, root)
    with _lock:
        cached = _cache.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
    resolver = PackResolver(venture_dir, enabled=enabled, packs_root=root)
    with _lock:
        _cache[key] = (stamp, resolver)
    return resolver


def clear_cache() -> None:
    """Drop cached resolvers (tests and config reloads)."""
    with _lock:
        _cache.clear()


def venture_dir_for(kb_path: Path, system_config: dict) -> Path:
    """The venture folder for a system config built by ``build_systems_dict``."""
    return Path(kb_path) / system_config.get("system_dir", "")


# ---------------------------------------------------------------------------
# Prompt context
# ---------------------------------------------------------------------------

MAX_RULES_IN_PROMPT = 8


def build_pack_context(resolver: PackResolver, user_message: str, sources_out: list[dict] | None = None) -> str:
    """Prompt layer with local terms, defaults and the most relevant rule cards.

    Rule cards are numbered ``[R1]…`` and reported to ``sources_out`` with their
    layer and verification level, so the trail can show where a rule came from.
    """
    if not resolver.packs and not resolver.firm.terms and not resolver.firm.rules:
        return ""
    lines = ["## Local context (profession and market packs)"]
    defaults = {k: r.value for k, r in resolver.list("default").items()}
    if defaults:
        lines.append("Defaults: " + ", ".join(f"{k}={v}" for k, v in sorted(defaults.items())))
    for pack in resolver.packs:
        level = pack.verification_level
        tag = f" (verification {level})" if level is not None else ""
        lines.append(f"- {pack.kind} pack {pack.ref}: {pack.title}{tag}")
        for limit in pack.limits:
            lines.append(f"  Limit: {limit}")
    hits = resolver.terms_in(user_message)
    if hits:
        lines.append("Local terms in this message:")
        for r in hits:
            entry = r.value
            kind = f"/{entry['kind']}" if entry.get("kind") else ""
            lines.append(f"- {entry['term']} → {entry['family']}{kind} [{r.label()}]")
    kinds = {r.value.get("kind") for r in hits if r.value.get("kind")}
    rules = list(resolver.list("rule").values())
    relevant = [r for r in rules if set(r.value.applies_to.get("kinds") or []) & kinds] or rules
    relevant = relevant[:MAX_RULES_IN_PROMPT]
    if relevant:
        lines.append(
            "Rules (cite as [R1]…; state the verification level when a rule decides the answer; "
            "level 0-1 means unverified):"
        )
        for i, r in enumerate(relevant, start=1):
            card = r.value
            lines.append(f"[R{i}] {card.statement} (source: {card.source}, as of {card.as_of}; {r.label()})")
            if sources_out is not None:
                sources_out.append(
                    {
                        "id": f"R{i}",
                        "title": card.statement[:120],
                        "path": card.source,
                        "layer": r.layer,
                        "pack": r.pack_id,
                        "verification": r.verification,
                    }
                )
    if not resolver.packs:
        lines.append("No market pack for this venture: local rules are general knowledge (verification 0).")
    return "\n".join(lines)
