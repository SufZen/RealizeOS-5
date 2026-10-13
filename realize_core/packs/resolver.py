"""Run-time cascade over firm, market, profession and core layers (spec 010 §3).

Higher layers win: firm > market > profession > core. Every resolved value
carries its layer, pack reference and, for rule cards, its verification level.
With the ``packs`` feature off, only the firm and core layers are consulted,
which is the behaviour before packs existed.

Only the packs a venture names in ``packs.yaml`` are loaded, so a broken pack
the venture doesn't use can't stop its context (audit N06).
"""

from __future__ import annotations

import logging
import stat
import threading
from pathlib import Path
from typing import Any

from realize_core.packs import loader as _loader
from realize_core.packs import state as _state
from realize_core.packs.loader import load_firm_layer, read_venture_packs
from realize_core.packs.models import ITEM_TYPES, Pack, Resolved

logger = logging.getLogger(__name__)

#: Defaults that hold when no pack sets them.
CORE_DEFAULTS: dict[str, Any] = {"units": "metric"}

_ATTR = {
    "term": "terms",
    "rule": "rules",
    "document": "documents",
    "skill": "skills",
    "agent": "agents",
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
        self._disabled = {item.casefold() for item in self.firm.disabled}
        self.layers: list[tuple[str, Pack]] = [("firm", self.firm)]
        self.missing: list[str] = []
        if enabled:
            wanted = read_venture_packs(self.venture_dir)
            for kind in ("market", "profession"):
                for entry in wanted[kind]:
                    if available is not None:
                        pack = available.get((kind, entry["id"]))
                    else:
                        pack = _loader.find_pack(kind, entry["id"], packs_root)
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

    def is_disabled(self, key: str) -> bool:
        """True when the firm switched ``key`` off in ``disable.yaml`` (ids compared case-insensitively)."""
        return key.casefold() in self._disabled

    def resolve(self, item_type: str, key: str) -> Resolved | None:
        """Resolve one item by key; the highest layer that defines it wins."""
        if item_type not in ITEM_TYPES:
            raise ValueError(f"Unknown item type '{item_type}'")
        lookup = key.casefold() if item_type == "term" else key
        if self.is_disabled(key):
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
            if self.is_disabled(key):
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
                    "verification_recorded": p.verification_state is not None,
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

_cache: dict[tuple, tuple[tuple, PackResolver]] = {}
_lock = threading.Lock()


def _tree_fingerprint(base: Path) -> list[tuple]:
    """Path, size, modification time and file id of every file under ``base`` (or of ``base`` itself)."""
    try:
        if base.is_file():
            paths = [base]
        elif base.is_dir():
            paths = sorted(base.rglob("*"))
        else:
            return [(str(base), "absent")]
    except OSError as exc:
        return [(str(base), "unreadable", str(exc))]
    out: list[tuple] = []
    for path in paths:
        try:
            st = path.stat()
        except OSError:
            out.append((str(path), "gone"))
            continue
        if not stat.S_ISDIR(st.st_mode):
            out.append((str(path), st.st_size, st.st_mtime_ns, st.st_ino))
    return out


def fingerprint(venture_dir: Path, roots: list[Path], *, enabled: bool) -> tuple:
    """Everything a resolver for this venture reads, file by file (audit N07).

    The venture's ``packs.yaml`` and firm overrides, every file in every pack
    root (when packs are on) and the recorded verification state. Any edit,
    addition or deletion changes it, whatever the other files' timestamps,
    unlike the newest-modification-time stamp it replaces.
    """
    venture_dir = Path(venture_dir)
    entries: list[tuple] = []
    bases = [venture_dir / "packs.yaml", venture_dir / "F-foundations" / "overrides"]
    if enabled:
        bases += roots
    for base in bases:
        entries.extend(_tree_fingerprint(base))
    if enabled:
        entries.append(("verification-state", _state.fingerprint()))
    return tuple(entries)


def get_resolver(venture_dir: Path, *, enabled: bool, packs_root: Path | None = None) -> PackResolver:
    """A cached resolver for a venture, rebuilt when any file it reads changes."""
    venture_dir = Path(venture_dir)
    roots = _loader.pack_roots(packs_root)
    key = (str(venture_dir.resolve()), enabled, tuple(str(r) for r in roots))
    stamp = fingerprint(venture_dir, roots, enabled=enabled)
    with _lock:
        cached = _cache.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
    resolver = PackResolver(venture_dir, enabled=enabled, packs_root=packs_root)
    with _lock:
        _cache[key] = (stamp, resolver)
    return resolver


def clear_cache() -> None:
    """Drop cached resolvers and the cached verification state (tests and config reloads)."""
    with _lock:
        _cache.clear()
    _state.clear_cache()


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
    layer, pack, verification level and dates, so the trail can show where a
    rule came from and how far it has been checked.
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
                        "as_of": card.as_of,
                        "review_by": card.review_by,
                    }
                )
    if not resolver.packs:
        lines.append("No market pack for this venture: local rules are general knowledge (verification 0).")
    return "\n".join(lines)
