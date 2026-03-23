# Project Context

project_name: "RealizeOS 5"
version: "5.0.0"
type: software

## Tech Stack

language: Python 3.11+ (backend), TypeScript (frontend)
framework: FastAPI (backend), React 19 + Vite 8 (frontend)
database: SQLite (FTS5 + operational tables) — default; pluggable storage layer for S3/GCS/Azure
frontend: Tailwind CSS v4 + shadcn/ui + Lucide icons
hosting: Docker Compose / local (`python cli.py serve`) / npm CLI (`npx realize-os start`)
scheduler: APScheduler (integrated)
realtime: SSE (primary) + WebSocket (dashboard live events)
llm_routing: Built-in 4-provider router + LiteLLM (50+ providers via benchmark routing)

## Conventions

naming: snake_case (Python), camelCase (TypeScript), kebab-case (component files)
testing: pytest (backend), vitest (frontend — planned)
git_branching: feature branches off main
commit_style: conventional commits (feat:, fix:, refactor:, docs:)
code_style: ruff (Python), eslint + prettier (TypeScript)

## Architecture Decisions

- Dashboard served as static build by FastAPI (`StaticFiles` mount) — single deployment
- SSE for real-time activity feed; WebSocket added for bidirectional dashboard events
- SQLite for operational data (default) — pluggable storage layer enables S3/GCS/Azure for cloud deployments
- FABRIC remains file-based (not migrated to DB) — file-based is a feature
- Existing `base_handler` instrumented with activity logging hooks (non-breaking, fire-and-forget)
- Agent status tracked in DB; agent definitions in `.md` (V1) or `.yaml` (V2 composable)
- All new features behind feature flags in `realize-os.yaml`
- Dashboard API endpoints under `/api/` prefix, separate route modules per domain
- Dev mode: Vite dev server proxies `/api/*` to FastAPI on port 8080
- Production: `pnpm build` outputs to `static/`, FastAPI serves it
- Agents: V1 (.md markdown) + V2 (.yaml composable with pipelines, handoffs, guardrails)
- Skills: YAML (v1/v2) + SKILL.md (Anthropic-inspired) with semantic triggering fallback
- Extensions: unified registry (plugins→extensions, auto-discovery from config + filesystem)
- npm CLI package: `npx realize-os init` / `start` / `stop` / `upgrade` for easy distribution

## V5 Agent Architecture (NEW)

### Composable Agent V2 Format (YAML)
- Enriched schema: scope, inputs, outputs, guardrails, tools, critical_rules, decision_logic, success_metrics, learning, communication_style
- Persona bundles: exec-assistant, writer, PM, etc.
- Pipeline executor: sequential stages with structured handoffs
- 7 handoff types: standard, QA-pass, QA-fail, escalation, phase-gate, sprint, incident
- Dev-QA retry loop: max 3 retries → auto-escalation
- V1 (.md) agents remain fully supported — backward compatible

### Dual Skill Format
- YAML skills: existing v1/v2 format (unchanged)
- SKILL.md: Anthropic-inspired markdown format (YAML frontmatter + markdown body)
- Semantic triggering: LLM-based fallback when keyword matching fails
- Skill creator: meta-skill for conversational skill creation

## Implementation Rules

- Never break existing `base_handler` message flow
- All new features behind feature flags in `realize-os.yaml`
- Activity logging is fire-and-forget (never block main flow)
- All approval gates are configurable (can be disabled)
- CLI must keep working independently of dashboard
- Follow the dependency graph in the improvement plan
- Every story follows BMAD MTH-37: Load Context → Plan → Implement → Self-Review (MTH-22) → Verify → Close
- Update sprint tracking after each story completion

## Anti-Patterns (never do these)

- Do not move FABRIC to database — file-based is a feature
- Do not require dashboard for core functionality — CLI must keep working
- Do not copy Paperclip's fully-autonomous model — RealizeOS is human-centered
- Do not use `print()` for logging — use structured logging
- Do not swallow exceptions with bare `except`
- Do not add dependencies without documenting the reason

## File Ownership (Parallel Development)

When multiple agents work in parallel, each agent owns specific directories:
- Agent A (Infra & Agents): `realize_core/agents/`, `Dockerfile`, `docker-compose.yml`, `cli.py`
- Agent B (Skills & Dashboard): `realize_core/skills/`, `dashboard/src/`
- Agent C (LLM & CLI): `realize_core/llm/`, `realize-os-cli/`, `realize_core/prompt/`, `realize_core/optimizer/`
- Agent D (Google & Extensions): `realize_core/tools/`, `realize_core/extensions/`, `realize_core/storage/`
- Shared files (`base_handler.py`, `config.py`, `main.py`) modified ONLY at sprint integration gates

## Notes

- Source codebase from V05 development (28 stories already implemented)
- Development follows the RealizeOS 5 Improvement Plan
- BMAD framework workflows at `H:\BMAD\workflows\`
- Brand colors: dark theme (#0a0a0f background), yellow accent (#ffcc00), Poppins font
- Two tiers: Lite (Obsidian/Claude Code) + Full (Python/FastAPI/Docker)
