# Story: STORY-04 — MCP ops tools

## Epic: Workstream B — Built-in MCP server
## Priority: P0
## Status: done (2026-05-11, +13 tests, 1770 total passing)

## Description

Add the **operational** tool family to the MCP server, gated by `mcp.expose_ops: true`. Covers workflows, skills, evolution loop, suggestions, and approvals — the surface external agents need to drive RealizeOS as an operational layer.

## Acceptance Criteria

- [ ] New `realize_core/mcp_server/tools/ops_tools.py` with: `run_workflow`, `list_workflows`, `trigger_skill`, `run_evolution`, `list_suggestions`, `approve_suggestion`, `dismiss_suggestion`, `apply_refinement`, `refine_prompt`.
- [ ] `mcp.expose_ops` flag respected (default `true`); when `false`, these tools are hidden from `tools/list`.
- [ ] Scope check: ops tools require `role >= editor` from the JWT. `role = viewer` calls return 403 with structured error code.
- [ ] Each tool wraps existing route handlers in `workflows.py`, `evolution.py`, `approvals.py`, `settings_skills.py`. No duplicated logic.
- [ ] `run_workflow` and `trigger_skill` are async — long-running calls return a task ID; pollers can use existing REST `GET /api/pipelines/{id}`.
- [ ] Tests in `tests/test_mcp_tools_ops.py`: 200-path each tool, scope rejection for viewer, async dispatch returns task ID, skill that doesn't exist returns structured error.
- [ ] All pass in CI; test count goes up by ≥ 12.

## Technical Notes

- `run_workflow` should respect the same approval gates as the REST handler — don't bypass `governance/`.
- `trigger_skill` accepts the skill key from `R-routines/skills/*.yaml`; surface helpful error when key not found.
- Audit log entry for every call (already inherited from STORY-02).

## Dependencies

- STORY-02 (MCP scaffold) merged.

## Files Affected

- `realize_core/mcp_server/tools/ops_tools.py` — new.
- `realize_core/mcp_server/tools/__init__.py` — register.
- `realize_core/mcp_server/schemas.py` — add ops schemas.
- `tests/test_mcp_tools_ops.py` — new.
- `docs/mcp-server.md` — append ops reference.
