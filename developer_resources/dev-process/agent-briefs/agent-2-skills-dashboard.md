# Agent 2 Brief: Skills System & Dashboard

## Role
You are **Agent 2** in a 4-agent parallel BMAD development session for RealizeOS V5.

## Context
Read these files first to understand the project:
- `project-context.md` — conventions, tech stack, architecture decisions
- `CLAUDE.md` — development rules and anti-patterns
- `docs/dev-process/plans/realizeos-5-improvement-plan.md` — full improvement plan

## Your File Ownership
You own these files exclusively — NO other agent may modify them:

### Sprint 1 (Foundation)
- `realize_core/migration/` (ALL files — new directory):
  - `__init__.py`
  - `engine.py` — schema migration runner (version tracking, up/down, rollback)
  - `versions/001_baseline.py` — baseline schema (existing tables)
  - `versions/002_v5_tables.py` — new V5 operational tables

### Sprint 2 (Core Intelligence)
- `realize_core/skills/` (MODIFY existing + ADD new):
  - `md_loader.py` [NEW] — parse SKILL.md format (YAML frontmatter + markdown body)
  - `semantic.py` [NEW] — LLM-based semantic skill matching (fallback when keywords miss)
  - `creator.py` [NEW] — meta-skill for creating new skills conversationally
  - `detector.py` [MODIFY] — add SKILL.md scanning, add semantic fallback trigger
  - `executor.py` [MODIFY] — handle SKILL.md format execution alongside YAML

### Sprint 3 (Dashboard Enhancement)
- `dashboard/src/` (ADD new pages + components):
  - `pages/pipeline-builder.tsx` [NEW] — agent pipeline visual builder
  - `pages/workflow-editor.tsx` [NEW] — skill/workflow editor (YAML + SKILL.md)
  - `pages/routing-page.tsx` [NEW] — routing analytics visualization
  - `pages/integrations-page.tsx` [NEW] — integrations manager
  - `App.tsx` [MODIFY] — add routes for new pages
  - New shared components as needed

### Sprint 4 (Storage)
- `realize_core/storage/` (ALL files — new directory):
  - `base.py` — BaseStorageProvider abstract (if not created by Agent 4 in Sprint 1)
  - `local.py` — local filesystem storage (default)
  - `s3.py` — S3-compatible storage
  - `sync.py` — background sync manager

## Files You Must NOT Touch
- `realize_core/agents/` (Agent 1)
- `realize_api/routes/agents_v2.py`, `workflows.py`, `extensions.py`, `routing.py` (Agent 1)
- `realize_core/llm/` (Agent 3)
- `realize-os-cli/` (Agent 3)
- `realize_core/tools/` (Agent 4)
- `realize_core/extensions/` (Agent 4)
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
Begin with the migration engine:
1. Create `realize_core/migration/engine.py` with version tracking
2. Create baseline migration and V5 migration scripts
3. Write tests for migration up/down/rollback

## Sprint 2 Start
Begin with `realize_core/skills/md_loader.py` (SKILL.md parser), then semantic matching, then modify existing detector/executor.

## Dashboard Guidelines (Sprint 3)
- Follow existing component patterns in `dashboard/src/`
- Use shadcn/ui components, Tailwind CSS v4
- Use Lucide icons (consistent with existing pages)
- Fetch data from API endpoints created by Agent 1
- Dark theme with yellow accent (#ffcc00)
- Proxy `/api/*` to FastAPI in dev mode

## Tests
Create test files in `tests/` matching each module:
- `tests/test_migration_engine.py`
- `tests/test_skill_md_loader.py`
- `tests/test_skill_semantic.py`
- `tests/test_storage_backend.py`
