<p align="center">
  <img src="docs/assets/logo.png" alt="RealizeOS" width="200" />
</p>

<h1 align="center">RealizeOS V5</h1>

<p align="center">
  <strong>The AI operations system for your business.</strong><br/>
  Coordinated AI agents that understand your venture, remember your preferences,<br/>
  and execute multi-step workflows — not just another chatbot.
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

```bash
git clone https://github.com/SufZen/RealizeOS-5.git
cd RealizeOS-5
cp .env.example .env       # Add your API key(s)
docker compose up           # Dashboard at localhost:3000
```

> 📖 Full setup guide: **[QUICKSTART.md](QUICKSTART.md)**

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
- **Pipelines** — sequential execution with Dev-QA retry loops
- **7 handoff types** — standard, QA-pass, QA-fail, escalation, phase-gate, sprint, incident
- **Hot-reload** — filesystem-watched agent registry

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

### 🛠️ 24 Google Workspace Tools

| Service | Tools | Capabilities |
|---------|-------|-------------|
| **Gmail** | 8 | Search, read, send, draft, reply, forward, triage, label |
| **Calendar** | 4 | List, create, update, find free time |
| **Drive** | 9 | Search, list, read, create, append, upload, download, permissions, move |
| **Sheets** | 3 | Read, append, create |

### 📋 Business Templates

Pre-built configurations for common ventures:

`consulting` · `agency` · `portfolio` · `saas` · `ecommerce` · `accounting` · `coaching` · `freelance`

```bash
python cli.py init --template consulting
```

### 🛡️ Security & Governance

- JWT authentication with RBAC (owner, admin, user, guest)
- Prompt injection scanner (pattern + heuristic detection)
- Human-in-the-loop approval gates for consequential actions
- SQLite-backed audit logging with SSE streaming
- Secret redaction in error responses

## Architecture

```
User → Channel (API/Telegram/CLI) → Security → Base Handler
  → LLM Router (Flash/Sonnet/Opus) → Prompt Builder (FABRIC context)
  → Tool Execution → Extensions → Evolution Engine → Response
```

> 📖 Deep dive: **[docs/architecture.md](docs/architecture.md)**

## CLI

```bash
python cli.py init --template NAME           # Initialize from template
python cli.py serve [--port PORT] [--reload] # Start API + dashboard
python cli.py bot                            # Start Telegram bot
python cli.py status                         # Show system status
python cli.py index                          # Rebuild KB search index
python cli.py venture create --key KEY       # Create new venture
python cli.py venture list                   # List ventures
```

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
| GET | `/health` | Health check |

## Documentation

| Guide | Description |
|-------|-------------|
| [⚡ Quickstart](QUICKSTART.md) | Zero to running in 10 minutes |
| [🏗️ Architecture](docs/architecture.md) | FABRIC, message flow, modules |
| [📖 Getting Started](docs/getting-started.md) | First steps after setup |
| [🔧 Configuration](docs/configuration.md) | Customize your deployment |
| [🚀 Self-Hosting](docs/self-hosting-guide.md) | Production deployment |
| [✍️ Skill Authoring](docs/skill-authoring.md) | Create custom skills |
| [📡 API Reference](docs/api-reference.md) | REST API documentation |
| [🤝 Contributing](CONTRIBUTING.md) | Developer guide |

## Requirements

- **Python 3.11+**
- At least one LLM API key (Anthropic, Google, OpenAI, or Ollama)
- Docker (optional, for containerized deployment)
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
