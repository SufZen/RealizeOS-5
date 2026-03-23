# RealizeOS V5

<p align="center">
  <strong>The AI operations system for your business.</strong><br/>
  Coordinated AI agents that understand your venture, remember your preferences,<br/>
  and execute multi-step workflows — not just another chatbot.
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#features">Features</a> ·
  <a href="docs/self-hosting-guide.md">Self-Hosting</a> ·
  <a href="docs/upgrade-from-v03.md">Upgrade from V03</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## What's New in V5

| Feature | Description |
|---------|-------------|
| **Multi-LLM Routing** | Automatic task classification → model selection across Claude, Gemini, OpenAI, and Ollama |
| **Visual Dashboard** | React 19 + Vite dashboard with real-time activity feed, venture management, and agent monitoring |
| **Agent Pipeline** | Composable V2 agent definitions with sequential pipelines and Dev-QA retry loops |
| **Extension System** | Unified registry for tools, channels, integrations, and hooks with auto-discovery |
| **24 Google Workspace Tools** | Gmail (8), Calendar (4), Drive (9), Sheets (3) — read/write with OAuth |
| **Cron Scheduler** | APScheduler-backed scheduled tasks as an extension |
| **Event Hooks** | Pub/sub for lifecycle events: `on_message`, `on_venture_change`, `on_agent_complete` |
| **Activity Logging** | SQLite-backed activity event log with SSE streaming |
| **Approval Gates** | Human-in-the-loop governance for consequential actions |

## Two Editions

### Lite (Obsidian + Claude Code) — $79

For operators who want AI assistance without servers or coding.

- Pre-structured knowledge base using the FABRIC system
- 4 agent templates (Orchestrator, Writer, Reviewer, Analyst)
- Venture voice and identity wizards (fill-in-the-blank)
- Skill workflows (YAML-defined pipelines)
- Works with Claude Code or Claude Desktop
- **Get started in 15 minutes**

### Full (Docker Self-Hosted) — $249

For technical users who want the complete engine.

- Multi-LLM routing with provider registry (Claude, Gemini, OpenAI, Ollama)
- Multi-layer dynamic prompt assembly from living knowledge base
- Hybrid KB search (FTS5 + vector embeddings)
- Multi-step skill executor (agent, tool, condition, human workflows)
- Creative pipelines with session management
- Tool integrations: Google Workspace (24 tools), web search, browser automation, MCP
- REST API + Telegram channels + React dashboard
- Self-evolution engine (gap detection, skill suggestion, prompt refinement)
- Extension system with auto-discovery, cron scheduling, and event hooks
- 8 system templates + CLI tooling (including venture management)
- **Deploy with one command:** `docker compose up`

## Quick Start

### Lite Edition

```bash
# 1. Download and unzip the Lite package

# 2. Open the folder as an Obsidian vault
#    Obsidian → "Open folder as vault" → select the unzipped folder

# 3. Follow the in-vault setup guide (setup-guide.md)
#    Fill in: venture identity, voice rules, agent tweaks (15 min)

# 4. Start working with Claude
#    Open Claude Code in the vault directory
#    Claude reads CLAUDE.md and becomes your AI team
```

### Full Edition (Windows One-Click Installer)

The easiest way to install and run RealizeOS on Windows is to use the automated wizard:
1. Download the [`Install-RealizeOS.bat`](https://github.com/SufZen/RealizeOS-5/blob/main/Install-RealizeOS.bat) file natively.
2. Double-click it. The wizard will securely install Python, set up the system, and place a shortcut on your Desktop!

### Full Edition (Manual/Mac/Linux)

```bash
# 1. Clone and install
git clone https://github.com/SufZen/RealizeOS-5.git
cd RealizeOS-5
pip install -r requirements.txt

# 2. Initialize from a template
python cli.py init --template consulting

# 3. Configure API keys
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY and/or GOOGLE_AI_API_KEY

# 4a. Run locally
python cli.py serve

# 4b. Or deploy with Docker
docker compose up
```

**Test it:**

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Help me plan Q2 strategy", "system_key": "consulting"}'
```

> For production deployment, see the [Self-Hosting Guide](docs/self-hosting-guide.md).

## Features

### The FABRIC Knowledge System

Every venture's knowledge base follows the FABRIC directory structure:

| Directory | Purpose |
|-----------|---------|
| **F**-foundations/ | Venture identity, voice rules, core standards |
| **A**-agents/ | Agent team definitions and routing guide |
| **B**-brain/ | Domain knowledge, market data, expertise |
| **R**-routines/ | Skills, workflows, state maps, SOPs |
| **I**-insights/ | Memory: learning log, feedback, decisions |
| **C**-creations/ | Output: deliverables, drafts, final assets |

### Multi-LLM Routing

The engine automatically selects the right model for each task:

| Task Type | Model Tier | Examples |
|-----------|------------|----------|
| Simple | Flash (Gemini) | Status checks, formatting, lookups |
| Content | Sonnet (Claude) | Writing, analysis, summarization |
| Complex | Opus (Claude) | Strategy, multi-step reasoning, code |

Providers are auto-discovered at startup based on installed SDKs and configured API keys.

### Agent System (V2)

V5 introduces composable agent definitions with:

- **Protocols**: `BaseAgent` with scope, inputs, outputs, guardrails, tools
- **Pipelines**: Sequential execution with Dev-QA retry loops
- **Handoffs**: 7 handoff types (standard, QA-pass, QA-fail, escalation, phase-gate, sprint, incident)
- **Hot-reload**: Agent registry with filesystem watching

### Extension System

Unified registry for extending RealizeOS:

| Type | Purpose | Example |
|------|---------|---------|
| `tool` | New tool capabilities | Stripe payments, Twilio SMS |
| `channel` | Communication channels | Slack, Discord, WhatsApp |
| `integration` | Backend integrations | CRM sync, analytics |
| `hook` | Event hooks | Notifications, logging |

Extensions are auto-discovered from `extensions/` directory, `realize-os.yaml`, and legacy `plugins/`.

### 24 Google Workspace Tools

| Service | Tools | Capabilities |
|---------|-------|-------------|
| **Gmail** | 8 | Search, read, send, draft, reply, forward, triage, label |
| **Calendar** | 4 | List events, create, update, find free time |
| **Drive** | 9 | Search, list, read, create doc, append doc, upload, download, permissions, move |
| **Sheets** | 3 | Read, append, create |

### Templates

Pre-built system configurations for common business types:

| Template | Best For |
|----------|---------|
| `consulting` | Solo consultants, advisory firms |
| `agency` | Creative/marketing agencies |
| `portfolio` | Multi-venture operators |
| `saas` | SaaS founders, product teams |
| `ecommerce` | Online stores, D2C ventures |
| `accounting` | Accountants, bookkeepers, tax advisors |
| `coaching` | Business/life coaches, course creators |
| `freelance` | Freelance developers, designers, writers |

```bash
python cli.py init --template agency
```

## Architecture

```
User Message
    │
    ▼
┌─────────────────────┐
│  Channel Layer       │  API / Telegram / CLI
└────────┬────────────┘
         │
    ▼
┌─────────────────────┐
│  Base Handler        │  Session → Skill → Agent routing
└────────┬────────────┘
         │
    ▼
┌─────────────────────┐
│  LLM Router          │  Task classification → model selection
│  Simple → Flash       │  Content → Sonnet  │  Complex → Opus
└────────┬────────────┘
         │
    ▼
┌─────────────────────┐
│  Prompt Builder       │  Multi-layer assembly from KB files
│  Identity → Venture   │  → Agent → RAG Context → Memory
│  → Session → Proactive│  → Channel Format
└────────┬────────────┘
         │
    ▼
┌─────────────────────────────┐
│  Tools (24 GWS + Web + MCP) │
└────────┬────────────────────┘
         │
    ▼
┌─────────────────────┐
│  Extensions          │  Hooks → Cron → Integrations
└────────┬────────────┘
         │
    ▼
┌─────────────────────┐
│  Evolution           │  Track → Detect gaps → Suggest skills
└─────────────────────┘
```

## CLI Commands

```bash
python cli.py init --template NAME           # Initialize from template
python cli.py serve [--port PORT] [--reload] # Start API server + dashboard
python cli.py bot                            # Start Telegram bot
python cli.py status                         # Show system status
python cli.py index                          # Rebuild KB search index
python cli.py venture create --key KEY       # Create new venture
python cli.py venture delete --key KEY       # Delete venture
python cli.py venture list                   # List ventures
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send message, get AI response |
| GET | `/api/systems` | List all systems |
| GET | `/api/systems/{key}` | System details |
| GET | `/api/systems/{key}/agents` | List agents |
| GET | `/api/systems/{key}/skills` | List skills |
| POST | `/api/systems/reload` | Hot-reload config |
| GET | `/api/activity/stream` | SSE activity feed |
| GET | `/health` | Health check |
| GET | `/status` | Detailed status |

## Project Structure

```
RealizeOS-5/
├── cli.py                       CLI entry point
├── realize-os.yaml              System configuration
├── realize_core/                Python engine
│   ├── base_handler.py          Message processing pipeline
│   ├── config.py                Config loader
│   ├── agents/                  V2 agent system (base, schema, loader, registry, pipeline)
│   ├── skills/                  Skill detection and execution
│   ├── llm/                     LLM abstraction + multi-provider routing
│   ├── tools/                   Tool SDK + 24 Google Workspace tools
│   ├── extensions/              Extension registry, loader, cron, hooks
│   ├── channels/                Channel adapters (API, Telegram)
│   ├── evolution/               Self-improvement engine
│   ├── prompt/                  Multi-layer prompt assembly
│   ├── kb/                      Knowledge base indexing and search
│   ├── memory/                  Conversation history
│   ├── pipeline/                Creative sessions
│   ├── security/                RBAC, audit, vault
│   ├── activity/                Activity event logging
│   ├── governance/              Approval gates
│   └── scheduler/               Agent lifecycle scheduling
├── realize_api/                 FastAPI REST API
├── dashboard/                   React 19 + Vite + TypeScript dashboard
├── realize-os-cli/              npm CLI package
├── templates/                   8 business templates
├── tests/                       Test suite (pytest)
└── docs/                        Documentation
```

## Documentation

- [Getting Started](docs/getting-started.md)
- [Core Concepts](docs/concepts.md)
- [Configuration Guide](docs/configuration.md)
- [Self-Hosting Guide](docs/self-hosting-guide.md)
- [Upgrade from V03](docs/upgrade-from-v03.md)
- [Lite Guide](docs/lite-guide.md)
- [Full Guide](docs/full-guide.md)
- [Skill Authoring Guide](docs/skill-authoring.md)
- [API Reference](docs/api-reference.md)
- [Contributing](CONTRIBUTING.md)

## Requirements

- **Python 3.11+**
- At least one LLM API key (Anthropic or Google)
- Docker (optional, for containerized deployment)
- Node.js 20+ (optional, for dashboard development)

## License

Core engine: MIT License
