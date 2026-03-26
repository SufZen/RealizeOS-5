# RealizeOS V5 — Architecture

> How the system works, from message to output.

## Overview

RealizeOS is an AI operations system that orchestrates multiple LLM-powered agents across business ventures. Each venture has its own knowledge base, agent team, and workflows — all structured using the **FABRIC** system.

## The FABRIC Knowledge System

Every venture's knowledge base follows the FABRIC directory structure:

```
systems/<venture-key>/
├── F-foundations/          Identity, voice, standards
│   ├── venture-identity.md
│   └── venture-voice.md
├── A-agents/               Agent team definitions
│   ├── _README.md          Routing guide
│   ├── orchestrator.md
│   ├── writer.md
│   └── analyst.md
├── B-brain/                Domain knowledge, expertise
├── R-routines/             Skills, workflows, SOPs
│   ├── skills/
│   └── state-map.md
├── I-insights/             Memory: logs, feedback, decisions
└── C-creations/            Output: deliverables, drafts, assets
```

| Layer | Purpose | Examples |
|-------|---------|---------|
| **F**oundations | Who you are | Brand voice, identity, target audience |
| **A**gents | Who does the work | Orchestrator, Writer, Reviewer, Analyst |
| **B**rain | What you know | Market data, competitor analysis, expertise |
| **R**outines | How you work | Content workflows, review pipelines, SOPs |
| **I**nsights | What you've learned | Decision log, feedback, performance notes |
| **C**reations | What you've built | Blog posts, proposals, reports, code |

## Message Flow

```
User Message
    │
    ▼
┌──────────────────┐
│  Channel Layer   │  REST API / Telegram / CLI
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Security Layer  │  JWT auth → RBAC → Injection scanner → Audit log
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Base Handler    │  Session management → Skill detection → Agent routing
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  LLM Router      │  Task classification → Model selection
│                  │  Simple → Gemini Flash
│                  │  Content → Claude Sonnet
│                  │  Complex → Claude Opus
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Prompt Builder  │  Multi-layer context assembly:
│                  │  Identity → Venture → Agent → RAG
│                  │  → Memory → Session → Proactive
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Tool Execution  │  24 Google Workspace + Web Search
│                  │  + Browser + MCP + Custom tools
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Extensions      │  Hooks → Cron → Integrations
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Evolution       │  Gap detection → Skill suggestion
│                  │  → Prompt refinement
└──────────────────┘
```

## Core Modules

### `realize_core/` — Python Engine

| Module | Purpose |
|--------|---------|
| `config.py` | YAML config loader with env var interpolation |
| `base_handler.py` | Message processing pipeline |
| `llm/` | Multi-provider LLM routing (Claude, Gemini, OpenAI, Ollama) |
| `prompt/` | Multi-layer prompt assembly from FABRIC knowledge base |
| `tools/` | Tool registry + implementations (Google Workspace, web, browser) |
| `skills/` | YAML-based skill detection and execution |
| `agents/` | V2 agent system — definitions, pipelines, handoffs |
| `security/` | JWT authentication, RBAC roles, injection scanning, audit logging |
| `storage/` | Pluggable storage providers (local filesystem, S3-compatible) |
| `scheduler/` | Agent lifecycle management and heartbeat |
| `channels/` | Channel adapters (REST API, Telegram, WhatsApp) |
| `extensions/` | Extension registry, cron scheduler, event hooks |
| `kb/` | Knowledge base indexing (FTS5 + vector embeddings) |
| `evolution/` | Self-improvement: gap detection, skill suggestion |
| `db/` | SQLite database utilities + migration system |

### `realize_api/` — FastAPI REST API

| Component | Purpose |
|-----------|---------|
| `main.py` | Application factory, CORS, lifespan |
| `routes/` | API endpoints (chat, systems, activity, setup, storage) |
| `middleware/` | Security middleware chain (JWT → RBAC → rate limiting) |
| `error_handlers.py` | Structured error responses with secret redaction |

### `dashboard/` — React Frontend

React 19 + Vite + TypeScript + Tailwind CSS dashboard providing:
- Real-time activity feed (SSE)
- Venture management
- Agent monitoring
- Chat interface

## Multi-LLM Routing

The LLM router classifies tasks and selects the optimal model:

| Task Type | Model Tier | Use Cases |
|-----------|-----------|-----------|
| Simple | Flash (Gemini) | Status checks, formatting, lookups |
| Content | Sonnet (Claude) | Writing, analysis, summarization |
| Complex | Opus (Claude) | Strategy, multi-step reasoning |

Providers are auto-discovered at startup from installed SDKs and configured API keys.

## Security Architecture

```
Request → JWT Verification → RBAC Role Check → Rate Limiting
    → Injection Scanning → Request Processing → Audit Logging
```

- **JWT**: HMAC-SHA256 tokens with role claims
- **RBAC**: YAML-defined roles (owner, admin, user, guest)
- **Injection Scanner**: Pattern-based + heuristic prompt injection detection
- **Audit Log**: SQLite-backed activity log with SSE streaming
- **Secret Redaction**: Automatic in error responses and logs

## Database

SQLite databases (no external database required):
- `realize_data.db` — Activity log, sessions, approval requests
- `kb_index.db` — Knowledge base full-text search index

Migration system in `realize_core/db/migrations/` handles schema evolution.

## Extension System

```yaml
# extensions/my-extension/extension.yaml
name: my-extension
version: "1.0.0"
type: tool          # tool | channel | integration | hook
entry_point: "extensions.my_extension.MyExtension"
```

Extensions are auto-discovered from:
1. `extensions/` directory
2. `realize-os.yaml` config
3. Legacy `plugins/` directory

## Deployment

- **Development**: `python cli.py serve` or `docker compose up`
- **Production**: `docker compose -f docker-compose.prod.yml up -d`
- See [Self-Hosting Guide](self-hosting-guide.md) for production configuration
