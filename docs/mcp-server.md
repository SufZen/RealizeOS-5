# RealizeOS Built-in MCP Server

> Introduced in **RealizeOS 5.1.0** — **35 tools** across 4 families in the 5.31 release content: Chat & Status (13), KB Read (7), Ops (11), Admin (4).

RealizeOS exposes its REST surface over the [Model Context Protocol](https://modelcontextprotocol.io) so any MCP-speaking agent — Claude Desktop, Cursor, n8n, cloud routines, your own scripts — can call into a user's RealizeOS instance.

This is the **inverse** of [`realize_core/tools/mcp.py`](../realize_core/tools/mcp.py), which is the outbound *client* (RealizeOS calling external MCP servers).

To connect a specific agent (Claude Code, Claude Desktop, Claude.ai, Cowork, ChatGPT, Cursor), follow [connect-your-agent.md](connect-your-agent.md).

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
  rate_limit_per_minute: null  # tool calls per caller per minute; empty = API_RATE_LIMIT_PER_MINUTE
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

Local agents can also use the [stdio transport](#local-agents-stdio) (`python cli.py mcp stdio`), which opens no port.

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

* `realize_chat` runs the same pipeline as `POST /api/chat` and returns its response, `message_id` and a **trail summary**: the knowledge-base sources (`id`, `title`, `path`), the pack rule cards (`[R1]`…) with their `layer`, `pack`, `verification` level (0 unverified to 4 field-proven) and `as_of` / `review_by` dates, and which tools ran (`name`, `success`, `held`, and `request_id` for held actions). Show a rule's level to the person whatever the answer text says; level 1 is a draft that no local professional has reviewed.
* Tool inputs, outputs and errors are left out of the summary. They can carry third-party text (email bodies, web pages, sheet cells), so, like approval results, they are not echoed to MCP clients. The full trail is in the dashboard and `GET /api/conversations`.
* `get_history` returns each stored answer with the same trail summary under `trail`, like `GET /api/conversations` does: the sources with their provenance (`layer`, `pack`, `verification`, `as_of`, `review_by`) and which tools ran, without tool inputs or outputs. Questions, and answers stored before trails were kept, have no `trail`.
* Same rule as the REST chat routes: callers act for themselves. Only `owner`/`admin` may pass another `user_id` to `realize_chat`, `get_history`, `clear_history` or `get_session`; anyone else chats as themselves and gets `MCP_FORBIDDEN` for another user's history or session.

### Venture scope

A caller limited to some ventures (a `users.yaml` user with `ventures`, or a JWT with `venture:<key>` scopes) gets a fail-closed subset: chat, agents, skills, history, session, KB search and approvals tools work only when they name one of those ventures; `approve_request` / `reject_request` only for approvals in them; `list_systems` / `list_ventures` are filtered; anything that spans every venture (admin, evolution, cross-venture KB) returns `MCP_FORBIDDEN`, and `tools/list` doesn't offer it to them. Callers without a venture limit are unaffected.

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
* The skill is the one of the venture named in `system_key`: that venture's own copy (every venture has its own copy of a pack skill, with its own `variables` such as its sheet ids), else a shared or global skill, never another venture's. Without `system_key` only a shared or global skill runs; a venture's skill returns `MCP_VALIDATION` (name the venture), even when only one venture has it. A caller limited to some ventures must name one of them as `system_key` (`MCP_FORBIDDEN` for any other, before the skill is looked up) and runs that venture's copy; a held write runs the copy of the venture it was held in. A venture can't be keyed `shared`: that name is reserved for the firm's shared skills, and such a venture's skills are not loaded.
* `run_evolution` triggers `realize_core.evolution.gap_detector.run_gap_analysis(days=...)`. Default window is 7 days; capped at 90.
* `approve_suggestion` / `dismiss_suggestion` operate on the in-memory `EvolutionEngine` proposal store (same singleton the dashboard uses).
* `approve_request` / `reject_request` delegate to `realize_core.governance.gates` for the approval queue — preserves all governance checks. A pack verification (`pack_verify`) changes what every venture sees: only an owner without a venture limit may decide it; anyone else gets `MCP_FORBIDDEN` and the request stays pending.
* Scope: every `list_*` is `read`; everything that changes state (`run_*`, `trigger_*`, `approve_*`, `dismiss_*`, `reject_*`) requires `role >= editor`.

### KB tool behaviour

* `kb_search` runs the same hybrid FTS5+vector indexer the dashboard uses (`realize_core.kb.indexer.semantic_search`). Snippets are capped at 500 chars; full content is available via `kb_get_document`.
* `kb_get_document` enforces path-traversal protection: the resolved path must live under `app.state.kb_path`. Absolute paths and `..` segments are rejected with `MCP_VALIDATION` / `MCP_FORBIDDEN`.
* `venture_kb_search` is a convenience: it validates the venture exists, then delegates to `kb_search` with the venture as `system_key`.
* `list_ventures` mirrors `GET /api/ventures` — venture key, name, agent count, skill count, FABRIC completeness.
* `list_packs`, `resolve_pack_item` and `glossary_lookup` expose a venture's profession and market packs ([packs.md](packs.md)). Each needs `venture_key`; resolved items (`term`, `rule`, `document`, `skill`, `agent`, `trust`, `measure`, `default`) come back with their layer, pack and verification level. With `features.packs` off they show only the firm layer and core. With it on, a venture's pack skills and agents are also listed by `list_skills`, `list_workflows` and `list_agents`, like its own.

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

## Agent tokens (one agent, one client's brain)

The API key is a service identity with access to every venture. Don't give it to an outside agent. Give each agent its own **agent token** instead: one agent, scoped to one client's ventures, that you can revoke on its own.

Create one on the server, in the project folder (where `users.yaml` lives):

```bash
python cli.py agent-token create --name claude-desktop-acme --user dana@acme.io --venture acme --expires-in-days 90
```

or over REST as an owner or admin:

```bash
curl -X POST http://localhost:8080/api/agent-tokens \
  -H "X-API-Key: $REALIZE_API_KEY" -H "Content-Type: application/json" \
  -d '{"name": "claude-desktop-acme", "user": "dana@acme.io", "ventures": ["acme"], "expires_in_days": 90}'
```

The token (`rzag_<id>_<secret>`) is shown once. Use it like the API key: `Authorization: Bearer rzag_...` (or `X-API-Key`) on `/mcp`, `/mcp/sse` and the REST API. It is never accepted in the URL.

What a token is:

- **Bound to a `users.yaml` user.** Their role applies (a viewer's agent can only read). If you remove the user, their agents' tokens stop working at once.
- **Limited to the ventures it names.** It must name at least one, each one the user may see. On every request the token's ventures are intersected with the user's current list, so a token never sees more than its user, and one whose ventures all fall away stops working.
- **Its own identity.** Requests carry `agent:<id>` as the user: in the audit log, the approval queue (`requested_by`), conversation memory and the rate limiter. An agent always chats and reads history as itself, whatever its user's role.
- **Stored as a SHA-256 hash** (migration 012) and compared in constant time. Optional expiry; `last_used_at` is recorded.
- **Revocable:** `python cli.py agent-token revoke <id>` or `DELETE /api/agent-tokens/<id>`. It stops at once, and everything the agent has waiting for approval is withdrawn: its held writes, writes held from its chat, and its decision proposals. Before anything an agent asked for runs, its token is checked again; a token that expired or was turned off meanwhile means the approved item is recorded as failed and nothing runs.

`python cli.py agent-token list` (or `GET /api/agent-tokens`) shows every token without secrets. Creating, revoking and every refused use are audit-logged (`agent_token.*`).

In the dashboard, an owner or admin with every venture manages tokens under **Configure → Agent tokens** (`/settings/agent-tokens`, or Ctrl/⌘ K): the list (no secrets), a form to create one (the token is shown once, with a copy button), and Revoke. Other people don't see the page.

Agent tokens are on by default (`features.agent_tokens: true`). Nothing changes until you create one; turning the flag off makes every agent token stop working at once, including the writes its agents have waiting: approving one afterwards records it as failed, and nothing runs. They need auth to be on (`REALIZE_API_KEY` or JWT): with auth off the API is open and a token limits nothing.

Over REST an agent reads within its ventures and may chat (`/api/chat`, its own conversation). Every other REST write is refused with `403`: an outside agent changes things through MCP, where a person approves first. Approve, reject and dismiss return `403` with the same "People decide" rule as MCP. Chat over REST (`/api/chat`, `/api/chat/stream`) follows the same chat rules as `realize_chat` below. Rules match the endpoint the router picked, never the URL, and any method other than GET, HEAD and OPTIONS counts as a write. REST and MCP use one predicate and one rule set (`realize_core/security/agent_access.py`), so the two surfaces can't drift.

Only a verified agent token makes a caller an agent. A JWT whose subject or scopes claim an agent identity is refused (`401`), `POST /api/auth/token` won't mint one, an `X-User-ID: agent:...` header is ignored, and `users.yaml` can't define an `agent:` user.

## Governed writes from outside agents

Outside agents go through the same approvals as internal ones. **People decide:** an agent never approves or rejects anything, including its own held writes. Each MCP tool has one rule for an outside agent: a caller with an agent token, or a [local stdio session](#local-agents-stdio):

| Rule | Tools | What happens |
|---|---|---|
| Allowed (read) | `realize_health`, `list_systems`, `get_system`, `list_agents`, `list_skills`, `get_history`, `get_session`, `kb_search`, `venture_kb_search`, `list_ventures`, `list_packs`, `resolve_pack_item`, `glossary_lookup`, `list_workflows`, `list_approvals` | Runs, within the agent's ventures. `realize_status`, `kb_get_document` and `list_suggestions` span every venture, so the venture guard refuses them. |
| Allowed (already governed) | `realize_chat`, `clear_history`, `log_decision`, `tender_register_method`, `tender_register_submit`, `request_audit_call` | Chat runs for the agent: every write tool the internal agent calls is held for a person, **even where the trust ladder would run it automatically**. Without `features.enforce_gates` an agent's chat can't run write tools at all. A trigger phrase doesn't start a skill (the agent is told to use `trigger_skill`), and the agent can't answer a paused skill's question. `clear_history` only clears the agent's own conversation. `log_decision` only proposes; a person confirms. |
| **Held** | `run_workflow`, `trigger_skill` | Nothing runs. The call waits in the approval queue for a person. |
| **People decide** | `approve_request`, `reject_request`, `approve_suggestion`, `dismiss_suggestion` | Refused: `MCP_AGENT_CANNOT_DECIDE`. |
| Refused | `create_venture`, `delete_venture`, `update_setting`, `reload_agents`, `run_evolution` | Refused: `MCP_AGENT_REFUSED`. They change every venture or remove a client's brain, so an owner does them in the dashboard or CLI. Holding them in one venture's queue would let a person limited to that venture approve a change to all of them. |

A tool with no rule is refused (deny by default, exact names only), so a new tool needs a decision before outside agents can call it. `tools/list` shows an outside agent only the tools it may call or have held: the people-decide and refused tools above aren't listed, and calling one by name is still refused. People (dashboard users, the API key, OAuth connectors, JWTs) keep today's behaviour. An OAuth connector acts as the person who signed in; to govern an outside agent as an agent, give it an agent token.

A held call keeps only the arguments the tool declares and must name exactly one of the agent's ventures; that venture's queue gets the item.

A held call answers:

```json
{ "status": "pending_approval", "approval_id": "…", "tool": "run_workflow", "venture_key": "acme",
  "message": "Held for a person to approve. Nothing has run yet. …" }
```

It shows up in the dashboard's approval queue as `mcp:run_workflow`, from the agent (`requested_by: agent:<id>`), with its arguments and an **Outside agent: <token name>** badge (`requested_by_agent` on `GET /api/approvals`), so the person deciding sees that the request came from outside. When a person approves it:

- it runs **once**, as the agent with its own narrowed scope, never as the person who approved it: the row is claimed before anything runs, so a double click or a retry does nothing;
- the token is checked again first: if it was revoked or expired, its user removed, or the venture taken away, nothing runs and the item records why. The stored call must still name the item's venture alone;
- approving the run starts it; each write it makes still waits for a person. Its inputs came from the agent, so it stays the agent's run, under the same rule as an agent's chat: a tool step that writes is held as a new approval from the agent, even where the trust ladder would run it automatically (without `features.enforce_gates` it can't run at all). The workflow pauses there and continues once a person approves that write; the rest of it is still the agent's run, whoever resumes it. If the agent's token stops working (revoked, expired, agent tokens turned off, user removed) while the run is paused or between two steps, the run stops there and nothing after it runs;
- the outcome is posted into the agent's own conversation in that venture.

Held writes expire after 24 hours. At most 25 items per agent wait for a person at once, counting everything it asked for: its held writes, the writes held from its chat or its runs, its `log_decision` proposals and its questions. Past that, a new held write or proposal returns `MCP_TOO_MANY_PENDING`, and a write from its chat is blocked with the same reason ("25 of your requests are already waiting for approval; wait for a decision"). People are not capped.

Follow an item with `list_approvals` (`venture_key` and `approval_id`). An agent sees status, not other people's parameters or results, plus the result of its own writes:

| `outcome` | Meaning |
|---|---|
| `pending_approval` | Waiting for a person. Nothing has run. |
| `rejected` / `expired` | Nothing was done. |
| `succeeded` | Approved and done; `result` has the output. |
| `failed` | Approved, but it failed or was stopped before running (`error` says why). Not retried. |
| `unknown_outcome` | Approved and started, but no result is recorded yet. If the server restarted while it ran, the outcome is unknown: it is never re-run automatically, and a person has to check. |
| `approved_not_started` | Approved, but the server stopped before it started. It will not start on its own. |

## Local agents (stdio)

An agent on the same computer can start RealizeOS itself and talk over stdin/stdout, with no port open:

```bash
python cli.py mcp stdio --directory /path/to/RealizeOS --user dana@example.com [--venture tower-b]
```

- Same tools, families, `mcp.tools`, permission checks, venture scope and audit log as `/mcp`.
- **Identity:** stdio has no HTTP request, so `--user` names the caller. It must be a `users.yaml` entry, and that user's role and ventures apply. `--venture` (repeatable) can only narrow them. There is no default or anonymous user, identity is never read from environment variables, and the server refuses to start without one, in every environment. The `REALIZE_ADMIN_USER` login is not accepted here.
- **Configuration:** `--directory` (or `--root`) is the absolute path of the RealizeOS folder (config, `users.yaml`, `.env`, data, KB). Without it, the folder RealizeOS is installed in is used. The folder the agent starts the command in is never read, so a planted `users.yaml` or config there has no effect.
- **Admin tools** are served over stdio only with `--allow-admin` on the command line (and only to an owner). `mcp.allow_admin` / `MCP_ALLOW_ADMIN` don't widen a stdio session. In production, `--allow-admin` still needs strong JWT settings. A stdio session is an outside agent, so it is still refused every admin tool (`MCP_AGENT_REFUSED`) and `tools/list` doesn't show them.
- Needs `MCP_ENABLED=true`. stdout carries only JSON-RPC: logs, stray `print()` output and child processes go to stderr. A refused start exits with code 2 and the reason on stderr.
- **A stdio session is an outside agent.** Its client is always an AI agent, so it is governed like an agent token: its user id is `agent:stdio:<email>` (everything it asks a person for, held writes, writes held from its chat and decision proposals, is requested by `agent:stdio:<email>`, so the queue shows the **Outside agent** badge, never the person), it sees the ventures named with `--venture` (else the user's ventures, else every venture configured at start), [writes are held](#governed-writes-from-outside-agents) for a person, and it can't approve, reject or dismiss. `--user`'s role and ventures are the upper bound. The marker is set by the stdio entry point itself, so it can't be spoofed. Pilot accounts can't open a stdio session.

Client configs for Claude Code, Claude Desktop and Cursor are in [connect-your-agent.md](connect-your-agent.md).

## Security

- No anonymous access — `/mcp`, the SSE handshake and every JSON-RPC POST go through the existing auth middleware.
- Scope hierarchy: `read` < `editor` < `owner`. Chat-family tools require `read`; `clear_history` requires `editor`; admin tools (Story 5) require `owner`.
- `tools/list` shows each caller only the tools it may call: an RBAC role sees the tools its permissions cover (a viewer doesn't see `realize_chat` or `run_workflow`), the MCP-only roles the tools within their scope, outside agents the tools their rules allow or hold, pilot accounts the pilot tools, and a venture-limited caller no tool that spans every venture. Hiding is a courtesy, not the control: a call to an unlisted tool is refused as before.
- Audit log: every tool call goes through `realize_core/security/audit.py` (same retention + log file as REST).
- Rate limits: see [below](#rate-limits).

## Rate limits

The HTTP rate limiter lets `/mcp` and `/mcp/*` through untouched (buffering them would break the SSE and Streamable HTTP transports), so the MCP dispatcher limits tool calls itself. Each `tools/call` counts against the caller's bucket for one minute, whether it runs, is refused or names an unknown tool:

| Caller | Bucket |
|---|---|
| Agent token | `agent:<token id>`, apart from the person it acts for |
| Local stdio session | `agent:stdio:<email>` |
| Anyone else signed in (API key, JWT, OAuth connector, dashboard user) | `user:<id>` |
| Anonymous (auth off) | `ip:<client address>` |

These are the same buckets as the HTTP limiter, but MCP calls are counted on their own, so a person's dashboard traffic doesn't use up their agent's calls. The limit is `MCP_RATE_LIMIT_PER_MINUTE` (or `mcp.rate_limit_per_minute`), else `API_RATE_LIMIT_PER_MINUTE` (120). A value that isn't a whole number of 1 or more is logged and the API limit applies; there is no "unlimited".

Only tool calls are limited. The connection (the SSE stream, the Streamable HTTP session), `initialize`, `tools/list` and pings are never cut off. A limited call gets an ordinary tool result:

```json
{ "error": "Too many tool calls; try again in 60 seconds.", "code": "MCP_RATE_LIMITED", "retry_after_seconds": 60 }
```

and is audit-logged with outcome `rate_limited` (channel `mcp`, the bucket in `metadata.bucket`). The limiter keeps its counts in memory, per process.
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
| `MCP_AGENT_CANNOT_DECIDE` | An outside agent tried to approve, reject or dismiss. People decide. |
| `MCP_AGENT_REFUSED` | The tool isn't available to an outside agent. |
| `MCP_TOO_MANY_PENDING` | The agent already has 25 items (held writes, writes held from its chat, decision proposals) waiting for approval. |
| `MCP_RATE_LIMITED` | The caller made too many tool calls this minute; `retry_after_seconds` says when to try again. See [Rate limits](#rate-limits). |

## Roadmap

- ~~stdio transport (local install without network)~~ — done: [`mcp stdio`](#local-agents-stdio), with guides per agent in [connect-your-agent.md](connect-your-agent.md).
- ~~Venture-scoped agent tokens and governed MCP writes~~ — done: see [Agent tokens](#agent-tokens-one-agent-one-clients-brain) and [Governed writes](#governed-writes-from-outside-agents).
- Remove HTTP+SSE after a deprecation window, once existing clients have moved to `/mcp`.
- ~~Per-tool feature flags inside `mcp:` config~~ — done: `mcp.tools`.
