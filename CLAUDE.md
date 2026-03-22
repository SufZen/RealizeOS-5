# CLAUDE.md — RealizeOS 5 (Development)

This is the RealizeOS 5 codebase — the next production-level version of the AI operations engine. It contains the full existing engine (copied from V03) plus new features being built on top: visual dashboard, activity logging, agent lifecycle, governance, scheduling, and more.

**Master plan:** `docs/dev-process/plans/realizeos-5-improvement-plan.md` — contains PRD, architecture, all 28 stories, dependency graph, and sprint tracking.

**Project conventions:** `project-context.md` at repo root (BMAD MTH-40).

## Architecture Overview

```
realize-os/
├── cli.py                    CLI entry point (init, serve, bot, status, venture)
├── realize-os.yaml           User's system configuration
├── project-context.md        BMAD project conventions (MTH-40)
├── realize_core/             Python engine
│   ├── base_handler.py       Message processing pipeline
│   ├── config.py             Config loader (YAML → dicts, feature flags)
│   ├── scaffold.py           Venture scaffolding (create/delete)
│   ├── prompt/
│   │   └── builder.py        Multi-layer prompt assembly (12 layers)
│   ├── llm/
│   │   ├── router.py         Task classification → model selection
│   │   ├── registry.py       Provider registry (auto-discovers available LLMs)
│   │   ├── base_provider.py  Abstract provider interface
│   │   ├── providers/        Claude, Gemini, OpenAI, Ollama adapters
│   │   ├── claude_client.py  Claude API client (direct, legacy)
│   │   └── gemini_client.py  Gemini API client (direct, legacy)
│   ├── memory/               Conversation history management
│   ├── pipeline/             Creative sessions (briefing → drafting → review)
│   ├── skills/               Skill detection and execution (v1 + v2)
│   ├── kb/                   Knowledge base indexing and search
│   ├── tools/                External tools (Google, web, browser, MCP)
│   ├── channels/             Channel adapters (API, Telegram)
│   ├── evolution/            Self-improvement (gap detection, skill suggestion)
│   ├── activity/             [NEW] Activity event logging and querying
│   ├── governance/           [NEW] Approval gates and enforcement
│   ├── scheduler/            [NEW] Agent lifecycle and heartbeat scheduling
│   └── db/                   [NEW] SQLite schema and migrations
├── realize_api/              FastAPI REST API
│   └── routes/               Route modules (chat, health, systems, dashboard, activity, etc.)
├── dashboard/                [NEW] React 19 + Vite + TypeScript + Tailwind + shadcn/ui
│   ├── src/
│   │   ├── components/       Shared UI components
│   │   ├── pages/            Page components (Overview, Ventures, Activity, etc.)
│   │   ├── hooks/            Custom React hooks
│   │   └── lib/              Utilities (cn(), API client)
│   └── package.json
├── static/                   [BUILD OUTPUT] Dashboard production build (served by FastAPI)
├── realize_lite/             Embedded Lite package (scaffold source for cli.py init)
├── templates/                8 business templates
├── tests/                    Test suite (pytest)
└── docs/                     Documentation + improvement plan
```

## Key Patterns

### Message Flow
`Channel → base_handler.process_message() → session check → skill check → agent routing → LLM`

### Auto-Discovery
- **Agents**: Drop `.md` files in `A-agents/` → `config.py:_discover_agents()` finds them
- **Skills**: Drop `.yaml` files in `R-routines/skills/` → `skills/detector.py` loads them
- **Ventures**: `cli.py venture create` scaffolds FABRIC dirs → immediately available

### Feature Flags
Defined in `realize-os.yaml` under `features:`, accessed via `config.py:get_features()`:
- `review_pipeline` — auto-route to reviewer agent
- `auto_memory` — log learnings after interactions
- `proactive_mode` — include proactive layer in prompts
- `cross_system` — share context across all ventures
- `activity_log` — [NEW] log activity events to SQLite
- `agent_lifecycle` — [NEW] track agent status (idle/running/paused/error)
- `heartbeats` — [NEW] scheduled agent runs
- `approval_gates` — [NEW] human approval on consequential actions

### Multi-LLM Routing
`router.py:classify_task()` → simple/content/complex → model selection via `ProviderRegistry`

The engine supports multiple LLM providers (Claude, Gemini, OpenAI, Ollama). Providers are auto-discovered at startup based on installed SDKs and configured API keys.

## Dashboard (NEW in V5)

**Stack:** React 19 + Vite 8 + TypeScript + Tailwind CSS v4 + shadcn/ui + Lucide icons

**Dev mode:** `cd dashboard && pnpm dev` (port 5173, proxies `/api/*` to FastAPI on 8080)

**Production:** `cd dashboard && pnpm build` → outputs to `static/` → served by FastAPI `StaticFiles`

**Brand:** Dark theme (#0a0a0f), yellow accent (#ffcc00), Poppins font

**Pages:** Overview, Ventures, Venture Detail, Agent Detail, Activity, Evolution Inbox, Approvals, Settings

**Real-time:** SSE stream at `/api/activity/stream` for live activity feed

## CLI Commands

```bash
python cli.py init --template NAME           # Initialize from template
python cli.py serve [--port PORT] [--reload] # Start API server (+ serves dashboard)
python cli.py bot                            # Start Telegram bot
python cli.py status                         # Show system status
python cli.py index                          # Rebuild KB search index
python cli.py venture create --key KEY       # Create new venture
python cli.py venture delete --key KEY       # Delete venture
python cli.py venture list                   # List ventures
```

## Development Process (BMAD)

Every story follows MTH-37: Load Context → Plan → Implement → Self-Review (MTH-22) → Verify → Close.

- **Plan:** `docs/dev-process/plans/realizeos-5-improvement-plan.md`
- **Conventions:** `project-context.md`
- **BMAD workflows:** `H:\BMAD\workflows\`

## Critical Rules

- **Never break existing functionality** — CLI, API, FABRIC must keep working
- **All new features behind feature flags** in `realize-os.yaml`
- **Follow the dependency graph** — never start a story before its deps are done
- **FABRIC stays file-based** — do not migrate to database
- **SSE only** — do not add WebSocket
- **SQLite only** — do not add PostgreSQL
- **Human-centered** — RealizeOS is NOT fully autonomous

## Extending the System

### Adding a new tool
1. Create module in `realize_core/tools/`
2. Register in the tool dispatcher
3. Add task classification keywords in `llm/router.py`

### Adding a new channel
1. Create adapter in `realize_core/channels/` following `base.py` pattern
2. Add channel config support in `config.py`
3. Add CLI command if needed

### Adding a new LLM provider
1. Create provider in `realize_core/llm/providers/` extending `BaseLLMProvider`
2. Implement `name`, `complete()`, `list_models()`, `is_available()`
3. Register in `registry.py:auto_register()`

### Adding a new dashboard page

1. Create page component in `dashboard/src/pages/`
2. Add route in `dashboard/src/App.tsx`
3. Add nav item to sidebar if it's a top-level page
4. Create corresponding API route module in `realize_api/routes/`
