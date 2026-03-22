# RealizeOS 5 — Development Session Prompt

Copy the prompt below to start a new Claude Code session in `H:\RealizeOS_V05`.

---

## Prompt

```
You are starting development on **RealizeOS 5** — the next production-level version of the RealizeOS AI operations engine.

## Essential Context

1. **Read the full improvement plan first:**
   `H:\RealizeOS_V05\docs\dev-process\plans\realizeos-5-improvement-plan.md`
   This is the master plan with PRD, Architecture, 11 Sprints, 28 Stories, Dependency Graph, Conflict Management, and Verification Plan. Every decision is documented there.

2. **Read the BMAD framework workflows you'll use:**
   - `H:\BMAD\workflows\MTH-37-dev-story-workflow.md` (per-story implementation cycle)
   - `H:\BMAD\workflows\MTH-38-sprint-tracking-workflow.md` (sprint status tracking)
   - `H:\BMAD\templates\project-context-template.md` (for project-context.md creation)
   - `H:\BMAD\skills\MTH-22-code-review-skill.md` (self-review checklist)
   - `H:\BMAD\skills\MTH-23-readiness-check-skill.md` (sprint boundary verification)

3. **Source codebase to copy:**
   `H:\realize-os\RealizeOS-Full-V03` — this is the current working version. The ENTIRE codebase gets copied into `H:\RealizeOS_V05` as the foundation. Read its `CLAUDE.md` and `README.md` to understand the existing architecture.

4. **Existing comparison report (for strategic context):**
   `H:\realize-os\comparison\realizeos-vs-paperclip.html`

## What RealizeOS 5 IS

- The **full next version** of RealizeOS — complete existing codebase + new features built on top
- A **human-centered creative system** — AI agents with human oversight, NOT fully autonomous
- Keeps **Lite + Full tiers** (Lite = Obsidian/Claude Code, Full = Python/FastAPI/Docker)
- Visual dashboard is the **top priority** (React 19 + Vite 7 + TypeScript + Tailwind + shadcn/ui, served by FastAPI)
- SSE for real-time (not WebSocket), SQLite for operational data (not PostgreSQL), FABRIC stays file-based

## Development Rules

- **Every story follows BMAD MTH-37:** Load Context → Plan Approach → Implement → Self-Review (MTH-22) → Verify → Close
- **Update sprint tracking** in the plan file after each story completion
- **Run MTH-23 readiness check** at each sprint boundary
- **All new features behind feature flags** in `realize-os.yaml`
- **Never break existing functionality** — CLI, API, and FABRIC must keep working
- **Follow the dependency graph** — never start a story before its dependencies are done

## Current Status

Sprint 1 has not started yet. Begin with **ROS5-01: Repository Bootstrap**.

## Your Task

Start Sprint 1. Execute story **ROS5-01: Repository Bootstrap** following the BMAD MTH-37 workflow:

1. Copy the ENTIRE `H:\realize-os\RealizeOS-Full-V03` codebase into `H:\RealizeOS_V05`
2. Initialize git repo, make initial commit of existing code
3. Verify existing functionality works (backend starts, tests pass)
4. Set up `dashboard/` directory with Vite + React 19 + TypeScript + Tailwind + shadcn/ui
5. Configure path aliases, ESLint, Prettier for dashboard
6. Create `project-context.md` (BMAD MTH-40) at repo root
7. Update CLAUDE.md to reflect RealizeOS 5 architecture

Acceptance Criteria: Full codebase in H:\RealizeOS_V05; `python cli.py serve` runs backend; `cd dashboard && pnpm dev` serves React shell; existing tests pass; git history starts clean.

After completing ROS5-01, run MTH-22 self-review, then proceed to Sprint 2 (ROS5-02 + ROS5-05 in parallel tracks).
```
