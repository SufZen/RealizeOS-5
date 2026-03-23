# Agent 3 Brief: LLM Routing & npm CLI

## Role
You are **Agent 3** in a 4-agent parallel BMAD development session for RealizeOS V5.

## Context
Read these files first to understand the project:
- `project-context.md` — conventions, tech stack, architecture decisions
- `CLAUDE.md` — development rules and anti-patterns
- `docs/dev-process/plans/realizeos-5-improvement-plan.md` — full improvement plan

## Your File Ownership
You own these files exclusively — NO other agent may modify them:

### Sprint 1 (Foundation)
- `.github/workflows/` (ALL files — new directory):
  - `ci.yml` — lint (ruff) + test (pytest) + security scan + Docker build
  - `release.yml` — multi-arch Docker build + push to GHCR + npm publish

### Sprint 2 (Core Intelligence)
- `realize_core/llm/` (MODIFY existing + ADD new):
  - `litellm_provider.py` [NEW] — LiteLLM wrapper implementing existing provider interface
  - `benchmark_cache.py` [NEW] — weekly benchmark fetcher + cost-benefit scorer
  - `router.py` [MODIFY] — add LiteLLM as routing option, benchmark-based model selection
- `requirements.txt` [MODIFY] — add `litellm` dependency

### Sprint 3 (npm CLI)
- `realize-os-cli/` (ALL files — entirely new directory):
  - `package.json` — npm package config (`@realize-os/cli`)
  - `tsconfig.json`
  - `src/cli.ts` — Commander.js entry point
  - `src/commands/init.ts` — scaffold project (docker-compose, .env, systems/)
  - `src/commands/start.ts` — `docker compose up -d`
  - `src/commands/stop.ts` — `docker compose down`
  - `src/commands/upgrade.ts` — pull latest image + migrate
  - `src/commands/status.ts` — health check + container status
  - `src/commands/venture.ts` — venture management (list, create, export, import)
  - `src/commands/logs.ts` — `docker compose logs -f`
  - `src/docker/compose-template.ts` — docker-compose.yml generator
  - `src/docker/image-manager.ts` — image version management
  - `templates/docker-compose.yml.ejs` — EJS template
  - `templates/.env.ejs` — environment template

### Sprint 4 (Optimization)
- `realize_core/prompt/builder.py` [MODIFY] — token optimization (minimize redundant context, smart truncation)
- `realize_core/optimizer/` (ALL files — new directory):
  - `base.py` — BaseExperiment, ExperimentResult, OptimizationTarget (if not done in Sprint 1)
  - `engine.py` — experiment loop runner (autoresearch pattern)
  - `tracker.py` — git-based experiment tracking
  - `metrics.py` — KPI definition and measurement

## Files You Must NOT Touch
- `realize_core/agents/` (Agent 1)
- `realize_core/skills/` (Agent 2)
- `dashboard/src/` (Agent 2)
- `realize_core/tools/` (Agent 4)
- `realize_core/extensions/` (Agent 4)
- `realize_core/storage/` (Agent 2/4)
- `Dockerfile`, `docker-compose.yml` (Agent 1)
- `realize_core/base_handler.py` — SHARED, only at sprint integration gate
- `realize_core/config.py` — SHARED, only at sprint integration gate

## BMAD Workflow Per Story
1. Load Context (read relevant files)
2. Plan (outline approach)
3. Implement (write code + tests)
4. Self-Review (verify no anti-patterns from CLAUDE.md)
5. Verify (run `python -m pytest tests/ -v --tb=short`)
6. Close (commit with conventional commit message)

## Sprint 1 Start
Begin with CI/CD:
1. Create `.github/workflows/ci.yml` — trigger on push/PR to main
2. Create `.github/workflows/release.yml` — trigger on tags
3. Test locally with `act` or verify GitHub Actions syntax

## Sprint 2 Start
Begin with `realize_core/llm/litellm_provider.py`:
1. Read existing `realize_core/llm/router.py` to understand the provider interface
2. Read existing `realize_core/llm/gemini_client.py` and `claude_client.py` for patterns
3. Implement LiteLLM wrapper that follows the same interface
4. Add benchmark routing logic

## npm CLI Guidelines (Sprint 3)
- Use TypeScript + Commander.js
- Package name: `@realize-os/cli` (or `realize-os`)
- Binary name: `realize-os` (so `npx realize-os init` works)
- All Docker commands use `docker compose` (v2 syntax)
- Templates use EJS for dynamic generation
- Include `--help` for every command

## Tests
- `tests/test_litellm_provider.py`
- `tests/test_benchmark_cache.py`
- `tests/test_optimizer.py`
- npm CLI: `npm test` in `realize-os-cli/` directory
