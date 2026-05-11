# AGENTS.md — RealizeOS-5

> Top-level instructions for AI coding agents (Claude Code, Cursor, Codex, Aider, OpenAI agents, …) working in this repo. This is the public contract — start here.

## Read these first, in order

1. **[`_bmad/project-context.md`](_bmad/project-context.md)** — the constitution (tech stack, conventions, anti-patterns). Every session loads this.
2. **[`_bmad/release-5.1.0-plan.md`](_bmad/release-5.1.0-plan.md)** — what we're building right now and why.
3. **[`_bmad/sprint-status.yaml`](_bmad/sprint-status.yaml)** — which story is in progress; do not start a new story without checking this.
4. The story file you're working on, e.g. **[`_bmad/stories/STORY-01-ci-green.md`](_bmad/stories/STORY-01-ci-green.md)**.
5. **[`CONTRIBUTING.md`](CONTRIBUTING.md)** — pull-request mechanics and code standards.

## How we work (BMAD framework)

- One PR = one story from `_bmad/stories/`. No drive-by changes outside scope.
- Workflow per story: **load context → plan → implement → self-review → verify → update sprint-status → commit**. See [MTH-37 Dev Story](file:///H:/BMAD/workflows/MTH-37-dev-story-workflow.md).
- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `security:`.
- Tests required for every functional change. Update relevant docs in the **same** PR.
- Mark the story `done` in [`_bmad/sprint-status.yaml`](_bmad/sprint-status.yaml) before you open the PR.

## Hard rules (non-negotiable)

- **No new dependencies** without explicit approval and a pin in `requirements.txt` / `pyproject.toml`.
- **`logging.getLogger(__name__)`**, never `print()` outside user-facing CLI output.
- **No bare `except:`** and no catching generic `Exception` without re-raise/log context.
- **No wildcard imports.**
- **SQLite only** — do not add Postgres / MySQL.
- **SSE only** for streaming — do not add WebSocket.
- **FABRIC stays file-based** — agents, skills, KB live on disk.
- **Backwards compat:** `python cli.py <verb>` paths from earlier versions must keep working.
- **Never break the test suite.** Baseline is 1,709 passing tests; PRs that drop the count are rejected.
- **Never skip git hooks** (`--no-verify`, `--no-gpg-sign`, etc.) unless the user asks for it.
- **Never force-push to `main`.** Warn the user before any force push on a shared branch.

## Anti-patterns

- Wildcard imports.
- Catching `Exception` generically.
- Speculative abstractions for hypothetical future use.
- Backward-compat shims for code paths nobody uses.
- Renaming unused `_vars`, leaving `// removed` comments, etc.
- Adding feature flags or compat layers when a direct change suffices.
- Committing `.env` files or anything matching `.gitleaks.toml`'s sensitive patterns.

## Quick reference

| Need | File |
|---|---|
| What 5.1.0 is | [`_bmad/PRD.md`](_bmad/PRD.md) |
| How 5.1.0 is structured | [`_bmad/architecture.md`](_bmad/architecture.md) |
| Project conventions | [`_bmad/project-context.md`](_bmad/project-context.md) |
| Release plan | [`_bmad/release-5.1.0-plan.md`](_bmad/release-5.1.0-plan.md) |
| Current sprint status | [`_bmad/sprint-status.yaml`](_bmad/sprint-status.yaml) |
| Architecture (product-level) | [`docs/architecture.md`](docs/architecture.md) |
| API reference | [`docs/api-reference.md`](docs/api-reference.md) |
| Configuration | [`docs/configuration.md`](docs/configuration.md) |
| Contribution guide | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
