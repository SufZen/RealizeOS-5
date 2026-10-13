"""Schema extensions from a venture's packs, for entity validation (spec 010 §4.3).

A pack's ``schemas/*.json`` extend a core family (``allOf`` a core schema)
and validate entities of their own type, such as ``payment-claim``. They are
registered per venture: entities in a venture are checked against the core
schemas plus the extensions of the packs that venture links, so two ventures
with different packs never see each other's types.

Extensions are registered lowest layer first (profession, market, firm
overrides), so a higher layer replaces a lower layer's extension of the same
name. None of them can replace a core schema (see
:meth:`realize_core.fabric.validator.SchemaRegistry.extend`).
"""

from __future__ import annotations

import logging
from pathlib import Path

from realize_core.fabric.validator import SchemaRegistry
from realize_core.packs.loader import LOAD_ERRORS, warn_once
from realize_core.packs.resolver import get_resolver

logger = logging.getLogger(__name__)


def schema_registry_for(
    venture_dir: Path | None,
    *,
    enabled: bool,
    packs_root: Path | None = None,
    registry: SchemaRegistry | None = None,
) -> SchemaRegistry:
    """A schema registry with the core schemas and, with packs on, the venture's pack extensions.

    Args:
        venture_dir: The venture folder (None gives the core schemas only).
        enabled: ``features.packs``. Off gives exactly the core registry.
        packs_root: Pack folder to use instead of the configured ones (tests).
        registry: A registry to add to instead of a new one.

    Returns:
        The registry. An extension that tries to replace or fork a core schema
        is left out with a warning; the others are registered.
    """
    registry = registry or SchemaRegistry()
    if not enabled or venture_dir is None:
        return registry
    venture_dir = Path(venture_dir)
    try:
        resolver = get_resolver(venture_dir, enabled=True, packs_root=packs_root)
    except LOAD_ERRORS as exc:
        warn_once("Pack schemas for venture %s skipped (%s: %s)", venture_dir.name, type(exc).__name__, exc)
        return registry
    for layer, pack in reversed(resolver.layers):
        origin = "firm overrides" if layer == "firm" else f"{layer} pack {pack.ref}"
        for name, schema in sorted(pack.schemas.items()):
            if name in resolver.firm.disabled:
                continue
            registered, problems = registry.extend(name, schema)
            for problem in problems:
                if registered:
                    warn_once("Schema %s from %s: %s (the core type is kept)", name, origin, problem)
                else:
                    warn_once("Schema %s from %s skipped: %s", name, origin, problem)
    return registry
