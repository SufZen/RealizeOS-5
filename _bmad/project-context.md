# Project Context — RealizeOS-5

> The "constitution" for AI-assisted development on this repo. Loaded by every BMAD workflow (planning, architecture, dev story, code review). Per [MTH-40](file:///H:/BMAD/protocols/MTH-40-project-context-protocol.md).

`project_name: "RealizeOS-5"`
`type: software`

## Tech Stack

- **Language:** Python 3.12 (3.11+ supported)
- **Backend framework:** FastAPI (uvicorn)
- **Database:** SQLite (file-based, named-volume in Docker). **Postgres is explicitly out of scope.**
- **Frontend:** React 19 + Vite 8 + TypeScript + Tailwind CSS 4 + TanStack Query + React Router 7 (in `dashboard/`)
- **CLI (operator, Python):** argparse today → migrating to Typer in 5.1.0 (Story 6)
- **CLI (bootstrap, npm):** TypeScript in `realize-os-cli/`, published as `@realize-os/cli`. Stays scoped to Docker bootstrap.
- **Hosting:** Docker (multi-arch GHCR image) + bare-metal/VPS via `pip install realize-os`
- **CI/CD:** GitHub Actions (`.github/workflows/ci.yml` + `release.yml`)
- **Distribution:** GHCR + npm + PyPI (all from one tag via `release.yml`)

## Conventions

- **Naming:**
  - Files / functions / variables: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_SNAKE`
  - Enum classes `PascalCase`, members `UPPER_SNAKE`
  - JS / TS: `camelCase`
- **Testing:** `pytest` (+ `pytest-asyncio`, `pytest-cov`) for backend; `vitest` for dashboard; `vitest` for the npm CLI. Tests live in `tests/` with `test_` prefix.
- **Lint / format:** `ruff check` + `ruff format --check` over `realize_core/`, `realize_api/`, `tests/`, `cli.py`. Dashboard uses ESLint via `pnpm lint`.
- **Git branching:** `main` + short-lived feature branches. PR-per-story (per BMAD MTH-37).
- **Commit style:** Conventional commits — `feat:` `fix:` `docs:` `test:` `refactor:` `chore:` `security:`.
- **Docstrings:** required on all public functions and classes.
- **Type hints:** required on all public functions.
- **Logging:** `logging.getLogger(__name__)`. **Never `print()`** outside `cli.py` user-facing output.

## Architecture Decisions

- **API-first.** Every feature exposed as a REST endpoint in `realize_api/routes/` first; UI and CLI are clients.
- **MCP dual role (5.1.0+).** RealizeOS is both an MCP **client** (`realize_core/tools/mcp.py` connects to external MCP servers) and an MCP **server** (`realize_core/mcp_server/` exposes RealizeOS to external agents).
- **FABRIC stays file-based.** Knowledge bases, agents, skills, ventures live as files on disk. Do not migrate to database.
- **SSE only for streaming.** Do not add WebSocket.
- **SQLite only.** No Postgres, no MySQL.
- **Human-centered.** RealizeOS is not fully autonomous — admin/write paths require approval or explicit role.
- **Feature flags in `realize-os.yaml`** under `features:` and `mcp:`; accessed via `config.py:get_features()`. New capabilities ship behind a flag.
- **Security stack order (request inbound):** Security headers → Audit → Rate limiting → Injection guard → JWT auth → Route handler.
- **Async-over-sync.** Blocking I/O is wrapped with `asyncio.to_thread()`.

## Implementation Rules

- Every endpoint validates input via Pydantic models.
- Secrets only via environment variables / `.env`. Never hardcoded.
- Auto-discovery: agents from `A-agents/`, skills from `R-routines/skills/`, extensions from `extensions/`. Don't introduce manual registration paths when auto-discovery covers the case.
- Backwards compatibility: `python cli.py <verb>` paths from earlier versions must keep working.
- One PR = one BMAD story. Each story updates `_bmad/sprint-status.yaml` on merge.
- New features: add tests **and** update the relevant doc(s) in the same PR.

## Anti-Patterns (never do these)

- Wildcard imports (`from x import *`).
- `print()` for logging — use the structured logger.
- Bare `except:` — always catch a specific exception class.
- Catching generic `Exception` without re-raising or logging context.
- New dependencies without explicit approval and a pin in `requirements.txt` / `pyproject.toml`.
- Skipping git hooks (`--no-verify`, `--no-gpg-sign`) unless the user asks for it.
- Force-pushing to `main`; force-pushing without warning the user on any shared branch.
- Adding speculative abstractions or backward-compat shims for code paths nobody uses.
- Commenting out code instead of deleting it.

## Notes

- **CI discipline:** the repo has 1,709+ tests, ~33 s pytest run. Don't merge a PR that drops the test count or breaks lint/format.
- **Production posture:** `REALIZE_ENV=production` requires `REALIZE_API_KEY`, `REALIZE_JWT_ENABLED=true`, and a strong `REALIZE_JWT_SECRET`. The MCP server inherits these.
- **License:** [BSL 1.1](LICENSE), converts to Apache 2.0 on 2030-03-26.
- **Audit trail:** every state-changing API/MCP call is logged via `realize_core/security/audit.py::get_audit_logger()`. Don't add a write path that bypasses it.
