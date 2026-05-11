# Story: STORY-02 — MCP server scaffolding

## Epic: Workstream B — Built-in MCP server
## Priority: P0
## Status: todo

## Description

Stand up the new `realize_core/mcp_server/` package, mount it on the existing FastAPI app at `/mcp/sse` + `/mcp/messages/{session_id}`, wire auth, and ship the **chat & status** tool family (`realize_chat`, `realize_status`, `realize_health`, `list_systems`, `list_agents`, `list_skills`, `get_system`, `get_session`, `get_history`, `clear_history`). KB / ops / admin tools land in subsequent stories.

## Acceptance Criteria

- [ ] `realize_core/mcp_server/` package created with `server.py`, `auth.py`, `schemas.py`, `tools/__init__.py`, `tools/chat_tools.py`.
- [ ] `realize_api/routes/mcp.py` mounts `/mcp/sse` (GET, SSE) and `/mcp/messages/{session_id}` (POST).
- [ ] Router registered in [realize_api/main.py](../../realize_api/main.py).
- [ ] New `mcp:` config block in `realize-os.yaml` template; new env vars in `.env.example` and `setup.yaml.example`.
- [ ] Master switch: `MCP_ENABLED=false` (default) keeps the new routes unmounted (no perf or security impact).
- [ ] When enabled, an MCP `tools/list` call returns the chat & status tools.
- [ ] `realize_chat` MCP call returns the same payload as `POST /api/chat`.
- [ ] Auth: SSE handshake + every JSON-RPC POST require `Authorization: Bearer <jwt>` or `X-API-Key`. Anonymous returns 401.
- [ ] Audit logging: every tool call goes through `realize_core/security/audit.py::get_audit_logger()`.
- [ ] New tests in `tests/test_mcp_server.py`: tool listing, schema validation, auth enforcement, end-to-end `realize_chat` call via the in-process MCP client.
- [ ] Test count goes up by ≥ 15 from baseline; all pass in CI.

## Technical Notes

- Reuse `realize_api/dependencies.py::get_current_user` for auth — do not introduce a parallel auth stack.
- Tool naming mirrors existing public `realizeos_*` tools (cloud routines depend on these names).
- `mcp.server.lowlevel.Server` + `mcp.server.sse.SseServerTransport` from the `mcp` SDK already in `requirements.txt`. Verify version supports server-side SSE; bump pin if needed.
- Do not duplicate business logic — each tool handler calls the existing REST route handler in-process.
- Pydantic schemas can be derived from existing route models with `model.model_json_schema()`.

## Dependencies

- STORY-01 (CI green) must be merged first so this PR lands on a green base.

## Files Affected

- `realize_core/mcp_server/__init__.py` — public API: `build_mcp_server()`, `register_routes()`.
- `realize_core/mcp_server/server.py` — `Server` instance + capability declarations.
- `realize_core/mcp_server/auth.py` — auth bridge.
- `realize_core/mcp_server/schemas.py` — JSON schemas for tool inputs.
- `realize_core/mcp_server/tools/__init__.py` — tool registry.
- `realize_core/mcp_server/tools/chat_tools.py` — chat & status tools.
- `realize_api/routes/mcp.py` — FastAPI router.
- `realize_api/main.py` — register router; lifespan init/shutdown for MCP server.
- `.env.example`, `setup.yaml.example`, `realize-os.yaml` (or template) — config keys.
- `requirements.txt` — verify/bump `mcp` pin.
- `tests/test_mcp_server.py` — new test module.
- `docs/mcp-server.md` — new doc (skeleton; expanded by Story 9).
