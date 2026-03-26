# Project Context — RealizeOS V5

> AI agents read this file before every task. It defines the project's rules.

## Project Overview

- **Name:** RealizeOS V5
- **Description:** An AI operations system for multi-venture businesses, built on FABRIC architecture, orchestrating intelligent agents across geographic regions, business verticals, and operational workflows.
- **Primary language:** Python 3.12
- **Framework:** FastAPI (async)
- **Dashboard:** React 19 + Vite + TypeScript
- **Shared learnings source:** `H:\AutoBuild\sharedlearnings.md`

## Tech Stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.12 |
| Framework | FastAPI (async) |
| Database | SQLite (realize_data.db, kb_index.db) |
| Dashboard | React 19, Vite, TypeScript, Tailwind |
| Testing | pytest + pytest-asyncio |
| Linting | ruff |
| Type Checking | mypy |
| CI/CD | GitHub Actions |
| Containerization | Docker + Docker Compose |

## Code Conventions

### File Structure

```
realize_core/              # Core engine (Python)
  agent/                   # Agent loop, providers, persona
  prompt/                  # Prompt builder, context assembly
  tools/                   # Tool registry + individual tools
  skills/                  # Skill definitions + executor
  scheduler/               # Heartbeat, lifecycle, hierarchy
  security/                # JWT, RBAC, injection scanning, audit
  storage/                 # Storage providers (local, S3, sync)
  db/                      # Database utilities + migrations
  optimizer/               # Experiment engine, metrics
realize_api/               # FastAPI API layer
  routes/                  # API endpoints
  middleware/              # Security middleware chain
dashboard/                 # React/Vite frontend
  src/components/          # UI components
  src/pages/               # Page routes
ventures/                  # Venture configurations + templates
  _templates/              # Venture template library
tests/                     # Test suite
  integration/             # Integration tests
  load/                    # Load/stress tests
docs/                      # Documentation
```

### Naming Conventions

- **Files:** snake_case.py (Python), kebab-case.tsx (React)
- **Functions:** snake_case
- **Classes:** PascalCase
- **Constants:** UPPER_SNAKE_CASE
- **Variables:** snake_case (Python), camelCase (TypeScript)

### Import Ordering

stdlib → third-party → local, sorted alphabetically per group

### Documentation Style

Google-style docstrings for Python, JSDoc for TypeScript

## Architecture Decisions

1. All agents are defined as YAML skill files in `realize_core/skills/`
2. Security middleware chain must process every API request
3. Configuration via environment variables, never hardcoded
4. Storage abstraction — all file I/O through storage providers
5. Database access through the `db/` utility module with migration system
6. Prompts must use the template/builder system, never inline strings
7. Tool registry pattern — each tool is a Python class with schema discovery + action dispatch
8. Multi-provider LLM routing — never hardcode model names
9. Venture-centric data model — all business logic scoped to ventures
10. BSL 1.1 licensing — code is source-available with 4-year Apache 2.0 change date

## Anti-Patterns (NEVER DO)

1. Never use synchronous I/O in async endpoint handlers
2. Never import from `_internal` modules of third-party packages
3. Never catch generic `Exception` without re-raising or specific handling
4. Never hardcode model names — use the LLM routing system
5. Never bypass the security middleware
6. Never store secrets, API keys, or credentials in source code
7. Never write raw SQL outside the db/ module — use the query helpers
8. Never add tools without registering them in the tool registry
9. Never modify venture data without venture_id scoping

## Implementation Rules

1. Every public function must have type annotations
2. Every new feature must have unit tests
3. All database changes require a migration file in `realize_core/db/migrations/`
4. All API endpoints must go through the middleware chain
5. All new tools must follow the BaseTool pattern and register in tool_registry
6. Dashboard components must be accessible (ARIA labels, keyboard navigation)
7. New YAML schemas must include validation logic
8. Configuration must support both `.env` files and environment variables
