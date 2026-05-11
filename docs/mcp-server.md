# RealizeOS Built-in MCP Server

> Status: **5.1.0 — chat & status tools shipping in Story 2.** KB, ops, and admin tool families land in Stories 3-5. Full doc lands in Story 9.

RealizeOS exposes its REST surface over the [Model Context Protocol](https://modelcontextprotocol.io) so any MCP-speaking agent — Claude Desktop, Cursor, n8n, cloud routines, your own scripts — can call into a user's RealizeOS instance.

This is the **inverse** of [`realize_core/tools/mcp.py`](../realize_core/tools/mcp.py), which is the outbound *client* (RealizeOS calling external MCP servers).

## Enable it

In `.env`:

```env
MCP_ENABLED=true
```

Or in `realize-os.yaml`:

```yaml
mcp:
  enabled: true
  expose_kb: true
  expose_ops: true
  allow_admin: false           # off by default
  audit_full_payload: false
```

Start RealizeOS as usual. The server logs:

```
MCP server mounted at /mcp/sse — families=chat,kb,ops, allow_admin=False
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/mcp/sse` | SSE handshake. The client keeps this connection open. |
| `POST` | `/mcp/messages/{session_id}` | Client posts JSON-RPC payloads here. |
| `GET` | `/mcp/health` | No-auth liveness probe — returns `{ ok, name, tools, families }`. |

Auth: same as the REST API. Pass `Authorization: Bearer <jwt>` (from `POST /api/auth/token`) or `X-API-Key: <key>`.

## Tool families (Story 2 surface)

| Family | Gating | Tools |
|---|---|---|
| `chat` | always on | `realize_chat`, `realize_health`, `realize_status`, `list_systems`, `get_system`, `list_agents`, `list_skills`, `get_history`, `clear_history`, `get_session` |
| `kb`   | `mcp.expose_kb` (on by default) | `kb_search`, `venture_kb_search`, `kb_get_document`, `list_ventures` |
| `ops`  | `mcp.expose_ops` (on by default) | `list_workflows`, `run_workflow`, `trigger_skill`, `run_evolution`, `list_suggestions`, `approve_suggestion`, `dismiss_suggestion`, `list_approvals`, `approve_request`, `reject_request` |
| `admin`| `mcp.allow_admin` + `role=owner` + production JWT | _(Story 5)_ |

### Ops tool behaviour

* `run_workflow` (alias `trigger_skill`) executes a registered skill against an input message via `realize_core.skills.executor.execute_skill` in-process. Same auth + audit as the REST path. Returns `{ name, system_key, user_id, output }`.
* `run_evolution` triggers `realize_core.evolution.gap_detector.run_gap_analysis(days=...)`. Default window is 7 days; capped at 90.
* `approve_suggestion` / `dismiss_suggestion` operate on the in-memory `EvolutionEngine` proposal store (same singleton the dashboard uses).
* `approve_request` / `reject_request` delegate to `realize_core.governance.gates` for the approval queue — preserves all governance checks.
* Scope: every `list_*` is `read`; everything that changes state (`run_*`, `trigger_*`, `approve_*`, `dismiss_*`, `reject_*`) requires `role >= editor`.

### KB tool behaviour

* `kb_search` runs the same hybrid FTS5+vector indexer the dashboard uses (`realize_core.kb.indexer.semantic_search`). Snippets are capped at 500 chars; full content is available via `kb_get_document`.
* `kb_get_document` enforces path-traversal protection: the resolved path must live under `app.state.kb_path`. Absolute paths and `..` segments are rejected with `MCP_VALIDATION` / `MCP_FORBIDDEN`.
* `venture_kb_search` is a convenience: it validates the venture exists, then delegates to `kb_search` with the venture as `system_key`.
* `list_ventures` mirrors `GET /api/ventures` — venture key, name, agent count, skill count, FABRIC completeness.

## Plug into Claude Desktop

```json
{
  "mcpServers": {
    "realize-os": {
      "url": "http://localhost:8080/mcp/sse",
      "headers": { "Authorization": "Bearer <your jwt>" }
    }
  }
}
```

Restart Claude Desktop. The RealizeOS tools appear in the tool palette.

## Security

- No anonymous access — the SSE handshake and every JSON-RPC POST go through the existing auth middleware.
- Scope hierarchy: `read` < `editor` < `owner`. Chat-family tools require `read`; `clear_history` requires `editor`; admin tools (Story 5) require `owner`.
- Audit log: every tool call goes through `realize_core/security/audit.py` (same retention + log file as REST).
- Production guard: in `REALIZE_ENV=production`, enabling `mcp.allow_admin` requires `REALIZE_JWT_ENABLED=true` and a 32+ char `REALIZE_JWT_SECRET`. The server refuses to start otherwise.

## Error model

All MCP tool responses are JSON in a `TextContent` block. Errors look like:

```json
{ "error": "Tool 'foo' is not registered.", "code": "MCP_TOOL_NOT_FOUND" }
```

Stable `code` values:

| Code | Meaning |
|---|---|
| `MCP_TOOL_NOT_FOUND` | Unknown tool name. |
| `MCP_TOOL_DISABLED` | Tool's family is not enabled on this instance. |
| `MCP_ADMIN_DISABLED` | Admin tool while `mcp.allow_admin` is false. |
| `MCP_INSUFFICIENT_SCOPE` | Caller's role doesn't meet the tool's required scope. |
| `MCP_NOT_FOUND` | Referenced resource (system, venture, …) doesn't exist. |
| `MCP_INTERNAL` | Tool raised an exception. |

## Roadmap

- **Story 3 (this release):** KB read tools.
- **Story 4 (this release):** workflows, skills, evolution, approvals.
- **Story 5 (this release):** admin / write tools + adversarial tests.
- **5.2.0:** stdio transport (Claude Desktop local install).
- **5.2.0:** Streamable HTTP transport.
- **5.2.0:** per-tool feature flags inside `mcp:` config.
