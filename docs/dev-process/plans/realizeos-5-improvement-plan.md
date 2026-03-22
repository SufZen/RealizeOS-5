# RealizeOS 5 — Production-Level Improvement Plan

## Context

Based on the competitive analysis of RealizeOS vs Paperclip, this plan takes RealizeOS to production-level while preserving its identity as a **human-centered creative system** — one that harnesses AI power without neglecting the human decision-maker. The goal is "best of both worlds": keep RealizeOS's deep intelligence (FABRIC KB, 12-layer prompts, multi-LLM routing, self-evolution) while selectively adopting governance, visibility, and operational maturity features inspired by Paperclip's control-plane model.

**Development folder:** `H:\RealizeOS_V05` — **full codebase copy** of existing RealizeOS + all new features built on top. The previous version at `H:\realize-os\RealizeOS-Full-V03` is preserved as-is for safety.

**Key principle:** RealizeOS 5 is NOT a separate add-on — it IS the next version of the full system. The new folder contains the complete working codebase (existing engine + new dashboard + new features). Everything builds on top of what already exists.

**User-specified priorities:**
- Visual dashboard is the **top priority**
- Human-centered (not fully autonomous)
- Keep Lite + Full tiers
- Preserve previous version — develop in `H:\RealizeOS_V05` (full copy)
- Cost tracking is **low priority**
- Pay close attention to **development order** — manage conflicts and dependencies so everything builds smoothly
- **Entire process follows the BMAD framework**

**BMAD framework integration:**
| BMAD Workflow | Purpose | When Used |
|---|---|---|
| **MTH-35** (Planning) | This plan document | Done (this file) |
| **MTH-36** (Architecture) | Architecture decisions & data model | Done (Part 2 of this file) |
| **MTH-37** (Dev Story Workflow) | Per-story implementation cycle | Every story: Load Context → Plan Approach → Implement → Self-Review → Verify → Close |
| **MTH-38** (Sprint Tracking) | Sprint status YAML | Updated after each story completion (Part 5 of this file) |
| **MTH-40** (Project Context) | project-context.md in repo | Created in Sprint 1 (ROS5-01), lives at `H:\RealizeOS_V05\project-context.md` |
| **MTH-22** (Code Review) | Self-review checklist | Applied after each story implementation |
| **MTH-23** (Readiness Check) | Pre-release verification | Applied at end of each sprint and before major milestones |

---

# Part 1: PRD — Product Requirements Document

## Overview

RealizeOS 5 evolves the existing AI operations engine into a production-grade system with visual management, agent observability, human governance, and scheduled operations. The target user is a business operator who wants AI agents handling work while retaining full visibility and control.

## User Stories

### Dashboard & Visibility
- As an operator, I want a **web dashboard** so I can see what my AI agents are doing at a glance.
- As an operator, I want an **activity feed** so I can understand what happened while I was away.
- As an operator, I want to see **agent status and recent actions** so I know which agents are active and what they're working on.
- As an operator, I want to see my **venture health** (KB completeness, skill coverage, recent interactions) at a glance.

### Governance & Human Control
- As a decision-maker, I want **approval gates** on consequential actions (sending emails, publishing content, external API calls) so nothing goes out without my review.
- As a decision-maker, I want to **pause, resume, or override** any agent or running workflow.
- As a decision-maker, I want **notification alerts** when agents need my input or encounter errors.

### Agent Operations
- As an operator, I want agents to run on **schedules** (heartbeats) so they can proactively check email, generate reports, or monitor trends.
- As an operator, I want agents to be able to **delegate tasks to other agents** so complex work flows through the right specialists.
- As an operator, I want a clear **agent status model** (idle, running, paused, error) so I always know the state.

### Self-Evolution & Intelligence (preserve + enhance)
- As an operator, I want the **evolution inbox** to show suggested skills, prompt improvements, and detected gaps in a visual interface.
- As an operator, I want to **approve or reject** evolution suggestions before they're applied.

### Extensibility
- As a developer, I want a **plugin system** so I can add tools, channels, and integrations without modifying core.
- As a community member, I want to **share and discover** venture templates and skill packs.

## Functional Requirements

### F1: Visual Dashboard (HIGH PRIORITY)
- Real-time overview: active ventures, agent states, recent activity
- Venture detail view: FABRIC completeness, agents, skills, sessions
- Agent detail view: status, recent actions, configuration
- Activity feed: chronological log of all agent actions and skill executions
- Skill management: list, enable/disable, view execution history
- Evolution inbox: pending suggestions with approve/reject UI
- Responsive design, RealizeOS brand (dark theme, #ffcc00 accent)

### F2: Activity Audit Log (HIGH PRIORITY)
- Log every agent action, skill execution, tool call, and LLM invocation
- Structured events with: timestamp, actor (agent/system/user), action, entity, details
- Filterable by venture, agent, action type, time range
- API endpoint for querying activity

### F3: Agent Lifecycle & Status (HIGH PRIORITY)
- Agent status model: idle | running | paused | error
- Status transitions tracked and logged
- Pause/resume from dashboard
- Error visibility with details

### F4: Scheduled Agent Heartbeats (MEDIUM PRIORITY)
- Per-agent schedule configuration (cron-like or interval)
- Scheduler service that triggers agent runs on schedule
- Skip if agent is paused or already running
- Dashboard shows next scheduled run and last run result

### F5: Agent Hierarchy & Delegation (MEDIUM PRIORITY)
- Optional `reports_to` field in agent definitions
- Cross-agent task delegation through skills
- Visual org tree in dashboard (optional, non-blocking)

### F6: Governance & Approval Gates (MEDIUM PRIORITY)
- Configurable approval gates on tool write operations
- Approval queue visible in dashboard
- Approve/reject with optional notes
- Timeout handling for pending approvals

### F7: Plugin Architecture (LOWER PRIORITY)
- Tool plugins: register new tools via directory convention
- Channel plugins: register new channel adapters
- Lifecycle hooks for plugin initialization

### F8: Template Sharing (LOWER PRIORITY)
- Export venture as portable package
- Import venture from package
- (Future) Community registry

### F9: Cost Tracking (LOW PRIORITY — deferred)
- Basic per-session token counting (already partially exists)
- Dashboard display of aggregate costs
- No budget enforcement in RealizeOS 5

## Non-Functional Requirements

### Performance
- Dashboard loads in < 2s
- Activity feed streams in real-time (SSE or WebSocket)
- API p95 latency < 250ms for CRUD operations

### Security
- Session-based auth for dashboard
- API key auth for programmatic access
- CSRF protection on mutation endpoints

### Scalability
- Single-tenant (matches current model)
- Support up to 10 ventures, 50 agents, 10k activity events per instance

### Accessibility
- Dashboard meets WCAG 2.1 AA
- Keyboard navigable
- Screen reader compatible

## Information Architecture

### Dashboard Pages
```
/                           → Overview (ventures, agent summary, recent activity)
/ventures                   → Venture list
/ventures/:key              → Venture detail (FABRIC, agents, skills)
/ventures/:key/agents       → Agent list with status
/ventures/:key/agents/:id   → Agent detail (config, history, actions)
/ventures/:key/skills       → Skill list with execution stats
/ventures/:key/activity     → Activity feed (filterable)
/evolution                  → Evolution inbox (pending suggestions)
/approvals                  → Pending approval queue
/settings                   → System configuration
```

## Technical Constraints

- `H:\RealizeOS_V05` contains the **full RealizeOS codebase** (copy of existing + new features on top)
- Previous version preserved at `H:\realize-os\RealizeOS-Full-V03` (untouched)
- New features are additive — existing engine code, CLI, API, and FABRIC all continue to work
- Keep Python/FastAPI backend (proven, working)
- FABRIC directory structure and YAML config format must remain compatible
- Lite tier must continue to work independently (no server dependency)
- All development follows BMAD framework (MTH-35 through MTH-40)

## Success Metrics

- Dashboard fully functional with real data from existing ventures
- An operator can see agent activity without checking logs
- Approval gates prevent unreviewed external actions
- Scheduled agents run autonomously with human oversight
- Zero regressions in existing Full package functionality

## Resolved Design Decisions

- Q1: Dashboard embedded in FastAPI server (static build served by `StaticFiles`)
- Q2: SSE for real-time (simpler, unidirectional fits activity feed, native browser support)
- Q3: Lite users — deferred to post-V5 (possible static HTML export in future)

---

# Part 2: Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Dashboard (React)                     │
│  Vite + React 19 + TypeScript + Tailwind CSS + shadcn/ui    │
│  Pages: Overview | Ventures | Agents | Activity | Evolution  │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API + SSE
┌──────────────────────────┴──────────────────────────────────┐
│                     FastAPI Backend (Python)                  │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Dashboard │ │ Activity  │ │ Approval │ │  Scheduler   │  │
│  │   API     │ │   Log     │ │  Queue   │ │  (heartbeat) │  │
│  └──────────┘ └───────────┘ └──────────┘ └──────────────┘  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Existing RealizeOS Core                  │    │
│  │  base_handler | llm/ | prompt/ | skills/ | tools/    │    │
│  │  channels/ | evolution/ | memory/ | kb/ | pipeline/  │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌──────────┐ ┌───────────┐                                  │
│  │  SQLite   │ │  FABRIC   │                                  │
│  │  (events, │ │  (files)  │                                  │
│  │  sessions)│ │           │                                  │
│  └──────────┘ └───────────┘                                  │
└──────────────────────────────────────────────────────────────┘
```

## Tech Stack Decisions

| Decision | Choice | Rationale | Alternatives Considered |
|----------|--------|-----------|------------------------|
| Dashboard framework | React 19 + Vite 7 + TypeScript | Already proven in project (frontend/), team familiar, shadcn/ui components ready | Next.js (overkill for SPA), HTMX (limited interactivity), Vue (no existing code) |
| UI components | shadcn/ui + Tailwind CSS | Already configured in project, consistent with brand, accessible | Material UI (heavy), Chakra (different design system) |
| Dashboard serving | FastAPI serves static build + API | Single deployment, no CORS issues, simpler ops | Separate Vite dev server (complexity), Nginx (extra infra) |
| Real-time updates | Server-Sent Events (SSE) | Simpler than WebSocket, unidirectional fits activity feed, native browser support | WebSocket (bidirectional not needed), polling (wasteful) |
| Activity storage | SQLite (same DB as existing) | Zero additional infrastructure, sufficient for single-tenant | PostgreSQL (overkill for RealizeOS 5), separate DB (fragmentation) |
| Scheduler | APScheduler (Python) | Lightweight, in-process, cron + interval support, already used in Python ecosystem | Celery (heavy), systemd timers (not portable) |
| Auth | Session cookie (FastAPI) | Simple, secure for single-tenant dashboard | JWT (over-engineered for single-user), OAuth (external dependency) |

## Data Model — New Tables (SQLite)

### `activity_events`
| Field | Type | Notes |
|-------|------|-------|
| id | TEXT (UUID) | Primary key |
| venture_key | TEXT | FK to venture |
| actor_type | TEXT | 'agent' / 'system' / 'user' |
| actor_id | TEXT | Agent key or 'system' |
| action | TEXT | 'skill_executed', 'llm_called', 'tool_used', etc. |
| entity_type | TEXT | 'skill', 'agent', 'tool', 'session', etc. |
| entity_id | TEXT | Identifier of the entity |
| details | TEXT (JSON) | Action-specific payload |
| created_at | TEXT (ISO8601) | Timestamp |

### `agent_states`
| Field | Type | Notes |
|-------|------|-------|
| agent_key | TEXT | PK, matches agent .md file key |
| venture_key | TEXT | FK to venture |
| status | TEXT | 'idle' / 'running' / 'paused' / 'error' |
| last_run_at | TEXT | Last execution timestamp |
| last_error | TEXT | Error message if status='error' |
| schedule_cron | TEXT | Cron expression (nullable) |
| schedule_interval_sec | INTEGER | Interval in seconds (nullable) |
| next_run_at | TEXT | Next scheduled execution |
| updated_at | TEXT | Last status change |

### `approval_queue`
| Field | Type | Notes |
|-------|------|-------|
| id | TEXT (UUID) | Primary key |
| venture_key | TEXT | FK to venture |
| agent_key | TEXT | Requesting agent |
| action_type | TEXT | 'send_email', 'publish', 'external_api', etc. |
| payload | TEXT (JSON) | Full action details for review |
| status | TEXT | 'pending' / 'approved' / 'rejected' / 'expired' |
| decision_note | TEXT | Optional reviewer note |
| created_at | TEXT | When the request was created |
| decided_at | TEXT | When the decision was made |
| expires_at | TEXT | Auto-expire timestamp |

### Indexes
- `activity_events(venture_key, created_at DESC)`
- `activity_events(venture_key, actor_id, created_at DESC)`
- `agent_states(venture_key, status)`
- `approval_queue(venture_key, status)`

## API Design — New Endpoints

### Dashboard API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/dashboard` | Session | Overview: ventures, agent counts, recent activity |
| GET | `/api/ventures` | Session | List ventures with health summary |
| GET | `/api/ventures/:key` | Session | Venture detail (FABRIC, agents, skills) |
| GET | `/api/ventures/:key/agents` | Session | Agents with current status |
| GET | `/api/ventures/:key/agents/:id` | Session | Agent detail + action history |
| POST | `/api/ventures/:key/agents/:id/pause` | Session | Pause agent |
| POST | `/api/ventures/:key/agents/:id/resume` | Session | Resume agent |
| GET | `/api/ventures/:key/skills` | Session | Skills with execution stats |
| GET | `/api/ventures/:key/activity` | Session | Activity feed (paginated, filterable) |
| GET | `/api/activity/stream` | Session | SSE stream of new activity events |

### Approval API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/approvals` | Session | Pending approvals (all ventures) |
| POST | `/api/approvals/:id/approve` | Session | Approve with optional note |
| POST | `/api/approvals/:id/reject` | Session | Reject with optional note |

### Evolution API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/evolution/suggestions` | Session | Pending evolution suggestions |
| POST | `/api/evolution/suggestions/:id/approve` | Session | Apply suggestion |
| POST | `/api/evolution/suggestions/:id/dismiss` | Session | Dismiss suggestion |

## Component Breakdown

### Backend Components (Python — additions to realize_core/)

| Component | Responsibility | New Files |
|-----------|---------------|-----------|
| `activity/` | Event logging, querying, SSE streaming | `logger.py`, `store.py`, `stream.py` |
| `governance/` | Approval queue, gate enforcement | `approvals.py`, `gates.py` |
| `scheduler/` | Heartbeat scheduling, agent lifecycle | `scheduler.py`, `heartbeat.py` |
| `dashboard/` | Dashboard API routes, aggregation | `routes.py`, `aggregator.py` |
| `db/` | SQLite schema, migrations | `schema.py`, `migrations.py` |

### Frontend Components (React — new dashboard/ directory)

| Component | Responsibility |
|-----------|---------------|
| `pages/Overview` | Main dashboard with venture cards, agent summary, activity feed |
| `pages/VentureDetail` | FABRIC visualization, agent list, skill list |
| `pages/AgentDetail` | Agent config, status, action history, controls |
| `pages/Activity` | Full activity log with filters |
| `pages/Evolution` | Suggestion inbox with approve/dismiss |
| `pages/Approvals` | Pending approval queue |
| `components/ActivityFeed` | Real-time SSE-powered activity stream |
| `components/AgentStatusBadge` | Visual status indicator |
| `components/VentureHealthCard` | FABRIC completeness, agent counts, skill counts |
| `components/ApprovalCard` | Action review with approve/reject buttons |

## Infrastructure

- **Hosting:** Same as current (Docker Compose or local `python cli.py serve`)
- **Dashboard build:** Vite builds to `static/` directory, served by FastAPI `StaticFiles`
- **Dev mode:** Vite dev server with proxy to FastAPI for hot-reload
- **CI/CD:** GitHub Actions (typecheck, test, build)

## Security

- **Authentication:** Simple session-based auth (configurable password or local-trusted mode)
- **Authorization:** Single-user (board operator) — full access to all ventures
- **Data Protection:** SQLite on local disk, no external data transmission
- **API Security:** CSRF tokens on mutation endpoints, rate limiting on auth

---

# Part 3: Phased Implementation Plan

## Priority Ladder

| Priority | Feature | Rationale |
|----------|---------|-----------|
| **P0** | Visual Dashboard + Activity Log | User's explicit top priority; enables all other visibility features |
| **P1** | Agent Status Model + Lifecycle | Foundation for dashboard agent views and scheduling |
| **P2** | Scheduled Agent Heartbeats | Transforms agents from reactive to proactive |
| **P3** | Governance & Approval Gates | Human-centered control — core identity of RealizeOS |
| **P4** | Agent Hierarchy & Delegation | Enables complex multi-agent workflows |
| **P5** | Evolution Inbox (visual) | Surfaces existing self-evolution in the dashboard |
| **P6** | Plugin Architecture | Extensibility for tools, channels, integrations |
| **P7** | Template Sharing / Export | Community and marketplace foundation |
| **P8** | Cost Tracking (basic) | User explicitly marked low priority |

---

## Dependency Graph

The build order is critical. Each story has explicit dependencies. Stories within the same sprint that share a track (A/B) can be built in parallel; stories on different tracks within the same sprint are independent.

```
LAYER 0 — Foundation (must be first)
  ROS5-01: Repository Bootstrap

LAYER 1 — Parallel Foundation (both depend only on ROS5-01)
  Track A: ROS5-02: Database Schema ──────────────┐
  Track B: ROS5-05: Dashboard Shell & Navigation ──┤ (independent tracks)
                                                    │
LAYER 2 — Backend Core (depend on ROS5-02)          │
  Track A: ROS5-03: Activity Event Logger           │
  Track B: ROS5-11: Agent Status Model              │
  (parallel — different tables, no conflict)        │
                                                    │
LAYER 3 — Backend APIs                              │
  ROS5-10: Venture API ─── needs ROS5-03 + ROS5-11 │
  ROS5-07: Activity API ── needs ROS5-03            │
  ROS5-04: Dashboard API ─ needs ROS5-03            │
  (ROS5-07 and ROS5-04 can parallel; ROS5-10 waits)│
                                                    │
LAYER 4 — Frontend Pages (all need ROS5-05) ────────┘
  ROS5-06: Overview Page ────── needs ROS5-04
  ROS5-08: Activity Page ────── needs ROS5-07
  ROS5-09: Venture Detail Page ─ needs ROS5-10
  (all three can parallel once their API is ready)

LAYER 5 — Agent Detail + Controls
  ROS5-12: Agent Detail Page ── needs ROS5-10 + ROS5-11 + ROS5-05
  ROS5-13: Agent Pause/Resume ─ needs ROS5-11
  (parallel — frontend vs backend)

LAYER 6 — Scheduling (sequential chain)
  ROS5-14: Scheduler Service ──── needs ROS5-11 + ROS5-13
  ROS5-15: Schedule Configuration ─ needs ROS5-14
  ROS5-16: Heartbeat Dashboard ─── needs ROS5-14 + ROS5-12

LAYER 7 — Governance (can start after Layer 2)
  ROS5-17: Approval Gate System ── needs ROS5-02 + ROS5-03
  ROS5-18: Approval Queue API ─── needs ROS5-17
  ROS5-19: Approval Queue Page ── needs ROS5-18 + ROS5-05

LAYER 8 — Hierarchy & Delegation
  ROS5-20: Agent Hierarchy Model ──── needs ROS5-11
  ROS5-21: Inter-Agent Delegation ─── needs ROS5-20
  ROS5-22: Org Chart Component ────── needs ROS5-20 + ROS5-05

LAYER 9 — Evolution Inbox
  ROS5-23: Evolution API ────── needs ROS5-02
  ROS5-24: Evolution Inbox Page ─ needs ROS5-23 + ROS5-05

LAYER 10 — Extensibility (independent of Layers 5-9)
  ROS5-25: Plugin Discovery ──── needs ROS5-01
  ROS5-26: Tool Plugin Interface ─ needs ROS5-25
  ROS5-27: Venture Export ──────── needs ROS5-01
  ROS5-28: Venture Import ──────── needs ROS5-27
```

## Conflict Management Rules

| Potential Conflict | Mitigation |
|---|---|
| ROS5-03 (Activity Logger) and ROS5-11 (Agent Status) both modify `base_handler.py` | **Build ROS5-03 first.** ROS5-11 adds a thin status wrapper around the same handler — changes are in different sections (logging hooks vs. status transitions). If built in parallel, merge conflicts are minor (different functions). |
| ROS5-04 and ROS5-10 both add routes to `realize_api/` | Use separate route modules: `routes/dashboard.py` and `routes/ventures.py`. Register via FastAPI `include_router()`. No conflict. |
| ROS5-07 (SSE) and other API stories share the FastAPI app | SSE endpoint is a standalone route — no shared state. Use `asyncio.Queue` per connection, fed by the activity logger's event bus. |
| Multiple frontend pages (ROS5-06/08/09/12) all import shared components | Build shared components (ActivityFeed, AgentStatusBadge, VentureHealthCard) as part of ROS5-05 shell. Pages consume them. |
| ROS5-14 (Scheduler) and ROS5-17 (Approval Gates) both hook into the execution pipeline | Different hook points: Scheduler triggers `base_handler`; Approval Gates intercept tool dispatch inside `base_handler`. No overlap. |
| `realize-os.yaml` feature flags touched by multiple stories | Each feature adds a new flag key (e.g., `activity_log`, `agent_lifecycle`, `heartbeats`, `approval_gates`). No key collisions. |

---

## Sprint Plan — Optimized Build Order

### Sprint 1: Foundation (Week 1)
> **Goal:** Complete working codebase in `H:\RealizeOS_V05` — full copy of existing system + new dashboard scaffolding.
> **BMAD:** MTH-37 (Dev Story Workflow) + MTH-40 (Project Context)

**ROS5-01: Repository Bootstrap**
- Depends on: nothing (FIRST)
- **Step 1:** Copy the ENTIRE `H:\realize-os\RealizeOS-Full-V03` codebase to `H:\RealizeOS_V05` (full working copy — all Python engine, API, CLI, templates, docs, tests, realize_lite/, etc.)
- **Step 2:** Initialize git repo in `H:\RealizeOS_V05`, initial commit of existing code
- **Step 3:** Verify all existing functionality works: `python cli.py serve`, `python cli.py status`, existing tests pass
- **Step 4:** Set up `dashboard/` directory with Vite + React 19 + TypeScript + Tailwind + shadcn/ui (new, alongside existing code)
- **Step 5:** Configure path aliases (`@/` → `./src/`), ESLint, Prettier for dashboard
- **Step 6:** Create `project-context.md` (BMAD MTH-40) at repo root
- **Step 7:** Update CLAUDE.md to reflect RealizeOS 5 architecture (add dashboard section)
- AC: Full codebase in `H:\RealizeOS_V05`; `python cli.py serve` runs backend; `cd dashboard && pnpm dev` serves React shell; existing tests pass; git history starts clean

### Sprint 2: Parallel Foundation (Week 2)
> **Goal:** Database operational + Dashboard shell with navigation and brand theming.
> Two independent tracks — no conflict.
> **BMAD:** MTH-37 per story, MTH-22 review after each track

**Track A — ROS5-02: Database Schema & Migrations**
- Depends on: ROS5-01
- Create `realize_core/db/schema.py` with `activity_events`, `agent_states`, `approval_queue` tables
- Create migration system (simple Python scripts, auto-run on startup)
- Auto-create tables on first `python cli.py serve`
- AC: Tables exist after startup; can insert/query activity events via Python

**Track B — ROS5-05: Dashboard Shell & Navigation**
- Depends on: ROS5-01
- React app with sidebar navigation: Overview, Ventures, Activity, Evolution, Approvals, Settings
- RealizeOS brand: dark theme (#0a0a0f), yellow accent (#ffcc00), Poppins font
- Responsive layout with mobile sidebar (Sheet component)
- Build shared components: `ActivityFeed`, `AgentStatusBadge`, `VentureHealthCard`, `ApprovalCard`
- Set up API client utility with fetch wrapper
- AC: Dashboard renders in browser with all navigation links; shared components importable

### Sprint 3: Backend Instrumentation (Week 3)
> **Goal:** Activity logging and agent status tracking operational in the backend.
> Two parallel tracks working on different DB tables and different `base_handler` sections.
> **BMAD:** MTH-37 per story, MTH-22 review (critical — these stories touch `base_handler.py`)

**Track A — ROS5-03: Activity Event Logger**
- Depends on: ROS5-02
- Create `realize_core/activity/logger.py` — async, fire-and-forget event emitter
- Create `realize_core/activity/store.py` — SQLite read/query layer
- Create in-memory event bus (for SSE later)
- Instrument `base_handler.py` to log: message_received, agent_routed, llm_called, skill_executed, tool_used
- Feature flag: `features.activity_log: true` in `realize-os.yaml`
- AC: After sending a chat message, activity_events table has 3+ records; event bus receives events

**Track B — ROS5-11: Agent Status Model**
- Depends on: ROS5-02
- Define status enum: idle | running | paused | error
- Create `realize_core/scheduler/lifecycle.py` — status transition manager
- Add thin hooks in `base_handler.py`: set `running` on message start, `idle` on completion, `error` on exception
- Persist status changes in `agent_states` table
- Feature flag: `features.agent_lifecycle: true`
- AC: After a chat using agent "writer", agent_states shows status=idle and last_run_at set

### Sprint 4: Backend APIs (Week 4)
> **Goal:** All dashboard-facing API endpoints operational.
> Three stories; ROS5-07 and ROS5-04 can be parallel. ROS5-10 depends on both Sprint 3 tracks.

**Track A — ROS5-07: Activity API & SSE Stream**
- Depends on: ROS5-03
- `GET /api/ventures/:key/activity` — paginated, filterable (by agent, action type, date range)
- `GET /api/activity/stream` — SSE endpoint streaming from the event bus
- Route module: `realize_api/routes/activity.py`
- AC: curl gets paginated activity; SSE stream receives events in real-time

**Track B — ROS5-04: Dashboard API — Overview Endpoint**
- Depends on: ROS5-03
- `GET /api/dashboard` returns: venture list with agent counts, skill counts, recent activity (last 20 events)
- Route module: `realize_api/routes/dashboard.py`
- Reads FABRIC filesystem + activity_events + agent_states
- AC: curl returns JSON with real venture data

**Track C — ROS5-10: Venture API Endpoints** (start after Tracks A/B begin, needs Sprint 3 complete)
- Depends on: ROS5-03, ROS5-11
- `GET /api/ventures` — list with health summary
- `GET /api/ventures/:key` — detail with FABRIC analysis, agents, skills
- `GET /api/ventures/:key/agents` — agent list with current states
- `GET /api/ventures/:key/skills` — skill list with execution stats
- Route module: `realize_api/routes/ventures.py`
- AC: All endpoints return accurate data matching filesystem state + DB state

### Sprint 5: Core Dashboard Pages (Week 5-6)
> **Goal:** Three main dashboard pages rendering real data.
> All three pages are independent — they consume different APIs and share components from Sprint 2.
> **BMAD:** MTH-37 per page, MTH-23 readiness check at sprint end (first visual milestone)

**Track A — ROS5-06: Overview Page**
- Depends on: ROS5-04, ROS5-05
- Venture cards with: name, agent count, skill count, last activity
- Recent activity feed (last 20 events) using `ActivityFeed` component
- System health indicators (provider status, venture count)
- AC: Overview shows real venture data from API

**Track B — ROS5-08: Activity Page**
- Depends on: ROS5-07, ROS5-05
- Chronological event list with: timestamp, actor, action, entity, details
- Filter controls: venture, agent, action type, date range
- Real-time SSE updates with "new events" indicator
- AC: Filter by agent shows only that agent's events; new events appear live

**Track C — ROS5-09: Venture Detail Page**
- Depends on: ROS5-10, ROS5-05
- FABRIC directory visualization (F/A/B/R/I/C with file counts and completeness)
- Agent list with status badges using `AgentStatusBadge`
- Skill list with last execution time
- Venture configuration summary
- AC: Navigate to venture, see FABRIC structure, agents, and skills

### Sprint 6: Agent Management (Week 7)
> **Goal:** Agent detail views with pause/resume control.
> Backend and frontend can be parallel.

**Track A — ROS5-13: Agent Pause/Resume API**
- Depends on: ROS5-11
- `POST /api/ventures/:key/agents/:id/pause` — sets status to paused
- `POST /api/ventures/:key/agents/:id/resume` — sets status to idle
- Update `base_handler.py`: skip paused agents, route to fallback
- AC: Pause agent via API; send message to that agent; message routed to fallback; resume; agent handles next message

**Track B — ROS5-12: Agent Detail Page**
- Depends on: ROS5-10, ROS5-11, ROS5-05
- Agent configuration display (from .md file)
- Status with visual indicator (green=idle, yellow=running, red=error, gray=paused)
- Action history (filtered activity events for this agent)
- Pause/Resume buttons (connected to ROS5-13 API)
- AC: Navigate to agent, see config, status, action history; pause/resume works from UI

### Sprint 7: Scheduling (Week 8-9)
> **Goal:** Agents can run on schedules. Sequential chain — each story depends on the previous.

**ROS5-14: Scheduler Service**
- Depends on: ROS5-11, ROS5-13
- APScheduler integration in FastAPI startup lifecycle
- Read schedule config from `agent_states` table
- Trigger agent heartbeat: invoke `base_handler.process_message()` with system message
- Skip agents with status=paused or status=running
- Log heartbeat results to activity_events
- Feature flag: `features.heartbeats: true`
- AC: Agent with `schedule_interval_sec: 300` runs every 5 minutes; events logged

**ROS5-15: Schedule Configuration**
- Depends on: ROS5-14
- Add schedule fields to agent `.md` frontmatter (YAML): `schedule_cron` or `schedule_interval`
- CLI command: `python cli.py agent schedule --key writer --interval 300`
- API endpoint: `PUT /api/ventures/:key/agents/:id/schedule`
- Dashboard UI: schedule editor in Agent Detail Page
- AC: Set schedule from CLI or dashboard; agent runs on time; schedule persisted

**ROS5-16: Heartbeat Dashboard Indicators**
- Depends on: ROS5-14, ROS5-12
- Show next scheduled run countdown per agent (in Agent Detail + Venture agents list)
- Show last run result (success/error/skipped)
- Visual timeline of recent heartbeats
- AC: Dashboard shows "Next run: 4m 32s" and last 5 run results per agent

### Sprint 8: Governance (Week 10-11)
> **Goal:** Human approval gates on consequential agent actions.
> Sequential chain: system → API → page.

**ROS5-17: Approval Gate System**
- Depends on: ROS5-02, ROS5-03
- Create `realize_core/governance/gates.py` — configurable gates per action type
- Gate types: `send_email`, `publish_content`, `external_api`, `create_event`, `high_cost_llm`
- Hook into tool dispatcher: when gate triggers → create `approval_queue` record → pause workflow → emit activity event
- Configuration in `realize-os.yaml` under `governance.gates`
- Feature flag: `features.approval_gates: true`
- AC: Agent attempts to send email → approval created in queue → action blocked until approved

**ROS5-18: Approval Queue API**
- Depends on: ROS5-17
- `GET /api/approvals` — list pending approvals (filterable by venture, status)
- `POST /api/approvals/:id/approve` — execute the gated action with optional decision_note
- `POST /api/approvals/:id/reject` — cancel the action, log rejection, notify agent context
- Route module: `realize_api/routes/approvals.py`
- AC: Approve via API → gated action executes; reject → agent receives cancellation context

**ROS5-19: Approval Queue Page**
- Depends on: ROS5-18, ROS5-05
- List of pending approvals with: action type, agent, payload preview, time pending
- Approve/Reject buttons with optional note input
- Expiration countdown (visual urgency)
- AC: Navigate to approvals page, see pending items, approve one, see it execute and disappear

### Sprint 9: Agent Hierarchy (Week 12-13)
> **Goal:** Agents can be organized in a hierarchy and delegate work.

**ROS5-20: Agent Hierarchy Model**
- Depends on: ROS5-11
- Optional `reports_to` field in agent `.md` frontmatter
- `GET /api/ventures/:key/org-tree` — returns hierarchy structure
- Org tree derivable from agent definitions
- AC: Agent definitions with `reports_to` fields render as navigable tree in API response

**ROS5-21: Inter-Agent Delegation Skill Step**
- Depends on: ROS5-20
- New skill step type: `delegate` — routes to another agent with full context
- Example: orchestrator delegates to writer, writer delegates to reviewer
- Results flow back through the delegation chain
- AC: Skill with delegate steps executes across 3 agents, final result returned to originator

**ROS5-22: Org Chart Dashboard Component**
- Depends on: ROS5-20, ROS5-05
- Visual org tree with status indicators
- Click agent node to navigate to agent detail page
- AC: Org chart renders hierarchy from agent definitions on Venture Detail Page

### Sprint 10: Evolution Inbox (Week 14)
> **Goal:** Surface existing self-evolution system in the dashboard.

**ROS5-23: Evolution API**
- Depends on: ROS5-02
- `GET /api/evolution/suggestions` — read pending suggestions from evolution engine's file output
- `POST /api/evolution/suggestions/:id/approve` — apply suggestion (create skill file, update prompt)
- `POST /api/evolution/suggestions/:id/dismiss` — mark dismissed
- Route module: `realize_api/routes/evolution.py`
- AC: Evolution engine generates suggestion → appears in API; approve → skill file created

**ROS5-24: Evolution Inbox Page**
- Depends on: ROS5-23, ROS5-05
- List of suggestions: skill suggestions, prompt improvements, gap detections
- Preview of what would change (diff view for prompt changes, preview for new skills)
- Approve/Dismiss with one click
- AC: Navigate to evolution inbox, see suggestions, approve one, verify skill file created in FABRIC

### Sprint 11: Extensibility (Week 15-16)
> **Goal:** Plugin system and template portability.
> Two independent tracks.

**Track A — ROS5-25: Plugin Discovery & Loading**
- Depends on: ROS5-01
- Plugin directory convention: `plugins/<name>/plugin.yaml` + Python module
- Plugin manifest: name, version, type (tool/channel/integration), entry point
- Auto-discovery at startup, lifecycle hooks (on_load, on_unload)
- AC: Drop plugin in plugins/ directory → available at next restart

**Track A (cont.) — ROS5-26: Tool Plugin Interface**
- Depends on: ROS5-25
- Extend existing `BaseTool` with plugin registration
- Plugins declare capabilities and trigger keywords
- Router discovers plugin tools via registry
- AC: Custom tool plugin receives requests matching its keywords

**Track B — ROS5-27: Venture Export**
- Depends on: ROS5-01
- `python cli.py venture export --key my-biz --output my-biz.zip`
- Exports: FABRIC structure, agent definitions, skill definitions, config (sanitized — strips secrets)
- AC: Export creates zip; contents match venture structure minus sensitive data

**Track B (cont.) — ROS5-28: Venture Import**
- Depends on: ROS5-27
- `python cli.py venture import --file my-biz.zip --key imported-biz`
- Creates venture from package, scaffolds FABRIC, restores agents and skills
- AC: Import creates working venture; agents and skills functional

---

# Part 4: Project Context (BMAD MTH-40)

```yaml
project_name: "RealizeOS 5"
version: "5.0.0"
folder: "H:\\RealizeOS_V05"
type: software

tech_stack:
  backend_language: Python 3.11+
  backend_framework: FastAPI
  frontend_framework: React 19 + Vite 7 + TypeScript
  frontend_ui: Tailwind CSS + shadcn/ui
  database: SQLite (FTS5 + new operational tables)
  scheduler: APScheduler
  realtime: Server-Sent Events (SSE)
  hosting: Docker Compose / local

conventions:
  naming: snake_case (Python), camelCase (TypeScript), kebab-case (files)
  testing: pytest (backend), vitest (frontend)
  git_branching: feature branches off main
  commit_style: conventional commits (feat:, fix:, refactor:, docs:)
  code_style: ruff (Python), eslint+prettier (TypeScript)

architecture_decisions:
  - "Dashboard served as static build by FastAPI (single deployment)"
  - "SSE for real-time activity feed (not WebSocket)"
  - "SQLite for operational data (activity, agent states, approvals)"
  - "FABRIC remains file-based (not migrated to DB)"
  - "Existing base_handler instrumented with activity logging (non-breaking)"
  - "Agent status tracked in DB, agent definitions remain in .md files"

implementation_rules:
  - "Never break existing base_handler message flow"
  - "All new features behind feature flags in realize-os.yaml"
  - "Dashboard API endpoints under /api/ prefix"
  - "Activity logging is fire-and-forget (never block main flow)"
  - "All approval gates configurable (can be disabled)"

anti_patterns:
  - "Do not move FABRIC to database — file-based is a feature"
  - "Do not add WebSocket complexity — SSE is sufficient"
  - "Do not require dashboard for core functionality — CLI must keep working"
  - "Do not add PostgreSQL dependency — SQLite is sufficient for single-tenant"
  - "Do not copy Paperclip's fully-autonomous model — RealizeOS is human-centered"

bmad_framework:
  source: "H:\\BMAD"
  workflows_used:
    - "MTH-35: Planning (this plan document)"
    - "MTH-36: Architecture (Part 2 of this plan)"
    - "MTH-37: Dev Story Workflow (every story implementation)"
    - "MTH-38: Sprint Tracking (Part 5 of this plan)"
    - "MTH-40: Project Context (project-context.md in repo)"
    - "MTH-22: Code Review (self-review after each story)"
    - "MTH-23: Readiness Check (sprint boundary verification)"

codebase_origin:
  source: "H:\\realize-os\\RealizeOS-Full-V03"
  target: "H:\\RealizeOS_V05"
  relationship: "Full copy of existing codebase + new features built on top"
  previous_version_preserved: true
```

---

# Part 5: Sprint Tracking Structure (BMAD MTH-38)

```yaml
project: "RealizeOS 5"
folder: "H:\\RealizeOS_V05"
started: 2026-03-17
status: in_progress

sprints:
  - sprint: 1
    title: "Foundation"
    week: 1
    stories:
      - { id: ROS5-01, title: "Repository Bootstrap", depends_on: [], status: done }

  - sprint: 2
    title: "Parallel Foundation"
    week: 2
    tracks:
      A: "Backend (DB)"
      B: "Frontend (Shell)"
    stories:
      - { id: ROS5-02, title: "Database Schema & Migrations", track: A, depends_on: [ROS5-01], status: done }
      - { id: ROS5-05, title: "Dashboard Shell & Navigation", track: B, depends_on: [ROS5-01], status: done }

  - sprint: 3
    title: "Backend Instrumentation"
    week: 3
    tracks:
      A: "Activity Logging"
      B: "Agent Lifecycle"
    stories:
      - { id: ROS5-03, title: "Activity Event Logger", track: A, depends_on: [ROS5-02], status: done }
      - { id: ROS5-11, title: "Agent Status Model", track: B, depends_on: [ROS5-02], status: done }

  - sprint: 4
    title: "Backend APIs"
    week: 4
    tracks:
      A: "Activity API"
      B: "Dashboard API"
      C: "Venture API (waits for Sprint 3)"
    stories:
      - { id: ROS5-07, title: "Activity API & SSE Stream", track: A, depends_on: [ROS5-03], status: done }
      - { id: ROS5-04, title: "Dashboard API — Overview", track: B, depends_on: [ROS5-03], status: done }
      - { id: ROS5-10, title: "Venture API Endpoints", track: C, depends_on: [ROS5-03, ROS5-11], status: done }

  - sprint: 5
    title: "Core Dashboard Pages"
    weeks: "5-6"
    tracks:
      A: "Overview"
      B: "Activity"
      C: "Venture Detail"
    stories:
      - { id: ROS5-06, title: "Overview Page", track: A, depends_on: [ROS5-04, ROS5-05], status: done }
      - { id: ROS5-08, title: "Activity Page", track: B, depends_on: [ROS5-07, ROS5-05], status: done }
      - { id: ROS5-09, title: "Venture Detail Page", track: C, depends_on: [ROS5-10, ROS5-05], status: done }

  - sprint: 6
    title: "Agent Management"
    week: 7
    tracks:
      A: "Backend (Pause/Resume)"
      B: "Frontend (Agent Detail)"
    stories:
      - { id: ROS5-13, title: "Agent Pause/Resume API", track: A, depends_on: [ROS5-11], status: done }
      - { id: ROS5-12, title: "Agent Detail Page", track: B, depends_on: [ROS5-10, ROS5-11, ROS5-05], status: done }

  - sprint: 7
    title: "Scheduling"
    weeks: "8-9"
    note: "Sequential chain — each story depends on the previous"
    stories:
      - { id: ROS5-14, title: "Scheduler Service", depends_on: [ROS5-11, ROS5-13], status: done }
      - { id: ROS5-15, title: "Schedule Configuration", depends_on: [ROS5-14], status: done }
      - { id: ROS5-16, title: "Heartbeat Dashboard Indicators", depends_on: [ROS5-14, ROS5-12], status: done }

  - sprint: 8
    title: "Governance"
    weeks: "10-11"
    note: "Sequential chain: system → API → page"
    stories:
      - { id: ROS5-17, title: "Approval Gate System", depends_on: [ROS5-02, ROS5-03], status: done }
      - { id: ROS5-18, title: "Approval Queue API", depends_on: [ROS5-17], status: done }
      - { id: ROS5-19, title: "Approval Queue Page", depends_on: [ROS5-18, ROS5-05], status: done }

  - sprint: 9
    title: "Agent Hierarchy"
    weeks: "12-13"
    stories:
      - { id: ROS5-20, title: "Agent Hierarchy Model", depends_on: [ROS5-11], status: done }
      - { id: ROS5-21, title: "Inter-Agent Delegation Skill Step", depends_on: [ROS5-20], status: done }
      - { id: ROS5-22, title: "Org Chart Dashboard Component", depends_on: [ROS5-20, ROS5-05], status: done }

  - sprint: 10
    title: "Evolution Inbox"
    week: 14
    stories:
      - { id: ROS5-23, title: "Evolution API", depends_on: [ROS5-02], status: done }
      - { id: ROS5-24, title: "Evolution Inbox Page", depends_on: [ROS5-23, ROS5-05], status: done }

  - sprint: 11
    title: "Extensibility"
    weeks: "15-16"
    tracks:
      A: "Plugin System"
      B: "Template Portability"
    stories:
      - { id: ROS5-25, title: "Plugin Discovery & Loading", track: A, depends_on: [ROS5-01], status: done }
      - { id: ROS5-26, title: "Tool Plugin Interface", track: A, depends_on: [ROS5-25], status: done }
      - { id: ROS5-27, title: "Venture Export", track: B, depends_on: [ROS5-01], status: done }
      - { id: ROS5-28, title: "Venture Import", track: B, depends_on: [ROS5-27], status: done }
```

---

# Part 6: Verification Plan

## BMAD Per-Story Workflow (MTH-37)

Every story follows this exact cycle — no exceptions:

1. **Load Context** — Read project-context.md + story dependencies + relevant source files
2. **Plan Approach** — Identify files to create/modify, list changes, check for conflicts with parallel tracks
3. **Implement** — Write code following conventions in project-context.md
4. **Self-Review (MTH-22)** — Code review checklist: no regressions, feature flag gated, no hardcoded values, error handling, tests
5. **Verify** — Run acceptance criteria tests, verify dependent stories still pass
6. **Close** — Update sprint tracking YAML (Part 5), mark story `done`, commit with conventional commit message

**At sprint boundaries:** Run MTH-23 (Readiness Check) — verify all stories in the sprint pass, no regressions in existing functionality, milestone checkpoint passes.

## Milestone Checkpoints

After each sprint, verify the accumulated state before proceeding. This prevents compounding errors.

| After Sprint | Checkpoint | Command / Test |
|---|---|---|
| 1 | Backend starts, existing tests pass, React shell renders | `cd H:\RealizeOS_V05 && python cli.py serve` + `pnpm dev` |
| 2 | DB tables exist, dashboard shell shows navigation | `python -c "from realize_core.db.schema import ..."` + browser check |
| 3 | Chat message → 3+ activity events logged; agent status tracked | `curl -X POST .../api/chat` then query SQLite |
| 4 | All API endpoints return data | `curl /api/dashboard`, `/api/ventures`, `/api/ventures/:key/activity` |
| 5 | Three dashboard pages render real data | Visual check: Overview, Activity, Venture Detail |
| 6 | Pause/resume works end-to-end; Agent Detail page functional | Pause agent → send message → verify fallback → resume |
| 7 | Scheduled heartbeat fires and logs | Set 30s interval → wait → verify activity event logged |
| 8 | Approval gate blocks action until approved | Trigger email tool → check approval queue → approve → verify sent |
| 9 | Delegation chain executes across agents | Skill with delegate steps → multi-agent execution → result returned |
| 10 | Evolution suggestions visible and actionable | Generate suggestion → see in inbox → approve → skill file created |
| 11 | Plugin loads; venture exports/imports cleanly | Drop plugin → restart → verify active; export → import → verify functional |

## End-to-End Smoke Test (after Sprint 8+)
1. Start RealizeOS 5: `cd H:\RealizeOS_V05 && docker compose up`
2. Open dashboard at `http://localhost:8080`
3. See ventures with agents and skills
4. Send message via API → see activity in real-time SSE feed
5. Pause an agent → verify message routes to fallback
6. Set schedule on agent → verify heartbeat runs
7. Trigger email action → see approval in queue → approve → email sends
8. Check evolution inbox → approve suggestion → skill appears in venture

## Dependency Validation
Before starting any story, verify its dependencies are complete:
```python
# Example: Before starting ROS5-10 (Venture API), verify:
# - ROS5-03 (Activity Logger) is done: activity_events table has data
# - ROS5-11 (Agent Status) is done: agent_states table tracks status
```
