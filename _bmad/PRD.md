# PRD: RealizeOS 5.1.0 — Built-in MCP Server + First-class Operator CLI + Green CI

> Built per [MTH-35 Full PRD track](file:///H:/BMAD/workflows/MTH-35-planning-workflow.md). Companion: [`architecture.md`](architecture.md).

## Overview

RealizeOS-5 currently ships as an API + dashboard + Telegram bot. Two strategic gaps block the next public release:

1. **CI is red on `main`** — every push since 2026-05-10 12:33 UTC fails because the `Docker Build (verify)` job's `compose config` step requires a `.env` that doesn't exist in CI. Tests are green; the gate is purely plumbing. This blocks the release pipeline because [release.yml](../.github/workflows/release.yml) gates every job on `needs: ci`.
2. **RealizeOS speaks MCP only as a client.** It can call external MCP servers, but no MCP server *exposes* RealizeOS itself. External agents (Claude Desktop, Cursor, n8n, cloud routines) can't plug in. There's also no first-class operator CLI — the existing `cli.py` is deployment-only (`init`, `serve`, `bot`, `status`, `audit`, `index`, `venture`).

5.1.0 fixes CI and turns RealizeOS into a true integration hub — any MCP-speaking agent can use a user's RealizeOS as a "second brain", and operators can drive the system from the terminal.

**Audience:** RealizeOS self-hosters (single-user and small-team deployments) and integrators connecting RealizeOS to their wider AI/agent stack.

## User Stories

- **As an integrator,** I want to plug RealizeOS into Claude Desktop / Cursor / cloud routines via MCP, so external agents can use it as a second brain without me building a custom adapter.
- **As an operator,** I want to chat with my RealizeOS from the terminal, so I don't need to open the dashboard for quick queries.
- **As an operator with multiple instances,** I want named CLI profiles, so I can switch between local-dev and a production VPS without re-typing endpoints and tokens.
- **As a maintainer,** I want green CI on every push to `main`, so I can tag a release without manual workarounds.
- **As a security-conscious user,** I want write/admin MCP tools off by default and gated by config + auth, so I can opt in only when I need that surface.
- **As an open-source consumer,** I want full upgrade and configuration documentation, so I can adopt 5.1.0 without reading source.

## Functional Requirements

### Feature 1: Green CI

- `Docker Build (verify)` job passes by creating `.env` from `.env.example` before `compose config`.
- Gitleaks runs against a checked-in `.gitleaks.toml` allowlist (3 known false positives) and is **blocking** on real findings.
- `safety check -r requirements.txt` runs without `|| true` (blocking), assuming 0 known vulns at the time of patch.
- Optional: GitHub Actions bumped to versions that don't trip Node-20 deprecation warnings (deadline 2026-06-02).

### Feature 2: Built-in MCP Server

- New Python package [`realize_core/mcp_server/`](../realize_core/mcp_server/) (planned) exposing the RealizeOS surface over MCP.
- **Transport:** HTTP+SSE only in 5.1.0. Mounted on the existing FastAPI app at `/mcp/sse` (events) and `/mcp/messages/{session_id}` (JSON-RPC POST).
- **Auth:** reuses [auth.py](../realize_api/routes/auth.py) — `Authorization: Bearer <jwt>` or `X-API-Key`. No separate auth system.
- **Tool families:**
  - **Chat & status (always on):** `realize_chat`, `realize_status`, `realize_health`, `list_systems`, `list_agents`, `list_skills`, `get_system`, `get_session`, `get_history`, `clear_history`.
  - **KB read (gated by `mcp.expose_kb`):** `kb_search`, `kb_get_document`, `venture_kb_search`, `list_ventures`.
  - **Ops (gated by `mcp.expose_ops`):** `run_workflow`, `list_workflows`, `trigger_skill`, `run_evolution`, `list_suggestions`, `approve_suggestion`, `dismiss_suggestion`, `apply_refinement`, `refine_prompt`.
  - **Admin/write (gated by `mcp.allow_admin` + production auth):** `create_venture`, `delete_venture`, `update_setting`, `reload_agents`, `refresh_tools`, `trigger_webhook`, `create_skill_suggestion`.
- Tool naming mirrors existing public `realizeos_*` tools so cloud routines and downstream prompts migrate without rewrites.
- Audit logged via `realize_core/security/audit.py::get_audit_logger()`.
- Off by default. Enabled via `MCP_ENABLED=true` env or `mcp.enabled: true` in `realize-os.yaml`.

### Feature 3: First-class Operator CLI

- Python entry point: `realize-os` (declared in `pyproject.toml [project.scripts]`).
- Backend: Typer (replaces argparse in `cli.py`); existing `python cli.py …` paths preserved.
- New subcommands:
  - `chat`, `ask`, `repl` — conversational
  - `venture run / show` — venture invocation
  - `kb search / get / reindex` — KB queries
  - `workflow list / run` — workflow execution
  - `skill list / trigger` — skill triggers
  - `evolution run / suggestions / approve / dismiss` — evolution loop
  - `mcp serve / status / token` — start API+MCP, issue bearer tokens
  - `config profile list / add / set-default / show` and `config show / set / unset` — multi-instance, safe yaml editing
  - `version`
- Output formatters: `--format json|yaml|table` on every list/get command.
- Profiles persisted in `~/.realize-os/config.toml`; `realize-os --profile prod chat …` for one-call switching.
- Autocomplete: `realize-os --install-completion` for bash/zsh/fish/PowerShell.
- Interactive REPL via `prompt-toolkit` with line history, slash commands (`/system`, `/agent`, `/clear`, `/exit`), streaming responses.

### Feature 4: Production-ready Documentation

- Every user-facing doc updated: README, QUICKSTART, CONTRIBUTING, all `docs/*.md`.
- New: `docs/mcp-server.md`, `docs/cli-reference.md`, `docs/upgrade-from-v50.md`, `CHANGELOG.md`.
- Root `AGENTS.md` and `CLAUDE.md` (industry-standard agent contract files) created in Phase 0.
- Release notes for 5.1.0 written before the tag; surface MCP server as the headline.

## Non-Functional Requirements

### Performance

- MCP `list_tools` round-trip: ≤ 100 ms p50 on `localhost`.
- MCP `realize_chat` adds ≤ 50 ms overhead vs the equivalent REST `POST /api/chat` call (it's a thin wrapper).
- CI total wall-time stays under 4 minutes on standard GitHub-hosted runners.
- CLI cold start ≤ 200 ms for non-network commands (e.g. `realize-os --version`).

### Security

- All MCP requests require auth — no anonymous SSE handshake.
- Admin tools require `role=owner` JWT scope; ops tools require `role>=editor`; reads accept any authenticated role.
- Same `InjectionGuardMiddleware` and `RateLimitMiddleware` apply to MCP messages as to REST.
- Bearer-token rotation documented in `docs/self-hosting-guide.md`.
- New adversarial test suite: `tests/security/test_mcp_adversarial.py` — admin-without-token, scope escalation, oversized payload, mismatched session-id.

### Scalability

- Single-uvicorn-process deployment must continue to work; MCP doesn't introduce a separate daemon.
- Multi-tenant isolation via `system_key` and `venture_key` already enforced in REST routes; MCP tools inherit it.

### Accessibility / UX

- CLI `--format table` renders cleanly in 80-col terminals (Windows + Unix).
- REPL respects `NO_COLOR` env and degrades to plain text when stdout is not a TTY.
- Error messages from MCP tool failures include a stable `code` field for programmatic clients.

## Information Architecture

```
RealizeOS-5/
├── _bmad/                          ← BMAD scaffold (this PR's process artifacts)
├── .github/workflows/              ← CI + release pipelines
├── realize_api/
│   ├── main.py                     ← mounts /mcp routes
│   └── routes/
│       └── mcp.py (NEW)            ← /mcp/sse + /mcp/messages/{session_id}
├── realize_core/
│   ├── tools/mcp.py                ← unchanged: outbound MCP client
│   ├── mcp_server/ (NEW)           ← inbound MCP server
│   │   ├── server.py
│   │   ├── auth.py
│   │   ├── schemas.py
│   │   └── tools/
│   │       ├── chat_tools.py
│   │       ├── kb_tools.py
│   │       ├── ops_tools.py
│   │       └── admin_tools.py
│   └── cli/ (NEW)                  ← Typer-based operator CLI
│       ├── __init__.py
│       ├── commands/
│       ├── profiles.py
│       ├── repl.py
│       └── formatters.py
├── cli.py                          ← slim shim → realize_core.cli
├── tests/
│   ├── test_mcp_server.py (NEW)
│   ├── test_cli_commands.py (NEW)
│   └── security/test_mcp_adversarial.py (NEW)
└── docs/
    ├── mcp-server.md (NEW)
    ├── cli-reference.md (NEW)
    └── upgrade-from-v50.md (NEW)
```

External flow:
```
[Claude Desktop / Cursor / n8n / cloud routine]
         │
         │  HTTP+SSE  Authorization: Bearer <jwt>
         ▼
[FastAPI :8080]──/mcp/sse──>[mcp_server.Server]──>[REST route handlers]──>[realize_core/*]
```

## Technical Constraints

- Cannot break existing `python cli.py …` paths.
- Cannot drop test count below 1,709.
- Cannot move database off SQLite or KB off filesystem.
- Cannot add a second long-running daemon (MCP must run inside the API process).
- Must keep the `@realize-os/cli` npm bootstrap CLI working unchanged.
- License: BSL 1.1 — every new file inherits it.

## Success Metrics

- ✅ 6 / 6 CI jobs green on `main` post-Story-1.
- ✅ Claude Desktop, when configured against a local 5.1.0 instance, lists ≥ 10 RealizeOS tools and successfully calls `realize_chat`.
- ✅ A user runs `pip install realize-os==5.1.0 && realize-os chat "..."` against a local server and gets a response.
- ✅ Test count ≥ 1,800 (1,709 baseline + ~50 MCP + ~40 CLI tests).
- ✅ All artifacts (Docker, npm, PyPI, GitHub release zip) published from the `v5.1.0` tag.
- ✅ Zero docs reference removed/renamed APIs after the docs overhaul.

## Open Questions

- **Q1.** Should the MCP server expose a discovery endpoint (`/mcp/.well-known`) so clients can find it without prior knowledge of the SSE path? *(Defer: 5.2.0 if asked for.)*
- **Q2.** Do we need per-tool feature flags inside the MCP config (e.g. enable `kb_search` but disable `kb_get_document`), or are family-level flags (`expose_kb`) granular enough? *(Default: family-level. Revisit after first integrator feedback.)*
- **Q3.** Should `realize-os repl` support model selection per turn (`/model claude-opus`)? *(Defer: 5.2.0.)*
