"""Load profession, market and firm packs from disk (spec 010 §4).

Packs are content only. Loading is tolerant: problems become warnings on the
pack, and a broken file never stops the rest of the pack from loading.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from realize_core.packs.models import Pack, RuleCard

logger = logging.getLogger(__name__)

PACK_KINDS = ("profession", "market")


def default_packs_root() -> Path:
    """The repository's ``packs/`` folder."""
    return Path(__file__).resolve().parent.parent.parent / "packs"


def _read_yaml(path: Path, warnings: list[str]) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        warnings.append(f"{path.name}: cannot read ({exc})")
        return None


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = yaml.safe_load(text[3:end]) or {}
    return (meta if isinstance(meta, dict) else {}), text[end + 4 :].lstrip("\n")


def load_rule_card(path: Path, warnings: list[str]) -> RuleCard | None:
    """Parse one rule card. Cards without ``source`` and ``as_of`` are skipped."""
    try:
        meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        warnings.append(f"{path.name}: cannot read rule card ({exc})")
        return None
    missing = [k for k in ("id", "statement", "source", "as_of") if not meta.get(k)]
    if missing:
        warnings.append(f"{path.name}: rule card skipped, missing {', '.join(missing)}")
        return None
    try:
        level = int(meta.get("verification", 1))
    except (TypeError, ValueError):
        level = 1
    return RuleCard(
        id=str(meta["id"]),
        statement=str(meta["statement"]),
        source=str(meta["source"]),
        as_of=str(meta["as_of"]),
        body=body,
        applies_to=meta.get("applies_to") or {},
        review_by=str(meta["review_by"]) if meta.get("review_by") else None,
        verification=max(0, min(4, level)),
        verified_by=meta.get("verified_by"),
        path=path,
    )


def _load_content(pack: Pack, root: Path) -> None:
    """Index the pack folders that share one layout across packs and firm overrides."""
    w = pack.warnings
    glossary_dir = root / "glossary"
    if glossary_dir.is_dir():
        for gfile in sorted(glossary_dir.glob("*.yaml")):
            entries = _read_yaml(gfile, w) or []
            if not isinstance(entries, list):
                w.append(f"{gfile.name}: glossary must be a list")
                continue
            for entry in entries:
                if isinstance(entry, dict) and entry.get("term") and entry.get("family"):
                    pack.terms[str(entry["term"]).casefold()] = {**entry, "language": gfile.stem}
                else:
                    w.append(f"{gfile.name}: glossary entry needs term and family")
    rules_dir = root / "rules"
    if rules_dir.is_dir():
        for rfile in sorted(rules_dir.glob("*.md")):
            card = load_rule_card(rfile, w)
            if card:
                pack.rules[card.id] = card
    docs_dir = root / "documents"
    if docs_dir.is_dir():
        for dfile in sorted(p for p in docs_dir.iterdir() if p.is_file()):
            pack.documents[dfile.stem] = dfile
    skills_dir = root / "R-routines" / "skills"
    if skills_dir.is_dir():
        for sfile in sorted(skills_dir.glob("*.yaml")):
            data = _read_yaml(sfile, w)
            skill_id = (data or {}).get("id") or (data or {}).get("name") or sfile.stem
            pack.skills[str(skill_id)] = sfile
    trust_file = root / "trust.yaml"
    if trust_file.is_file():
        data = _read_yaml(trust_file, w) or {}
        if isinstance(data, dict):
            pack.trust.update({str(k): str(v) for k, v in data.items()})
    measures_file = root / "measures.yaml"
    if measures_file.is_file():
        data = _read_yaml(measures_file, w) or []
        for m in data if isinstance(data, list) else []:
            if isinstance(m, dict) and m.get("id"):
                pack.measures[str(m["id"])] = m
    schemas_dir = root / "schemas"
    if schemas_dir.is_dir():
        for jfile in sorted(schemas_dir.glob("*.json")):
            try:
                pack.schemas[jfile.stem] = json.loads(jfile.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                w.append(f"{jfile.name}: invalid schema ({exc})")


def load_pack(root: Path) -> Pack | None:
    """Load a pack folder with a ``pack.yaml`` manifest. Returns None if unusable."""
    manifest_path = root / "pack.yaml"
    warnings: list[str] = []
    manifest = _read_yaml(manifest_path, warnings) if manifest_path.is_file() else None
    if not isinstance(manifest, dict):
        logger.warning("Pack at %s has no usable pack.yaml", root)
        return None
    kind = manifest.get("kind")
    if kind not in PACK_KINDS or not manifest.get("id") or not manifest.get("version"):
        logger.warning("Pack at %s needs id, version and kind in %s", root, PACK_KINDS)
        return None
    verification = manifest.get("verification") or {}
    level = verification.get("level") if isinstance(verification, dict) else None
    pack = Pack(
        id=str(manifest["id"]),
        kind=kind,
        version=str(manifest["version"]),
        root=root,
        title=str(manifest.get("title", "")),
        languages=list(manifest.get("languages") or []),
        defaults=dict(manifest.get("defaults") or {}),
        verification_level=int(level) if isinstance(level, int) else None,
        limits=list(manifest.get("limits") or []),
        requires=dict(manifest.get("requires") or {}),
        warnings=warnings,
    )
    _load_content(pack, root)
    for msg in pack.warnings:
        logger.warning("Pack %s: %s", pack.ref, msg)
    return pack


def load_firm_layer(venture_dir: Path) -> Pack:
    """Load the firm layer from ``F-foundations/overrides/`` (spec 010 §9.2)."""
    root = venture_dir / "F-foundations" / "overrides"
    pack = Pack(id="firm", kind="firm", version="local", root=root)
    if not root.is_dir():
        return pack
    defaults_file = root / "defaults.yaml"
    if defaults_file.is_file():
        data = _read_yaml(defaults_file, pack.warnings) or {}
        pack.defaults = dict(data) if isinstance(data, dict) else {}
    disable_file = root / "disable.yaml"
    if disable_file.is_file():
        data = _read_yaml(disable_file, pack.warnings) or []
        pack.disabled = {str(x) for x in data} if isinstance(data, list) else set()
    _load_content(pack, root)
    return pack


def discover_packs(packs_root: Path | None = None) -> dict[tuple[str, str], Pack]:
    """All packs under ``packs/<kind>/<id>/``, keyed by ``(kind, id)``."""
    root = packs_root or default_packs_root()
    found: dict[tuple[str, str], Pack] = {}
    for kind in PACK_KINDS:
        kind_dir = root / kind
        if not kind_dir.is_dir():
            continue
        for pack_dir in sorted(p for p in kind_dir.iterdir() if p.is_dir()):
            pack = load_pack(pack_dir)
            if pack is not None:
                found[(pack.kind, pack.id)] = pack
    return found


def read_venture_packs(venture_dir: Path) -> dict[str, list[dict[str, str]]]:
    """Read ``packs.yaml`` at the venture root: ``{"profession": [...], "market": [...]}``."""
    path = venture_dir / "packs.yaml"
    if not path.is_file():
        return {"profession": [], "market": []}
    warnings: list[str] = []
    data = _read_yaml(path, warnings) or {}
    for msg in warnings:
        logger.warning("packs.yaml: %s", msg)
    out: dict[str, list[dict[str, str]]] = {"profession": [], "market": []}
    if not isinstance(data, dict):
        return out
    for kind in PACK_KINDS:
        for entry in data.get(kind) or []:
            if isinstance(entry, str):
                out[kind].append({"id": entry, "version": ""})
            elif isinstance(entry, dict) and entry.get("id"):
                out[kind].append({"id": str(entry["id"]), "version": str(entry.get("version", ""))})
    return out
