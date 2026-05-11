<p align="center">
  <img src="docs/assets/logo.png" alt="RealizeOS" width="200" />
</p>

<h1 align="center">RealizeOS V5</h1>

<p align="center">
  <strong>The AI operations system for your business.</strong><br/>
  Coordinated AI agents that understand your venture, remember your preferences,<br/>
  and execute multi-step workflows — not just another chatbot.<br/><br/>
  <em>Now with built-in MCP server + first-class operator CLI.</em>
</p>

<p align="center">
  <a href="https://github.com/SufZen/RealizeOS-5/actions"><img src="https://github.com/SufZen/RealizeOS-5/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-BSL_1.1-blue.svg" alt="License: BSL 1.1"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB.svg" alt="Python 3.11+"></a>
  <a href="https://github.com/SufZen/RealizeOS-5/stargazers"><img src="https://img.shields.io/github/stars/SufZen/RealizeOS-5?style=social" alt="Stars"></a>
</p>

<p align="center">
  <a href="QUICKSTART.md">⚡ Quickstart</a> ·
  <a href="docs/architecture.md">🏗️ Architecture</a> ·
  <a href="#features">✨ Features</a> ·
  <a href="docs/mcp-server.md">🔌 MCP Server</a> ·
  <a href="docs/cli-reference.md">💻 CLI Reference</a> ·
  <a href="docs/self-hosting-guide.md">🚀 Self-Host</a> ·
  <a href="CONTRIBUTING.md">🤝 Contribute</a>
</p>

---

## What is RealizeOS?

RealizeOS is a **self-hosted AI operations system** that gives your business a coordinated team of AI agents. Unlike generic chatbots, RealizeOS agents:

- 🧠 **Know your venture** — identity, voice, audience, domain expertise
- 🔄 **Run multi-step workflows** — not just single-shot Q&A
- 🤖 **Route to the right model** — Flash for speed, Sonnet for content, Opus for strategy
- 🛡️ **Respect governance** — approval gates, audit logs, human-in-the-loop
- 📈 **Self-improve** — gap detection, skill suggestion, prompt refinement

## Quick Start

### From Source (recommended first install)

`ash
git clone https://github.com/SufZen/RealizeOS-5.git
cd RealizeOS-5
cp .env.example .env       # Add your API key(s)
docker compose up --build   # Dashboard at http://localhost:8080
`

> **No Docker?** Use the Python-native method below.

### pip (Python-native, no Docker)

`ash
pip install realize-os
realize-os init --template consulting
realize-os serve
# Dashboard at http://localhost:8080
`

> Requires **Python 3.11+**. Works on Windows, macOS, and Linux.

### Linux / macOS (one-liner)

`ash
curl -fsSL https://raw.githubusercontent.com/SufZen/RealizeOS-5/main/scripts/install.sh | bash
`

### Windows (PowerShell, one-liner)

`powershell
irm https://raw.githubusercontent.com/SufZen/RealizeOS-5/main/scripts/install.ps1 | iex
`

### NPX (scaffolds a new project)

`ash
npx @realize-os/cli init my-business
cd my-business
# Edit .env to add your API key(s)
npx @realize-os/cli start
# Dashboard at http://localhost:8080
`

> Requires **Node.js 18+** and **Docker**.

### Docker (standalone container)

`ash
docker run -d -p 8080:8080 -v realizeos-data:/app/data ghcr.io/sufzen/realizeos-5:latest
# Dashboard at http://localhost:8080
`

| Method | Requires | Best For |
|--------|----------|----------|
| **Source** | Git + Docker (or Python 3.11+) | Contributing, customization, first-time users |
| **pip** | Python 3.11+ | Python devs, local development without Docker |
| **curl/PS1** | bash/PowerShell + Docker | Server deployment, CI/CD scripting |
| **NPX** | Node.js 18+ & Docker | Quickest scaffolding of a new project |
| **Docker** | Docker | Isolated, reproducible, production-ready |

> 📖 Full setup guide: **[QUICKSTART.md](QUICKSTART.md)** · Self-hosting: **[docs/self-hosting-guide.md](docs/self-hosting-guide.md)**

## Features

### 🏗️ The FABRIC Knowledge System

Every venture's AI knowledge is organized into six layers:

| Layer | Purpose |
|-------|---------|
| **F**oundations | Venture identity, voice, core standards |
| **A**gents | AI team definitions and routing guide |
| **B**rain | Domain knowledge, market data, expertise |
| **R**outines | Skills, workflows, state maps, SOPs |
| **I**nsights | Memory: learning log, feedback, decisions |
| **C**reations | Output: deliverables, drafts, final assets |

### 🤖 Multi-LLM Routing

The engine classifies every task and selects the optimal model:

| Task Type | Model | Examples |
|-----------|-------|----------|
| Simple | Gemini Flash | Status checks, formatting, lookups |
| Content | Claude Sonnet | Writing, analysis, summarization |
| Complex | Claude Opus | Strategy, multi-step reasoning |

Providers auto-discovered at startup. Supports **Claude**, **Gemini**, **OpenAI**, and **Ollama** (local).

### 🔧 Agent System (V2)

- **Composable agents** with scope, inputs, outputs, guardrails, and tools
- **Pipelines** — sequential execution with Dev-QA retry loops and circular dependency detection
- **7 handoff types** — standard, QA-pass, QA-fail, escalation, phase-gate, sprint, incident
- **Hot-reload** — filesystem-watched agent registry
- **Tool gating** — per-agent allowlists/denylists for tool access

### 🧬 Agent Intelligence (V5)

- **Per-Agent Persona (SOUL)** — Each agent has persistent identity: role, personality, expertise, communication style, defined in YAML
- **Workspace Goal Injection** — Venture-level goals auto-injected into every agent session via `GOAL.md` or config
- **Session Startup Brief** — Auto-generated situational briefs at session start with pending tasks, recent activity, and open approvals
- **Brand Profile System** — Venture-level brand voice, tone, and guidelines injected into content-focused sessions
- **Per-Agent Tool Gating** — Agents only see tools for their role via `tools_allowlist` / `tools_denylist` in persona config

### 🤝 Coordination & Messaging (V5)

- **Operator Approval Primitive** — Agents pause and request human approval, credentials, or input (`request_decision`, `request_credential`, `request_input`)
- **Agent-to-Agent Messaging Bus** — Direct messaging (`agent:<slug>`), human notifications (`human:default`), channel broadcasts (`channel:<name>`), and offline queuing
- **Eval Harness** — YAML-based behavioral test suites with scoring (pattern matching, tool accuracy, custom dimensions)
- **Template Marketplace** — Install pre-built venture templates: `agency`, `saas`, `consulting` — each with agents, goals, brand profiles, and skills

### 🧩 Extension System

| Type | Purpose | Example |
|------|---------|---------|
| `tool` | New capabilities | Stripe, Twilio, custom APIs |
| `channel` | Communication | Slack, Discord, WhatsApp |
| `integration` | Backend sync | CRM, analytics |
| `hook` | Event reactions | Notifications, logging |

### 🛠️ Tool Ecosystem

| Category | Tools | Capabilities |
|----------|-------|-------------|
| **Gmail** | 8 | Search, read, send, draft, reply, forward, triage, label |
| **Calendar** | 4 | List, create, update, find free time |
| **Drive** | 9 | Search, list, read, create, append, upload, download, permissions, move |
| **Sheets** | 3 | Read, append, create |
| **Stripe** | Financial | Charges, subscriptions, invoices with safety guards |
| **Browser** | Web automation | Headless Chromium page interaction |
| **Web** | Search + fetch | Brave API search, page scraping with SSRF protection |
| **MCP** | Protocol | Connect to any MCP-compatible tool server |
| **MCP Server** | Integration | Expose RealizeOS as an MCP server for Claude Desktop, Cursor, n8n |
| **Messaging** | Agent bus | Agent-to-agent, human notifications, channel broadcasts |
| **Social** | Publishing | Social media content posting |
| **Telephony** | Voice | Twilio-powered voice/SMS |
| **PM** | Project mgmt | Task tracking, status reporting |
| **Docs** | Generation | Document and report generation |
| **Approval** | Governance | Human-in-the-loop approval workflows |

### 📋 Business Templates

Pre-built configurations for common ventures:

`consulting` · `agency` · `portfolio` · `saas` · `ecommerce` · `accounting` · `coaching` · `freelance`

```bash
realize-os init --template consulting
```

### 🔌 MCP Server (5.1.0+)

RealizeOS ships a **built-in MCP server** so any MCP-speaking agent can use it as a second brain:

- **24 tools** across 4 families: Chat & Status, KB Read, Ops, Admin
- **HTTP+SSE transport** — works with Claude Desktop, Cursor, n8n, cloud routines
- **Same auth** — Bearer JWT or API key, same roles and audit logs
- **Gated access** — KB, ops, and admin tools are independently toggleable

```bash
realize-os mcp serve --port 8080          # Start API + MCP together
realize-os mcp token --user owner         # Issue a bearer token
```

> 📖 Full details: **[docs/mcp-server.md](docs/mcp-server.md)**

### 🛡️ Security & Governance

- **5-layer security middleware**: Security headers → Audit logging → Rate limiting → Injection guard → JWT auth
- **JWT authentication** with HMAC-SHA256 tokens and refresh flow
- **RBAC** with 6 roles: owner, admin, operator, user, viewer, guest (+ custom YAML roles)
- **Prompt injection scanner** — pattern + heuristic + Unicode normalization defense
- **Human-in-the-loop** approval gates for consequential actions
- **Audit logging** — JSONL persistent logs with SSE streaming
- **Secret redaction** in error responses and logs
- **Built-in security scanner** — automated posture checks at startup

## Architecture

```
User → Channel (API/Telegram/WhatsApp/Webhooks/MCP)
  → Security (Headers → Audit → Rate Limit → Injection Guard → JWT)
  → Base Handler → LLM Router (Flash/Sonnet/Opus)
  → Prompt Builder (FABRIC context) → Tool Execution
  → Extensions → Governance → Evolution Engine → Response
```

> 📖 Deep dive: **[docs/architecture.md](docs/architecture.md)**

## Operator CLI (5.1.0+)

The `realize-os` CLI is a first-class operator interface. Both `realize-os` (pip-installed)
and `python cli.py` (source checkout) work identically.

```bash
# Deploy & manage
realize-os init --template consulting       # Initialize from template
realize-os serve [--port PORT] [--reload]   # Start API + dashboard
realize-os bot                               # Start Telegram bot
realize-os status                            # Show system status
realize-os doctor                            # Diagnose installation issues

# Talk to your instance
realize-os chat "What's the pipeline status?" --system arena
realize-os ask "summarize yesterday's emails"
realize-os repl --system realization-il      # Interactive REPL

# Knowledge base
realize-os kb search "investment thesis" --venture personal-investments
realize-os kb reindex

# Workflows, skills, evolution
realize-os workflow list
realize-os skill trigger daily-digest
realize-os evolution suggestions --status pending
realize-os evolution approve SUGGESTION_ID

# MCP server
realize-os mcp serve --allow-admin           # API + MCP on one process
realize-os mcp token --user owner            # Issue bearer token

# Multi-instance profiles
realize-os config profile add prod --endpoint https://my-vps:8080
realize-os --profile prod status

# Config management
realize-os config set mcp.enabled true
realize-os config show mcp
```

> 📖 Full command reference: **[docs/cli-reference.md](docs/cli-reference.md)**

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send message, get AI response |
| GET | `/api/systems` | List all systems |
| GET | `/api/systems/{key}` | System details |
| GET | `/api/systems/{key}/agents` | List agents |
| GET | `/api/systems/{key}/skills` | List skills |
| POST | `/api/systems/reload` | Hot-reload configuration |
| GET | `/api/activity/stream` | SSE activity feed |
| POST | `/api/auth/token` | Generate JWT access + refresh tokens |
| POST | `/api/auth/refresh` | Refresh an expired access token |
| `CRUD` | `/api/ventures/*` | Venture management |
| `CRUD` | `/api/ventures/{key}/agents/*` | Per-venture agent management |
| `CRUD` | `/api/ventures/{key}/kb/*` | Per-venture knowledge base |
| `CRUD` | `/api/workflows/*` | Workflow management |
| `CRUD` | `/api/approvals/*` | Approval request management |
| `CRUD` | `/api/extensions/*` | Extension management |
| `CRUD` | `/api/webhooks/*` | Webhook management |
| GET | `/api/settings/*` | System settings (LLM, security, tools, memory, etc.) |
| GET | `/api/security/scan` | Run security posture scan |
| GET | `/api/evolution/*` | Self-improvement suggestions |
| GET | `/api/devmode/*` | Developer mode status |
| GET | `/api/health` | Health check |
| GET | `/mcp/sse` | MCP server SSE endpoint (when enabled) |
| POST | `/mcp/messages/{session}` | MCP JSON-RPC messages |
| GET | `/mcp/health` | MCP server health |
| GET | `/status` | Detailed system status |

## Documentation

| Guide | Description |
|-------|-------------|
| [⚡ Quickstart](QUICKSTART.md) | Zero to running in 10 minutes |
| [🏗️ Architecture](docs/architecture.md) | FABRIC, message flow, modules |
| [💻 CLI Reference](docs/cli-reference.md) | Full operator CLI command tree |
| [🔌 MCP Server](docs/mcp-server.md) | Built-in MCP server: tools, security, integration |
| [🩺 Audit Playbook](docs/audit-playbook.md) | Risk-first audit workflow and session template |
| [📖 Getting Started](docs/getting-started.md) | First steps after setup |
| [🔧 Configuration](docs/configuration.md) | Customize your deployment |
| [🚀 Self-Hosting](docs/self-hosting-guide.md) | Production deployment |
| [✍️ Skill Authoring](docs/skill-authoring.md) | Create custom skills |
| [📡 API Reference](docs/api-reference.md) | REST + MCP API documentation |
| [📋 Upgrade from 5.0](docs/upgrade-from-v50.md) | Migration guide: 5.0.x → 5.1.0 |
| [🤝 Contributing](CONTRIBUTING.md) | Developer guide |

## Requirements

- **Python 3.11+** (3.12+ recommended)
- At least one LLM API key (Anthropic, Google, OpenAI, or Ollama)
- Docker 24.0+ (optional, for containerized deployment)
- Node.js 20+ (optional, for dashboard development)

## Community

- 🐛 [Report a Bug](https://github.com/SufZen/RealizeOS-5/issues/new?template=bug_report.md)
- 💡 [Request a Feature](https://github.com/SufZen/RealizeOS-5/issues/new?template=feature_request.md)
- 📖 [Read the Docs](docs/)
- ⭐ [Star the Repo](https://github.com/SufZen/RealizeOS-5)

## License

RealizeOS V5 is licensed under the [Business Source License 1.1](LICENSE).

**What this means:**
- ✅ Free to use, modify, and self-host
- ✅ Free for internal business operations
- ✅ Converts to Apache 2.0 on **March 26, 2030**
- ❌ Cannot offer as a hosted/managed service to third parties without a commercial license

For commercial licensing inquiries, contact [realizeos@realization.co.il](mailto:realizeos@realization.co.il).
