"""Ventures that get their team or skills from packs while ``features.packs`` is off.

A venture created from a template with packs on links the packs instead of
copying their agents and skills (spec 010 §7): its ``A-agents/`` and
``R-routines/skills/`` stay empty. If the flag is turned off later, nothing
loads its packs any more and the venture silently has no team and no skills.

:func:`packs_off_warning` names that case for one venture. It runs where the
systems dict is built (:func:`realize_core.config.build_systems_dict`, at
startup and on every config reload), which logs the warning and lists it in
the venture's ``warnings`` (``GET /api/ventures``, ``GET /api/status``).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from realize_core.packs.loader import LOAD_ERRORS, read_venture_packs
from realize_core.packs.resolver import get_resolver

logger = logging.getLogger(__name__)

_SKILL_SUFFIXES = (".yaml", ".yml")

#: Venture folder -> the warning last logged for it, so a systems rebuild
#: (every config reload, every mission step) logs a venture once per change.
_reported: dict[str, str] = {}
_reported_lock = threading.Lock()


def _has_own_skills(venture_dir: Path) -> bool:
    """True when the venture has a skill file of its own (or its folder can't be listed)."""
    skills = venture_dir / "R-routines" / "skills"
    try:
        return skills.is_dir() and any(p.is_file() and p.suffix in _SKILL_SUFFIXES for p in skills.iterdir())
    except OSError:
        return True  # can't tell: don't claim it has none


def packs_off_warning(venture_key: str, venture_dir: Path, own_agents: dict) -> str | None:
    """The warning for a venture that relies on its packs while ``features.packs`` is off, else None.

    A venture relies on its packs when its ``packs.yaml`` names at least one
    pack, it has no agents (or no skills) of its own, and the packs it names
    provide some. Only that case reads the packs; every other venture costs
    one file check.

    Args:
        venture_key: The venture's key, for the message.
        venture_dir: The venture folder.
        own_agents: The agents found in the venture's own ``A-agents/``.
    """
    venture_dir = Path(venture_dir)
    if not (venture_dir / "packs.yaml").is_file():
        return None
    has_agents, has_skills = bool(own_agents), _has_own_skills(venture_dir)
    if has_agents and has_skills:
        return None
    wanted = read_venture_packs(venture_dir)
    if not any(wanted.values()):
        return None
    try:
        resolver = get_resolver(venture_dir, enabled=True)
        agents = {} if has_agents else resolver.list("agent")
        skills = {} if has_skills else resolver.list("skill")
    except LOAD_ERRORS as exc:
        logger.debug("Venture %s: packs not checked (%s: %s)", venture_key, type(exc).__name__, exc)
        return None
    missing = [name for name, items in (("agents", agents), ("skills", skills)) if items]
    if not missing:
        return None
    lost = " and ".join(f"{len(items)} {name}" for name, items in (("agents", agents), ("skills", skills)) if items)
    links = ", ".join(f"{kind} {entry['id']}" for kind in ("profession", "market") for entry in wanted[kind])
    return (
        f"Venture {venture_key} links packs ({links}) but features.packs is off: it has no "
        f"{' or '.join(missing)} of its own, so it runs without the {lost} its packs provide. "
        "Turn features.packs back on, or copy them into the venture's A-agents/ and R-routines/skills/."
    )


def report(venture_dir: Path, message: str | None) -> None:
    """Log ``message`` for a venture when it is new or changed; forget it once the venture is fine again."""
    key = str(Path(venture_dir).resolve())
    with _reported_lock:
        if message is None:
            _reported.pop(key, None)
            return
        if _reported.get(key) == message:
            return
        _reported[key] = message
    logger.warning("%s", message)
