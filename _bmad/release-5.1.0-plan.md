# RealizeOS 5.1.0 Release Plan (canonical, in-repo copy)

> This is the canonical, in-repo mirror of the approved release plan. The original draft lives outside the repo at `C:\Users\Utilizador\.claude\plans\regarding-the-exisitng-ci-dazzling-unicorn.md` (per-machine). This file is the version other contributors and AI agents should read.
>
> Companion BMAD artifacts: [`PRD.md`](PRD.md), [`architecture.md`](architecture.md), [`project-context.md`](project-context.md), [`stories/`](stories/), [`sprint-status.yaml`](sprint-status.yaml), [`readiness-check.md`](readiness-check.md).

## Headline

**Ship RealizeOS 5.1.0 — Green CI + Built-in MCP Server + First-class Operator CLI.**

## Context

- 1,709 tests passing; 5/6 CI jobs green on `main`.
- The one red job is `Docker Build (verify)` failing at `compose config` because CI has no `.env` (env_file required by Compose v2).
- RealizeOS speaks MCP only as a client; no MCP server exposes RealizeOS itself, so no external agent can plug into it without custom plumbing.
- The existing `cli.py` is deployment-only; users have no first-class terminal interface.
- Last published artifacts are `v5.0.6` (2026-03-29) on Docker / npm / PyPI.

## Decisions taken

- **Bundle everything into 5.1.0.** Skip a 5.0.7 patch.
- **MCP transport:** HTTP+SSE only.
- **MCP surface:** full — chat, KB, ops, admin (admin gated by config + auth).
- **CLI:** full first-class — profiles, REPL, formatters, autocomplete.
- **Process scaffold:** BMAD framework at `H:\BMAD`. Artifacts live in `_bmad/` in this repo.
- **Documentation:** every user-facing doc updated as part of the release (own story, not an afterthought).

## Three workstreams

### Workstream A — Unblock CI
1. Patch `.github/workflows/ci.yml` `Docker Build (verify)` step to `cp .env.example .env` before `compose config`.
2. Add `.gitleaks.toml` with allowlist for 3 known false positives. Drop `continue-on-error: true`.
3. Promote `safety check` from advisory (`|| true`) to blocking.
4. Optional: bump deprecated GitHub Actions to silence Node 20 warnings.

### Workstream B — Built-in MCP server
- New package `realize_core/mcp_server/` (~500–800 lines).
- Mounted at `/mcp/sse` + `/mcp/messages/{session_id}` on the existing FastAPI app.
- Reuses JWT/X-API-Key auth; no parallel auth stack.
- Tool families: chat (always on), KB (gated `expose_kb`), ops (gated `expose_ops`), admin (gated `allow_admin` + `role=owner`).
- Adversarial test suite under `tests/security/test_mcp_adversarial.py`.

### Workstream C — First-class operator CLI
- Typer-based; new entry point `realize-os`; existing `python cli.py …` continues to work.
- Profiles in `~/.realize-os/config.toml`.
- Subcommands: chat / ask / repl / venture run-show / kb / workflow / skill / evolution / mcp / config.
- REPL via prompt-toolkit; formatters via rich.
- Distributed via PyPI (`realize-os` package). Existing `@realize-os/cli` npm package keeps its bootstrap-only role.

## Build sequence

| # | Story | Workstream | Story file |
|---|---|---|---|
| 0 | BMAD scaffold (this PR) | – | _bmad/* (this directory) |
| 1 | CI green | A | [stories/STORY-01-ci-green.md](stories/STORY-01-ci-green.md) |
| 2 | MCP server scaffold + chat/status tools | B | [stories/STORY-02-mcp-scaffold.md](stories/STORY-02-mcp-scaffold.md) |
| 3 | MCP KB tools | B | [stories/STORY-03-mcp-kb.md](stories/STORY-03-mcp-kb.md) |
| 4 | MCP ops tools | B | [stories/STORY-04-mcp-ops.md](stories/STORY-04-mcp-ops.md) |
| 5 | MCP admin tools + adversarial tests | B | [stories/STORY-05-mcp-admin.md](stories/STORY-05-mcp-admin.md) |
| 6 | CLI foundation (Typer + profiles + entry point) | C | [stories/STORY-06-cli-foundation.md](stories/STORY-06-cli-foundation.md) |
| 7 | CLI operator commands | C | [stories/STORY-07-cli-operator.md](stories/STORY-07-cli-operator.md) |
| 8 | CLI MCP + REPL + formatters | C | [stories/STORY-08-cli-mcp-repl.md](stories/STORY-08-cli-mcp-repl.md) |
| 9 | Documentation overhaul | D | [stories/STORY-09-docs.md](stories/STORY-09-docs.md) |
| 10 | Release prep + tag v5.1.0 | D | [stories/STORY-10-release-prep.md](stories/STORY-10-release-prep.md) |

Each story = one PR, following [MTH-37 Dev Story Workflow](file:///H:/BMAD/workflows/MTH-37-dev-story-workflow.md): load context → plan → implement → self-review (MTH-22) → verify → update [`sprint-status.yaml`](sprint-status.yaml) → commit. After Story 10 merges and the audit re-runs, we tag `v5.1.0` and watch the release pipeline ship to GHCR + npm + PyPI + GitHub.

## Out of scope for 5.1.0

- stdio MCP transport (defer to 5.2.0 if Claude Desktop users want a no-network local install).
- Streamable HTTP MCP transport (spec still evolving).
- TypeScript operator CLI (the Python CLI is canonical).
- Coverage threshold enforcement.

## Realistic timeline

~2–3 weeks of focused work. Each story-PR stays small and reviewable; the docs are kept current as we go (each story updates the docs it touches); the release is shippable at every merge point.
