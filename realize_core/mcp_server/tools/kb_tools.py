"""Knowledge base read tools — gated by ``mcp.expose_kb``.

Lets external agents use a user's RealizeOS as a "second brain" read
layer: FTS5 + vector search over indexed FABRIC content, document
fetch with path-traversal protection, and venture inventory.

All handlers wrap existing primitives in :mod:`realize_core.kb.indexer`
and :mod:`realize_api.routes.venture_kb` — no new business logic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from realize_api.dependencies import CurrentUser

from realize_core.mcp_server.registry import MCPTool, ToolRegistry

logger = logging.getLogger(__name__)

#: Cap snippet length surfaced to MCP callers. Keeps responses small
#: enough for an LLM tool-result without losing search context. Full
#: content is available via ``kb_get_document``.
MAX_SNIPPET_CHARS = 500

#: Cap document content surfaced to MCP callers. Documents larger than
#: this are truncated with a marker so the caller knows there's more.
MAX_DOC_CHARS = 50_000

#: Cap search query length to prevent abusive payloads.
MAX_QUERY_CHARS = 1_000

#: Cap ``top_k`` to keep responses bounded.
MAX_TOP_K = 50


# ---------------------------------------------------------------------------
# kb_search — global search across all systems
# ---------------------------------------------------------------------------

KB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Search query — supports FTS5 syntax (e.g. 'investment AND thesis').",
            "maxLength": MAX_QUERY_CHARS,
        },
        "system_key": {
            "type": ["string", "null"],
            "description": "Optional system/venture filter. Omit to search across all systems.",
        },
        "top_k": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_TOP_K,
            "default": 10,
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


async def kb_search(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Hybrid FTS5 + vector search across the knowledge base."""
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "Query is required", "code": "MCP_VALIDATION"}
    if len(query) > MAX_QUERY_CHARS:
        return {
            "error": f"Query too long ({len(query)} chars, max {MAX_QUERY_CHARS}).",
            "code": "MCP_VALIDATION",
        }

    top_k = min(max(int(args.get("top_k", 10) or 10), 1), MAX_TOP_K)
    system_key = args.get("system_key") or None

    try:
        from realize_core.kb.indexer import semantic_search

        results = semantic_search(query=query, system_key=system_key, top_k=top_k)
    except Exception as exc:
        logger.warning("kb_search failed: %s", exc)
        return {"query": query, "results": [], "error": str(exc)[:200], "code": "MCP_INTERNAL"}

    trimmed: list[dict[str, Any]] = []
    for r in results:
        snippet = r.get("snippet") or ""
        if isinstance(snippet, str) and len(snippet) > MAX_SNIPPET_CHARS:
            snippet = snippet[:MAX_SNIPPET_CHARS] + "…"
        trimmed.append(
            {
                "path": r.get("path"),
                "title": r.get("title"),
                "system_key": r.get("system_key"),
                "snippet": snippet,
                "score": r.get("score") or r.get("rank"),
            }
        )

    return {"query": query, "system_key": system_key, "results": trimmed}


# ---------------------------------------------------------------------------
# venture_kb_search — same as kb_search but with a required venture filter
# ---------------------------------------------------------------------------

VENTURE_KB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "venture_key": {"type": "string"},
        "query": {"type": "string", "maxLength": MAX_QUERY_CHARS},
        "top_k": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_TOP_K,
            "default": 10,
        },
    },
    "required": ["venture_key", "query"],
    "additionalProperties": False,
}


async def venture_kb_search(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Search within a single venture's KB."""
    venture_key = (args.get("venture_key") or "").strip()
    if not venture_key:
        return {"error": "venture_key is required", "code": "MCP_VALIDATION"}

    systems = getattr(app_state, "systems", {}) or {}
    if venture_key not in systems:
        return {
            "error": f"Venture '{venture_key}' not found",
            "code": "MCP_NOT_FOUND",
            "available": list(systems.keys()),
        }

    return await kb_search(
        {
            "query": args.get("query", ""),
            "system_key": venture_key,
            "top_k": args.get("top_k", 10),
        },
        app_state,
        user,
    )


# ---------------------------------------------------------------------------
# kb_get_document — fetch a single KB file's contents
# ---------------------------------------------------------------------------

KB_GET_DOCUMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative path within the KB root (as returned by kb_search.path).",
        },
        "max_chars": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_DOC_CHARS,
            "default": MAX_DOC_CHARS,
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}


async def kb_get_document(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Return the contents of a single KB document.

    Enforces the same path-traversal protection as the REST handler in
    :func:`realize_api.routes.venture_kb.read_kb_file` — the resolved
    path must live under ``app.state.kb_path``.
    """
    raw_path = (args.get("path") or "").strip()
    if not raw_path or ".." in raw_path or "\x00" in raw_path:
        return {"error": "Invalid path", "code": "MCP_VALIDATION"}

    kb_root = getattr(app_state, "kb_path", None)
    if kb_root is None:
        return {"error": "KB root not configured", "code": "MCP_INTERNAL"}
    kb_root = Path(kb_root)

    file_path = kb_root / raw_path
    try:
        file_path.resolve().relative_to(kb_root.resolve())
    except ValueError:
        return {"error": "Access denied (path escapes KB root)", "code": "MCP_FORBIDDEN"}

    if not file_path.exists() or not file_path.is_file():
        return {"error": "File not found", "code": "MCP_NOT_FOUND"}

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("kb_get_document read failed for %s: %s", file_path, exc)
        return {"error": f"Cannot read file: {exc}", "code": "MCP_INTERNAL"}

    max_chars = min(int(args.get("max_chars", MAX_DOC_CHARS) or MAX_DOC_CHARS), MAX_DOC_CHARS)
    truncated = False
    if len(content) > max_chars:
        content = content[:max_chars]
        truncated = True

    return {
        "path": raw_path,
        "content": content,
        "size": file_path.stat().st_size,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# list_ventures — venture inventory with health summary
# ---------------------------------------------------------------------------

LIST_VENTURES_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


async def list_ventures(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """List all ventures with a health snapshot — mirrors ``GET /api/ventures``."""
    systems = getattr(app_state, "systems", {}) or {}
    kb_path = getattr(app_state, "kb_path", None)

    try:
        from realize_api.routes.route_helpers import analyze_fabric, count_skills
    except ImportError as exc:
        logger.debug("route_helpers import failed: %s", exc)
        analyze_fabric = None  # type: ignore[assignment]
        count_skills = None  # type: ignore[assignment]

    ventures: list[dict[str, Any]] = []
    for key, sys_conf in systems.items():
        entry: dict[str, Any] = {
            "key": key,
            "name": sys_conf.get("name", key),
            "description": sys_conf.get("description", ""),
            "agent_count": len(sys_conf.get("agents", {}) or {}),
        }
        if analyze_fabric is not None and kb_path is not None:
            try:
                fabric = analyze_fabric(kb_path, sys_conf)
                entry["fabric_completeness"] = fabric.get("completeness")
            except Exception:  # best-effort
                pass
        if count_skills is not None and kb_path is not None:
            try:
                entry["skill_count"] = count_skills(kb_path, sys_conf)
            except Exception:
                pass
        ventures.append(entry)

    return {"ventures": ventures}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="kb_search",
        family="kb",
        description="Hybrid FTS5 + vector search across the RealizeOS knowledge base.",
        input_schema=KB_SEARCH_SCHEMA,
        scope="read",
        handler=kb_search,
    ),
    MCPTool(
        name="venture_kb_search",
        family="kb",
        description="Search within a single venture's knowledge base.",
        input_schema=VENTURE_KB_SEARCH_SCHEMA,
        scope="read",
        handler=venture_kb_search,
    ),
    MCPTool(
        name="kb_get_document",
        family="kb",
        description="Read a single KB document by relative path (path-traversal protected).",
        input_schema=KB_GET_DOCUMENT_SCHEMA,
        scope="read",
        handler=kb_get_document,
    ),
    MCPTool(
        name="list_ventures",
        family="kb",
        description="List all ventures with a health snapshot (agents, skills, FABRIC completeness).",
        input_schema=LIST_VENTURES_SCHEMA,
        scope="read",
        handler=list_ventures,
    ),
)


def register(registry: ToolRegistry) -> None:
    """Register every KB tool with the shared registry."""
    for tool in _TOOLS:
        registry.register(tool)
