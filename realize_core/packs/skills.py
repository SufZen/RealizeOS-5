"""Skills a venture gets from its packs, for the skill detector (spec 010 §3.1).

A pack skill is a plain skill file (``R-routines/skills/*.yaml``) that the
detector adds to the venture's own skills when ``features.packs`` is on. It
runs through the same executor, governance gate, approvals and trail as a
skill in the venture's folder: this module only reads and merges content.

Precedence, highest first:

1. the venture's own skills (``systems/<venture>/R-routines/skills/``) and the
   firm's shared skills: a pack skill with the same id or name is left out;
2. firm overrides (``F-foundations/overrides/R-routines/skills/``);
3. market packs;
4. profession packs.

Within the packs the highest layer wins per skill id, and the firm can switch
an id off in ``F-foundations/overrides/disable.yaml``.

``skill-settings.yaml`` (in a pack or in the firm overrides) extends a skill
from a lower layer without copying it: ``triggers`` from every layer are
added, and ``variables`` (sheet and document ids) are taken from the firm
layer only. A pack can't point another pack's skill at different files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from realize_core.packs.loader import LOAD_ERRORS, warn_once
from realize_core.packs.resolver import PackResolver, get_resolver

logger = logging.getLogger(__name__)

#: Keys a skill file may not set to a non-list (detection would fail on them).
_TEXT_LISTS = ("triggers", "negative_triggers")


def _read_skill(path: Path) -> dict[str, Any] | None:
    """Parse one pack skill file, or None (with a warning) when it can't be used."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:  # ValueError covers undecodable bytes
        warn_once("Pack skill %s skipped: cannot read it (%s)", path, exc)
        return None
    if not isinstance(data, dict):
        warn_once("Pack skill %s skipped: a skill must be a mapping", path)
        return None
    for key in _TEXT_LISTS:
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            warn_once("Pack skill %s skipped: %s must be a list", path, key)
            return None
        kept = [str(v) for v in value if isinstance(v, (str, int, float)) and not isinstance(v, bool)]
        if len(kept) != len(value):
            warn_once("Pack skill %s: %s that aren't text were dropped", path, key)
        data[key] = kept
    steps = data.get("steps")
    if steps is not None and not (isinstance(steps, list) and all(isinstance(s, dict) for s in steps)):
        warn_once("Pack skill %s skipped: steps must be a list of mappings", path)
        return None
    if data.get("variables") is not None and not isinstance(data["variables"], dict):
        warn_once("Pack skill %s skipped: variables must be a mapping", path)
        return None
    return data


def _apply_settings(skill: dict[str, Any], keys: set[str], resolver: PackResolver, venture: str) -> None:
    """Add every layer's extra triggers; take variable values from the firm layer only."""
    triggers = list(skill.get("triggers") or [])
    seen = {t.casefold() for t in triggers}
    variables = dict(skill.get("variables") or {})
    for layer, pack in resolver.layers:
        for key in keys:
            settings = pack.skill_settings.get(key)
            if not settings:
                continue
            for trigger in settings.get("triggers", []):
                if trigger.casefold() not in seen:
                    seen.add(trigger.casefold())
                    triggers.append(trigger)
            if "variables" not in settings:
                continue
            if layer == "firm":
                variables.update(settings["variables"])
            else:
                warn_once(
                    "Venture %s: %s pack %s sets variables for skill '%s'; ignored (only the firm sets them)",
                    venture,
                    layer,
                    pack.ref,
                    key,
                )
    if triggers:
        skill["triggers"] = triggers
    if variables:
        skill["variables"] = variables


def pack_skills(venture_dir: Path, *, taken: set[str], packs_root: Path | None = None) -> list[dict[str, Any]]:
    """The skill definitions a venture's packs add to its own skills.

    Args:
        venture_dir: The venture folder (``systems/<venture>``).
        taken: Ids and names of the skills the venture already has (its own and
            the shared ones). A pack skill with one of them is left out.
        packs_root: Pack folder to use instead of the configured ones (tests).

    Returns:
        Fresh skill dicts in the shape the detector loads from YAML, each
        marked with where it came from: ``_layer`` (``firm``, ``market`` or
        ``profession``), ``_pack`` (``id@version``, None for the firm),
        ``_skill_id`` and ``_source`` (the file).
    """
    venture_dir = Path(venture_dir)
    resolver = get_resolver(venture_dir, enabled=True, packs_root=packs_root)
    out: list[dict[str, Any]] = []
    for skill_id, resolved in resolver.list("skill").items():
        if skill_id in taken:
            logger.debug("Venture %s has its own skill '%s'; the pack's is not used", venture_dir.name, skill_id)
            continue
        data = _read_skill(Path(resolved.value))
        if data is None:
            continue
        name = data.get("name") if isinstance(data.get("name"), str) and data.get("name") else skill_id
        if name in taken:
            logger.debug("Venture %s has its own skill '%s'; the pack's is not used", venture_dir.name, name)
            continue
        data["name"] = name
        _apply_settings(data, {skill_id, name}, resolver, venture_dir.name)
        data["_version"] = 2 if "steps" in data else 1
        data["_source"] = str(resolved.value)
        data["_skill_id"] = skill_id
        data["_layer"] = resolved.layer
        data["_pack"] = resolved.pack_id
        taken = taken | {skill_id, name}
        out.append(data)
    return out


def load_venture_pack_skills(
    kb_path: Path, loaded: dict[str, list[dict[str, Any]]], *, packs_root: Path | None = None
) -> int:
    """Add every venture's pack skills to ``loaded`` (the detector's skills by venture).

    Ventures are the folders under ``<kb>/systems/``, keyed by folder name like
    their own skills. A venture whose packs can't be read is skipped with a
    warning; the others still load.

    Returns:
        How many pack skills were added.
    """
    systems = Path(kb_path) / "systems"
    if not systems.is_dir():
        return 0
    shared = {s.get("name") for s in loaded.get("shared", []) if s.get("name")}
    added = 0
    for venture_dir in sorted(p for p in systems.iterdir() if p.is_dir()):
        key = venture_dir.name
        own = loaded.get(key, [])
        taken = shared | {s.get("name") for s in own if s.get("name")} | {s.get("id") for s in own if s.get("id")}
        try:
            skills = pack_skills(venture_dir, taken={t for t in taken if isinstance(t, str)}, packs_root=packs_root)
        except LOAD_ERRORS as exc:
            warn_once("Pack skills for venture %s skipped (%s: %s)", key, type(exc).__name__, exc)
            continue
        if skills:
            loaded.setdefault(key, []).extend(skills)
            added += len(skills)
            logger.debug("Venture %s: %d skill(s) from packs", key, len(skills))
    return added
