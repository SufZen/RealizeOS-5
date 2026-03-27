# Intent 6.1 — Dashboard & System Optimization

## Goal

Fix critical backend bugs, refactor oversized route modules, and optimize the dashboard frontend for reliability, maintainability, and user experience.

## Context

Full A-to-Z audit of the codebase identified **18 issues** across backend logic, API structure, and frontend architecture. The system is functional but has accumulated technical debt:
- `ventures.py` grew to 932 lines (6+ concerns in one file)
- `settings.py` has 467 lines of mixed concerns
- Critical bug: `create_venture` returns null (missing return statement)
- DB connection leak in dashboard route
- ~40 inline imports adding request latency
- Frontend has stale data, duplicate imports, native browser dialogs

Current Quality Score: 95/100 (1505 tests passing). No regression is acceptable.

## Scope

### IN (must do)

**Phase 1 — Critical Backend Fixes:**
- Fix missing return in `realize_api/routes/ventures.py:create_venture` (line 410)
- Fix DB connection leak in `realize_api/routes/dashboard.py` (add try/finally)
- Remove duplicated `_count_skills` helper (exists in both `dashboard.py` and `ventures.py`)
- Move inline imports to module-level in route handlers

**Phase 2 — Backend Structure Refactor:**
- Split `realize_api/routes/ventures.py` (932 lines → 4 files: ventures, venture_agents, venture_kb, venture_shared)
- Create `realize_api/routes/route_helpers.py` for shared utilities
- Extract settings sub-sections to separate files (reports, trust, skills, memory, llm)
- Register new routers in `realize_api/main.py`
- Add Pydantic request models for untyped POST/PUT endpoints

**Phase 3 — Frontend Optimization:**
- Fix duplicate `useApi` import in `venture-detail.tsx`
- Extract inline sections from `settings-page.tsx` (545 lines)
- Fix chat page height calculation (`h-[calc(100vh-6rem)]`)
- Wire existing `createActivityStream` SSE to Activity page
- Add auto-refresh polling to Overview page
- Replace `confirm()` / `alert()` with modal components
- Add page transition animations

### OUT (explicitly excluded)

- No changes to `realize_core/` engine logic (agents, pipeline, scheduler)
- No database schema changes
- No new API endpoints (only restructuring existing ones)
- No dependency additions (use existing packages)
- No changes to tests/ directory structure (only run existing tests)

## Acceptance Criteria

- [ ] `POST /api/ventures` returns a valid JSON response (not null)
- [ ] No DB connection leaks in dashboard route
- [ ] No duplicated helper functions across route files
- [ ] `ventures.py` reduced to ≤250 lines (from 932)
- [ ] `settings.py` reduced to ≤150 lines (from 467)
- [ ] All 1505+ existing tests still pass
- [ ] Quality Score ≥ 90 (no regression from baseline 95)
- [ ] Dashboard pages load without console errors
- [ ] No `confirm()` or `alert()` calls in frontend code
- [ ] `venture-detail.tsx` has no duplicate imports

## Build Mode

**Mode:** `standard`

> Rationale: The changes are well-understood (bugs are identified, split points are clear). Standard mode with 3 build phases matches the natural structure. Each phase has clear acceptance criteria.
