# CLAUDE.md — RealizeOS-5

> Loaded automatically by Claude Code. Mirrors the agent-agnostic [AGENTS.md](AGENTS.md) — see that file for the full contract. This file is the Claude-Code-aware shortcut.

## Read these first, in order

1. **[`_bmad/project-context.md`](_bmad/project-context.md)** — the constitution. Conventions, anti-patterns, hard rules. Always loaded.
2. **[`_bmad/release-5.1.0-plan.md`](_bmad/release-5.1.0-plan.md)** — what's currently being built and why.
3. **[`_bmad/sprint-status.yaml`](_bmad/sprint-status.yaml)** — which story is in progress.
4. The active story file under [`_bmad/stories/`](_bmad/stories/).

## How we work

- One PR per BMAD story (`_bmad/stories/STORY-NN-*.md`). Load story → plan → implement → self-review → verify → update sprint-status → commit.
- Conventional commits, structured logging, async-over-sync, type hints + docstrings on public functions.
- New features behind a flag in `realize-os.yaml`. Tests + docs in the same PR.

## Hard rules (please respect)

- No new dependencies without approval.
- Never `print()` outside user-facing CLI output; use `logging.getLogger(__name__)`.
- No bare `except:`; no generic `Exception` swallowing.
- SQLite only, SSE only, FABRIC stays file-based.
- `python cli.py …` paths must keep working forever.
- Don't drop the test count below 1,709.
- Don't skip git hooks. Don't force-push `main`.

## What's in `_bmad/`

| File | What it is |
|---|---|
| `project-context.md` | Constitution. |
| `PRD.md` | Product requirements for the current release. |
| `architecture.md` | Component design + decisions. |
| `release-5.1.0-plan.md` | Canonical release plan (mirror of `~/.claude/plans/...`). |
| `sprint-status.yaml` | Live tracker. Update on PR merge. |
| `readiness-check.md` | MTH-23 gate before starting implementation. |
| `stories/STORY-NN-*.md` | One story = one PR. |

## When in doubt

- Match existing patterns in `realize_core/` and `realize_api/`.
- Check [`CONTRIBUTING.md`](CONTRIBUTING.md) — same standards.
- Read [`docs/architecture.md`](docs/architecture.md) for product-level shape.
- Read [`AGENTS.md`](AGENTS.md) for the full agent contract.
