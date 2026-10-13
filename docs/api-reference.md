# API Reference

## Base URL

```
http://localhost:8080
```

## Authentication

RealizeOS supports three authentication methods:

### API Key (simple)

If `REALIZE_API_KEY` is set, include it in requests:

```
Authorization: Bearer YOUR_API_KEY
```
or
```
X-API-Key: YOUR_API_KEY
```

### JWT (multi-user)

If `REALIZE_JWT_ENABLED=true`, obtain a token first:

```bash
# Get tokens
curl -X POST http://localhost:8080/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'

# Use the access token
curl -H "Authorization: Bearer <access_token>" http://localhost:8080/api/systems
```

### Agent token (outside agents)

An outside agent gets its own venture-scoped token (`rzag_...`, see [Agent Tokens](#agent-tokens)) instead of the API key. Send it the same way, as `Authorization: Bearer rzag_...` or `X-API-Key: rzag_...` (never in the URL). The agent reads within its ventures and may chat; every other write returns `403`, because outside agents change things through [MCP](mcp-server.md#governed-writes-from-outside-agents), where a person approves first. An invalid, expired or revoked token returns `401` with `"error": "invalid_token"`.

### No Auth (development)

If neither `REALIZE_API_KEY` nor JWT is configured, the API runs in open mode (suitable for local development).

---

## Chat

### POST /api/chat

Send a message and receive an AI response.

**Request:**
```json
{
  "message": "Help me draft a strategy for Q2",
  "system_key": "consulting",
  "user_id": "user-123",
  "agent_key": "analyst",
  "channel": "api"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| message | string | yes | The user's message |
| system_key | string | yes | Target system key |
| user_id | string | no | User identifier (default: "api-user"). With auth on, only `owner`/`admin` callers (including API-key integrations) may name another user; anyone else always chats as themselves |
| agent_key | string | no | Force a specific agent |
| channel | string | no | Channel for formatting (default: "api") |

**Response:**
```json
{
  "response": "Tower B has 900k EUR left [S1].",
  "system_key": "consulting",
  "agent_key": "analyst",
  "user_id": "user-123",
  "message_id": 412,
  "trail": {
    "sources": [{"id": "S1", "title": "Budget", "path": "systems/consulting/B-brain/budget.md"}],
    "steps": [
      {"type": "tool_call", "id": "toolu_01", "name": "sheets_read", "input": {"range": "A1:D20"}},
      {"type": "tool_result", "id": "toolu_01", "name": "sheets_read", "success": true, "held": false,
       "output": "spent: 300k", "error": null, "duration_ms": 412.3}
    ]
  }
}
```

`trail` is the "what I used" record of the answer (since 5.7.0): the knowledge-base sources its
prompt included, numbered `[S1]…[Sn]`, and the tool steps it took, in order. Step types are
`tool_call`, `tool_result` and `approval_requested` (an action held for approval, with its
`request_id`). `message_id` is the stored assistant message. With `features.cite_sources` on,
answers on the `api`, `dashboard` and `mcp` channels cite sources inline as `[S1]`.

With packs on, the rule cards the prompt included are sources too, numbered `[R1]…[Rn]`. A rule
source also carries its provenance; fields a source doesn't have are left out:

```json
{"id": "R1", "title": "Public works contracts include price revision.",
 "path": "https://diariodarepublica.pt/", "layer": "market", "pack": "pt@0.1.0",
 "verification": 1, "as_of": "2026-10-13", "review_by": "2027-04-13"}
```

`layer` is `firm`, `market` or `profession`; `pack` is `id@version` (absent for the firm's own
rules); `verification` is the level from 0 (unverified) to 4 (field-proven), see
[packs](packs.md#verification-levels). Older stored trails have no provenance.

### POST /api/chat/stream

Same request as `POST /api/chat`; the answer arrives as Server-Sent Events. Each event is a
`data:` line with a JSON object and a `type`:

| `type` | When |
|--------|------|
| `source` | A numbered source the prompt includes (`id`, `title`, `path`; rule cards add `layer`, `pack`, `verification`, `as_of`, `review_by`) |
| `tool_call` | The agent calls a tool (`id`, `name`, `input`) |
| `tool_result` | The tool finished (`success`, `held`, `output` preview, `error`, `duration_ms`) |
| `approval_requested` | The action is held for approval (`request_id`) |
| `text` | The model's final answer text (before output cleanup) |
| `final` | Last event: the full `POST /api/chat` response, including `trail` and `message_id` |
| `error` | Last event on failure: `detail` (no internal information) |

Lines starting with `:` are keepalives. An unknown `system_key` returns a plain HTTP 404 before the
stream starts.

### GET /api/conversations/{system_key}/{user_id}

Get conversation history. Each message has its stored `id`; assistant messages that used sources or
tools also carry their `trail`. With auth on, callers other than `owner`/`admin` get 403 for any
`user_id` but their own (this also applies to `DELETE`).

**Query params:** `limit` (int, default 50)

### DELETE /api/conversations/{system_key}/{user_id}

Clear conversation history.

---

## Authentication

### POST /api/auth/token

Generate JWT access + refresh token pair.

**Request:**
```json
{
  "username": "admin",
  "password": "your-password"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### POST /api/auth/refresh

Refresh an expired access token.

**Request:**
```json
{
  "refresh_token": "eyJ..."
}
```

### GET /api/auth/me

Verify current token and return user claims.

### GET /api/auth/session

The dashboard's cookie session: `authenticated`, `user_id`, `role`, `ventures` (the ventures the user is limited to, or `null` for all) and `permissions` (the role's RBAC permissions, sorted). `POST /api/auth/login` returns `permissions` too. The dashboard uses them to hide or explain controls the role can't use (for example, a viewer sees no Approve or Reject); the server still checks every request.

---

## Systems

### GET /api/systems

List all configured systems.

### GET /api/systems/{system_key}

Get system details (agents, routing, venture config).

### GET /api/systems/{system_key}/agents

List agents for a system.

### GET /api/systems/{system_key}/skills

List available skills for a system.

### GET /api/systems/{system_key}/sessions/{user_id}

Get active creative session. Same rule as `/api/conversations`: a caller reads their own session; only owner and admin people may name another user, and an outside agent (agent token) never may (`403`).

### POST /api/systems/reload

Reload system configurations from YAML (hot reload).

---

## Ventures

### GET /api/ventures

List all ventures with their configuration and status.

The response also carries `config_writable` (bool). It is `false` when `realize-os.yaml` can't be edited (for example a read-only Docker mount); the dashboard then hides create and delete, because both edit that file.

### POST /api/ventures

Create a new venture. The key must be a lowercase slug (letters, numbers, hyphens). Errors: `400` invalid key, `409` the venture already exists, `503` the config can't be written (nothing is left behind).

**Request:**
```json
{
  "key": "my-venture",
  "name": "My Venture",
  "description": "Venture description",
  "template": "consulting"
}
```

### GET /api/ventures/{key}

Get venture details.

### PUT /api/ventures/{key}

Update venture configuration.

### DELETE /api/ventures/{key}

Delete a venture: its entry in `realize-os.yaml`, its sessions and conversations, and its folder (the `directory` from its config entry, which must sit directly under `systems/` or `ventures/`).

The delete is all-or-nothing. The folder is moved aside, then the config is rewritten; if that write fails the folder is moved back and nothing has changed. A venture whose folder is already gone is removed from the config only, with a warning.

**Response:** `{"status": "deleted", "key": "...", "warnings": [...]}`

Errors: `400` unsafe or shared folder, `404` unknown venture, `503` the config can't be written (nothing was changed; the detail says why).

---

## Venture Agents

### GET /api/ventures/{key}/agents

List all agents for a venture.

### POST /api/ventures/{key}/agents

Create a new agent within a venture.

### GET /api/ventures/{key}/agents/{agent_key}

Get agent definition and configuration.

`definition_path` (here, in the agent list and in `GET /api/ventures/{key}`) is never a path on the server's disk: a venture's own agent shows its path in the KB (`systems/acme/A-agents/writer.md`), and an agent from a pack shows `<layer>:<pack>@<version>/A-agents/<file>` (`profession:developer@0.1.0/A-agents/procurement.md`).

### PUT /api/ventures/{key}/agents/{agent_key}

Update an agent definition.

### DELETE /api/ventures/{key}/agents/{agent_key}

Delete an agent from a venture.

---

## Agent registry

The registry of loaded agent definitions (V1 markdown and V2 YAML), across the ventures the caller may see.

### GET /api/agents

Query: `version` (`1` or `2`), `persona` (V2 persona key), `venture` (one venture's agents; `404` for a venture you can't see).

With `features.packs` on, each venture's **effective team** is listed: its own agents plus the agents of its profession and market packs and its firm overrides ([packs.md](packs.md#what-packs-change-at-run-time)). Each entry then also says where it came from:

| Field | Meaning |
|---|---|
| `venture_key` | The venture the agent belongs to (`null` for one registered through this API) |
| `layer` | `venture` (the venture's own `A-agents/` file), `firm`, `market` or `profession` (from a pack), or `api` |
| `pack` | `id@version` of the pack (pack agents only) |
| `verification` | The market pack's verification level, 0–4 (market pack agents only) |
| `read_only` | `true` for pack and firm-override agents |
| `override_path` | For a read-only agent: where the venture's own copy goes (relative to the KB root) |

The venture's own file wins: a pack agent with the same key as one of the venture's agents isn't listed for that venture. A pack shared by several ventures is listed once per venture. With the flag off, the response is the same as before packs (no provenance fields).

```json
{ "key": "estimator", "name": "Estimator", "venture_key": "acme", "layer": "profession",
  "pack": "developer@0.1.0", "read_only": true, "override_path": "systems/acme/A-agents/estimator.md", "...": "..." }
```

### GET /api/agents/{agent_key}

One agent. Query `venture` names the venture whose agent is meant (a pack agent of that venture, or the venture's own); without it, the registry's agent, else the first visible venture's pack agent of that key.

### PUT /api/agents/{agent_key} · DELETE /api/agents/{agent_key}

Update (V2 only) or unregister an agent in the in-memory registry. Query `venture` as above. A pack or firm-override agent is read-only: `409` and nothing is written into the pack:

```json
{ "detail": { "error": "pack_agent_read_only", "agent_key": "estimator", "venture_key": "acme",
  "layer": "profession", "pack": "developer@0.1.0", "override_path": "systems/acme/A-agents/estimator.md",
  "message": "Agent 'estimator' comes from the profession pack developer@0.1.0 and is read-only here; ... override it in your venture: add systems/acme/A-agents/estimator.md. ..." } }
```

To change a pack agent for one venture, copy it to `override_path` and edit the copy; the venture's own file wins over the pack's.

---

## Venture Knowledge Base

### GET /api/ventures/{key}/kb

Browse the FABRIC directory structure for a venture.

### GET /api/ventures/{key}/kb/{path}

Read a file from the venture knowledge base.

### PUT /api/ventures/{key}/kb/{path}

Create or update a file in the venture knowledge base.

### DELETE /api/ventures/{key}/kb/{path}

Delete a file from the venture knowledge base.

---

## Workflows

### GET /api/workflows

List all workflows.

### POST /api/workflows

Create a new workflow.

### GET /api/workflows/{id}

Get workflow details and execution status.

### POST /api/workflows/{id}/execute

Execute a workflow.

---

## Approvals

### GET /api/approvals

List approval requests, newest first, in the caller's ventures. Query: `status` (default `pending`; `decided` for approved, rejected and answered items; empty for every status), `venture_key` and `limit` (default 50, at most 500; outside that range is `422`). Decided items (`decided`, `approved`, `rejected`, `answered`) come most recently decided first (`decided_at`); the rest newest first. The dashboard's Decided tab asks for `?status=decided&limit=50`.

Each row's `status` is its **effective** status, and every row carries `expired` (bool):

- `pending` means it can still be decided: a pending item whose `expires_at` has passed is listed as `expired`, not `pending`, and `?status=pending` leaves it out.
- `?status=expired` returns the items no one decided in time. Nothing ran for them, and they can't be approved or rejected any more.

The MCP `list_approvals` tool and the morning briefing use the same rule.

Every row also carries `requested_by_agent`: `{"token_id", "name"}` when an outside agent asked for it (its [agent token](#agent-tokens)'s current name; `{"token_id": null, "name": "stdio"}` for a local stdio session), else `null`. The dashboard shows it as an "Outside agent" badge on the card, so the person deciding sees that the request crossed the approval boundary. A caller with an agent token gets its usual status summary instead, without this field.

### POST /api/approvals/{id}/approve

Approve an approval request. The response is the decided row plus `execution` (`{executed, success, output, error}` for an action that ran, else `null`) and `skill_output`. Approved does not mean done: check `execution`, or later the row's `execution_status` (`succeeded`, `failed`, or `claimed`, which means started with no result recorded, so a person must check).

### POST /api/approvals/{id}/reject

Reject an approval request.

People decide: a caller with an agent token gets `403` on approve and reject.

Both return the approval row with the outcomes added: `execution` (a held action that ran), `skill_output` (a skill that resumed) and `decision_log`, whether the decision reached the venture's [decision log](decision-log.md#when-a-write-fails): `{"logged", "pending", "error", "decision_id"}`. `pending: true` means the write failed and is queued for a retry; the decision itself stands.

A mission step whose action was held waits as `awaiting-approval`, and the steps that depend on it wait too. Approving the action completes the step and the mission continues; rejecting it (or an approved action that fails) fails the step, and the steps that depend on it never run.

When the item exists but can't be decided any more, approve and reject return `409` and change nothing:

```json
{
  "detail": "This request was already approved by dana@acme.io. Your decision was not applied.",
  "reason": "already_decided",
  "approval": {"id": "…", "status": "approved", "expired": false, "decided_by": "dana@acme.io", "decided_at": "…", "execution_status": "succeeded", "…": "…"}
}
```

`reason` is `expired` (no one decided in time) or `already_decided` (someone else decided first; of two concurrent decisions exactly one wins). An item that doesn't exist, or isn't in the caller's ventures, is `404` as before. (Earlier versions returned `404` for a repeat or expired decision too.)

---

## Agent Tokens

Venture-scoped tokens for outside agents (STORY-37). Owner or admin only, and not a user limited to some ventures. An admin can't issue a token that acts for a user with a higher role (the owner). Behind `features.agent_tokens` (on by default). See [mcp-server.md](mcp-server.md#agent-tokens-one-agent-one-clients-brain) for what a token can do.

### GET /api/agent-tokens

List every token. Secrets are never stored, so they are never listed.

```json
{
  "enabled": true,
  "tokens": [
    {
      "id": "3f9a0c1d2e4b",
      "name": "claude-desktop-acme",
      "principal": "agent:3f9a0c1d2e4b",
      "user": "dana@acme.io",
      "ventures": ["acme"],
      "status": "active",
      "created_by": "owner@example.com",
      "created_at": "2026-10-13T09:00:00+00:00",
      "expires_at": "2027-01-11T09:00:00+00:00",
      "last_used_at": "2026-10-13T09:05:12+00:00",
      "revoked_at": null,
      "revoked_by": null
    }
  ]
}
```

`status` is `active`, `expired` or `revoked`.

### POST /api/agent-tokens

Issue a token. The token is in this response only: copy it now.

```json
{
  "name": "claude-desktop-acme",
  "user": "dana@acme.io",
  "ventures": ["acme"],
  "expires_in_days": 90
}
```

- `name` — 1-64 letters, digits, spaces, dots, dashes or underscores.
- `user` — a `users.yaml` user; their role applies to the agent.
- `ventures` — at least one configured venture, each one the user may see.
- `expires_in_days` — optional, 1-3650. Omit for no expiry.

Returns `201`:

```json
{
  "token": "rzag_3f9a0c1d2e4b_…",
  "agent_token": { "id": "3f9a0c1d2e4b", "status": "active", "…": "…" },
  "message": "Copy the token now: it is shown only once. Send it as 'Authorization: Bearer <token>'."
}
```

`400` for an unknown user or venture, or a venture outside the user's list; `403` for a caller who may not manage tokens; `409` when `features.agent_tokens` is off.

### DELETE /api/agent-tokens/{id}

Revoke a token now. The agent's held MCP writes that are still waiting for approval are withdrawn (rejected).

```json
{ "agent_token": { "id": "3f9a0c1d2e4b", "status": "revoked", "…": "…" }, "withdrawn_approvals": 1 }
```

`404` for an unknown id. Revoking twice is harmless.

---

## Extensions

### GET /api/extensions

List all extensions and their status.

### POST /api/extensions/install

Install a new extension.

### DELETE /api/extensions/{name}

Uninstall an extension.

---

## Webhooks

### GET /api/webhooks

List registered webhooks.

### POST /api/webhooks

Register a new webhook.

### DELETE /api/webhooks/{id}

Delete a webhook.

### POST /api/webhooks/{id}/test

Send a test event to a webhook.

---

## Settings

### GET /api/settings

Get general system settings.

### PUT /api/settings

Update general system settings.

### Settings Sub-Categories

| Endpoint | Description |
|----------|-------------|
| `GET/PUT /api/settings/llm` | LLM provider configuration and routing |
| `GET/PUT /api/settings/memory` | Memory and learning log settings |
| `GET/PUT /api/settings/security` | Security configuration |
| `GET/PUT /api/settings/tools` | Tool availability and configuration |
| `GET/PUT /api/settings/trust` | Trust and approval gate settings |
| `GET/PUT /api/settings/skills` | Skill configuration |
| `GET /api/settings/reports` | System reports and analytics |

---

## Trust

### GET /api/trust

The trust ladder: `level` (1-5) and `actions` (each governance action's decision per level: `block`, `approve` or `auto`). The ladder spans every venture: a venture-limited caller gets `403`.

With `features.packs` on, `ventures` adds each venture's **effective** decisions at the current level, after its packs and firm overrides ([packs.md](packs.md#what-packs-change-at-run-time)). Packs only tighten trust, so `effective` is never looser than `ladder`:

```json
"ventures": {
  "acme": {
    "name": "Acme Tower",
    "layers": [{"layer": "firm", "pack": null}, {"layer": "market", "pack": "pt@0.1.0"}, {"layer": "profession", "pack": "developer@0.1.0"}],
    "actions": [
      {"action": "data_write", "governed_by": null, "ladder": "approve", "effective": "block", "tightened": true,
       "source": {"layer": "market", "pack": "pt@0.1.0", "key": "data_write", "value": "block", "label": "market pack pt@0.1.0"},
       "ignored": []},
      {"action": "gmail_send", "governed_by": "send_email", "ladder": "approve", "effective": "approve", "tightened": false,
       "source": null,
       "ignored": [{"layer": "profession", "pack": "developer@0.1.0", "key": "gmail_send", "value": "auto", "label": "profession pack developer@0.1.0", "reason": "loosen"}]}
    ],
    "warnings": ["profession pack developer@0.1.0 would loosen gmail_send from approve to auto; ignored (packs only tighten trust)"]
  }
}
```

There is one row per governance action of the ladder and one per tool action a pack or the firm names on its own (`governed_by` is the governance action it falls under; a tool action the ladder has no rule for is shown as a write, `unknown_write`). `source` is the layer whose default set the effective decision (`label` is `firm overrides` for the firm's own `F-foundations/overrides/trust.yaml`). `ignored` lists defaults that were not applied: `loosen` (it would loosen the ladder's decision) or `invalid` (not `auto`, `approve` or `block`); `warnings` says the same once per venture. The governance gate uses the same calculation, so the matrix and the gate agree. With the flag off the response has no `ventures`.

### PUT /api/trust/level

Body `{"level": 1-5}`: set the trust level in `realize-os.yaml` and reload. Needs `system:manage`.

---

## Storage

### GET /api/settings/storage

Get storage configuration (local/S3).

### PUT /api/settings/storage

Update storage configuration.

### POST /api/settings/storage/test

Test storage connection.

### POST /api/settings/storage/sync

Trigger a sync operation.

---

## Security

### GET /api/security/scan

Run the security posture scanner and return results.

### GET /api/security/audit

Get audit log entries.

---

## Evolution

### GET /api/evolution/suggestions

Get self-improvement suggestions (gap detection, skill suggestions).

### POST /api/evolution/accept/{id}

Accept a suggestion.

### POST /api/evolution/reject/{id}

Reject a suggestion.

---

## Activity

### GET /api/activity/stream

SSE (Server-Sent Events) activity feed streaming real-time agent actions.

### GET /api/activity

Get recent activity log entries.

---

## Dashboard

### GET /api/dashboard

Dashboard overview for the caller's ventures: `ventures` (each with `agent_count` and `skill_count`), `venture_count`, `recent_activity`, `agent_total` and `agent_summary`.

`agent_total` is the number of configured agents, the sum of the ventures' `agent_count`. `agent_summary` counts those same agents by runtime state (`idle`, `running`, `paused`, `error`), so its values add up to `agent_total`. An agent with no runtime state yet (a fresh install, or one that has never run) counts as `idle`; state left over for an agent that is no longer configured is not counted.

---

## Developer Mode

### GET /api/devmode/status

Get developer mode status and configuration.

### POST /api/devmode/setup

Generate AI tool context files.

### GET /api/devmode/health

Run developer mode health check.

---

## MCP Server (5.1.0+)

The MCP server is enabled when `MCP_ENABLED=true` or `mcp.enabled: true` in config. It uses the same authentication as the REST API.

### GET /mcp/sse

Establish an SSE connection for MCP JSON-RPC. Returns a session ID for subsequent message calls.

**Headers:**
```
Authorization: Bearer <token>
Accept: text/event-stream
```

### POST /mcp/messages/{session_id}

Send a JSON-RPC request to an active MCP session.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "realize_chat",
    "arguments": {
      "message": "What's the pipeline status?",
      "system_key": "arena"
    }
  },
  "id": "1"
}
```

### GET /mcp/health

MCP-specific health check. Returns enabled tool families and session count.

**Response:**
```json
{
  "mcp_enabled": true,
  "tools": 24,
  "families": ["chat_status", "kb_read", "ops", "admin"],
  "active_sessions": 3
}
```

> 📖 Full tool catalog: **[MCP Server Reference](mcp-server.md)**

---

## Health

### GET /api/health

Basic health check. Returns `{"status": "ok"}`.

**Alias:** Also available at `GET /health` (root path) for load balancers and older deployments.

### GET /api/status

Detailed status: ventures and their agents, LLM providers, tool availability, usage.

Requires authentication, like the rest of the API: it names every venture and agent the caller can see, so it is not a public probe. Use `GET /api/health` for liveness checks.
