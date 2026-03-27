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
│  Tool Execution  │  Google Workspace + Stripe + MCP
│                  │  + Browser + Web + Messaging + Approval
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
| `tools/` | Tool registry + implementations (Google Workspace, Stripe, web, browser, MCP, messaging, social, telephony, approval, PM, docs) |
| `skills/` | YAML-based skill detection and execution (v1 + v2) |
| `agents/` | V2 agent system — definitions, pipelines, handoffs, guardrails |
| `security/` | JWT authentication, RBAC (6 roles), injection scanning, audit logging, security scanner |
| `storage/` | Pluggable storage providers (local filesystem, S3-compatible) |
| `memory/` | Persistent memory store and learning log |
| `scheduler/` | Agent lifecycle management and heartbeat |
| `channels/` | Channel adapters (REST API, Telegram, WhatsApp, Webhooks, Scheduler) |
| `extensions/` | Extension registry, cron scheduler, event hooks |
| `kb/` | Knowledge base indexing (FTS5 + vector embeddings) |
| `evolution/` | Self-improvement: gap detection, skill suggestion |
| `db/` | SQLite database utilities + migration system |
| `governance/` | Approval workflows and human-in-the-loop gates |
| `workflows/` | Workflow engine and execution |
| `pipeline/` | Pipeline builder and session management |
| `devmode/` | Developer mode (context generation, git safety, scaffolder, health check) |
| `eval/` | Agent evaluation harness (YAML-based behavioral tests) |
| `migration/` | Data migration engine |
| `media/` | Media handling and processing |
| `ingestion/` | Data ingestion pipelines |
| `utils/` | Shared utilities (rate limiter, etc.) |

### `realize_api/` — FastAPI REST API

| Component | Purpose |
|-----------|---------|
| `main.py` | Application factory, CORS, lifespan |
| `routes/` | 32 route modules (chat, auth, ventures, agents, workflows, approvals, extensions, webhooks, settings, security, devmode, etc.) |
| `middleware/` | API key middleware |
| `security_middleware.py` | 5-layer security stack (SecurityHeaders, Audit, RateLimit, InjectionGuard, JWT) |
| `error_handlers.py` | Structured error responses with secret redaction |

### `dashboard/` — React Frontend

React 19 + Vite 8 + TypeScript + Tailwind CSS 4 dashboard providing:
- Real-time activity feed (SSE)
- Venture management (CRUD)
- Agent monitoring and configuration
- Chat interface
- Settings management (LLM, security, tools, storage, memory)
- State management with TanStack Query v5
- Client-side routing with React Router v7

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
Request → Security Headers → Audit Log → Rate Limiting
    → Injection Scanning → JWT Verification → RBAC Role Check
    → Request Processing → Response
```

- **Security Headers**: Content-Security-Policy, X-Frame-Options, etc. on all responses
- **JWT**: HMAC-SHA256 tokens with role claims, refresh flow, token revocation
- **RBAC**: 6 built-in roles (owner, admin, operator, user, viewer, guest) + custom YAML roles
- **Injection Scanner**: Pattern-based + heuristic + Unicode normalization defense
- **Audit Log**: JSONL persistent files with SSE streaming
- **Secret Redaction**: Automatic in error responses and logs
- **Security Scanner**: Automated posture checks at startup (API keys, JWT config, middleware, storage, DB permissions)

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
