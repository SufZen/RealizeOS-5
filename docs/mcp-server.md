# RealizeOS Built-in MCP Server

> Shipping in **RealizeOS 5.1.0** — 24 tools across 4 families (Chat & Status, KB Read, Ops, Admin).

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
  streamable_http: true        # serve /mcp next to /mcp/sse (default on)
  public_url: ""               # https://your-host — needed for OAuth
  oauth:
    enabled: false             # Claude.ai custom connectors (see below)
    redirect_hosts: []         # empty = claude.ai, claude.com and loopback
  tools: []                    # only serve these tools; empty = every tool of the exposed families
```

`tools` (env `MCP_TOOLS`, comma-separated) narrows what a server offers. It can't widen it: a tool is served only when its family is exposed and the list names it. A hosted profile uses it to serve one workflow, for example the [self-serve tender register](self-serve-wedge.md#host-the-pilot). Names that match no tool are logged as a warning at startup. A value that is neither a list of names nor a comma-separated string (a mapping, a number) serves no tools at all, rather than every tool.

Start RealizeOS as usual. The server logs:

```
MCP server mounted at /mcp/sse and /mcp (Streamable HTTP) — families=chat,kb,ops, allow_admin=False, oauth=False, tools=all
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/mcp` | **Streamable HTTP** transport (stateless, JSON responses). Use this for new clients. |
| `GET` | `/mcp/sse` | HTTP+SSE handshake (older transport, kept for existing clients). The client keeps this connection open. |
| `POST` | `/mcp/messages/?session_id=` | SSE clients post JSON-RPC payloads here. |
| `GET` | `/mcp/health` | Liveness probe — returns `{ ok, name, tools, families }`. |

Auth: the same as the REST API. Send `Authorization: Bearer <jwt>` (from `POST /api/auth/token`), `X-API-Key: <key>`, or an OAuth access token (see below).

HTTP+SSE is deprecated in the MCP spec. It stays here for Claude Code, `mcp-remote` bridges and other existing clients; new clients should use `/mcp`.

## Connect Claude.ai (custom connector, OAuth)

Claude.ai custom connectors (web and desktop, **Settings → Connectors → Add custom connector**) can't send a fixed `Authorization` header. They sign in with OAuth 2.1. RealizeOS has a small authorization server for this:

1. Serve RealizeOS over **HTTPS** on a public host, for example `https://realizeos.example.com`.
2. Set, in `.env`:

   ```env
   MCP_ENABLED=true
   MCP_OAUTH_ENABLED=true
   MCP_PUBLIC_URL=https://realizeos.example.com
   REALIZE_API_KEY=...        # auth must be on, or /mcp would be open
   ```

3. Make sure the person who connects has an entry in `users.yaml` (email + password hash). Their role and ventures decide what the connector can do.
4. In Claude.ai, add a custom connector with the URL `https://realizeos.example.com/mcp`.
5. Claude opens a RealizeOS sign-in page. It shows which app is asking and where it will send you back. Sign in and click **Sign in and allow**.

What happens behind it:

| Step | Endpoint |
|---|---|
| Claude calls `/mcp` without a token and gets `401` with `WWW-Authenticate: Bearer resource_metadata=".../.well-known/oauth-protected-resource/mcp"` | `/mcp` |
| Protected-resource metadata (RFC 9728) names the authorization server | `GET /.well-known/oauth-protected-resource/mcp` |
| Authorization-server metadata (RFC 8414) | `GET /.well-known/oauth-authorization-server` |
| Dynamic client registration (RFC 7591) | `POST /register` |
| Authorization code with PKCE (S256 only) | `GET /authorize` → `/oauth/login` |
| Code → access + refresh token; refresh rotates the pair | `POST /token` |
| Revoke a token (ends the whole grant) | `POST /revoke` |

Rules:

- **Tokens map to a `users.yaml` user.** On every request the user is looked up again, like cookie sessions. RBAC roles (owner/admin/operator/user/viewer) and venture scope apply exactly as for that user on the REST API and the SSE transport. If you remove the user, their tokens stop working at once.
- Access tokens last 1 hour and refresh tokens 30 days. Codes are single-use and last 5 minutes. Codes and tokens are stored only as SHA-256 hashes (migration 009).
- **Only allowed redirect hosts.** Registration and `/authorize` refuse a `redirect_uri` outside `mcp.oauth.redirect_hosts` (env `MCP_OAUTH_REDIRECT_HOSTS`, comma-separated). The default is `claude.ai`, `claude.com` and loopback (`localhost`, `127.0.0.1`, `[::1]`, for local clients such as Claude Code). Non-loopback hosts need `https`. Without this list, anyone could register a client called "Claude" that sends codes to their own site. Add a host only for a client you trust, for example `chatgpt.com`. Setting the list replaces the defaults.
- **Sign-in limits.** Within 15 minutes, sign-in is refused for an IP after 10 failures, and for an account after 30 failures, whatever IPs they come from. Since 30 is above the per-IP limit, one IP can't lock someone else's account. That takes failures from at least three IPs, and even then the lock is 15 minutes and covers only connector sign-in, not the dashboard. Behind a reverse proxy, start uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy ip>`, so the limit sees real client IPs rather than the proxy's. Every sign-in, failure, lockout and denial is audit-logged (channel `mcp`).
- API keys and JWTs keep working on both transports for service integrations (Hermes, cron, bots).
- OAuth stays off unless `MCP_PUBLIC_URL` is set and auth is on (`REALIZE_API_KEY` or JWT). The issuer must be `https://`; plain `http://` is allowed only for `localhost`.

## Tool Families

| Family | Gating | Tools |
|---|---|---|
| `chat` | always on | `realize_chat`, `realize_health`, `realize_status`, `list_systems`, `get_system`, `list_agents`, `list_skills`, `get_history`, `clear_history`, `get_session`, `tender_register_method`, `tender_register_submit`, `request_audit_call` (only with `features.wedge`) |
| `kb`   | `mcp.expose_kb` (on by default) | `kb_search`, `venture_kb_search`, `kb_get_document`, `list_ventures`, `list_packs`, `resolve_pack_item`, `glossary_lookup` |
| `ops`  | `mcp.expose_ops` (on by default) | `list_workflows`, `run_workflow`, `trigger_skill`, `run_evolution`, `list_suggestions`, `approve_suggestion`, `dismiss_suggestion`, `list_approvals`, `approve_request`, `reject_request`, `log_decision` |
| `admin`| `mcp.allow_admin` + `role=owner` + production JWT | `create_venture`, `delete_venture`, `update_setting`, `reload_agents` |

### Chat tool behaviour

* `realize_chat` runs the same pipeline as `POST /api/chat` and returns its response, `message_id` and a **trail summary**: the knowledge-base sources (`id`, `title`, `path`) and which tools ran (`name`, `success`, `held`, and `request_id` for held actions).
* Tool inputs, outputs and errors are left out of the summary. They can carry third-party text (email bodies, web pages, sheet cells), so, like approval results, they are not echoed to MCP clients. The full trail is in the dashboard and `GET /api/conversations`.
* Same rule as the REST chat routes: callers act for themselves. Only `owner`/`admin` may pass another `user_id` to `realize_chat`, `get_history`, `clear_history` or `get_session`; anyone else chats as themselves and gets `MCP_FORBIDDEN` for another user's history or session.

### Venture scope

A caller limited to some ventures (a `users.yaml` user with `ventures`, or a JWT with `venture:<key>` scopes) gets a fail-closed subset: chat, agents, skills, history, session, KB search and approvals tools work only when they name one of those ventures; `approve_request` / `reject_request` only for approvals in them; `list_systems` / `list_ventures` are filtered; anything that spans every venture (admin, evolution, cross-venture KB) returns `MCP_FORBIDDEN`. Callers without a venture limit are unaffected.

### Self-serve tender register

With `features.wedge` on, `tender_register_method`, `tender_register_submit` and `request_audit_call` let anyone's agent build a tender requirements register. The agent reads the document itself; RealizeOS supplies the method and the market's sourced rules, checks the register, and returns it as a finished document with its verification level. See [self-serve-wedge.md](self-serve-wedge.md).

### Decision log

`log_decision` (ops, editor scope) proposes a decision made outside RealizeOS, such as in a meeting, a call or a message thread, with its source and locator. It never writes directly: the proposal goes to the approval queue, and the decision is recorded in the venture's `B-brain/decisions/` only when a person approves it. Without a located source the decision is stored as unverified. See [decision-log.md](decision-log.md).

### Admin tool behaviour

* Off by default. To expose, set `mcp.allow_admin: true` (or `MCP_ALLOW_ADMIN=true`).
* In `REALIZE_ENV=production`, enabling admin requires `REALIZE_JWT_ENABLED=true` and a ≥ 32-char `REALIZE_JWT_SECRET`. The server refuses to start otherwise.
* Caller must hold `role=owner`. Editor and viewer get `MCP_INSUFFICIENT_SCOPE`.
* `delete_venture` requires an explicit `confirm: true` flag — guards against an over-eager external agent.
* `update_setting` does an atomic YAML write with rollback on parse failure (same pattern as `PUT /api/settings/features`).
* `create_venture` + `delete_venture` refresh `app.state.systems` in-process so subsequent MCP calls see the change immediately.
* Every admin call is audit-logged with full payload regardless of `mcp.audit_full_payload`.

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
* `list_packs`, `resolve_pack_item` and `glossary_lookup` expose a venture's profession and market packs ([packs.md](packs.md)). Each needs `venture_key`; resolved items come back with their layer, pack and verification level. With `features.packs` off they show only the firm layer and core.

## Plug into Claude Code or a header-based client

```json
{
  "mcpServers": {
    "realize-os": {
      "type": "http",
      "url": "http://localhost:8080/mcp",
      "headers": { "Authorization": "Bearer <your jwt or API key>" }
    }
  }
}
```

Clients that only speak HTTP+SSE can keep using `http://localhost:8080/mcp/sse`. For Claude.ai and Claude Desktop custom connectors, use OAuth (above).

## Security

- No anonymous access — `/mcp`, the SSE handshake and every JSON-RPC POST go through the existing auth middleware.
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

- stdio transport (local install without network) — STORY-37.
- Venture-scoped agent tokens and governed MCP writes — STORY-37.
- Remove HTTP+SSE after a deprecation window, once existing clients have moved to `/mcp`.
- ~~Per-tool feature flags inside `mcp:` config~~ — done: `mcp.tools`.
