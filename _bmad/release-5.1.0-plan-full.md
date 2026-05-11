# Plan: Ship RealizeOS 5.1.0 — Green CI + Built-in MCP Server + First-class Operator CLI

## Context

**Where we are (verified live, 2026-05-10):** RealizeOS-5 has been hardened over the last 6 weeks. The audit report ([AUDIT-REPORT.md](h:/RealizeOS-5/AUDIT-REPORT.md)) confirms 1,688/1,688 unit tests + 24/24 e2e checks green; the most recent CI run on `main` shows **1,709 tests passing in 32.6 s** and **5 of 6 CI jobs green**. New phases were added (Phase 1 JWT/oversized body/audit integrity, Phase 3 perf, Phase 5 data integrity) and all pass. Last published artifacts are `v5.0.6` on Docker/npm/PyPI from 2026-03-29.

**The blockers and the strategic gap.** Two things stand in the way of cutting the next public release:

1. **CI is red on `main`** — every push since 2026-05-10 12:33 UTC fails. The single failing job is `Docker Build (verify)` at the very first step ("Validate Docker Compose files"):
   ```
   env file /home/runner/work/RealizeOS-5/RealizeOS-5/.env not found
   ```
   `docker-compose.yml` (line 28-29) and `docker-compose.prod.yml` (line 33-34) declare `env_file: - .env`. Docker Compose v2 hard-fails `compose config` if any `env_file:` path is missing, and CI legitimately doesn't have a `.env`. This cascades into the release pipeline, because [release.yml](h:/RealizeOS-5/.github/workflows/release.yml) gates every job on `needs: ci`. So `git tag v5.1.0 && git push --tags` fails today even though tests are green.

2. **RealizeOS speaks MCP only as a client, not a server.** [`realize_core/tools/mcp.py`](h:/RealizeOS-5/realize_core/tools/mcp.py) lets RealizeOS **call into** other MCP servers, but there is no inverse path: nothing lets Claude Desktop, Cursor, OpenClaw, n8n, or any other MCP-speaking agent **call into** a user's RealizeOS instance. The OpenClaw VPS exposes an SSE endpoint at `https://37.27.182.247:8090/sse`, but that's a custom one-off bolted on top of RealizeOS — not part of the product. Every new RealizeOS user has to either replicate that custom plumbing or do without integration. Combined with the current Python `cli.py` (596 lines, deployment-only: `init`, `serve`, `bot`, `status`, `audit`, `index`, `venture`), end users have no first-class way to *use* their RealizeOS from the terminal or to plug it into the broader agent ecosystem.

**Decisions taken (this conversation, 2026-05-10):**

- **Bundle everything into 5.1.0.** Skip 5.0.7. Hold the release until MCP server + operator CLI are done, ship one combined version.
- **MCP transport: HTTP+SSE (remote) only.** Network-accessible endpoint with bearer-token auth — works for cloud routines, OpenClaw-style integrations, and any agent not on the same machine. No stdio for now (defer to 5.2.0 if there's demand from Claude Desktop users).
- **MCP surface: full** — chat + system queries, KB read/search, workflows + skills + evolution, **and** write/admin (ventures, settings). Write/admin is gated behind a config flag and requires production auth on.
- **Operator CLI: full first-class.** Config profiles, multi-instance support, autocomplete, interactive REPL, output formatters (json/yaml/table). Substantial new surface area — sized accordingly below.

**Intended outcome:** A green CI run on `main`; `v5.1.0` shipped to GHCR + npm + PyPI with (a) a built-in MCP server every user can flip on with a config flag, exposing the full RealizeOS surface to any MCP-speaking agent, and (b) a polished `realize-os` CLI that lets operators chat, run ventures, query the KB, and manage their instance from the terminal. RealizeOS stops being an "API + dashboard" and becomes a true operational layer + business second brain that integrates anywhere.

---

## What's already in place (reuse, don't rebuild)

The repo already gives us 70% of what 5.1.0 needs. The plan leans heavily on this:

| Capability | Where it lives | How 5.1.0 uses it |
|---|---|---|
| MCP **client** (consumer of external MCP servers) | [realize_core/tools/mcp.py](h:/RealizeOS-5/realize_core/tools/mcp.py) | Untouched. Stays as the "RealizeOS uses Adobe/Stripe/n8n MCPs" path. |
| Full REST API surface | [realize_api/routes/](h:/RealizeOS-5/realize_api/routes/) — 30 route modules: `chat`, `systems`, `agents_v2`, `ventures`, `venture_kb`, `workflows`, `evolution`, `approvals`, `health`, `dashboard`, `integrations`, `setup`, `settings*` | The new MCP server is a thin façade over these — every MCP tool maps 1:1 to an existing route handler. No new business logic. |
| Auth (API key + JWT) | [realize_api/routes/auth.py](h:/RealizeOS-5/realize_api/routes/auth.py), [realize_api/middleware.py](h:/RealizeOS-5/realize_api/middleware.py), `realize_core/security/jwt_auth.py` | MCP server reuses the same `Authorization: Bearer <jwt>` and `X-API-Key` story — no separate auth system. |
| Python CLI scaffolding | [cli.py](h:/RealizeOS-5/cli.py) (596 lines, argparse-based) | Migrate to a richer CLI framework (Typer or Click) and add operator subcommands alongside existing deploy commands. Keep all current CLI command paths working. |
| Distribution | [.github/workflows/release.yml](h:/RealizeOS-5/.github/workflows/release.yml) — Docker multi-arch + npm `@realize-os/cli` + PyPI `realize-os` + GitHub release | The same pipeline ships 5.1.0. CLI gets pip-installed entry point added to `pyproject.toml` so `pip install realize-os` gives `realize-os`. |
| FastAPI app | [realize_api/main.py](h:/RealizeOS-5/realize_api/main.py) | MCP server mounts as an additional route prefix (`/mcp/sse`) on the existing app — single process, single port, single auth. |

---

## Recommended approach — three workstreams, one release

### Workstream A — Unblock CI (small, surgical, ~30 min)

The same fix from before. This has to land first; it's a hard prerequisite for shipping anything via the release pipeline.

1. **Patch [.github/workflows/ci.yml](h:/RealizeOS-5/.github/workflows/ci.yml#L159-L162)** — `docker-build` job, "Validate Docker Compose files" step:
   ```yaml
   - name: Validate Docker Compose files
     run: |
       cp .env.example .env  # Compose v2 requires every env_file path to exist
       docker compose -f docker-compose.yml config
       docker compose -f docker-compose.prod.yml config
   ```
2. **Add [.gitleaks.toml](h:/RealizeOS-5/.gitleaks.toml)** allowlisting the three known false positives (`docs/getting-started.md`, `docs/user-guide.html`, `tests/security/test_phase1_adversarial.py`), then drop `continue-on-error: true` from the gitleaks step ([ci.yml:140-143](h:/RealizeOS-5/.github/workflows/ci.yml#L140-L143)) so future leaks block CI.
3. **Promote `safety check` to blocking** ([ci.yml:118-120](h:/RealizeOS-5/.github/workflows/ci.yml#L118-L120)) — run `safety check -r requirements.txt` locally; if 0 vulns, drop the `|| true`. Matches the comment already in the file.
4. **Optional housekeeping (defer if rushed):** bump `actions/checkout@v4`→`@v5`, `actions/setup-python@v5`→`@v6` to silence the Node-20-deprecation warnings (deadline 2026-06-02). Worth doing in this same PR since CI is already being touched.

Result: 6/6 jobs green on `main`.

### Workstream B — Built-in MCP server (the headline feature)

**New module:** [`realize_core/mcp_server/`](h:/RealizeOS-5/realize_core/mcp_server/) — Python package, ~500–800 lines of new code total.

**Transport:** HTTP+SSE per the official MCP spec, mounted on the existing FastAPI app at `/mcp/sse` (events) and `/mcp/messages` (JSON-RPC POST). Uses the same uvicorn process, same TLS terminator, same auth middleware as the REST API. No new port, no new daemon.

**Library:** [`mcp` Python SDK](https://github.com/modelcontextprotocol/python-sdk) — already in `requirements.txt` (used by the client), provides `mcp.server.lowlevel.Server` + `mcp.server.sse.SseServerTransport` for the server side too.

#### Files to create

| Path | Purpose |
|---|---|
| `realize_core/mcp_server/__init__.py` | Public API: `build_mcp_server()`, `register_routes(app)`. |
| `realize_core/mcp_server/server.py` | `Server` instance, capabilities declaration, `@server.list_tools()` and `@server.call_tool()` handlers. |
| `realize_core/mcp_server/tools/__init__.py` | Tool registry — assembles the four tool families below. |
| `realize_core/mcp_server/tools/chat_tools.py` | `realize_chat`, `realize_status`, `realize_health`, `list_systems`, `list_agents`, `list_skills`. Wraps `realize_api/routes/chat.py`, `health.py`, `systems.py`, `agents_v2.py`. |
| `realize_core/mcp_server/tools/kb_tools.py` | `kb_search`, `kb_get_document`, `venture_kb_search`. Wraps `venture_kb.py` and the KB indexer in `realize_core/kb/`. |
| `realize_core/mcp_server/tools/ops_tools.py` | `run_workflow`, `list_workflows`, `trigger_skill`, `run_evolution`, `list_suggestions`, `approve_suggestion`, `dismiss_suggestion`. Wraps `workflows.py`, `evolution.py`, `approvals.py`, `settings_skills.py`. |
| `realize_core/mcp_server/tools/admin_tools.py` | `create_venture`, `delete_venture`, `update_settings`, `reload_agents`, `refresh_tools`. Wraps `ventures.py`, `settings*.py`, `agents_v2.py`. **Gated by `mcp.allow_admin: true` in `realize-os.yaml` AND `REALIZE_ENV=production` requires JWT.** Off by default. |
| `realize_core/mcp_server/auth.py` | Reuses `realize_api/dependencies.py::get_current_user`. Maps the MCP request's `Authorization` header to RealizeOS's existing JWT/API-key auth. Same threat model, one identity system. |
| `realize_core/mcp_server/schemas.py` | JSON Schemas for each tool's `inputSchema`. Auto-derived from existing pydantic models in `realize_api/routes/*.py` where possible. |
| `realize_api/routes/mcp.py` | FastAPI router that mounts `/mcp/sse` (GET, SSE) and `/mcp/messages/{session_id}` (POST). Registered in [realize_api/main.py](h:/RealizeOS-5/realize_api/main.py). |
| `tests/test_mcp_server.py` | Unit + integration tests: tool listing, schema validation, auth enforcement, end-to-end call via the in-process MCP client. |
| `docs/mcp-server.md` | User-facing doc: how to enable, how to plug Claude Desktop / cloud routines / n8n into it, security model, config reference. |

#### Files to modify

| Path | Change |
|---|---|
| [realize_api/main.py](h:/RealizeOS-5/realize_api/main.py) | Import + register the new `mcp` router; call `build_mcp_server()` in lifespan. |
| [setup.yaml.example](h:/RealizeOS-5/setup.yaml.example), [.env.example](h:/RealizeOS-5/.env.example) | Document new keys: `MCP_ENABLED`, `MCP_ALLOW_ADMIN`, `MCP_BEARER_TOKEN_OVERRIDE` (optional, for clients that can't send JWTs). |
| [realize-os.yaml](h:/RealizeOS-5/realize-os.yaml) (or template) | New `mcp:` section with `enabled`, `allow_admin`, `expose_kb`, `expose_ops`. |
| [docs/architecture.md](h:/RealizeOS-5/docs/architecture.md), [docs/api-reference.md](h:/RealizeOS-5/docs/api-reference.md), README | Document the dual role (MCP client + MCP server) and how to integrate. |
| [requirements.txt](h:/RealizeOS-5/requirements.txt) | Pin `mcp >= <version-with-server-side-sse>`; verify SSE server transport is in the version we have. |

#### Tool inventory (the public MCP surface)

This is the contract external agents see. Naming mirrors the existing `realizeos_*` tools the user already has running on the OpenClaw VPS so cloud routines and downstream integrations migrate without prompt rewrites.

**Chat & status (always on):**
`realize_chat`, `realize_status`, `realize_health`, `list_systems`, `list_agents`, `list_skills`, `get_system`, `get_session`, `get_history`, `clear_history`

**KB read (gated by `mcp.expose_kb`):**
`kb_search`, `kb_get_document`, `venture_kb_search`, `list_ventures`

**Ops (gated by `mcp.expose_ops`):**
`run_workflow`, `list_workflows`, `trigger_skill`, `run_evolution`, `list_suggestions`, `approve_suggestion`, `dismiss_suggestion`, `apply_refinement`, `refine_prompt`

**Admin/write (gated by `mcp.allow_admin` + production auth):**
`create_venture`, `delete_venture`, `update_setting`, `reload_agents`, `refresh_tools`, `trigger_webhook`, `create_skill_suggestion`

#### Security model

- **Bearer auth required.** No anonymous access. SSE endpoint requires `Authorization: Bearer <jwt>` or `X-API-Key: <key>`. Reuses [auth.py](h:/RealizeOS-5/realize_api/routes/auth.py) for token issuance — `POST /api/auth/token` is the same flow.
- **Audit logging.** Every MCP tool call goes through `realize_core/security/audit.py::get_audit_logger()` — same logs, same retention as REST.
- **Injection guard.** The existing `InjectionGuardMiddleware` already covers POSTs; extend it to cover the MCP messages endpoint or wrap inside `mcp_server/server.py` before dispatching to the tool handler.
- **Rate limit.** Same `RateLimitMiddleware` per-user.
- **Scope checks.** `admin_tools` require `role=owner` from the JWT; `ops_tools` require `role>=editor`; read tools require any authenticated role.

### Workstream C — First-class operator CLI

**Approach:** Migrate [cli.py](h:/RealizeOS-5/cli.py) from argparse → **[Typer](https://typer.tiangolo.com/)** (sits on top of Click; gives autocomplete, rich help, easy subcommand groups, `Annotated` type hints). Already production-grade and used by FastAPI's own CLI — no new fragile dependency.

**Backwards compatibility:** every existing `python cli.py <verb>` still works. We add new verbs and a new entry point `realize-os` (declared in `pyproject.toml [project.scripts]`).

#### CLI command tree (target for 5.1.0)

```
realize-os
├── init [--template NAME] [--setup PATH]      (existing)
├── serve [--port PORT] [--reload]             (existing)
├── bot                                         (existing)
├── status                                      (existing → enriched)
├── audit                                       (existing)
├── index                                       (existing)
├── venture
│   ├── list                                    (existing)
│   ├── create [--template NAME] KEY            (existing)
│   ├── delete KEY                              (existing)
│   ├── run KEY [--input TEXT]                  NEW — invoke a venture's default agent
│   └── show KEY                                NEW — config/agents/skills snapshot
├── chat [--system KEY] [--agent KEY]           NEW — one-shot prompt
├── ask QUERY                                   NEW — alias for chat with smart routing
├── repl [--system KEY]                         NEW — interactive session
├── kb
│   ├── search QUERY [--venture KEY]            NEW
│   ├── get DOC_ID                              NEW
│   └── reindex [--venture KEY]                 NEW (alias for index)
├── workflow
│   ├── list                                    NEW
│   └── run NAME [--input JSON]                 NEW
├── skill
│   ├── list                                    NEW
│   └── trigger NAME                            NEW
├── evolution
│   ├── run                                     NEW
│   ├── suggestions [--status STATE]            NEW
│   ├── approve ID                              NEW
│   └── dismiss ID                              NEW
├── mcp
│   ├── serve [--port PORT] [--allow-admin]     NEW — start API+MCP together
│   ├── status                                  NEW — show enabled tools, recent calls
│   └── token                                   NEW — issue a bearer token for an MCP client
├── config
│   ├── profile list / add / set-default / show NEW — multi-instance support
│   └── show / set / unset                      NEW — read/write realize-os.yaml safely
└── version                                     NEW
```

#### CLI features in 5.1.0

- **Config profiles** ([`~/.realize-os/config.toml`](file:///~/.realize-os/config.toml)) — `default`, plus per-instance entries with `endpoint`, `api_key_env`, `default_system`. `realize-os --profile prod chat` switches instance for one call. Solves "I have a local dev box AND a VPS RealizeOS — how do I talk to both."
- **Interactive REPL** — `realize-os repl` launches a prompt-toolkit session with line history, multi-line input, slash commands (`/system arena`, `/agent writer`, `/clear`, `/exit`), and live streaming responses.
- **Output formatters** — every list/get command takes `--format json|yaml|table` (default `table`). Powers shell pipelines (`realize-os venture list --format json | jq …`) without losing human ergonomics.
- **Autocomplete** — Typer's built-in `--install-completion` for bash/zsh/fish/PowerShell.
- **Auth** — first-run prompts for endpoint + API key, stores in profile. `realize-os mcp token` issues a fresh JWT for plugging into Claude Desktop / cloud routines / Cursor.

#### Files to create / modify

| Path | Change |
|---|---|
| [cli.py](h:/RealizeOS-5/cli.py) | Slim entrypoint that delegates to `realize_core/cli/` package. |
| `realize_core/cli/__init__.py` | Typer app assembly; subcommand groups attached. |
| `realize_core/cli/commands/{init,serve,venture,chat,kb,workflow,skill,evolution,mcp,config,status}.py` | One module per command group. Each is a thin client over the REST API + MCP server (where local) — minimal new logic. |
| `realize_core/cli/profiles.py` | TOML-backed profile manager; `~/.realize-os/config.toml`. |
| `realize_core/cli/repl.py` | prompt-toolkit-based REPL; reuses streaming chat from [chat.py](h:/RealizeOS-5/realize_api/routes/chat.py). |
| `realize_core/cli/formatters.py` | `to_table`, `to_json`, `to_yaml` helpers using `rich` (already in deps for tests). |
| [pyproject.toml](h:/RealizeOS-5/pyproject.toml) | `[project.scripts] realize-os = "realize_core.cli:main"`; add `typer`, `prompt-toolkit`, `rich` to dependencies. |
| [requirements.txt](h:/RealizeOS-5/requirements.txt) | Pin `typer>=0.12`, `prompt-toolkit>=3.0`, `rich>=13`. |
| `tests/test_cli_commands.py` | Typer's testing utility (`CliRunner`); cover each new command. |
| [docs/getting-started.md](h:/RealizeOS-5/docs/getting-started.md), [docs/full-guide.md](h:/RealizeOS-5/docs/full-guide.md) | Add CLI quickstart and command reference. |

**The existing TypeScript CLI ([realize-os-cli/](h:/RealizeOS-5/realize-os-cli/))** stays scoped to Docker bootstrap (one-line `npx @realize-os/cli init` for users who don't have Python yet). Renamed in docs as the *bootstrap CLI*; the new Python `realize-os` is the *operator CLI*. Two complementary tools, one product.

---

## Process scaffold — BMAD framework

To control this multi-week, multi-workstream release, we use the [BMAD-inspired framework](file:///H:/BMAD/README.md) at `H:\BMAD`. It gives us six artifacts that live in a new `_bmad/` directory in the repo and one shared rule file at the root. Every dev session loads the same context, so decisions stay consistent across PRs.

| BMAD artifact | Source workflow | Path in RealizeOS-5 | Purpose |
|---|---|---|---|
| **project-context.md** | [MTH-40](file:///H:/BMAD/protocols/MTH-40-project-context-protocol.md) | `_bmad/project-context.md` | The "constitution" — Python 3.12 + FastAPI conventions, anti-patterns (no wildcard imports, structured logging, secrets via env), test/lint/format rules. Generated by reading the existing codebase + [CONTRIBUTING.md](h:/RealizeOS-5/CONTRIBUTING.md). Loaded by every workstream session. |
| **PRD.md** | [MTH-35 Full PRD](file:///H:/BMAD/workflows/MTH-35-planning-workflow.md) | `_bmad/PRD.md` | Product spec for 5.1.0: user stories, functional + non-functional requirements (auth, performance, security), success metrics. Built from `templates/prd-template.md`. |
| **architecture.md** | [MTH-36](file:///H:/BMAD/workflows/MTH-36-architecture-workflow.md) | `_bmad/architecture.md` | Tech-stack decisions, MCP server component diagram, JSON-RPC↔REST mapping, auth flow, data model deltas, deployment topology. Built from `templates/architecture-template.md`. |
| **stories/*.md** | [MTH-37](file:///H:/BMAD/workflows/MTH-37-dev-story-workflow.md) | `_bmad/stories/STORY-NN-*.md` | One file per implementation unit (one PR = one story). Each has prerequisites, files-to-touch, acceptance criteria, test plan. Built from `templates/story-template.md`. |
| **sprint-status.yaml** | [MTH-38](file:///H:/BMAD/workflows/MTH-38-sprint-tracking-workflow.md) | `_bmad/sprint-status.yaml` | Live tracker: which stories are done / in-flight / blocked. Updated after each PR merges. |
| **readiness-check.md** | [MTH-23](file:///H:/BMAD/skills/MTH-23-readiness-check-skill.md) | `_bmad/readiness-check.md` | Gate before coding starts. Verdict: READY / NEEDS WORK. Re-run after major scope changes. |
| **AGENTS.md** | (root file, industry standard) | [AGENTS.md](h:/RealizeOS-5/AGENTS.md) (new) | Top-level agent instructions read by all AI agents (Claude Code, Cursor, Codex, Aider). Points at `_bmad/project-context.md` for full rules. Same content also surfaced via [CLAUDE.md](h:/RealizeOS-5/CLAUDE.md) (new) for Claude Code's automatic loader. |

The `_bmad/` directory is committed to the repo so every clone — local, CI, and AI session — sees the same scaffold. Code review (`MTH-22`) runs against each story before merge.

---

## Build sequence

### Phase 0 — BMAD scaffold (1 day, before any code)

0a. **Create `_bmad/project-context.md`** by reading the existing codebase + [CONTRIBUTING.md](h:/RealizeOS-5/CONTRIBUTING.md). Capture: Python 3.12 / FastAPI / SQLite-via-named-volume / pytest+ruff toolchain / pnpm dashboard / 1709-test discipline / "no production code touched in CI-only PRs" rule.
0b. **Create `_bmad/PRD.md`** for 5.1.0. User stories: "As an integrator, I want to plug RealizeOS into Claude Desktop / Cursor / cloud routines via MCP so external agents can use it as a second brain"; "As an operator, I want to chat with my RealizeOS from the terminal without opening the dashboard"; "As a maintainer, I want green CI so I can ship."
0c. **Create `_bmad/architecture.md`** covering the three workstreams' design — copy material from "Recommended approach" above, expand with sequence diagrams (MCP handshake, JWT issuance, tool dispatch), data-model deltas (new `mcp:` config section), auth model.
0d. **Create `_bmad/stories/`** — break the build sequence below into 12 numbered story files (one per phase below).
0e. **Create `_bmad/sprint-status.yaml`** seeded with all 12 stories at `status: pending`.
0f. **Run MTH-23 readiness check.** Output verdict to `_bmad/readiness-check.md`. Must read READY before any implementation PR is opened.
0g. **Create root [AGENTS.md](h:/RealizeOS-5/AGENTS.md) and [CLAUDE.md](h:/RealizeOS-5/CLAUDE.md)** — short, point at `_bmad/`. This is the public contract for any AI agent touching the repo from now on.

### Phase 1–10 — Implementation stories (each one PR + one BMAD story file)

| # | Story | Workstream | BMAD story file |
|---|---|---|---|
| 1 | CI green: env-file fix + gitleaks allowlist + safety enforcement + Node 24 actions bump | A | `STORY-01-ci-green.md` |
| 2 | MCP server scaffolding: package, FastAPI mount, auth, chat/status/health tools | B | `STORY-02-mcp-scaffold.md` |
| 3 | MCP KB tools: `kb_search`, `kb_get_document`, `venture_kb_search`, `list_ventures` | B | `STORY-03-mcp-kb.md` |
| 4 | MCP ops tools: workflows, skills, evolution, suggestions, approvals | B | `STORY-04-mcp-ops.md` |
| 5 | MCP admin tools (gated): venture CRUD, settings, agent reload + adversarial tests | B | `STORY-05-mcp-admin.md` |
| 6 | CLI foundation: Typer migration of existing commands + profile system + entry point | C | `STORY-06-cli-foundation.md` |
| 7 | CLI operator commands: `chat`, `ask`, `kb`, `workflow`, `skill`, `evolution` | C | `STORY-07-cli-operator.md` |
| 8 | CLI MCP integration + REPL + formatters (`mcp serve`/`mcp token`, prompt-toolkit, rich) | C | `STORY-08-cli-mcp-repl.md` |
| 9 | Documentation overhaul (Phase 11 below — full detail there) | D | `STORY-09-docs.md` |
| 10 | Release prep: VERSION bump, audit re-run, release notes, migration guide | D | `STORY-10-release-prep.md` |

Each story PR follows MTH-37: load context → plan → implement → self-review (MTH-22) → verify → update `sprint-status.yaml`. After PR #10 is merged we run final verification, then tag.

### Phase 11 — Documentation overhaul (Story 9, before tag)

Production-ready release means **every doc reflects 5.1.0**. This is its own story, not an afterthought.

**Files updated:**

| Path | Update |
|---|---|
| [README.md](h:/RealizeOS-5/README.md) | Top-banner: "Now with built-in MCP server + first-class operator CLI." Add "Connect any agent" + "Use from the terminal" sections to the feature table. New quickstart snippets for the CLI and MCP integration. Update install/run examples to show `realize-os` instead of `python cli.py` where appropriate. Update version badge → 5.1.0. |
| [QUICKSTART.md](h:/RealizeOS-5/QUICKSTART.md) | New "5-minute paths": Docker run, `pip install realize-os`, plug into Claude Desktop via MCP. |
| [CONTRIBUTING.md](h:/RealizeOS-5/CONTRIBUTING.md) | Reference the new `_bmad/` workflow; document AGENTS.md/CLAUDE.md contract; explain story-per-PR cadence. |
| [docs/getting-started.md](h:/RealizeOS-5/docs/getting-started.md) | Add CLI quickstart section + MCP enablement section. Replace any `curl http://localhost:8080/api/chat …` examples with `realize-os chat …` equivalents (keep the curl as "via the API" alternative). |
| [docs/full-guide.md](h:/RealizeOS-5/docs/full-guide.md) | Sections for MCP server (config, security, tool catalog) + CLI command reference. |
| [docs/architecture.md](h:/RealizeOS-5/docs/architecture.md) | New "MCP integration layer" section with mermaid diagram. Updated component map showing dual MCP role. |
| [docs/api-reference.md](h:/RealizeOS-5/docs/api-reference.md) | New section: `/mcp/sse` and `/mcp/messages/{session_id}` with full request/response examples. |
| [docs/configuration.md](h:/RealizeOS-5/docs/configuration.md) | New `mcp:` config block; new env vars (`MCP_ENABLED`, `MCP_ALLOW_ADMIN`, etc.). |
| [docs/self-hosting-guide.md](h:/RealizeOS-5/docs/self-hosting-guide.md) | TLS termination guidance for the MCP SSE endpoint, firewall notes, bearer-token rotation. |
| [docs/lite-guide.md](h:/RealizeOS-5/docs/lite-guide.md) | Note that Lite includes the CLI but ships with MCP off by default. |
| [docs/mcp-server.md](h:/RealizeOS-5/docs/mcp-server.md) (new) | Definitive MCP server reference: tool catalog, security model, integration recipes (Claude Desktop, Cursor, n8n, cloud routines). |
| [docs/cli-reference.md](h:/RealizeOS-5/docs/cli-reference.md) (new) | Auto-generated by Typer — full command tree, flags, examples. |
| [docs/upgrade-from-v50.md](h:/RealizeOS-5/docs/upgrade-from-v50.md) (new) | Migration: 5.0.x → 5.1.0. What's new, what changed, what's deprecated. Mostly additive: `python cli.py …` keeps working but new entry point is `realize-os`. |
| [docs/user-guide.html](h:/RealizeOS-5/docs/user-guide.html), [docs/quick-install.html](h:/RealizeOS-5/docs/quick-install.html) | Regenerated from their source markdown. |
| [CHANGELOG.md](h:/RealizeOS-5/CHANGELOG.md) (new or appended) | Standard Keep-a-Changelog format. 5.1.0 entry: Added (MCP server, operator CLI, BMAD scaffolding, AGENTS.md/CLAUDE.md), Changed (CI hardening, deps), Fixed (env-file CI bug). |
| [AGENTS.md](h:/RealizeOS-5/AGENTS.md) | Created in Phase 0g; reviewed for any 5.1.0-specific guidance. |
| [CLAUDE.md](h:/RealizeOS-5/CLAUDE.md) | Created in Phase 0g; same. |
| [VERSION](h:/RealizeOS-5/VERSION) | `5.0.0` → `5.1.0`. |
| [pyproject.toml](h:/RealizeOS-5/pyproject.toml) | `version = "5.1.0"` (release workflow rewrites from tag, but file should match for local installs). |
| [realize-os-cli/package.json](h:/RealizeOS-5/realize-os-cli/package.json) | `"version": "5.1.0"`. |

**New screenshots / GIFs:** dashboard's existing screenshots stay valid; add three new assets — (1) `realize-os repl` interactive session, (2) Claude Desktop tool palette showing RealizeOS tools, (3) `realize-os mcp serve` log output. Stored under `docs/assets/`.

### Phase 12 — Release

11. **Run the full audit playbook** ([docs/audit-playbook.md](h:/RealizeOS-5/docs/audit-playbook.md)) against `main`. Update [AUDIT-REPORT.md](h:/RealizeOS-5/AUDIT-REPORT.md) with new test counts (target: 1,800+ tests passing including the new MCP/CLI suites).
12. **Update `_bmad/sprint-status.yaml`** — all stories `status: done`. Run sprint retrospective (MTH-38) and append to a new `_bmad/retro-5.1.0.md`.
13. **Tag `v5.1.0`** → release pipeline runs CI → multi-arch Docker → npm → PyPI → GitHub release.
14. **Post-release smoke tests** (commands in Verification below).
15. **Announce** — GitHub release notes + dashboard banner + (optional) tweet/blog.

This is meaningful new surface area — realistic timeline is **~2–3 weeks of focused work**, not days. The BMAD scaffold means each story-PR stays small and reviewable, the docs are kept current as we go (each story updates the docs it touches), and the release is shippable at every merge point.

---

## Critical files to modify or create

**CI (workstream A):**
- [.github/workflows/ci.yml](h:/RealizeOS-5/.github/workflows/ci.yml)
- [.gitleaks.toml](h:/RealizeOS-5/.gitleaks.toml) (new)

**MCP server (workstream B):**
- `realize_core/mcp_server/` (new package — server.py, auth.py, schemas.py, tools/{chat,kb,ops,admin}_tools.py)
- [realize_api/routes/mcp.py](h:/RealizeOS-5/realize_api/routes/mcp.py) (new)
- [realize_api/main.py](h:/RealizeOS-5/realize_api/main.py) (mount router)
- [requirements.txt](h:/RealizeOS-5/requirements.txt), [.env.example](h:/RealizeOS-5/.env.example), [setup.yaml.example](h:/RealizeOS-5/setup.yaml.example)
- [docs/mcp-server.md](h:/RealizeOS-5/docs/mcp-server.md) (new)

**CLI (workstream C):**
- `realize_core/cli/` (new package — Typer app + commands/, profiles, repl, formatters)
- [cli.py](h:/RealizeOS-5/cli.py) (slim shim)
- [pyproject.toml](h:/RealizeOS-5/pyproject.toml) (entry point + deps)
- [requirements.txt](h:/RealizeOS-5/requirements.txt) (typer, prompt-toolkit, rich)

**Tests:**
- `tests/test_mcp_server.py`, `tests/test_mcp_tools_*.py` (new)
- `tests/test_cli_commands.py` (new)
- `tests/security/test_mcp_adversarial.py` (new)

---

## Verification

### CI (after workstream A)
```bash
ruff check realize_core/ realize_api/ tests/ cli.py
ruff format --check realize_core/ realize_api/ tests/ cli.py
cp .env.example .env && docker compose -f docker-compose.yml config > /dev/null && docker compose -f docker-compose.prod.yml config > /dev/null
gitleaks detect --redact -v --config .gitleaks.toml
safety check -r requirements.txt
```
All exit 0. `gh run watch` on the next push: 6/6 jobs ✓.

### MCP server (after workstream B)
```bash
# Boot RealizeOS with MCP enabled
REALIZE_API_KEY=devkey MCP_ENABLED=true python cli.py serve &

# Issue a bearer token
TOKEN=$(curl -s -X POST localhost:8080/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"user_id":"owner","role":"owner","api_key":"devkey"}' | jq -r .access_token)

# List tools via SSE handshake
npx @modelcontextprotocol/inspector http://localhost:8080/mcp/sse -H "Authorization: Bearer $TOKEN"
```
Expect: tool list shows all enabled families (chat + kb + ops; admin only if `mcp.allow_admin=true`). Calling `realize_chat` returns a response. Calling `delete_venture` without `allow_admin` returns 403.

**Claude Desktop integration test:** add a `mcpServers` entry pointing to the SSE endpoint with the bearer token; restart Claude Desktop; verify `realize_chat` shows up and works in a conversation.

**Cloud routines test:** swap the OpenClaw VPS endpoint for the new local endpoint in one of the routines from [the routines plan](file:///C:/Users/Utilizador/.claude/plans/read-c-users-utilizador-downloads-reali-piped-willow.md). Run the routine manually. Same behavior.

### CLI (after workstream C)
```bash
pip install -e .  # local dev install
realize-os --version          # → 5.1.0
realize-os config profile add prod --endpoint https://my-vps:8080
realize-os --profile prod status
realize-os chat "what's my arena pipeline status?"
realize-os kb search "investment thesis" --venture personal-investments --format json | jq .
realize-os repl --system realization-il      # interactive REPL
realize-os mcp token --user owner            # prints a JWT
realize-os mcp serve                         # API + MCP on one process
```
Each must produce sensible output and exit 0.

### Release pipeline (after tag)
```bash
git tag v5.1.0 && git push --tags
gh run watch        # release.yml: ci → docker-release → npm-publish → pypi-publish → github-release
```
Then:
```bash
docker pull ghcr.io/sufzen/realizeos-5:5.1.0 && docker run --rm ghcr.io/sufzen/realizeos-5:5.1.0 realize-os --version
npx @realize-os/cli@5.1.0 --version
pip install realize-os==5.1.0 && realize-os --version
```
GitHub release page shows `RealizeOS-Lite-5.1.0.zip` + `.sha256`.

### Rollback
- Pre-tag: revert PRs, push to `main`, re-run CI.
- Post-tag failure mid-pipeline: `gh release delete v5.1.0 -y && git tag -d v5.1.0 && git push origin :refs/tags/v5.1.0`. PyPI versions can't be deleted but yanked is fine; npm `unpublish` works <72 h; Docker tags can be retagged; GHCR can re-publish.
- Post-release MCP issue at runtime: users disable via `MCP_ENABLED=false` env or `mcp.enabled: false` in config. No code rollback needed; CLI keeps working.

---

## Out of scope for 5.1.0 (explicit)

- **stdio MCP transport.** Defer to 5.2.0 if Claude Desktop users want a no-network local install.
- **Streamable HTTP MCP transport.** Spec is still evolving; SSE covers the same use cases today.
- **TypeScript operator CLI.** The Python CLI is canonical; the TS bootstrap CLI keeps its scope (Docker init).
- **Coverage threshold enforcement.** Worth adding `--cov-fail-under=80` in a follow-up after the new MCP+CLI code lands and we know its real coverage.
- **Re-running the full live-stack audit** ([docs/audit-playbook.md](h:/RealizeOS-5/docs/audit-playbook.md)) before tag — required as a release gate, scheduled in step 8 of the build sequence, but the procedure already exists and isn't being designed in this plan.
