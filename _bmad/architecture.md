# Architecture: RealizeOS 5.1.0

> Built per [MTH-36](file:///H:/BMAD/workflows/MTH-36-architecture-workflow.md). Companion: [`PRD.md`](PRD.md), [`project-context.md`](project-context.md).

## System Overview

5.1.0 adds two new components to the existing RealizeOS-5 architecture without changing the deployment topology — they live inside the same FastAPI/uvicorn process and talk to the same SQLite + filesystem state.

```
                ┌─────────────────────────────────────────────────────────────┐
                │                  Single uvicorn process :8080                │
                │                                                              │
                │  ┌──────────────────────────────────────────────────────┐    │
                │  │              FastAPI app (realize_api/main.py)        │    │
                │  │                                                       │    │
   REST  ──────►│  │  /api/*       routes/{chat,systems,ventures,...}      │    │
                │  │                                                       │    │
   MCP   ──────►│  │  /mcp/sse                                             │◄── NEW (Story 2)
   (SSE)        │  │  /mcp/messages/{session_id}                           │    │
                │  │                  │                                    │    │
                │  │                  ▼                                    │    │
                │  │  realize_core/mcp_server/  ──► same route handlers    │    │
                │  └──────────────────────────────────────────────────────┘    │
                │            │                              │                   │
                │            ▼                              ▼                   │
                │  ┌──────────────────────┐    ┌──────────────────────────┐    │
                │  │  SQLite              │    │  filesystem (FABRIC)      │    │
                │  │  /app/data/*.db      │    │  /app/systems, /app/shared│    │
                │  └──────────────────────┘    └──────────────────────────┘    │
                └─────────────────────────────────────────────────────────────┘
                            ▲                              ▲
                            │                              │
                  realize-os CLI (Python)          @realize-os/cli (npm)
                  ── operator: chat, kb, mcp, ──   ── bootstrap: docker init ──
                     workflow, skill, repl
                  NEW (Stories 6-8)
```

External agents (Claude Desktop, Cursor, n8n, cloud routines) point at `https://<host>:8080/mcp/sse` with `Authorization: Bearer <jwt>` and use RealizeOS as a tool surface. Internal call path: MCP request → auth check → tool dispatch → existing REST route handler → core engine. No business logic duplicated.

## Tech Stack Decisions

| Decision | Choice | Rationale | Alternatives Considered |
|---|---|---|---|
| **MCP transport** | HTTP+SSE | Network-accessible (cloud routines, remote agents); only well-supported MCP transport in the official Python SDK as a server today. | stdio (defer to 5.2.0 — only useful for Claude Desktop on the same machine; Streamable HTTP — spec still evolving). |
| **MCP SDK** | `mcp` Python package (already in `requirements.txt`) | Used as the *client* today — same package gives us the *server* via `mcp.server.lowlevel.Server` + `mcp.server.sse.SseServerTransport`. No new dep. | Hand-rolled JSON-RPC. Rejected: more code, more bugs, no spec compliance. |
| **MCP mount point** | Same FastAPI app, `/mcp/*` prefix | One process, one port, one TLS terminator, one auth middleware. Operationally simpler. | Separate uvicorn process. Rejected: doubles deploy complexity, fights `docker-compose.yml`. |
| **MCP auth** | Reuse `realize_api/dependencies.py::get_current_user` (JWT + X-API-Key) | One identity system across REST + MCP. Token issuance via existing `POST /api/auth/token`. | Per-MCP bearer tokens. Rejected: two auth systems = bugs. |
| **CLI framework** | [Typer](https://typer.tiangolo.com/) | Sits on Click, gives autocomplete + rich help + subcommand groups + `Annotated` type hints. Used by FastAPI's own CLI — battle-tested. | Click directly (more boilerplate); `argparse` (no autocomplete, weak help); `fire` (less polish for production). |
| **CLI REPL** | `prompt-toolkit` | Streaming-friendly, multi-line input, history, slash commands. Standard choice. | `cmd` (stdlib) — no async streaming; `rich.prompt` — no multi-line/history. |
| **CLI output** | `rich` for tables + colour | Already a transitive dep; cross-platform; respects `NO_COLOR`. | Plain print — fails the UX bar; `tabulate` — narrower. |
| **CLI profile storage** | `~/.realize-os/config.toml` (TOML) | Stdlib `tomllib` (read) + `tomli_w` (write). Human-editable. | YAML — fine but TOML is the modern Python config standard (`pyproject.toml` precedent). |

## Data Model

### New config section in `realize-os.yaml`

```yaml
mcp:
  enabled: false              # master switch — off by default
  expose_kb: true             # KB read tools available to authenticated callers
  expose_ops: true            # workflow / skill / evolution tools
  allow_admin: false          # admin/write tools — opt-in, requires production auth
  bearer_token_override: ""   # optional: hard-coded token for clients that can't do JWT (rotate often)
  audit_full_payload: false   # if true, log full tool args (PII risk; off by default)
```

### New env vars (`.env.example`)

| Var | Type | Purpose |
|---|---|---|
| `MCP_ENABLED` | `bool` | Overrides `mcp.enabled` in YAML. |
| `MCP_ALLOW_ADMIN` | `bool` | Overrides `mcp.allow_admin`. |
| `MCP_BEARER_TOKEN_OVERRIDE` | `string` | Overrides `mcp.bearer_token_override`. |

### CLI profile file (`~/.realize-os/config.toml`)

```toml
default_profile = "local"

[profiles.local]
endpoint = "http://localhost:8080"
api_key_env = "REALIZE_API_KEY"
default_system = ""

[profiles.prod]
endpoint = "https://realize.example.com"
api_key_env = "REALIZE_PROD_API_KEY"
default_system = "realization-il"
```

### No SQLite schema changes

5.1.0 reuses every existing table. MCP tool calls hit the same handlers as REST and write to the same DB.

## API Design

### MCP endpoints (new)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/mcp/sse` | Bearer / X-API-Key | SSE handshake; opens an event stream tied to a `session_id`. |
| `POST` | `/mcp/messages/{session_id}` | Bearer / X-API-Key | JSON-RPC payload (`initialize`, `tools/list`, `tools/call`). |
| `GET` | `/mcp/health` *(optional)* | none | Lightweight liveness probe for monitoring. Returns `{ "ok": true, "tools": <count> }`. |

### Tool inventory

See [`PRD.md`](PRD.md#feature-2-built-in-mcp-server) for the full catalogue. Each tool is a thin façade:

```python
# realize_core/mcp_server/tools/chat_tools.py
@register_tool(name="realize_chat", schema=CHAT_SCHEMA, scopes=["read"])
async def realize_chat(args: dict, user: CurrentUser) -> ToolResult:
    body = ChatRequest(**args)
    return await chat_route_handler(body, user)  # the REST handler, called in-process
```

### CLI ↔ API contract

The CLI is an HTTP client of its own server. Commands like `realize-os chat "..."` POST to `/api/chat`; commands like `realize-os mcp serve` exec into uvicorn directly. No new endpoints needed for the CLI.

### Error handling

All MCP responses use the JSON-RPC error envelope with a stable `code` extension:

```json
{
  "error": {
    "code": -32001,
    "message": "Forbidden: admin tools disabled",
    "data": { "code": "MCP_ADMIN_DISABLED" }
  }
}
```

`data.code` values are documented in [`docs/mcp-server.md`](../docs/mcp-server.md).

## Component Breakdown

### `realize_core/mcp_server/` (new)

- **Responsibility:** Translate MCP JSON-RPC into RealizeOS REST handler calls; enforce auth + scope; serialize responses.
- **Dependencies:** `mcp` SDK; `realize_api.routes.*`; `realize_api.dependencies.get_current_user`.
- **Interface:**
  - `build_mcp_server() -> mcp.server.lowlevel.Server`
  - `register_routes(app: FastAPI) -> None` (called from `realize_api/main.py`)

### `realize_core/cli/` (new)

- **Responsibility:** Operator-facing terminal interface. Delegates to REST API for live operations; delegates to `cli.py` legacy paths for `init`/`serve`/`bot`/`audit`.
- **Dependencies:** Typer, prompt-toolkit, rich, httpx (for talking to the REST API).
- **Interface:**
  - `main()` — entry point referenced by `pyproject.toml [project.scripts] realize-os = "realize_core.cli:main"`.

### `realize_api/routes/mcp.py` (new)

- **Responsibility:** FastAPI router for the MCP endpoints. Bridges Starlette/SSE to `mcp_server.Server`.
- **Dependencies:** `realize_core.mcp_server`.

### Unchanged (called by the new components, not modified)

- `realize_api/routes/{chat,systems,ventures,workflows,evolution,...}.py`
- `realize_core/tools/mcp.py` (outbound MCP client; orthogonal direction)
- `realize_core/security/{jwt_auth,audit,injection_guard,...}.py`

## Infrastructure

- **Hosting:** identical to 5.0.x — single Docker image (multi-arch GHCR) or `pip install realize-os` on a VPS.
- **CI/CD:** [.github/workflows/ci.yml](../.github/workflows/ci.yml) (patched in Story 1) + [.github/workflows/release.yml](../.github/workflows/release.yml) (unchanged).
- **Environments:**
  - `REALIZE_ENV=development` — MCP can run anonymously on localhost (with a default API key in `.env`).
  - `REALIZE_ENV=production` — MCP **requires** JWT auth + strong `REALIZE_JWT_SECRET`. Admin tools refuse to load otherwise.
- **Monitoring:** existing audit log + Bandit/safety/gitleaks in CI. New: `/mcp/health` for uptime probes.

## Security

### Authentication
- `Authorization: Bearer <jwt>` (preferred) — issued by `POST /api/auth/token` or `realize-os mcp token`.
- `X-API-Key: <key>` (acceptable for internal automation).
- **No anonymous access** — even read tools require an authenticated identity for audit attribution.

### Authorization (scopes)
- **Read** (`realize_chat`, `kb_*`, `list_*`, `get_*`): any authenticated role.
- **Ops** (`run_workflow`, `trigger_skill`, `run_evolution`, `approve_*`, `dismiss_*`): `role >= editor`.
- **Admin** (`create_venture`, `delete_venture`, `update_setting`, `reload_agents`, `refresh_tools`, `trigger_webhook`): `role = owner` **AND** `mcp.allow_admin: true`.

### Data Protection
- Audit log captures: `tool_name`, `user_id`, `role`, `result_status`, `duration_ms`. Args + return values logged only when `mcp.audit_full_payload: true`.
- Bearer-token rotation procedure documented in `docs/self-hosting-guide.md` (Story 9).

### API Security
- `InjectionGuardMiddleware` runs before MCP dispatch — same lower-block-threshold tuning as REST.
- `RateLimitMiddleware` per `(user_id, tool_name)`.
- Adversarial tests live in `tests/security/test_mcp_adversarial.py` (Story 5): admin-without-token, scope escalation, oversized payload, mismatched session-id, replay.

## Migration Notes

- **Backwards compat:** `python cli.py …` keeps working — `cli.py` becomes a 10-line shim that delegates to `realize_core.cli`. All existing automation, install scripts, and Telegram bot launchers are unaffected.
- **Defaults:** MCP is **off** by default. Existing 5.0.x deployments upgrading to 5.1.0 see no behavior change unless they set `MCP_ENABLED=true`.
- **Docs:** `docs/upgrade-from-v50.md` (Story 9) is the user-facing migration guide.

## Open Questions

Tracked in [`PRD.md`](PRD.md#open-questions). All deferred to 5.2.0 unless a Story 2-5 implementation discovers a hard blocker.
