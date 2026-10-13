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

:func:`explain_with` is the one implementation: the gate uses it through
:func:`tighten_with`, and the trust matrix (``GET /api/trust``) shows its
result per venture and action (:func:`venture_trust_matrix`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from realize_core.packs.loader import warn_once
from realize_core.packs.models import TRUST_STRICTNESS
from realize_core.packs.resolver import PackResolver, get_resolver

logger = logging.getLogger(__name__)

#: Why a layer's trust value was not applied.
IGNORED_LOOSER = "loosen"
IGNORED_INVALID = "invalid"


@dataclass(frozen=True)
class TrustSource:
    """One layer's trust value for one key."""

    #: ``firm``, ``market`` or ``profession``.
    layer: str
    #: ``id@version`` of the pack; None for the firm's overrides.
    pack: str | None
    #: The key the layer named (a tool action, a governance action or ``unknown_write``).
    key: str
    #: The value as written.
    value: str

    @property
    def label(self) -> str:
        """Where the value came from, e.g. ``market pack pt@0.1.0`` or ``firm overrides``."""
        return "firm overrides" if self.layer == "firm" else f"{self.layer} pack {self.pack}"

    def to_dict(self) -> dict[str, Any]:
        """JSON shape for the API."""
        return {"layer": self.layer, "pack": self.pack, "key": self.key, "value": self.value, "label": self.label}


@dataclass(frozen=True)
class TrustExplanation:
    """How the packs and firm overrides changed one ladder decision."""

    #: The trust ladder's decision (``realize-os.yaml``).
    decision: str
    #: The decision that applies: ``decision`` or a stricter one.
    effective: str
    #: The layer whose value set ``effective``; None when nothing tightened it.
    tightened_by: TrustSource | None = None
    #: Values not applied, each with why (:data:`IGNORED_LOOSER` or :data:`IGNORED_INVALID`).
    ignored: tuple[tuple[TrustSource, str], ...] = field(default_factory=tuple)

    def warning(self, source: TrustSource, reason: str) -> str:
        """The message for an ignored value (the same words the gate logs)."""
        if reason == IGNORED_INVALID:
            return f"{source.label} sets trust '{source.value}' for {source.key}; only auto, approve or block apply. Ignored."
        return (
            f"{source.label} would loosen {source.key} from {self.decision} to {source.value.strip().lower()}; "
            "ignored (packs only tighten trust)"
        )


def explain_with(resolver: PackResolver, decision: str, names: Iterable[str]) -> TrustExplanation:
    """The stricter of ``decision`` and every layer's trust default for ``names``, and why.

    Args:
        resolver: The venture's resolver (firm overrides and linked packs).
        decision: ``auto``, ``approve`` or ``block`` from the venture's trust ladder.
        names: The keys to look up: the tool action and its governance action.

    Returns:
        The effective decision (never looser than ``decision``), the layer
        that set it, and the values that were ignored.
    """
    base = TRUST_STRICTNESS.get(decision)
    if base is None:
        return TrustExplanation(decision, decision)
    keys = [n for n in dict.fromkeys(names) if n and n not in resolver.firm.disabled]
    result = decision
    tightened_by: TrustSource | None = None
    ignored: list[tuple[TrustSource, str]] = []
    for layer, pack in resolver.layers:
        for key in keys:
            raw = pack.trust.get(key)
            if raw is None:
                continue
            source = TrustSource(layer, None if layer == "firm" else pack.ref, key, str(raw))
            level = str(raw).strip().lower()
            strictness = TRUST_STRICTNESS.get(level)
            if strictness is None:
                ignored.append((source, IGNORED_INVALID))
                continue
            if strictness < base:
                ignored.append((source, IGNORED_LOOSER))
                continue
            if strictness > TRUST_STRICTNESS[result]:
                result = level
                tightened_by = source
    return TrustExplanation(decision, result, tightened_by, tuple(ignored))


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
    explained = explain_with(resolver, decision, names)
    for source, reason in explained.ignored:
        warn_once("Venture %s: %s", venture, explained.warning(source, reason))
    if explained.tightened_by is not None:
        logger.debug(
            "Venture %s: %s tightens %s from %s to %s",
            venture,
            explained.tightened_by.label,
            explained.tightened_by.key,
            decision,
            explained.effective,
        )
    return explained.effective


def tighten(decision: str, names: Iterable[str], venture_dir: Path, *, packs_root: Path | None = None) -> str:
    """:func:`tighten_with` for a venture folder, with its cached resolver."""
    resolver = get_resolver(Path(venture_dir), enabled=True, packs_root=packs_root)
    return tighten_with(resolver, decision, names, venture=Path(venture_dir).name)


def venture_trust_matrix(
    config: dict[str, Any], venture_dir: Path, *, packs_root: Path | None = None
) -> dict[str, Any]:
    """Every action's effective decision for one venture, at the current trust level.

    One row per governance action of the ladder (``send_email``,
    ``data_write``, ...) and one per tool action a layer names on its own
    (``sheets_append``). Each row has the ladder's decision, the effective
    one, and the layer that tightened it. A tool action the ladder has no
    rule for is shown as a write (``unknown_write``), as the gate treats an
    unmapped write.

    Args:
        config: The running config (``trust`` level and rules).
        venture_dir: The venture folder.
        packs_root: Pack folder to use instead of the configured ones (tests).

    Returns:
        ``{"actions": [...], "warnings": [...], "layers": [...]}``. ``warnings``
        lists every ignored value once (loosenings and unusable values).
    """
    from realize_core.governance.trust_ladder import ACTION_MAP, check_trust, get_trust_rules, trust_keys

    resolver = get_resolver(Path(venture_dir), enabled=True, packs_root=packs_root)
    rules = get_trust_rules(config)
    named = {str(k) for _layer, pack in resolver.layers for k in pack.trust}
    tool_actions = sorted(k for k in named if k not in rules)

    rows: list[dict[str, Any]] = []
    warnings: dict[str, None] = {}

    def row(action: str, decision: str, names: list[str], governed_by: str | None) -> None:
        explained = explain_with(resolver, decision, names)
        ignored = []
        for source, reason in explained.ignored:
            warnings[explained.warning(source, reason)] = None
            ignored.append({**source.to_dict(), "reason": reason})
        rows.append(
            {
                "action": action,
                "governed_by": governed_by,
                "ladder": decision,
                "effective": explained.effective,
                "tightened": explained.effective != decision,
                "source": explained.tightened_by.to_dict() if explained.tightened_by else None,
                "ignored": ignored,
            }
        )

    for action in sorted(rules):
        row(action, check_trust(action, config).value, [action], None)
    for action in tool_actions:
        decision = check_trust(action, config, is_destructive=True).value
        names = trust_keys(action, config, is_destructive=True)
        governed_by = ACTION_MAP.get(action) or ("unknown_write" if "unknown_write" in names else None)
        row(action, decision, names, governed_by)

    layers = [
        {"layer": layer, "pack": None if layer == "firm" else pack.ref}
        for layer, pack in resolver.layers
        if layer != "firm" or pack.trust
    ]
    return {"actions": rows, "warnings": list(warnings), "layers": layers}
