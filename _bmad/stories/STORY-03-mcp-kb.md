# Story: STORY-03 — MCP KB tools

## Epic: Workstream B — Built-in MCP server
## Priority: P0
## Status: done (2026-05-11, +19 tests, 1757 total passing)

## Description

Add the **KB read** tool family to the MCP server, gated by `mcp.expose_kb: true`. Lets external agents use a user's RealizeOS as a "second brain" read layer.

## Acceptance Criteria

- [ ] New `realize_core/mcp_server/tools/kb_tools.py` with: `kb_search`, `kb_get_document`, `venture_kb_search`, `list_ventures`.
- [ ] `mcp.expose_kb` config flag respected (default `true`); when `false`, these tools do not appear in `tools/list`.
- [ ] Each tool wraps existing handlers in `realize_api/routes/venture_kb.py`, `venture_shared.py`, `ventures.py` — no new business logic.
- [ ] Inputs validated against pydantic schemas (search query length cap, venture key sanitization).
- [ ] Returns include enough context for an agent to follow up (document IDs, scores, snippets ≤ 500 chars).
- [ ] Tests in `tests/test_mcp_tools_kb.py`: search returns ranked results, get returns full document, missing venture returns structured error, large query is rejected.
- [ ] All pass in CI; test count goes up by ≥ 8.

## Technical Notes

- Reuse the existing FTS5 + vector indexer in `realize_core/kb/`. Don't re-implement.
- `kb_search` snippet truncation lives in the tool handler, not the route handler — REST clients still get full content if they want it.
- `list_ventures` is read-only and exposes the same shape as `GET /api/ventures` (which already powers the dashboard).

## Dependencies

- STORY-02 (MCP server scaffold) merged.

## Files Affected

- `realize_core/mcp_server/tools/kb_tools.py` — new.
- `realize_core/mcp_server/tools/__init__.py` — register the new family.
- `realize_core/mcp_server/schemas.py` — add KB schemas.
- `tests/test_mcp_tools_kb.py` — new test module.
- `docs/mcp-server.md` — append KB tool reference (full polish in Story 9).
