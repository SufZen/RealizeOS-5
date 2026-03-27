# Contributing to RealizeOS

Welcome! We're glad you're interested in contributing to RealizeOS V5.

## Table of Contents

- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Code Standards](#code-standards)
- [Project Structure](#project-structure)
- [Architecture Guidelines](#architecture-guidelines)
- [Pull Request Process](#pull-request-process)
- [Development Workflow (BMAD)](#development-workflow-bmad)

## Quick Start

```bash
git clone https://github.com/SufZen/RealizeOS-5.git
cd RealizeOS-5
python -m venv venv
venv\Scripts\activate     # Windows
# source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -m pytest tests/ -v --tb=short
```

## Development Setup

### Prerequisites

- **Python 3.11+** (3.12+ recommended)
- **Git**
- **Node.js 20+** (only if working on the dashboard)

### Install

1. **Fork and clone** the repository
2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   venv\Scripts\activate       # Windows
   source venv/bin/activate    # macOS/Linux
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
4. **Run tests**:
   ```bash
   python -m pytest tests/ -v --tb=short
   ```
5. **Run coverage locally**:
   ```bash
   python -m pytest tests/ -v --tb=short --cov=realize_core --cov=realize_api --cov-report=term-missing
   ```
6. **Optional — install Google Workspace tools**:
   ```bash
   pip install google-api-python-client google-auth-oauthlib
   ```
7. **Optional — install dashboard dependencies**:
   ```bash
   cd dashboard && pnpm install && cd ..
   ```

### Environment Variables

Copy `.env.example` to `.env` and add at least one LLM API key:

```bash
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY or GOOGLE_AI_API_KEY
```

## How to Contribute

### Report Bugs

Open an issue using the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md) with:

- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
- Relevant logs or error messages

### Request Features

Open an issue using the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md) with:

- Problem description
- Proposed solution
- Alternatives considered

### Add a New Tool

1. Create a module in `realize_core/tools/`
2. Define schemas with `ToolSchema` from `base_tool.py`
3. Implement `execute()` and `is_available()`
4. Register in `tool_registry.py`
5. Add tests in `tests/`

Reference: [Build Your First Tool](docs/dev-process/reference/build-your-first-tool.md)

### Add a New Extension

1. Create a directory in `extensions/` with an `extension.yaml` manifest
2. Implement the `BaseExtension` protocol (`on_load`, `on_unload`, `is_available`)
3. The extension loader will auto-discover it at startup

```yaml
# extensions/my-extension/extension.yaml
name: my-extension
version: "1.0.0"
type: tool          # tool | channel | integration | hook
entry_point: "extensions.my_extension.MyExtension"
description: "What this extension does"
```

### Add a New Channel

1. Create an adapter in `realize_core/channels/` following `base.py` pattern
2. Implement `start()`, `stop()`, `send_message()`, `format_instructions()`
3. Add channel config support in `config.py`
4. Add tests

Reference: [Build Your Own Channel](docs/dev-process/reference/build-your-own-channel.md)

### Add a New LLM Provider

1. Create a provider in `realize_core/llm/providers/` extending `BaseLLMProvider`
2. Implement `name`, `complete()`, `list_models()`, `is_available()`
3. Register in `registry.py:auto_register()`
4. Add tests

### Add a Skill

1. Create a YAML skill file in `R-routines/skills/`
2. Define system prompt, agent key, tools, and trigger keywords
3. Test via the API channel

Reference: [Skill Authoring Guide](docs/skill-authoring.md)

## Code Standards

### Python

- **Python 3.11+** with type hints on all public functions
- **pytest** for all tests
- **Docstrings** on all public functions and classes
- **Logging**: Use `logging.getLogger(__name__)` — **never** `print()`
- **No bare `except`**: Always catch specific exceptions
- **No unused imports**: CI will catch these
- **snake_case** for all Python identifiers
- **Async-over-sync**: Wrap blocking I/O with `asyncio.to_thread()`
- Follow existing patterns in the codebase

### Naming Conventions

| Thing | Convention | Example |
|-------|-----------|---------|
| Files | `snake_case.py` | `google_sheets.py` |
| Classes | `PascalCase` | `ExtensionRegistry` |
| Functions | `snake_case` | `get_tool_registry()` |
| Constants | `UPPER_SNAKE` | `GOOGLE_TOOL_SCHEMAS` |
| Enums | `PascalCase` class, `UPPER_SNAKE` members | `ExtensionType.TOOL` |

### Tests

- Place tests in `tests/` with `test_` prefix
- Use descriptive test names: `test_register_replaces_existing`
- Group tests by class: `class TestExtensionRegistry`
- Avoid external dependencies in unit tests (mock API calls)

## Project Structure

```
RealizeOS-5/
├── realize_core/                Core Python engine
│   ├── agents/                  V2 agent system (definitions, pipelines, handoffs, guardrails)
│   ├── skills/                  Skill detection and execution (v1 + v2 skills)
│   ├── tools/                   Tool SDK + implementations
│   │   ├── base_tool.py         BaseTool, ToolSchema, ToolResult
│   │   ├── tool_registry.py     ToolRegistry with auto-discovery
│   │   ├── google_workspace.py  Gmail, Calendar, Drive tools
│   │   ├── google_sheets.py     Sheets API tools
│   │   ├── stripe_tools.py      Financial tools (Stripe)
│   │   ├── browser.py           Headless Chromium browser
│   │   ├── web.py / web_tool.py Web search + fetch (SSRF-protected)
│   │   ├── mcp.py               MCP protocol connector
│   │   ├── messaging.py         Agent-to-agent messaging bus
│   │   ├── social.py            Social media tools
│   │   ├── telephony.py         Twilio voice/SMS
│   │   ├── approval.py          Human-in-the-loop approval tools
│   │   ├── gating.py            Per-agent tool access control
│   │   └── doc_generator.py     Document generation
│   ├── extensions/              Extension system (registry, cron, hooks)
│   ├── llm/                     Multi-provider LLM routing (Claude, Gemini, OpenAI, Ollama)
│   ├── prompt/                  Multi-layer prompt assembly from FABRIC knowledge base
│   ├── security/                JWT auth, RBAC, injection scanning, audit logging, scanner
│   ├── channels/                Channel adapters (API, Telegram, WhatsApp, Webhooks, Scheduler)
│   ├── storage/                 Pluggable storage providers (local filesystem, S3-compatible)
│   ├── memory/                  Persistent memory store and learning log
│   ├── kb/                      Knowledge base indexing (FTS5 + vector embeddings)
│   ├── db/                      SQLite database utilities + migration system
│   ├── governance/              Approval workflows and human-in-the-loop gates
│   ├── workflows/               Workflow engine and execution
│   ├── pipeline/                Pipeline builder and session management
│   ├── devmode/                 Developer mode (context gen, git safety, scaffolder)
│   ├── eval/                    Agent evaluation harness (YAML-based behavioral tests)
│   ├── evolution/               Self-improvement: gap detection, skill suggestion
│   ├── migration/               Data migration engine
│   ├── media/                   Media handling and processing
│   ├── ingestion/               Data ingestion pipelines
│   ├── scheduler/               Agent lifecycle management and heartbeat
│   ├── optimizer/               Experiment tracking
│   ├── utils/                   Shared utilities (rate limiter, etc.)
│   └── templates/               Template engine
├── realize_api/                 FastAPI REST API (32 route modules)
├── dashboard/                   React 19 + Vite 8 + TypeScript + Tailwind CSS 4
│                                + TanStack Query + React Router 7
├── realize-os-cli/              npm CLI package (@realize-os/cli)
├── templates/                   8 business templates
├── scripts/                     Installation scripts (install.sh, install.ps1, deploy.sh)
├── tests/                       Test suite
├── docs/                        Documentation
├── .github/                     CI/CD workflows + issue templates
└── README.md                    This file
```

## Architecture Guidelines

### Critical Rules

- **Never break existing functionality** — CLI, API, FABRIC must keep working
- **All new features behind feature flags** in `realize-os.yaml`
- **FABRIC stays file-based** — do not migrate to database
- **SSE only** — do not add WebSocket
- **SQLite only** — do not add PostgreSQL
- **Human-centered** — RealizeOS is NOT fully autonomous

### Key Patterns

- **Message Flow**: `Channel → Security Middleware → base_handler → session → skill → agent → LLM`
- **Auto-Discovery**: Agents from `A-agents/`, skills from `R-routines/skills/`, extensions from `extensions/`
- **Feature Flags**: Defined in `realize-os.yaml` under `features:`, accessed via `config.py:get_features()`
- **Security Stack**: Security headers → Audit → Rate limiting → Injection guard → JWT auth
- **Async-over-sync**: Blocking I/O wrapped with `asyncio.to_thread()`

## Pull Request Process

1. **Create a feature branch** from `main`
2. **Write tests** for all new functionality
3. **Ensure all tests pass**: `python -m pytest tests/ -v --tb=short`
4. **Update docs** if adding new features
5. **Use conventional commits**:
   - `feat:` — new feature
   - `fix:` — bug fix
   - `docs:` — documentation changes
   - `test:` — test changes
   - `refactor:` — code restructuring
   - `chore:` — maintenance tasks
6. **Submit a PR** with a clear description

## Development Workflow (BMAD)

Every story follows the BMAD MTH-37 workflow:

1. **Load Context** — Read relevant files and understand the scope
2. **Plan** — Outline approach before coding
3. **Implement** — Write code + tests
4. **Self-Review** (MTH-22):
   - No `print()` statements
   - No bare `except` blocks
   - No new dependencies without approval
   - All public APIs have docstrings
5. **Verify** — `python -m pytest tests/ -v --tb=short`
6. **Close** — Commit with conventional commit message

## License

By contributing, you agree that your contributions will be licensed under the [Business Source License 1.1](LICENSE), the same license as the project. This license converts to Apache 2.0 on March 26, 2030.
