# RealizeOS — Development Guide (AGENTS.md)

> **Canonical tracked location**: `docs/development/AGENTS.md`
> Root `AGENTS.md` is gitignored for local customization; this file is the source of truth.

## Repository Structure

```
realize_core/      Python backend — the Heart, Spine, agents, extensions, LLM, MCP, storage
realize_api/       FastAPI REST layer — routes, middleware, security (separate from core)
realize_lite/      Packaged template systems (CLAUDE.md, systems/, shared/)
realize-os-cli/    TypeScript Node CLI, published as @realize-os/cli
dashboard/         React 19 / Vite 8 / Tailwind 4 / TanStack Query 5 frontend
docs/              Documentation (not shipped in pip dist)
docs/v5.5.0/       v5.5.0 design documents (pre-spec-kit staging)
tests/             Python test suite (unit, integration, performance, security, data_integrity)
templates/         Jinja/YAML templates for system scaffolding
ventures/          Venture workspace templates (_templates/)
.github/           CI/CD workflows, issue templates, PR template, CODEOWNERS
```

## Commit Convention

This project uses **Conventional Commits**. All commits must follow:

```
<type>(<scope>): <description>

[optional body]
[optional footer(s)]
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`, `dream`

**Scopes**: `core`, `api`, `dashboard`, `cli`, `lite`, `docs`, `v5.5.0`, `fabric`, `runtimes`, `synapse`, `heart`, `dreaming`, `infra`, `deps`, `release`

Commits are enforced by commitlint via pre-commit hooks.

## Development Setup

```bash
# Python
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .

# Pre-commit hooks
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg

# Dashboard
cd dashboard && pnpm install

# CLI
cd realize-os-cli && npm install
```

## Testing

```bash
# Python — unit tests (fast)
python -m pytest tests/ -m "not slow and not integration" -v

# Python — all tests
python -m pytest tests/ -v

# Dashboard
cd dashboard && pnpm test

# CLI
cd realize-os-cli && npm test
```

## Linting & Formatting

```bash
# Python
ruff check realize_core/ realize_api/ tests/ cli.py
ruff format --check realize_core/ realize_api/ tests/ cli.py

# Dashboard
cd dashboard && pnpm lint

# Pre-commit (all hooks)
pre-commit run --all-files
```

## Key Design Docs

See `docs/v5.5.0/` for the v5.5.0 architecture evolution:
- Master design (Heart, FABRIC, Senses/Limbs, Mission Engine, Runtime Adapters)
- Runtime Adapter Contract (Python Protocol)
- FABRIC Semantic Tags (13 canonical XML-in-markdown tags)
- FABRIC Entity Schemas (JSON Schema Draft 2020-12)
- Development Infrastructure Setup (CI/CD target state)

## CI/CD

GitHub Actions workflows in `.github/workflows/`:
- `ci.yml` — lint, test, security scan, Docker build, dashboard check, CLI check
- `release.yml` — CI → multi-arch Docker → npm publish → PyPI OIDC → GitHub Release
- `pr-labeler.yml` — auto-labels PRs based on changed files

## Important Conventions

1. **`docs/` is NOT shipped** in the pip distribution (setuptools.find includes only `realize_core*`, `realize_api*`, `realize_lite*`, `templates*`)
2. **`systems/` is gitignored** — this is where actual user venture data lives locally
3. **`.env` is gitignored** — use `.env.example` as a template
4. **License**: BSL-1.1 — all new dependencies must be MIT/Apache-2.0/BSD/ISC/PostgreSQL/MPL-2.0 compatible
