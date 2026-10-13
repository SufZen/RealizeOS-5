"""Trust defaults from a venture's packs: they tighten, never loosen (spec 010 §3.1).

A pack's ``trust.yaml`` (and the firm's ``F-foundations/overrides/trust.yaml``)
maps an action to ``auto``, ``approve`` or ``block``. The key is a tool action
(``sheets_append``) or a governance action (``data_write``, ``send_email``).

The governance gate first decides with the trust ladder in ``realize-os.yaml``
(the venture's configuration). The packs and the firm overrides are then laid
over that decision **only where they are stricter**: ``auto`` can become
``approve`` or ``block``, ``approve`` can become ``block``, and nothing ever
goes the other way. A value that would loosen the decision is ignored and
logged. The firm can switch a pack's default off by listing the action in
``F-foundations/overrides/disable.yaml``; that returns the action to the
``realize-os.yaml`` decision, never below it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from realize_core.packs.loader import warn_once
from realize_core.packs.models import TRUST_STRICTNESS
from realize_core.packs.resolver import PackResolver, get_resolver

logger = logging.getLogger(__name__)


def tighten_with(resolver: PackResolver, decision: str, names: Iterable[str], *, venture: str = "") -> str:
    """The stricter of ``decision`` and every layer's trust default for ``names``.

    Args:
        resolver: The venture's resolver (firm overrides and linked packs).
        decision: ``auto``, ``approve`` or ``block`` from the venture's trust ladder.
        names: The keys to look up: the tool action and its governance action.
        venture: Venture name for log messages.

    Returns:
        ``decision`` or a stricter level. Never a looser one.
    """
    base = TRUST_STRICTNESS.get(decision)
    if base is None:
        return decision
    keys = [n for n in dict.fromkeys(names) if n and n not in resolver.firm.disabled]
    result = decision
    for layer, pack in resolver.layers:
        origin = "firm overrides" if layer == "firm" else f"{layer} pack {pack.ref}"
        for key in keys:
            raw = pack.trust.get(key)
            if raw is None:
                continue
            level = str(raw).strip().lower()
            strictness = TRUST_STRICTNESS.get(level)
            if strictness is None:
                warn_once(
                    "Venture %s: %s sets trust '%s' for %s; only auto, approve or block apply. Ignored.",
                    venture,
                    origin,
                    raw,
                    key,
                )
                continue
            if strictness < base:
                warn_once(
                    "Venture %s: %s would loosen %s from %s to %s; ignored (packs only tighten trust)",
                    venture,
                    origin,
                    key,
                    decision,
                    level,
                )
                continue
            if strictness > TRUST_STRICTNESS[result]:
                logger.debug("Venture %s: %s tightens %s from %s to %s", venture, origin, key, result, level)
                result = level
    return result


def tighten(decision: str, names: Iterable[str], venture_dir: Path, *, packs_root: Path | None = None) -> str:
    """:func:`tighten_with` for a venture folder, with its cached resolver."""
    resolver = get_resolver(Path(venture_dir), enabled=True, packs_root=packs_root)
    return tighten_with(resolver, decision, names, venture=Path(venture_dir).name)
