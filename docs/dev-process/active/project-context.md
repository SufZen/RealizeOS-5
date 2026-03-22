# RealizeOS — Project Context

> This is the project "constitution". Every session must read this first.
> Last updated: 2026-03-10

## What Is RealizeOS

RealizeOS is an **AI operations platform** that ships a core intelligence engine and lets users build their own multi-venture AI assistant on top of it. It exists in two tiers:

- **Lite** — Local-first, Obsidian vault + Claude Code/Desktop. For non-technical solo entrepreneurs.
- **Full** — Server-based, Docker + FastAPI + multi-channel gateway. For technical users, agencies, dev teams.

## Competitive Position

| | OpenClaw | RealizeOS |
|---|---|---|
| **Pitch** | "AI on every device and channel" | "AI that thinks for your business" |
| **Strength** | 24+ channels, native apps | Multi-entity identity, smart routing, creative pipelines, self-evolution |
| **Target** | Power users wanting broad reach | Entrepreneurs/agencies managing multiple brands |

**We compete on intelligence depth, not channel breadth.**

## Core Engine Pillars (What Ships)

| # | Pillar | Description |
|---|---|---|
| P1 | Multi-Entity Identity | N business entities via YAML, each with distinct brand voice, agents, KB |
| P2 | 7-Layer Prompt Engine | Identity → Brand → Agent → Context → Memory → Session → Proactive |
| P3 | Smart LLM Router | Task classification → cost-optimal model, provider-agnostic, multi-modal |
| P4 | Creative Pipeline | Multi-agent sessions with gatekeeper review |
| P5 | Self-Evolution | Gap detection → skill suggestion → prompt refinement, with human approval |
| P6 | Hybrid KB/RAG | FTS5 + vector search over markdown/Obsidian knowledge base |
| P7 | YAML Skills | v1/v2 multi-step execution with hot-reload |

## Architecture

```
realize-os/
  realize_core/        ← Core intelligence engine (pillars P1-P7)
  realize_api/         ← FastAPI server (Full tier only)
  realize_lite/        ← Obsidian vault + CLAUDE.md (Lite tier)
  channels/            ← Channel adapters
  docs/                ← Documentation + dev-process/
  tests/               ← Test suite
  templates/           ← Onboarding templates (SaaS, Agency, Coaching, etc.)
```

## Origin

RealizeOS was developed from `asaf-kb-workspace` (a personal Telegram-based AI system). The workspace remains as a playground and test incubator. Features flow:

```
Prototype in asaf-kb-workspace → Validate daily → Generalize into realize-os
```

## Tech Stack

- **Language:** Python 3.11+
- **API:** FastAPI
- **LLM:** Multi-provider (Anthropic, Google, OpenAI, DeepSeek, Grok, Ollama)
- **KB:** SQLite (FTS5) + vector embeddings
- **Deployment:** Docker Compose
- **Frontend:** Next.js (realizeos-site)
- **Testing:** pytest
- **CI/CD:** GitHub Actions (planned)
- **Pre-commit:** gitleaks (secret scanning)

## Conventions

- **Naming:** snake_case for Python, camelCase for JS/TS
- **Testing:** pytest for all backend tests, `tests/` directory
- **Git branching:** main + feature branches
- **Commit style:** conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`)
- **Code style:** PEP 8, type hints on all public functions
- **Config:** YAML-based configuration (`realize-os.yaml`), env var interpolation via `${VAR}`
- **Logging:** `logging.getLogger(__name__)` — structured logger, never `print()`
- **Docstrings:** Google-style docstrings on all public functions

## Implementation Rules

- All secrets via environment variables, never hardcoded
- Every endpoint has input validation
- YAML for all configuration (systems, skills, routing, tools)
- Feature flags via `.env` (e.g., `BROWSER_ENABLED`, `MCP_ENABLED`)
- Provider interfaces first — concrete implementations behind `Base*` abstract classes
- One class per file for major components
- Tests for every new module — no untested code in core/

## Anti-Patterns (never do these)

- Never use `print()` for logging — use `logging` module
- Never use wildcard imports (`from x import *`)
- Don't catch generic `Exception` without re-raising
- No hardcoded API keys, tokens, or secrets anywhere
- No inline SQL — use parameterized queries
- Don't put business logic in API route handlers — delegate to core/
- Never commit `.env` files (gitleaks pre-commit hook enforces this)

## Key Design Decisions

- See `decisions/` for Architecture Decision Records
- ADR-001: Platform strategy — ship intelligence engine, not feature clones
- ADR-002: Lite/Full tier split — two runtime models, shared YAML config format

## Development Framework

This project uses the **BMAD-inspired development framework** for structured AI-driven development.

- **Framework location:** `D:\Antigravity\BMAD`
- **Workflow:** Plan (MTH-35) → Architect (MTH-36) → Build (MTH-37) → Review (MTH-22)
- **Sprint tracking:** MTH-38 with `sprint-status.yaml`
- **Quality gates:** MTH-23 Readiness Check before first story, MTH-22 Code Review after each story

## Development Plan

- See `plans/2026-03-realizeos-development-plan.md` for the full 13-phase roadmap
