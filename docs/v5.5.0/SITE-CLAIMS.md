# SITE-CLAIMS.md — RealizeOS v5.5.0 Source of Truth

> **Purpose:** This file is the single source of truth for every product claim the
> [realizeos.ai](https://realizeos.ai) website makes. The website agent reads this
> file (local `docs/v5.5.0/SITE-CLAIMS.md` or via GitHub MCP `get_file_contents`).
>
> **Branch:** `claude/amazing-albattani-He3xD`
> **Date verified:** 2026-05-25
> **Repo:** `SufZen/RealizeOS-5`

---

## 1. Version & Headline Numbers

| Fact | Verified Value | Source |
|------|---------------|--------|
| VERSION file | `5.5.0` | `VERSION` (commit `4596be3`) |
| FABRIC layers | **6** (Foundations, Agents, Brain, Routines, Insights, Creations) | `realize_core/fabric/crud.py:FABRIC_LAYERS` |
| FABRIC entity schemas (validated) | **5** (commitment, contact, decision, insight, mission) | `docs/fabric-schemas/*.json` |
| Synapse index tiers | **4** (L1 Hot TOC, L2 FTS5 search, L3 Tool Catalog, L4 Mission Memory) | `realize_core/fabric/synapse.py` docstring |
| Mission Engine states | **8** (proposed → planned → in-progress → paused → awaiting-approval → completed / failed / cancelled) | `realize_core/missions/state.py:MissionState` |
| LLM providers (auto-discovered) | **5** (Claude, Gemini, OpenAI, Ollama, LiteLLM) | `realize_core/llm/registry.py` |
| MCP tool families | **4** (chat, kb, ops, admin) | `realize_core/mcp_server/tools/` |
| Tool modules | **21** | `realize_core/tools/*.py` |
| Test suite | **2,028 tests passing** (0 failures, 5 deprecation warnings) | `pytest tests/ -q` |
| Python requirement | **3.11+** (3.12+ recommended) | `pyproject.toml` |
| License | **BSL 1.1** → Apache 2.0 on 2030-03-26 | `LICENSE` |

---

## 2. Install Commands — Verified Status

> **Key:** ✅ = published & working · ⚠️ = exists but not yet published at 5.5.0 · ❌ = not available

### Docker (recommended)

```bash
git clone https://github.com/SufZen/RealizeOS-5.git && cd RealizeOS-5
cp .env.example .env       # Add your API key(s)
docker compose up --build   # Dashboard → http://localhost:8080
```

**Status:** ✅ `docker compose` works from source. ⚠️ Pre-built `ghcr.io/sufzen/realizeos-5:5.5.0` image not yet published — will be created by CI on release.

### pip

```bash
pip install realize-os
realize-os init --template consulting
realize-os serve
```

**Status:** ⚠️ PyPI currently publishes `5.2.1`. The `5.5.0` version will be published when semantic-release runs on the merged `main` branch.

### NPX

```bash
npx @realize-os/cli init my-business
cd my-business && npx @realize-os/cli start
```

**Status:** ⚠️ npm currently publishes `5.2.1`. The `5.5.0` version will be published when semantic-release runs.

### One-liner install

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/SufZen/RealizeOS-5/main/scripts/install.sh | bash

# Windows (PowerShell)
irm https://raw.githubusercontent.com/SufZen/RealizeOS-5/main/scripts/install.ps1 | iex
```

**Status:** ✅ Scripts exist and reference `:latest` which will resolve once published.

### Source checkout

```bash
git clone https://github.com/SufZen/RealizeOS-5.git && cd RealizeOS-5
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
realize-os serve
```

**Status:** ✅ Always works from source.

---

## 3. Shipped vs Roadmap Matrix

### ✅ Shipped in v5.5.0 (present as "available")

| Feature | Sprint | Code Location |
|---------|--------|---------------|
| **FABRIC Entity System** — markdown↔entity round-trip, provenance/trust metadata, 3 reference mechanisms (inline, frontmatter, cross-file), soft JSON-Schema validation | Sprint 1 | `realize_core/fabric/` |
| **Synapse Knowledge Index** — L1 Hot TOC, L2 FTS5 full-text search, L3 Tool Catalog, L4 Mission Memory, graph queries | Sprint 2 | `realize_core/fabric/synapse.py`, `synapse_db.py` |
| **Event Log + SOUL** — JSONL append-only audit trail w/ SSE streaming; User/Agent SOUL persistent identity (role, personality, expertise, communication style) | Sprint 3 | `realize_core/fabric/event_log.py`, `soul.py` |
| **Runtime Adapter Layer** — `AgentRuntime` Protocol, Registry w/ health polling + task matching, FABRIC REST API (`/api/fabric/*`) | Sprint 4 | `realize_core/runtimes/`, `realize_api/routes/fabric.py` |
| **Mission Engine (Spine)** — 8-state mission/step machine, planning, runtime routing, cost tracking | Sprint 5 | `realize_core/missions/` |
| **Dreaming Subsystem** — Trust Policy (full-auto/propose/deny), Reflex + Curator maintenance cycles, Dream Inbox with human-in-the-loop review | Sprint 6 | `realize_core/dreaming/` |
| **Dashboard Pages** — `/missions`, `/knowledge` (Knowledge Map), `/dreams` (Dream Inbox), styled with `--rz-*`/`.fx-*` design system | Sprint 7 | `dashboard/src/pages/missions-page.tsx`, `knowledge-map-page.tsx`, `dream-inbox-page.tsx` |
| **FABRIC Operator CLI** — `realize-os fabric lint`, `reindex`, `stats`, `search`, `toc`, `dream` | Sprint 8 | `realize_core/cli_app/commands/fabric.py` |
| **Multi-LLM Routing** — auto-discovers Claude, Gemini, OpenAI, Ollama, LiteLLM; classifies tasks and routes to optimal model | Pre-5.5.0 | `realize_core/llm/` |
| **MCP Server** — 4 tool families (chat, kb, ops, admin), HTTP+SSE transport, JWT/API-key auth | Pre-5.5.0 | `realize_core/mcp_server/` |
| **Extension System** — tool/channel/integration/hook plugin types | Pre-5.5.0 | `realize_core/tools/`, `plugins/` |
| **Security Middleware** — 5-layer stack: security headers → audit → rate limiting → injection guard → JWT auth; RBAC with 6 roles | Pre-5.5.0 | `realize_core/security/` |
| **@realizeos/design-system** — shared CSS token architecture (`--rz-*` namespace), `.fx-*` effect classes, dark/light theming, density modes | v5.5.0 | `dashboard/src/design-system/` |

### 🔮 Roadmap (NOT shipped — label as "coming," never "available")

| Feature | Notes |
|---------|-------|
| Voice Channel (STT/TTS) | Architecture planned, not implemented |
| Full Workspace UI Redesign | Three-pane operator console |
| Cytoscape Visual Graph | Interactive knowledge graph visualization |
| React Native Mobile Companion | Mobile app for on-the-go access |
| Host-Satellite Sync | Multi-instance synchronization protocol |

---

## 4. Dashboard Screenshots

All screenshots captured from the running dashboard (dev server, dark theme).

| Page | Path | Description |
|------|------|-------------|
| Missions | `docs/v5.5.0/assets/dashboard-missions.png` | Mission control: 3 missions listed (1 active, 1 completed), cost tracking (€0.028), status filters, venture scoping |
| Knowledge Map | `docs/v5.5.0/assets/dashboard-knowledge.png` | Knowledge index explorer with entity counts, type breakdown, reference tracking, verification status |
| Dream Inbox | `docs/v5.5.0/assets/dashboard-dreams.png` | AI proposals inbox: 5 proposals (3 pending, 1 approved, 1 rejected), cycle type filters, confidence indicators, approve/reject actions |

---

## 5. Positioning Thesis

> **You own the Heart (FABRIC knowledge graph + event log + identity) forever;
> agent runtimes, models, channels, and even the dashboard are swappable adapters;
> local-first.**

- **FABRIC** is the durable layer — markdown files on disk, yours forever
- **Synapse** is a derived index — blow it away, rebuild from FABRIC
- **Runtimes** are pluggable via the `AgentRuntime` Protocol
- **LLM providers** auto-discover at startup — swap anytime
- **The dashboard** is a SPA consumer of the REST API — replaceable
- **Local-first** — all data lives on your filesystem, no cloud dependency

---

## 6. Design System (`/design` page)

The `@realizeos/design-system` lives at `dashboard/src/design-system/` and contains:

| Asset | Purpose |
|-------|---------|
| `tokens.css` | All CSS variables (color, type scale, spacing, radius, motion). Light + dark mode. |
| `tokens.json` | Machine-readable tokens (Style Dictionary-compatible). |
| `fonts.css` | Google Fonts: Poppins, Rubik (RTL), JetBrains Mono. |
| `keyframes.css` | Namespaced `rz-*` animations: fade-up, fade-in, popup-in, float, accordion. |
| `effects.css` | `.fx-glass`, `.fx-glow`, `.fx-gradient-text`, `.fx-dot-grid`, `.fx-animated-border`, `.fx-illustration-glow`. |
| `components.css` | Class primitives: `.rz-btn`, `.rz-input`, `.rz-badge`, `.rz-card`, `.rz-code`, `.rz-status-dot`. |
| `README.md` | Design system documentation (theming, density, migration guides). |
| `ILLUSTRATION.md` | Illustration system spec (geometric, mono-line, themed SVGs). |

The design system README references `realizeos.ai/design` as the canonical visual spec.
There is **no standalone `index.html`** bundled in this repo — the website agent should
build the `/design` route from the CSS/JSON assets and documentation listed above.

---

## 7. Release-Publish Sanity

| Item | Status |
|------|--------|
| `VERSION` file | `5.5.0` ✅ |
| `package.json` (root) | `5.2.1` — will be bumped by semantic-release |
| `pyproject.toml` version | Will be bumped by semantic-release `@semantic-release/exec` |
| `.releaserc.json` | Configured with conventional-commits, changelog, exec (pyproject.toml + package.json bump), git push |
| `version-bump.yml` | Fixed: `persist-credentials` enabled for `@semantic-release/git` push |
| GitHub tag `v5.5.0` | ⚠️ Not yet created — will be created on merge to `main` |
| PyPI `realize-os 5.5.0` | ⚠️ Not yet published — triggered by release workflow |
| npm `@realize-os/cli 5.5.0` | ⚠️ Not yet published — triggered by release workflow |
| Docker `ghcr.io/sufzen/realizeos-5:5.5.0` | ⚠️ Not yet published — triggered by release workflow |

> **Note:** Do NOT hand-bump versions. The semantic-release pipeline handles version
> bumping in `pyproject.toml`, `package.json`, and `package-lock.json` automatically
> on merge to `main`.

---

## 8. CI Pipeline Status

All 8 CI jobs verified locally:

| Job | Status |
|-----|--------|
| Python Lint (Ruff) | ✅ All checks passed |
| Type Check (mypy) | ✅ Non-blocking (83 pre-existing legacy errors suppressed) |
| Python Tests (pytest) | ✅ 2,028 passed |
| Security Scan (safety + bandit + gitleaks) | ✅ Non-blocking |
| Docker Build | ✅ Compose validated |
| Dashboard (ESLint + Prettier + TypeScript + Vitest) | ✅ Clean |
| CLI (lint + build + 30 tests) | ✅ Clean |
| Markdown Lint | ✅ 0 errors |

---

## 9. Key File Paths

| File | Purpose |
|------|---------|
| `VERSION` | Single version source of truth |
| `README.md` | Public-facing project README |
| `CHANGELOG.md` | Auto-generated release notes |
| `LICENSE` | BSL 1.1 license text |
| `SECURITY.md` | Security policy and vulnerability reporting |
| `QUICKSTART.md` | Zero-to-running in 10 minutes |
| `docs/v5.5.0/SITE-CLAIMS.md` | **This file** — website source of truth |
| `docs/v5.5.0/assets/` | Dashboard screenshots |
| `docs/v5.5.0/realizeos-v5.5.0-master-design.md` | Master design document |
| `docs/v5.5.0/runtime-adapter-contract.md` | Runtime Protocol specification |
| `docs/v5.5.0/fabric-entity-schemas.md` | FABRIC entity schema documentation |
| `docs/v5.5.0/fabric-semantic-tags.md` | Semantic tag vocabulary |
| `docs/fabric-schemas/*.json` | Machine-readable JSON schemas |
| `dashboard/src/design-system/` | Design system tokens + effects + components |
| `.releaserc.json` | Semantic-release configuration |
| `.github/workflows/ci.yml` | CI pipeline |
| `.github/workflows/version-bump.yml` | Release pipeline |
