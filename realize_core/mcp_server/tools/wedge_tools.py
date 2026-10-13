"""Self-serve wedge tools (STORY-46), in the always-on ``chat`` family.

They work only when ``features.wedge`` is on. The user's own agent reads the
tender; these tools give it the method, check and render its register, and
offer a hand-off to an Audit Sprint or a local partner.
"""

from __future__ import annotations

import logging
from typing import Any

from realize_api.dependencies import CurrentUser

from realize_core.mcp_server.registry import MCPTool, ToolRegistry

logger = logging.getLogger(__name__)

LANGUAGES = ("en", "he", "pt")


def _wedge_config(app_state: Any) -> dict | None:
    """The wedge section of the config, or None when the pilot is off."""
    from realize_core.config import get_features

    config = getattr(app_state, "config", {}) or {}
    if not get_features(config).get("wedge"):
        return None
    return config.get("wedge") or {}


def _off() -> dict:
    return {"error": "The self-serve tender register is not enabled on this server", "code": "MCP_TOOL_DISABLED"}


def _handoff(cfg: dict, market: str) -> dict:
    partners = cfg.get("partners") or {}
    partner = partners.get(market) if isinstance(partners, dict) else None
    out: dict[str, Any] = {
        "next_step": "Want this done on every tender, checked against your own past projects? Ask for an Audit Sprint.",
        "booking_url": cfg.get("booking_url"),
    }
    if isinstance(partner, dict):
        out["local_partner"] = {"name": partner.get("name"), "url": partner.get("url")}
    return out


METHOD_SCHEMA = {
    "type": "object",
    "properties": {"market": {"type": "string", "description": "Market pack id, e.g. il or pt. Omit if unknown."}},
    "additionalProperties": False,
}


async def tender_register_method(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Steps, register format and the market's terms and rules for building a tender register."""
    if _wedge_config(app_state) is None:
        return _off()
    from realize_core.wedge import get_method

    return get_method((args.get("market") or "").strip() or None)


SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "object"}, "maxItems": 300},
        "market": {"type": "string"},
        "language": {"type": "string", "enum": list(LANGUAGES)},
        "title": {"type": "string", "maxLength": 200},
    },
    "required": ["items"],
    "additionalProperties": False,
}


async def tender_register_submit(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Check the register, render it as a finished document and record the run."""
    cfg = _wedge_config(app_state)
    if cfg is None:
        return _off()
    from realize_core.wedge import check_register, record_run, render_register
    from realize_core.wedge.register import _market_context
    from realize_core.wedge.store import WedgeLimitError

    market = (args.get("market") or "").strip().lower() or None
    language = args.get("language") if args.get("language") in LANGUAGES else "en"
    try:
        checked = check_register(args.get("items") or [])
    except ValueError as exc:
        return {"error": str(exc), "code": "MCP_VALIDATION"}
    level = _market_context(market)["verification"]
    try:
        run_id = record_run(
            getattr(user, "user_id", None) or "anonymous",
            market=market or "any",
            verification=level,
            items=checked["counts"]["items"],
            without_locator=checked["counts"]["without_locator"],
        )
    except WedgeLimitError as exc:
        return {"error": str(exc), "code": "MCP_RATE_LIMITED"}
    return {
        "run_id": run_id,
        "document": render_register(checked, market=market, language=language, title=args.get("title") or ""),
        "counts": checked["counts"],
        "warnings": checked["warnings"],
        "verification": level,
        **_handoff(cfg, market or "any"),
    }


CALL_SCHEMA = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string"},
        "contact": {"type": "string", "maxLength": 200, "description": "Email or phone the user chose to share."},
    },
    "required": ["run_id", "contact"],
    "additionalProperties": False,
}


async def request_audit_call(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Record that the user asked to be contacted after a register run."""
    cfg = _wedge_config(app_state)
    if cfg is None:
        return _off()
    from realize_core.wedge import request_call

    contact = (args.get("contact") or "").strip()
    if not contact:
        return {"error": "contact is required", "code": "MCP_VALIDATION"}
    ok = request_call(args.get("run_id") or "", getattr(user, "user_id", None) or "anonymous", contact)
    if not ok:
        return {"error": "Run not found", "code": "MCP_NOT_FOUND"}
    return {
        "status": "requested",
        "message": "Thanks. Someone will contact you.",
        "booking_url": cfg.get("booking_url"),
    }


_TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="tender_register_method",
        family="chat",
        description=(
            "Get the method for a tender requirements register: steps, the register format, and the market's "
            "local terms and sourced rules with their verification level. Read the tender yourself, then submit."
        ),
        input_schema=METHOD_SCHEMA,
        scope="read",
        handler=tender_register_method,
    ),
    MCPTool(
        name="tender_register_submit",
        family="chat",
        description="Check a tender requirements register, flag items without a page, and return it as a finished document.",
        input_schema=SUBMIT_SCHEMA,
        scope="read",
        handler=tender_register_submit,
    ),
    MCPTool(
        name="request_audit_call",
        family="chat",
        description="Ask to be contacted about an Audit Sprint after a tender register run, with a contact the user chose to share.",
        input_schema=CALL_SCHEMA,
        scope="read",
        handler=request_audit_call,
    ),
)


def register(registry: ToolRegistry) -> None:
    """Register the wedge tools with the shared registry."""
    for tool in _TOOLS:
        registry.register(tool)
