"""Read tools for profession and market packs (spec 010 §6), in the ``kb`` family.

They let an outside agent see which packs a venture uses, resolve an item
through the cascade with its provenance, and map a local term to the core
language. Writes (enabling or verifying a pack) are not exposed here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from realize_api.dependencies import CurrentUser

from realize_core.mcp_server.registry import MCPTool, ToolRegistry
from realize_core.packs.models import ITEM_TYPES, Resolved, RuleCard

logger = logging.getLogger(__name__)

MAX_KEY_CHARS = 200


def _resolver_for(args: dict[str, Any], app_state: Any):
    """The venture's resolver, or an error dict."""
    venture_key = (args.get("venture_key") or "").strip()
    systems = getattr(app_state, "systems", {}) or {}
    if venture_key not in systems:
        return None, {"error": f"Venture '{venture_key}' not found", "code": "MCP_NOT_FOUND"}
    kb_path = getattr(app_state, "kb_path", None)
    if kb_path is None:
        return None, {"error": "KB root not configured", "code": "MCP_INTERNAL"}
    from realize_core.config import get_features
    from realize_core.packs import get_resolver, venture_dir_for

    features = get_features(getattr(app_state, "config", {}) or {})
    venture_dir = venture_dir_for(Path(kb_path), systems[venture_key])
    return get_resolver(venture_dir, enabled=bool(features.get("packs"))), None


def _jsonable(value: Any) -> Any:
    if isinstance(value, RuleCard):
        return {
            "id": value.id,
            "statement": value.statement,
            "source": value.source,
            "as_of": value.as_of,
            "review_by": value.review_by,
            "applies_to": value.applies_to,
            "body": value.body,
        }
    if isinstance(value, Path):
        return value.name
    return value


def _render(resolved: Resolved) -> dict[str, Any]:
    return {
        "value": _jsonable(resolved.value),
        "layer": resolved.layer,
        "pack": resolved.pack_id,
        "verification": resolved.verification,
        # Firm files are named, not given as local paths.
        "source": Path(resolved.source).name if resolved.layer == "firm" and resolved.source else resolved.source,
        "provenance": resolved.label(),
    }


VENTURE_ONLY_SCHEMA = {
    "type": "object",
    "properties": {"venture_key": {"type": "string"}},
    "required": ["venture_key"],
    "additionalProperties": False,
}


async def list_packs(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Packs enabled for a venture, with versions, verification levels and limits."""
    resolver, error = _resolver_for(args, app_state)
    if error:
        return error
    return {"venture_key": args["venture_key"], **resolver.summary()}


RESOLVE_SCHEMA = {
    "type": "object",
    "properties": {
        "venture_key": {"type": "string"},
        "item_type": {"type": "string", "enum": list(ITEM_TYPES)},
        "key": {"type": "string", "maxLength": MAX_KEY_CHARS},
    },
    "required": ["venture_key", "item_type", "key"],
    "additionalProperties": False,
}


async def resolve_pack_item(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Resolve one item through firm > market > profession > core, with provenance."""
    resolver, error = _resolver_for(args, app_state)
    if error:
        return error
    item_type = args.get("item_type", "")
    key = (args.get("key") or "").strip()
    if item_type not in ITEM_TYPES or not key:
        return {"error": "item_type and key are required", "code": "MCP_VALIDATION"}
    resolved = resolver.resolve(item_type, key)
    if resolved is None:
        return {"item_type": item_type, "key": key, "found": False}
    return {"item_type": item_type, "key": key, "found": True, **_render(resolved)}


GLOSSARY_SCHEMA = {
    "type": "object",
    "properties": {
        "venture_key": {"type": "string"},
        "term": {"type": "string", "maxLength": MAX_KEY_CHARS},
    },
    "required": ["venture_key", "term"],
    "additionalProperties": False,
}


async def glossary_lookup(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Map a local professional term to its core family and kind."""
    resolver, error = _resolver_for(args, app_state)
    if error:
        return error
    term = (args.get("term") or "").strip()
    if not term:
        return {"error": "term is required", "code": "MCP_VALIDATION"}
    resolved = resolver.glossary_lookup(term)
    if resolved is None:
        return {"term": term, "found": False}
    entry = resolved.value
    return {
        "term": term,
        "found": True,
        "family": entry.get("family"),
        "kind": entry.get("kind"),
        "field": entry.get("field"),
        "language": entry.get("language"),
        "layer": resolved.layer,
        "pack": resolved.pack_id,
        "verification": resolved.verification,
    }


_TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="list_packs",
        family="kb",
        description="List the profession and market packs a venture uses, with verification levels and limits.",
        input_schema=VENTURE_ONLY_SCHEMA,
        scope="read",
        handler=list_packs,
    ),
    MCPTool(
        name="resolve_pack_item",
        family="kb",
        description=(
            "Resolve a term, rule card, document template, skill, trust default, measure or default "
            "for a venture through firm > market > profession > core, with its layer and verification level."
        ),
        input_schema=RESOLVE_SCHEMA,
        scope="read",
        handler=resolve_pack_item,
    ),
    MCPTool(
        name="glossary_lookup",
        family="kb",
        description="Map a local professional term (any language) to its core-language family and kind.",
        input_schema=GLOSSARY_SCHEMA,
        scope="read",
        handler=glossary_lookup,
    ),
)


def register(registry: ToolRegistry) -> None:
    """Register the pack tools with the shared registry."""
    for tool in _TOOLS:
        registry.register(tool)
