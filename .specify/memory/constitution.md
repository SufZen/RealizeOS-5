# RealizeOS Constitution

## Core Principles

### I. Heart-First Architecture
The kernel is the three things you'd never want to throw away: **the FABRIC knowledge graph, the event log, and the identity/policy layer**. Agents, models, workflows, channels, and even the dashboard become adapters around that core. The Heart is yours, never replaced.

### II. Local-First Sovereignty
User permanently owns their data; portability is literal — your knowledge is markdown in a git repo. Local or self-hosted only (not SaaS). BSL 1.1 license enforces this commercially. Audio never leaves device by default. Every provider is tagged as `local` / `self-hosted` / `third-party-cloud`. No telemetry without explicit opt-in.

### III. Runtime Plurality
Multiple agent runtimes coexist as peers (Claude Code CLI, Codex CLI, Gemini CLI, Hermes, internal agents, and more). Each satisfies the Runtime Adapter Contract. No runtime is privileged above any other. Hot-swappable via the extension system.

### IV. FABRIC as Source of Truth
Six layers per venture (Foundations, Agents, Brain, Routines, Insights, Creations), filesystem-based, git-versioned. SQLite tables are derived projections — blow away the DB, rebuild from FABRIC. Content is markdown with YAML frontmatter and optional semantic XML tags.

### V. Trust Is Earned, Not Assumed
The Dreaming subsystem starts conservative and expands autonomy based on observed approval patterns. Per-category trust policies. Quarantine branches. Hard deny-lists for critical paths. Pause button with one-command revert. Proposals are git commits reviewable in the Dream Inbox.

### VI. Spec-Driven Development
Every feature begins with a specification (in `.specify/specs/`). The constitution is the project's north star. Implementations are validated against specs. Cross-artifact consistency is checked automatically. Tasks are generated from plans, not invented ad hoc.

### VII. Contract Stability
Six versioned contracts define the boundaries between layers:
1. Runtime Adapter Contract
2. Semantic Tag Vocabulary
3. FABRIC Entity Schemas
4. Tool Protocol
5. Channel Protocol
6. Workflow Protocol

Breaking changes require a MAJOR semver bump, migration path, and explicit ADR.

## Architecture

The biological metaphor structures the system into six layers:

| Layer | Role | Replaceable? |
|---|---|---|
| **Skin** | User-facing surfaces (Workspace UI, Mobile, Knowledge Map) | Yes — multiple skins on same Heart |
| **Senses** | Channel adapters (REST, MCP, Telegram, WhatsApp, Voice, CLI, Email) | Yes |
| **Spine** | Mission Engine + Smart Kanban Router (goal → plan → execute) | No (core logic) |
| **Heart** | FABRIC, Synapse, Event Log, SOUL, Identity & Policy | **No — this is yours forever** |
| **Limbs** | Runtime adapters, LLM router, MCP tool registry, extensions | Yes — each adapter is hot-swappable |
| **Dreaming** | Self-evolution (Reflex, Curator, Synthesis, Genesis) + Trust Policy | Yes (can be disabled per-venture) |

Full architectural reference: `docs/v5.5.0/realizeos-v5.5.0-master-design.md`

## Technical Stack

- **Python ≥ 3.11** — Backend (realize_core, realize_api)
- **TypeScript / React 19 / Vite 8 / Tailwind 4** — Dashboard
- **TypeScript / Node** — CLI (`@realize-os/cli`)
- **FastAPI** — REST API layer
- **SQLite + sqlite-vec** — Synapse derived projections
- **Git (pygit2)** — FABRIC versioning
- **Docker** — Containerized deployment

## Development Workflow

1. **Conventional Commits** — enforced by commitlint
2. **Pre-commit hooks** — ruff, format, commitlint
3. **CI gates** — lint, test, security, Docker build, dashboard, CLI
4. **PR template** — type, spec reference, contract impact, license compatibility
5. **Branch strategy** — `main` (protected), `feature/*`, `fix/*`, `chore/*`, `docs/*`, `spec/*`, `dream/*`

## Governance

- The constitution supersedes all other development guidance
- Amendments require: documentation, review, migration plan
- Core principle changes require explicit ADR (Architecture Decision Record)
- Contract changes require MAJOR semver bump
- All dependencies must be MIT / Apache-2.0 / BSD / ISC / PostgreSQL / MPL-2.0 compatible (exceptions documented in `docs/license-exceptions.md`)

**Version**: 1.0.0 | **Ratified**: 2026-05-24 | **Last Amended**: 2026-05-24
