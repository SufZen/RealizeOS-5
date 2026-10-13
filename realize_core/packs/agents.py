"""Agent definitions a venture gets from its packs (spec 010 §4.1).

With ``features.packs`` on, :func:`realize_core.config.build_systems_dict`
adds the agents of the venture's linked packs to the agents it found in the
venture's own ``A-agents/`` folder. The venture's own file wins over a pack
agent with the same key; among the packs the highest layer wins (firm
overrides > market > profession), and the firm can switch a key off in
``F-foundations/overrides/disable.yaml``.

A pack agent is only a prompt: the same markdown format as a venture agent.
It gets no extra privileges. Its tools are the registry tools every agent of
the venture gets, behind the same governance gate, and it can't bring a
``persona.yaml`` (tool allow-lists are read from the venture's folder only).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from realize_core.packs.loader import LOAD_ERRORS, warn_once
from realize_core.packs.models import Resolved
from realize_core.packs.resolver import get_resolver

logger = logging.getLogger(__name__)


@dataclass
class PackAgents:
    """What a venture's packs add to its agents."""

    #: Agent key → definition path, in the form the prompt builder reads (see :func:`display_path`).
    agents: dict[str, str] = field(default_factory=dict)
    #: Agent key → where it came from: ``layer``, ``pack`` (``id@version``) and,
    #: for a market pack, ``verification``. The trail shows these (spec 010 §3.2).
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: The routing guide to use when the venture has none of its own.
    readme: str | None = None


def provenance(resolved: Resolved) -> dict[str, Any]:
    """``layer``, ``pack`` and ``verification`` of a resolved pack item, leaving out what it hasn't."""
    out: dict[str, Any] = {"layer": resolved.layer, "pack": resolved.pack_id, "verification": resolved.verification}
    return {k: v for k, v in out.items() if v is not None}


def display_path(path: Path, kb_path: Path) -> str:
    """A pack file as the system config stores agent paths.

    Relative to the KB root when the pack lives under it (as a venture's own
    agents are), else absolute. The prompt builder reads ``kb_path / value``,
    which gives the file in both cases.
    """
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(Path(kb_path).resolve()))
    except ValueError:
        return str(resolved)


def pack_agents(venture_dir: Path, kb_path: Path, own: dict[str, str], *, packs_root: Path | None = None) -> PackAgents:
    """The agents a venture's packs add on top of its own.

    Args:
        venture_dir: The venture folder.
        kb_path: The KB root (agent paths are stored relative to it when possible).
        own: The venture's own agents (key → path); these keys are never replaced.
        packs_root: Pack folder to use instead of the configured ones (tests).

    Returns:
        The added agents, their provenance and, when the venture has no
        ``A-agents/_README.md``, the highest layer's routing guide. Empty when
        the packs can't be read (logged).
    """
    out = PackAgents()
    try:
        resolver = get_resolver(venture_dir, enabled=True, packs_root=packs_root)
    except LOAD_ERRORS as exc:
        warn_once("Pack agents for venture %s skipped (%s: %s)", Path(venture_dir).name, type(exc).__name__, exc)
        return out
    for key, resolved in resolver.list("agent").items():
        if key in own:
            logger.debug("Venture %s has its own agent '%s'; the pack's is not used", Path(venture_dir).name, key)
            continue
        out.agents[key] = display_path(resolved.value, kb_path)
        out.provenance[key] = provenance(resolved)
    if not (Path(venture_dir) / "A-agents" / "_README.md").is_file():
        for _layer, pack in resolver.layers:
            if pack.agents_readme is not None:
                out.readme = display_path(pack.agents_readme, kb_path)
                break
    return out
