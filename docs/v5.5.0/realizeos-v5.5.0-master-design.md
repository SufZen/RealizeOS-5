# RealizeOS v5.5.0 — Master Design Document

> A single canonical reference consolidating all architectural decisions, design rationale, and implementation guidance for v5.5.0.
>
> Status: Draft v3 (May 2026)  
> License of this document: MIT (so collaborators can freely fork and reference)  
> Target codebase: [`SufZen/RealizeOS-5`](https://github.com/SufZen/RealizeOS-5) — under BSL 1.1

---

## Table of Contents

1. [Vision & Position](#1-vision--position)
2. [Architecture Overview](#2-architecture-overview)
3. [The Heart — Knowledge & Identity](#3-the-heart--knowledge--identity)
4. [The Spine — Mission Engine & Routing](#4-the-spine--mission-engine--routing)
5. [The Limbs — Runtimes, Models, Tools](#5-the-limbs--runtimes-models-tools)
6. [The Senses — Channels Including Voice](#6-the-senses--channels-including-voice)
7. [The Skin — Workspace, Mobile, Knowledge Map](#7-the-skin--workspace-mobile-knowledge-map)
8. [Distribution Layer — Sync Protocol](#8-distribution-layer--sync-protocol)
9. [Dreaming — Self-Evolution with Trust Policy](#9-dreaming--self-evolution-with-trust-policy)
10. [Content Format Strategy](#10-content-format-strategy)
11. [Cross-Venture & Collaboration Model](#11-cross-venture--collaboration-model)
12. [Local-First Guarantees](#12-local-first-guarantees)
13. [Open-Source Dependency Catalog](#13-open-source-dependency-catalog)
14. [Migration Sequence](#14-migration-sequence)
15. [Kill-Switch Metrics](#15-kill-switch-metrics)
16. [Open Questions](#16-open-questions)
17. [Appendices](#17-appendices)

---

## 1. Vision & Position

### What v5.5.0 Is

RealizeOS v5.5.0 is the version where RealizeOS becomes a **personal AI operating system**:
- The user's knowledge, tasks, and preferences form the kernel
- Any CLI, MCP server, API, or agent runtime plugs in as a swappable peer
- Multiple agent runtimes coexist (Hermes, Claude Code CLI, Codex CLI, Gemini CLI, OpenClaw, Grok CLI, internal agents)
- The user permanently owns their data; portability is literal — your knowledge is markdown in a git repo
- Local or self-hosted only (not SaaS); BSL 1.1 license enforces this commercially
- Single-user or multi-tenant via VPS deployment
- Native multi-venture with the FABRIC system; venture-level permissions; cross-venture sharing

### What v5.5.0 Is Not

- Not a chatbot front-end
- Not a wrapper around a single agent runtime
- Not a SaaS platform
- Not a closed proprietary system — your data is yours, in open formats
- Not a rebuild — most of the v5.2.1 codebase is reused. Lego project: keep what works, add what's missing.

### The Strategic Bet

Every "Mission Control" stack circulating in 2026 (Hermes Agent OS, paperclip, OpenClaw-as-OS) puts the agent runtime at the kernel. When the agent updates, things shake. When you swap runtimes, it's a rebuild.

RealizeOS inverts this. The kernel is the three things you'd never want to throw away: **the FABRIC knowledge graph, the event log, and the identity/policy layer**. Agents, models, workflows, channels, and even the dashboard become adapters around that core. This makes RealizeOS the substrate other Mission Control distributions could run on top of — which is the actual moat.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  THE SKIN — Workspace UI · Mobile Companion · Visual Graph     │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│  THE SENSES — Channels                                          │
│  REST · MCP Server · Telegram · WhatsApp · Voice · CLI · Email │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│  THE SPINE — Mission Engine · Smart Kanban Router               │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│  THE HEART — yours, never replaced                              │
│  FABRIC (Git-versioned)  ·  Event Log  ·  SOUL (user + agent)  │
│  Synapse (4-tier index)  ·  Identity & Policy                  │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│  THE LIMBS — Swappable Adapters                                 │
│  Runtime Adapter Layer · LLM Router · MCP Tool Registry        │
│  Extensions (tool · channel · integration · hook)              │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│  DREAMING — Self-Evolution (cross-cutting)                      │
│  Reflex · Curator · Synthesis · Genesis · Trust Policy         │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│  DISTRIBUTION (VPS / cloud-install only)                        │
│  Host-Satellite Sync Protocol                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Role | Replaceable? |
|---|---|---|
| Skin | User-facing surfaces | Yes — multiple skins on same Heart |
| Senses | Channel adapters | Yes |
| Spine | Goal → plan → execute | No (core logic) |
| **Heart** | **Knowledge, identity, audit** | **No — this is yours forever** |
| Limbs | Agent runtimes, models, tools | Yes — each adapter is hot-swappable |
| Dreaming | Self-evolution cross-cutting | Yes (can be disabled per-venture) |
| Distribution | Multi-instance sync | Only present in VPS mode |

---

## 3. The Heart — Knowledge & Identity

The kernel of RealizeOS. Five subsystems, all derived from FABRIC; FABRIC is the source of truth.

### 3.1 FABRIC — The Knowledge Layer

Six layers per venture, filesystem-based, git-versioned:

```
ventures/<venture-key>/
├── .git/                       # versioning
├── F-foundations/              # identity, voice, standards
│   └── _shared/                # syncs to brand level
├── A-agents/                   # agent definitions for this venture
├── B-brain/                    # domain knowledge, expertise
├── R-routines/                 # skills, workflows, SOPs
├── I-insights/                 # learning log, decisions, feedback
│   └── _dream-inbox/           # pending dream proposals
└── C-creations/                # output artifacts, deliverables
```

Each venture is its own git repo. Brand-level shared content lives in `_brand/` above `ventures/`.

### 3.2 FABRIC as a Structured Knowledge Graph

Six concrete design decisions that elevate FABRIC from "folder of markdown" to "structured knowledge graph":

**Decision 1 — Stable Entity IDs**

Every entity has an immutable ID assigned at creation, independent of filename:

```yaml
---
id: dec-2026-05-pricing-001        # immutable forever
type: decision
title: RealizeOS pricing model
slug: pricing-model                # changeable
venture: realizeos
---
```

Format: `<type-prefix>-<yyyy-mm>-<short-slug>-<seq>`. Human-readable, sortable, collision-resistant.

**Decision 2 — Soft Schemas**

JSON Schemas in `docs/fabric-schemas/<type>.json` for the 10 core entity types. Validate on save with *warnings*, not errors. Unknown fields allowed. Agents read schemas to know expected shape; FABRIC never refuses content.

Initial core entity types:
- `decision` · `commitment` · `risk` · `insight`
- `contact` · `mission` · `deal` · `property`
- `document` · `learning`

**Decision 3 — Three Reference Mechanisms**

All three feed the same `refs` table in Synapse:

| Mechanism | Syntax | Best for |
|---|---|---|
| Wikilink | `[[dec-2026-05-pricing-001]]` | Inline prose |
| Inline XML ref | `<decision ref="dec-2026-05-pricing-001"/>` | Structured tags |
| Frontmatter ref | `partners: [contact-meirav]` | Structured fields |

**Decision 4 — Graph as Derived Projection**

The graph lives in SQLite tables, derived from FABRIC:

```sql
entities (id PRIMARY KEY, type, title, path, slug, summary,
          last_updated, hash, venture, source, created_by,
          confidence, verified)
tags (entity_id, tag, source)              -- source: frontmatter | xml | implicit
refs (from_entity, to_entity, ref_type, source_path, context)
embeddings (entity_id, chunk_id, embedding) -- via sqlite-vec
mission_memory (mission_id, summary, decisions, blockers, last_updated)
```

Blow away SQLite → rebuild from FABRIC. No separate truth source. Preserves "your data is just markdown in git."

**Decision 5 — Graph Queries as First-Class Agent Primitives**

```python
synapse.neighbors(entity_id, depth=1, types=None)
synapse.shortest_path(from_id, to_id)
synapse.by_type(type, filters=None, scope=None)
synapse.by_tag(tag, scope=None)
synapse.touched_since(timestamp, scope=None)
synapse.unverified(scope=None, max_confidence=0.7)
synapse.orphans(scope=None, since=None)
```

These are exposed to agents as MCP tools and to the UI as REST endpoints.

**Decision 6 — Provenance Tracking**

Every entity tracks origin and confidence:

```yaml
source: manual | agent-generated | imported | dreaming
created_by: user-asaf | agent-maria | dream-curator
last_modified_by: agent-antonio
confidence: 0.0-1.0       # agents only; users implicitly 1.0
verified: false | true
verified_by: user-asaf
last_verified: 2026-05-20
```

### 3.3 Synapse — Multi-Tier Knowledge & Tool Indexing

A subsystem inside the Heart: the connective tissue between FABRIC (durable knowledge) and agents (consumers). Pre-computed, hierarchically-summarized, semantically-indexed projection optimized for low-token, high-recall agent consumption.

**Four Tiers:**

| Tier | Contents | Size | Loaded |
|---|---|---|---|
| L1 — Hot TOC | Every entity: id, type, title, summary, tags, refs | ~5–10K tokens/venture | Always |
| L2 — Hybrid Search | FTS5 + sqlite-vec; BM25 + cosine | On disk | On demand |
| L3 — Tool Catalog | All tools/skills: name, desc, schema, cost, ranked | ~2–5K tokens | Always |
| L4 — Mission Memory | Per-mission compressed state | ~1–2K/mission | Per active mission |

**The single biggest design move: agents always see L1.** Agent never asks "what's in FABRIC?" — it already knows. Kills ~80% of unnecessary RAG retrievals.

**Background indexer:**
- `watchdog` filesystem watcher → debounced job queue
- Worker pool: hash, summary, embed, tag-extract, refs
- Per-file budget: <100ms (most under 30ms)
- SSE broadcast: L1 updates → active agents + UI
- Content-hash caching: unchanged files don't re-embed

**Hierarchical summarization:**
- Venture summary → FABRIC layer summary → entity summary → entity body
- Progressive disclosure: agent reads summaries first, drills down only on demand

**Mission-scoped retrieval:** within a mission, default search scope is constrained to the mission's topic area, with explicit override available.

**Expected token economy vs naive RAG: 60–80% reduction**, driven by TOC pre-loading, summaries-first disclosure, mission scoping, cached embeddings, and pre-computed summaries.

**Agent-facing API:**

```python
synapse.toc(venture)                     # L1 for a venture
synapse.search(query, scope?, n=10)      # L2 hybrid retrieval
synapse.get(entity_id, depth=0)          # full entity + refs
synapse.summary(scope)                   # hierarchical summary
synapse.recent(scope, n=10)              # recent changes
synapse.tools(context, n=20)             # L3 ranked tools
synapse.mission_memory(mission_id)       # L4
```

### 3.4 Event Log

JSONL append-only log (existing system, keep). Every action, decision, mission state change, channel event, dream proposal. SSE streaming for live consumers. Powers replay, audit, forensics, and dreaming.

### 3.5 SOUL — User and Agent Identity

Two levels (the user-level is new in v5.5.0):

**User SOUL** (new):
```yaml
locale: pt-PT
languages: [he, en, pt, it, es]
working_hours: 09:00-19:00 Europe/Lisbon
default_runtime_preferences:
  code: claude-code-cli
  research: claude-opus
  hebrew_content: claude-sonnet
voice: formal-but-warm
constraints:
  - "Never auto-send messages to clients without approval"
  - "Always price in EUR unless context demands otherwise"
```

**Agent SOUL** (existing per-agent SOUL system, extend):
- Role, personality, expertise, communication style
- Now also: home-runtime preference, scoped permissions, cost limits

### 3.6 Identity & Policy

Extend the existing RBAC (6 built-in roles + custom YAML) with venture-level permissions:

```yaml
# Per-user-per-venture permissions
user: meirav@suf.zen
venture: realization
role: collaborator
permissions:
  - fabric.read
  - fabric.write[I-insights, C-creations]
  - missions.create
  - missions.execute[scope=research]
  - tools.invoke[allowlist: [search, scrape, summarize]]
deny:
  - fabric.write[F-foundations]
  - fabric.write[A-agents]
```

---

## 4. The Spine — Mission Engine & Routing

### 4.1 Mission Engine

Extends the existing `realize_core/base_handler.py`. State machine that:
- Accepts a goal (text or structured)
- Produces a plan (ordered steps, each addressed to a Runtime + tool set)
- Dispatches steps, awaits results, advances state
- Records every step to event log with trace IDs
- Maintains L4 mission memory throughout
- Persists state — missions can pause, resume, hand off

Mission schema:

```yaml
id: m-2026-05-20-001
tenant: asaf
venture: burtucala
owner: user-asaf
goal: "Find 3 distressed inheritance properties in Setúbal under 150k"
constraints:
  budget_eur: 5.0          # cost cap
  deadline: 2026-05-22T18:00:00Z
  approval_required: ["external_send", "financial_commitment"]
plan:
  - step_id: s1
    runtime: internal
    agent: maria
    action: search.real_estate
    args: { region: "Setúbal", max_price: 150000, status: "distressed" }
  - step_id: s2
    runtime: internal
    agent: maria
    action: enrich.heir_contacts
    inputs: [s1]
  - step_id: s3
    runtime: claude-code-cli
    action: score.priority
    inputs: [s2]
state: in_progress
cost_consumed_eur: 0.34
```

### 4.2 Smart Kanban Router

Routes tasks to runtimes by:
1. **Explicit user rules** (highest priority): `route: when task_type=code use claude-code-cli`
2. **Per-agent SOUL preferences**: home-runtime defaults
3. **Learned preferences**: dreaming-derived rules based on observed success rates
4. **Cost-aware fallback**: if budget is tight, route to cheaper runtime

Visual: Kanban-style board in the Workspace UI showing missions in progress per runtime. Drag-to-reroute. The "Hermes dashboard" visual reference, applied to multi-runtime.

**Critical: full visibility with smart default.** User can always see which runtime handles each task. Router suggests; user overrides freely. Overrides become training data for dreaming.

---

## 5. The Limbs — Runtimes, Models, Tools

### 5.1 Runtime Adapter Layer (new abstraction)

The single most consequential new interface in v5.5.0. Defines the contract any agent runtime satisfies to be a peer in RealizeOS.

```python
class AgentRuntime(Protocol):
    """Contract for any agent runtime: internal, Hermes, Codex CLI, Claude Code, etc."""

    runtime_id: str
    capabilities: list[Capability]    # e.g., ["code.edit", "browser.use", "research"]
    
    def health_check(self) -> HealthStatus:
        """Is this runtime alive and ready?"""
    
    def cost_estimate(self, task: Task) -> CostEstimate:
        """Approximate token cost / time for this task."""
    
    def invoke(self, mission: Mission, context: Context) -> RuntimeResult:
        """Execute a mission step. Streams results."""
    
    def cancel(self, run_id: str) -> bool:
        """Cancel an in-flight invocation."""
    
    def export_skills(self) -> list[Skill]:
        """If this runtime maintains its own skill library, export it for cross-runtime reuse."""
```

**Initial runtime adapters:**
- `RealizeInternal` — wraps existing `realize_core/agents/`
- `HermesAdapter` — talks to Hermes over its HTTP API
- `ClaudeCodeAdapter` — subprocess to `claude` CLI
- `CodexAdapter` — subprocess to Codex CLI
- `GeminiCLIAdapter` — subprocess to Gemini CLI
- `OpenClawAdapter` — subprocess to OpenClaw
- `GrokCLIAdapter` — subprocess to Grok CLI

Hot-reloadable like extensions. Registered in a Runtime Registry. The Smart Kanban Router queries the registry to discover what's available.

### 5.2 LLM Router

Existing `realize_core/llm/` (Claude / Gemini / OpenAI / Ollama auto-discovery). Extend to:
- Tag every provider as `local` / `self-hosted` / `third-party-cloud`
- Surface these tags at routing time (UI shows where data is going)
- Honor user-level no-cloud mode toggle
- Support `mxbai-embed-large` and `nomic-embed-text` for embeddings via Ollama (default local), with OpenAI embeddings as opt-in

### 5.3 MCP Tool Registry

Existing dual MCP role (client + server, 24 tools across Chat/KB/Ops/Admin). Extend with:
- L3 ranked tool catalog (per-mission relevance)
- Per-agent allowlist (existing) + per-tenant allowlist (new for multi-user VPS mode)
- Auto-discovery of any MCP server the user registers

### 5.4 Extensions

Existing system (tool / channel / integration / hook). Keep. Add: Runtime extension type for adding new runtime adapters via the extension system.

---

## 6. The Senses — Channels Including Voice

### 6.1 Existing Channels
- REST API
- MCP Server (24 tools, HTTP+SSE)
- Telegram
- WhatsApp
- CLI / REPL
- Webhooks
- Email gateway

### 6.2 Voice Channel (new)

First-class channel adapter. Local-default to honor the local-first promise.

**STT (Speech-to-Text):**
- Primary: `faster-whisper` (CTranslate2-based, MIT, fast)
- Models: Whisper-medium (GPU) / Whisper-small (CPU)
- Target: <500ms for short utterance (GPU), <1.5s (CPU)
- Audio never leaves device by default; opt-in cloud STT for users who prefer quality

**TTS (Text-to-Speech):**
- Primary: Piper TTS (MIT, local, fast)
- Opt-in cloud: ElevenLabs Flash, OpenAI TTS

**UX:**
- Push-to-talk by default
- Always-listening as opt-in with explicit wake-word
- Voice channel adapter implements the same Channel Contract as Telegram/WhatsApp

---

## 7. The Skin — Workspace, Mobile, Knowledge Map

### 7.1 Workspace UI (redesigned)

Three-pane workspace replacing the current more traditional dashboard. Keep the existing dashboard as a "Classic mode" toggle.

```
┌──────────────────┬─────────────────────┬──────────────────┐
│  Left            │  Center             │  Right           │
│                  │                     │                  │
│  Venture         │  Active Mission     │  Live FABRIC     │
│  Switcher        │  / Conversation     │  Context Panel   │
│                  │                     │                  │
│  Kanban Mission  │  Streaming agent    │  Synapse L1 view │
│  List per        │  output, tool       │  of entities     │
│  Runtime         │  invocations,       │  relevant to     │
│                  │  human approvals    │  current mission │
└──────────────────┴─────────────────────┴──────────────────┘
```

Built on existing React 19 + Vite 8 + TypeScript + Tailwind 4 stack. Extend with **shadcn/ui** for accessible component primitives.

### 7.2 Mobile Companion (React Native + Expo, Android-first)

Capture-and-review surface. Not a full workspace.

Priority features:
1. Voice capture (push-to-talk, auto-transcribe, ingest to FABRIC capture inbox)
2. Mission inbox with approvals queue
3. Quick capture (photo, text, voice)
4. Push notifications for mission events
5. Mission detail view (read + approve/deny)
6. Venture switcher

Connection model:
- Local-only RealizeOS install: connects over Tailscale or LAN
- VPS-hosted: direct HTTPS + JWT
- No canonical local storage; thin client with optimistic cache

### 7.3 Visual Knowledge Map (new)

Obsidian-style force-directed graph view as one of the workspace panes. Critical for both:
- Human understanding ("show me the cluster of decisions about pricing")
- Dreaming Synthesis ("here are the entities that should be connected but aren't")

**Library choice: Cytoscape.js (MIT) as primary; react-force-graph (MIT) as a simpler alternative.**

Cytoscape.js is open-source under MIT, used in production by enterprises, includes graph theory algorithms built-in (centrality, community detection, shortest paths). Mature, well-documented, supports both desktop and mobile browsers with all gestures out of the box.

**Underlying data structure: Graphology (MIT)** — provides centrality, community detection, shortest path algorithms, and feeds both the visualization and the dreaming Synthesis cycle.

**Feature set:**
- Force-directed layout (Cytoscape's `cose-bilkent` or similar)
- Filters: venture, entity type, tag, recency, confidence, verified status
- Color by type / venture / confidence
- Click → jump to entity in main pane
- "Show subgraph" — N degrees from selected entity
- "Show this week" — only recently-touched
- Community detection overlay — visualize topic clusters
- Betweenness centrality overlay — show which entities are connection hubs

**Inspiration sources (study, don't depend on):**
- Obsidian's built-in Graph View — UX reference
- Juggl (Obsidian plugin, open-source) — advanced graph view patterns
- InfraNodus (commercial) — gap detection, community analysis (steal the patterns, not the code)
- Logseq (open-source) — alternative reference implementation

**Performance budget:** smooth interactive rendering up to ~2,000 entities. For ventures growing past that, Cytoscape.js degrades gracefully; if you outgrow it (10k+), the upgrade path is **Cosmograph** (GPU-accelerated, free core) or **Sigma.js + Graphology** for WebGL-accelerated large graphs.

---

## 8. Distribution Layer — Sync Protocol

VPS-mode only. Local-only installs are single-device by design.

### 8.1 Model: Hybrid Host-Per-Venture

- Each shared venture has a designated **host instance** (typically owner's VPS)
- Other RealizeOS instances are **satellites** that pull and push to the host's git repo
- Brand-level shared content has its own host (often same as primary venture host)
- Per-venture host avoids single-instance bottleneck while keeping federation simple

### 8.2 Sync Mechanics

**For FABRIC content:** git push/pull. Already-built infrastructure (every git host on the internet works as backup).

**For event log:** append-only replication via HTTP polling or SSE subscription, with vector clocks for ordering across satellites.

**For real-time collaborative editing (small subset of entities):** layer **`y-py`** (Y.js Python bindings, MIT) on top — current mission canvas, shared whiteboards, multi-participant chat. Most FABRIC content is not CRDT.

**Conflict resolution:**
- Atomic fields: last-write-wins with timestamps, surface both versions with "keep mine / theirs / merge" affordance
- Documents: GitHub-style 3-way merge UI in browser. Never expose `git status` or merge markers.

### 8.3 Collaborator Tiers

| Tier | Who | Access | Distribution |
|---|---|---|---|
| A | RealizeOS user | Native peer-to-peer sync | Each user has own install; git federation |
| B | Guest (no install) | Magic-link web UI | Scoped subdomain; no API tokens; conversion funnel |
| C | API/CLI integration | Service account JWT | Programmatic, no UI |

**The strategic move:** every Tier B guest interaction surfaces a "this is your data too, install your own RealizeOS to take it with you" CTA. BSL 1.1 license means they can't repackage as a SaaS — they install or they leave.

---

## 9. Dreaming — Self-Evolution with Trust Policy

### 9.1 State of the Art Leveraged

- **GEPA + DSPy** — MIT-licensed, ICLR 2026 Oral paper, available as `NousResearch/hermes-agent-self-evolution`. Reads execution traces to root-cause failures. **Pull as a dependency.**
- **Hermes Curator pattern** — background skill grading, consolidation, pruning on a cron cycle
- **Honcho user modeling** — persistent user model in `memory.md` / `user.md` (mapped into our User SOUL)
- **Anthropic Dreaming** — overnight session processing

### 9.2 Four Cycles

| Cycle | Cadence | Scope | Engine | Output |
|---|---|---|---|---|
| Reflex | Per-mission, ~30s | Single mission | Small local model | L4 update + insight to I-insights |
| Curator | Daily, 3am local | 24h activity | GEPA + DSPy | Skill grading, FABRIC hygiene, router rules |
| Synthesis | Weekly | 7 days, multi-venture | GEPA + larger model | Workflow extraction, drift detection, patterns |
| Genesis | Quarterly | 90 days | Largest model | Venture state-of-union, SOUL refinement |

### 9.3 Trust Policy System

The critical design move: **proposals are routed by per-category trust policy with smart defaults that lean conservative and expand based on observed approval patterns**. Not a global on/off toggle.

#### Four Trust Levels

| Level | Behavior | Default Categories |
|---|---|---|
| `ALWAYS_PROPOSE` | Never auto-apply; always to inbox | SOUL refinement, F-foundations edits, drift correction, cross-venture sharing changes, anything in `_brand/` |
| `DEFAULT_PROPOSE` | Goes to inbox; user can promote category to AUTO after approval streak | Skill consolidation, prompt refinement, router rule changes, workflow extraction |
| `AUTO_IF_CONFIDENCE_HIGH` | Auto-apply if confidence ≥ threshold (default 0.95); quarantine N days first | FABRIC hygiene fixes, broken ref repair, tag standardization |
| `ALWAYS_AUTO` | Auto-apply immediately, notification only | Mission summaries, Synapse index updates, derivations from event log |

#### Configurable Per Category

User can override per-category via `users.yaml` and per-venture via venture config:

```yaml
# users.yaml
dreaming:
  policies:
    skill_consolidation: DEFAULT_PROPOSE
    prompt_refinement: ALWAYS_PROPOSE          # I'm conservative on this
    fabric_hygiene: AUTO_IF_CONFIDENCE_HIGH
    fabric_hygiene_threshold: 0.97             # stricter than default
    mission_summaries: ALWAYS_AUTO
    soul_refinement: ALWAYS_PROPOSE
  quarantine_days: 3                            # for AUTO categories
  per_venture_overrides:
    arena-habitat:
      # Higher stakes legal/financial content
      fabric_hygiene: DEFAULT_PROPOSE
    burtucala:
      # Content marketing, lower stakes
      prompt_refinement: AUTO_IF_CONFIDENCE_HIGH
```

#### Trust Expansion

After observed approval patterns, the system suggests promoting categories:

> "I've proposed 47 skill consolidations in the last 30 days. You approved 46, rejected 1. Want me to promote `skill_consolidation` from DEFAULT_PROPOSE to AUTO_IF_CONFIDENCE_HIGH (threshold 0.92)?"

User can accept, reject, or modify the threshold. This builds calibrated trust over time without requiring the user to think about it upfront.

#### Quarantine Branches

Categories on `AUTO_IF_CONFIDENCE_HIGH` first commit to a `dream/quarantine` branch with the configured grace period (default 3 days). User can review during the quarantine; auto-merge to `main` happens at end of period unless rejected.

#### Hard Deny-Lists

Always-deny paths/types regardless of policy:
```yaml
dreaming:
  never_modify:
    paths:
      - "**/F-foundations/venture-identity.md"
      - "**/A-agents/_README.md"
    types:
      - decision  # never auto-modify committed decisions
```

#### Pause Button

`realize-os dreaming pause` halts all dreaming cycles. `realize-os dreaming resume` restarts. Manual revert of recent dream commits: `realize-os dream revert --last N`.

#### Negative Signal Loop

Rejected proposals are recorded as negative training signal in `I-insights/_dream-rejections.jsonl`. GEPA reads these to avoid proposing similar things. Patterns of rejection feed back into policy demotion suggestions ("you've rejected 5 cross-language consolidations — should I demote this subcategory to ALWAYS_PROPOSE?").

### 9.4 Per-Venture Privacy

- Reflex and Curator run per-venture by default; no cross-venture data leaks
- Synthesis and Genesis are the only cycles that look across ventures, and only for venture groups you've explicitly defined
- Trajectory export for fine-tuning: opt-in per venture
- VPS multi-user mode: dreams per-venture only, never bleeding across user boundaries

### 9.5 Why This Architecture

- **Trust is earned, not assumed** — system starts conservative, expands based on observed user feedback
- **Reversibility is built in** — every dream change is a git commit with `dream:` prefix
- **Per-category granularity** — different stakes get different treatment without burdening the user with binary global choices
- **Quarantine catches mistakes** — auto-applied changes have a review window before becoming permanent
- **Hard deny-lists** — critical paths never auto-modified regardless of confidence
- **Pause button** — emergency stop with one-command revert

### 9.6 Dream Inbox UX

Workspace UI surface for reviewing proposals:
- Morning email digest with summary + links into the workspace
- In-app inbox sorted by category, confidence, and impact
- Bulk actions ("approve all FABRIC hygiene fixes")
- Filter by venture
- Each proposal shows: title, rationale, diff, evidence (which past missions led to this), expected impact, confidence

---

## 10. Content Format Strategy

The "HTML is the new markdown" debate (kicked off by Thariq Shihipar of Claude Code in May 2026) resolves cleanly when you separate use cases. Empirical landscape: HTML wins when humans visually consume LLM output once; markdown wins for token economy, portability, diff-friendliness, and content that gets re-processed.

For FABRIC, most content is internal pipeline (agents read, agents write, humans review) — markdown wins. For human deliverables (proposals, dashboards, executive briefings) — HTML wins. Both coexist in FABRIC.

### Three-Tier Content Strategy

**Tier 1 — Markdown as default**
- Token-cheap (1.0×), git-diffable, human-authorable, portable
- All of `B-brain/`, `I-insights/`, `R-routines/`, most of `F-foundations/` and `A-agents/`
- YAML frontmatter for structured metadata
- Portability promise stays literal

**Tier 2 — Semantic XML tags inside markdown**
- Token overhead ~10–20%, dramatically more precise retrieval
- Anthropic prompt-engineering practice (XML tags for structure)
- Indexer extracts as first-class structured entities

Example:

```markdown
---
type: decision
id: dec-2026-05-pricing-001
venture: realizeos
---

# RealizeOS pricing model

<decision status="committed" date="2026-05-20" reviewers="meirav,miguel">
Setup-plus-maintenance model. €X setup, €Y/month maintenance.

<rationale>
Avoids per-seat SaaS dynamics. Aligns with BSL 1.1 self-hosted positioning.
</rationale>

<impacts ventures="burtucala,arena-habitat">
Burtucala lead funnel reframing; F&F launch webinar messaging.
</impacts>
</decision>
```

**Tier 3 — HTML for rich human deliverables**
- Token cost ~3× markdown
- `C-creations/` and parts of `I-insights/` (dashboards)
- Mission briefings, proposals, executive reports, interactive views
- Rendered in workspace via sandboxed iframe with CSP

### Canonical Semantic Tag Vocabulary

Starter set in `docs/fabric-semantic-tags.md`:

| Tag | Purpose |
|---|---|
| `<decision>` | A committed decision, with status/date/reviewers |
| `<commitment>` | A promise made (by you, to you, or by/to others) |
| `<risk>` | An identified risk with status |
| `<insight>` | A learning worth preserving |
| `<contact>` | A person reference (with `ref` attribute) |
| `<deadline>` | A time-bound obligation |
| `<question>` | An open question awaiting answer |
| `<assumption>` | A working assumption (to be validated) |
| `<reference>` | An external citation |
| `<draft>` | Content marked as work-in-progress |

Vocabulary is open-ended; new tags can be proposed by the dreaming Synthesis cycle.

---

## 11. Cross-Venture & Collaboration Model

### 11.1 Hierarchy

```
_brand/                              # owner's "Brand" or "Operator" level
├── contacts/                        # global people (Meirav, Miguel, etc.)
├── standards/                       # cross-venture standards
└── templates/                       # reusable templates

ventures/
├── realizeos/
│   ├── F-foundations/
│   │   └── _shared/                 # syncs to _brand/
│   └── ...
├── burtucala/
├── arena-habitat/
└── ...
```

### 11.2 Cross-Venture References

Namespace prefix in `ref` attributes:

```markdown
<contact ref="brand:meirav">Meirav</contact>
<contact ref="realization:lead-001">our Realization contact</contact>
```

### 11.3 Sharing Mechanics

- `_shared/` subdirectories within any venture sync to brand level
- Explicit grants for cross-venture reads in `_perms.yaml`
- Hidden refs render as `[access restricted]` for collaborators without permission
- Per-venture dreaming privacy boundaries (no cross-venture data bleeds)

### 11.4 Multi-Tenant on VPS

- Schema-per-tenant in Postgres OR row-level security (decision pending)
- Per-tenant cost caps with hard kill switch
- Per-tenant MCP server registrations
- Per-tenant model routing rules

---

## 12. Local-First Guarantees

Promote these from good practices to kernel-level guarantees exposed via API surface:

1. **Provider tagging** — every model/tool tagged `local` / `self-hosted` / `third-party-cloud`; surfaced at runtime
2. **No-cloud mode** — global toggle hides third-party-cloud providers entirely
3. **Credential vault** — all API keys encrypted at rest via OS keychain (`keyring` library) or user passphrase; never plaintext in `.env`
4. **One-line full export** — `realize-os export --venture <key>` produces tarball with git repo, SQLite, audit logs, configs (open formats throughout)
5. **Automatic backup** — scheduled exports to user-chosen destination
6. **Update path** — `realize-os update` with rollback support; never silently changes data semantics
7. **No telemetry by default** — opt-in only, transparent log
8. **Multi-device sync only on VPS mode** — local-only is single-device by design
9. **Plugin discovery without SaaS backend** — static JSON registry on GitHub Pages
10. **The LLM is the leak** — make this visible; document the trade-off honestly

### Honest Limitation

If a user calls Anthropic, OpenAI, or any cloud LLM, that data leaves their machine by definition. "Permanently owned" needs the footnote: *for local models, your data never leaves; for cloud providers, your prompts are subject to that provider's policies*. The system surfaces this at every routing decision.

---

## 13. Open-Source Dependency Catalog

Strategic principle: **leverage well-maintained, permissively-licensed open source aggressively. Don't rebuild what others have built well. Pay attention to license compatibility with BSL 1.1 distribution.**

License compatibility note: BSL 1.1 (your code) can incorporate MIT, Apache 2.0, BSD-style permissive licenses freely. Avoid AGPL (forces source distribution); avoid GPL for embedded use; LGPL is workable as dynamic library only. The catalog below is filtered to compatible licenses.

### Core Backend

| Library | Purpose | License | Status | Notes |
|---|---|---|---|---|
| FastAPI | REST API framework | MIT | Already in use | Keep |
| Pydantic v2 | Validation | MIT | Already in use | Keep |
| Uvicorn | ASGI server | BSD-3 | Already in use | Keep |
| pygit2 | Git operations via libgit2 | GPL-2.0 with linking exception | **New** | Linking exception allows use in proprietary/BSL code |
| watchdog | Filesystem watching | Apache 2.0 | **New** | Industry standard |
| sqlite-vec | Vector search in SQLite | Apache 2.0 | **New** | Or sqlite-vss as alternative (Apache 2.0) |
| keyring | OS keychain integration | MIT | **New** | Cross-platform credential storage |
| y-py | CRDT for collaborative entities | MIT | **New** | Python bindings for Y.js; only for collaborative subset |
| Typer | CLI framework | MIT | Already in use | Keep |
| MCP Python SDK | MCP protocol | MIT | Already in use | Keep |
| LiteLLM | Multi-LLM routing | MIT | Already in use or new | Critical for the multi-LLM abstraction |
| DSPy | Prompt optimization | MIT | **New** | Pulled with GEPA |
| GEPA | Trace-analysis self-evolution | MIT (ICLR 2026 Oral) | **New** | `NousResearch/hermes-agent-self-evolution` |

### Knowledge Layer

| Library | Purpose | License | Status | Notes |
|---|---|---|---|---|
| Graphology | Graph data structure + algorithms | MIT | **New** | Used by Cytoscape and Sigma; algorithms feed dreaming |
| markdown-it-py | Markdown parsing | MIT | New or already | For tag extraction |
| lxml or BeautifulSoup | HTML parsing | BSD-3 / MIT | Available | For HTML tier content |

### Voice

| Library | Purpose | License | Status | Notes |
|---|---|---|---|---|
| faster-whisper | STT (CTranslate2-based) | MIT | **New** | Fast local Whisper |
| Piper TTS | Local TTS | MIT | **New** | Lightweight, fast, fully local |

### Embeddings (via Ollama)

| Model | Source | License | Notes |
|---|---|---|---|
| `mxbai-embed-large` | Mixedbread | Apache 2.0 | Multilingual; default for Hebrew/Portuguese/Italian/Spanish |
| `nomic-embed-text` | Nomic AI | Apache 2.0 | English-first, faster |
| `bge-large` family | BAAI | MIT | Strong general-purpose |

### Frontend (Workspace UI)

| Library | Purpose | License | Status | Notes |
|---|---|---|---|---|
| React 19 | Framework | MIT | Already in use | Keep |
| Vite 8 | Build tool | MIT | Already in use | Keep |
| TanStack Query v5 | Server state | MIT | Already in use | Keep |
| React Router v7 | Routing | MIT | Already in use | Keep |
| Tailwind 4 | CSS | MIT | Already in use | Keep |
| shadcn/ui | Accessible components | MIT | **New** | Add for Workspace UI redesign |
| Cytoscape.js | Knowledge graph viz | MIT | **New** | Primary graph viz |
| react-cytoscapejs | React wrapper | MIT | **New** | If using Cytoscape with React |
| react-force-graph | Alternative graph viz | MIT | **New (alternative)** | Simpler force-directed |
| Zod | Runtime validation | MIT | **New** | TypeScript runtime types |
| React Hook Form | Forms | MIT | **New** | Recommended |
| Lucide React | Icons | ISC | **New** | Modern icon set |

### Mobile (React Native + Expo)

| Library | Purpose | License | Status | Notes |
|---|---|---|---|---|
| React Native | Framework | MIT | **New** | Android-first |
| Expo | Tooling | MIT | **New** | Managed workflow |
| Expo Voice | Audio capture | MIT | **New** | For voice input |
| Expo Notifications | Push | MIT | **New** | For mission alerts |
| Expo SecureStore | Encrypted local storage | MIT | **New** | For tokens |

### Storage & Sync

| Library | Purpose | License | Status | Notes |
|---|---|---|---|---|
| SQLite | Embedded DB | Public Domain | Already in use | Keep |
| Postgres (optional) | VPS multi-tenant | PostgreSQL License | New for VPS mode | Drop-in for SQLite at scale |
| rclone (external tool) | Backup sync | MIT | External | Recommended for backup destinations |

### Testing & Quality

| Library | Purpose | License | Status |
|---|---|---|---|
| pytest | Testing | MIT | Already in use |
| ruff | Linting | MIT | New or already |
| mypy | Type checking | MIT | New or already |
| playwright | E2E testing | Apache 2.0 | New |

### Reference / Inspiration (NOT dependencies — patterns to learn from)

| Project | License | What to learn |
|---|---|---|
| Obsidian | Proprietary | Graph view UX, plugin model |
| Logseq | AGPL-3.0 | Knowledge graph patterns — study, don't depend |
| Juggl | MIT | Advanced graph view in Obsidian |
| Hermes Agent | (varies) | Curator pattern, self-evolution loop |
| Honcho | Apache 2.0 | User modeling primitives |
| Mem0 | Apache 2.0 | Memory layer architecture |

### License Compatibility Summary

✅ MIT, Apache 2.0, BSD, ISC, PostgreSQL License — fully compatible with BSL 1.1  
⚠️ pygit2 (GPL-2.0 with linking exception) — usable due to the linking exception; document carefully  
❌ AGPL (Logseq, others) — do not depend; can learn from openly  
❌ GPL without linking exception — avoid in embedded use

---

## 14. Migration Sequence

Lego rebuild. Most of v5.2.1 codebase reused. New layers added; existing layers extended.

### Phase 0 — Decisions & Contracts (1 week)
- Lock the Runtime Adapter contract (most consequential new interface)
- Lock the FABRIC-as-git directory and commit conventions
- Define semantic tag vocabulary v1 (10–15 tags)
- JSON Schemas for top 10 entity types (soft validation)
- ADRs: sync protocol (hybrid host-per-venture), embedding default (mxbai-embed-large), summary model (Gemma 4 4B local), mobile stack (RN + Expo)
- Trust Policy default category mappings

### Phase 1 — Git-ify FABRIC + Synapse Foundation (2–3 weeks)
- `pygit2` integration in `realize_core/storage/`
- Auto-commit on FABRIC writes with debounce
- `watchdog` watcher → background indexer pipeline
- Synapse L1 (TOC) + L2 (FTS5 + sqlite-vec)
- Tag extractor (frontmatter + inline semantic XML + wikilinks)
- Provenance tracking in frontmatter
- Entity ID generation, graph tables
- Backfill: existing ventures → git repos, generate L1, populate L2

### Phase 2 — Runtime Adapter Layer (2–3 weeks)
- Define `AgentRuntime` Protocol
- Wrap existing internal agents as first runtime (zero behavior change)
- Add adapters: Claude Code CLI, Codex CLI, Gemini CLI, OpenClaw, Hermes (via HTTP API), Grok CLI
- Runtime Registry with hot-reload
- Health checks, cost estimation, cancellation

### Phase 3 — Synapse L3 + L4 + Smart Kanban Router (2 weeks)
- L3 tool catalog with mission-context ranking
- L4 mission memory with background summarization
- Smart Kanban Router using Synapse for routing decisions
- Graph query primitives (neighbors, shortest_path, etc.)
- Background validation loop (broken refs, orphans, staleness)

### Phase 4 — Voice + User SOUL (1–2 weeks)
- faster-whisper STT integration
- Piper TTS integration
- Voice channel adapter (follows existing Channel Contract)
- User SOUL schema + prompt-builder integration
- Optional cloud STT/TTS providers (ElevenLabs, OpenAI)

### Phase 5 — Workspace UI Redesign (3–4 weeks)
- Three-pane workspace layout
- shadcn/ui component library integration
- Mission inbox with SSE live updates
- Knowledge browser (FABRIC-aware navigation)
- Audit viewer
- Cost panel (per tenant, per mission)
- Tools picker (L3-ranked)
- Classic mode toggle for current dashboard users

### Phase 5.5 — Visual Knowledge Map (1–2 weeks, parallelizable with Phase 5)
- Cytoscape.js + Graphology integration
- Force-directed default layout
- Filters: venture, type, tag, recency, confidence, verified
- Color/size encodings
- Subgraph focus mode
- Recently-touched mode
- Community detection overlay
- Click-through to entity

### Phase 6 — Dreaming Subsystem (2–3 weeks)
- Pull `hermes-agent-self-evolution` (GEPA + DSPy) as dependency
- Reflex cycle (per-mission, low-stakes auto-applies)
- Curator cycle (daily cron)
- Trust Policy system with per-category defaults
- Dream Inbox UI in workspace
- Quarantine branches for AUTO_IF_CONFIDENCE_HIGH categories
- Git commit integration with `dream:` prefix
- Trust expansion suggestions
- Negative signal loop
- Pause/resume/revert commands
- Synthesis and Genesis cycles can defer to v5.5.1 if needed

### Phase 7 — Sync Protocol & Multi-User (3–4 weeks)
- Hybrid host-per-venture sync
- Git push/pull federation
- Event log replication (vector clocks)
- y-py for collaborative entity subset
- Conflict resolution UI (3-way merge in browser)
- Magic-link auth for Tier B guests
- Per-venture permission grants

### Phase 8 — Mobile Companion (2–3 weeks)
- React Native + Expo, Android-first
- Voice capture, mission inbox, quick capture, push, mission detail
- Connection via Tailscale (local) or HTTPS (VPS)

### Phase 9 — First-Time Install UX Polish (1 week)
- Guided onboarding wizard
- Venture template chooser with previews
- Sample FABRIC content for learning
- Voice setup, model provider selection, security wizard
- One-command upgrade from v5.2.1: `realize-os migrate-to-5.5`

### Total Estimate

~18–24 weeks for v5.5.0 with solo capacity. Phases 1+2 parallelizable; Phase 5 parallelizable with Phases 3+4; Phases 5.5/6 parallelizable with Phase 5; Phases 7+8 can ship in v5.5.1 if scope needs to land sooner.

---

## 15. Kill-Switch Metrics

Following your existing Realization platform discipline:

- **End of Phase 3:** Maria, Antonio, and Bruno all running through the kernel (not bypassing it) on at least one real Burtucala or HomeAid workflow
- **End of Phase 5:** Complete a real mission start-to-finish in the new workspace without touching n8n, the database, or a terminal
- **End of Phase 6:** Dreaming produces useful proposals 3 days running; approval rate >70% for DEFAULT_PROPOSE categories
- **End of Phase 7:** One F&F user onboards via VPS and runs their own mission without your help
- **End of Phase 8:** Voice capture from your phone ingests to FABRIC and shows in your morning Dream Inbox

**Hard kill switch:** if Phase 1+2 takes more than 6 weeks, the abstraction is wrong → collapse layers and retry.

---

## 16. Open Questions

1. **Migration UX from v5.2.1 to v5.5.0** — the most fragile moment. One-command `realize-os migrate-to-5.5` with mandatory backup beforehand. Concrete steps still to specify.

2. **Multi-tenant storage model on VPS** — schema-per-tenant in Postgres vs row-level security. Recommendation: schema-per-tenant for stronger isolation; switch only if it becomes operationally heavy.

3. **Cytoscape.js vs react-force-graph for v5.5.0 launch** — Cytoscape is more capable; react-force-graph is faster to integrate. Recommendation: ship with react-force-graph in v5.5.0, upgrade to Cytoscape in v5.5.1 if/when you need the advanced features.

4. **Dream Inbox email digest** — opt-in or opt-out by default? Recommendation: opt-in, surfaced in the first-time-install wizard.

5. **Quarterly Genesis cycle scheduling** — automatic every 90 days, or manual trigger? Recommendation: automatic with one-cycle defer option.

6. **Cosmograph for large-graph upgrade path** — Cosmograph's core is free but advanced features are commercial. Confirm BSL 1.1 compatibility before adopting if you cross the scale boundary.

7. **Honcho dependency decision** — pull `honcho` directly for user modeling, or implement equivalent inside User SOUL? Recommendation: implement inside SOUL; Honcho is great but adds another moving piece.

8. **Voice always-listening UX** — what's the wake-word phrase? "Realize" is too generic. Consider "Hey RealizeOS" or a custom user-chosen phrase.

---

## 17. Appendices

### Appendix A — Semantic Tag Vocabulary (initial)

See `docs/fabric-semantic-tags.md` (to be created in Phase 0).

| Tag | Required attrs | Optional attrs | Schema |
|---|---|---|---|
| `<decision>` | status, date | reviewers, ventures | `docs/fabric-schemas/decision.json` |
| `<commitment>` | by, to, deadline | status | `docs/fabric-schemas/commitment.json` |
| `<risk>` | level, status | mitigation | `docs/fabric-schemas/risk.json` |
| `<insight>` | date | source-mission | `docs/fabric-schemas/insight.json` |
| `<contact>` | ref | role | `docs/fabric-schemas/contact.json` |
| `<deadline>` | when | for | `docs/fabric-schemas/deadline.json` |
| `<question>` | date | for | (free-form) |
| `<assumption>` | confidence | needs-validation | (free-form) |
| `<reference>` | url-or-doi | accessed | (free-form) |
| `<draft>` | (none) | finalize-by | (free-form) |

### Appendix B — Runtime Adapter Contract (detailed)

To be written as JSON Schema in `contracts/runtime-adapter.schema.json` in Phase 0.

### Appendix C — Dream Proposal Schema

```yaml
id: dream-2026-05-21-curator-skill-001
cycle: reflex | curator | synthesis | genesis
created_at: ISO8601
proposed_by: dream-engine
category: skill_consolidation | skill_create | prompt_refine | router_rule
          | fabric_hygiene | workflow_extract | soul_refine | tag_evolve
          | drift_correction | other
trust_level_applied: ALWAYS_PROPOSE | DEFAULT_PROPOSE | AUTO_IF_CONFIDENCE_HIGH | ALWAYS_AUTO
status: pending | approved | rejected | deferred | auto-applied | reverted
title: string
rationale: markdown
diff:
  - operation: create | update | delete
    path: string
    content_before: optional string
    content_after: optional string
evidence:
  - mission_id: string
  - event_log_ref: string
  - ...
expected_impact:
  token_cost_reduction: optional percentage
  maintenance_burden: optional integer (file count delta)
  risk: low | medium | high
confidence: 0.0-1.0
auto_apply_threshold: optional 0.0-1.0
applied_at: optional ISO8601
applied_commit: optional git SHA
reverted_at: optional ISO8601
revert_reason: optional string
```

### Appendix D — File Layout for v5.5.0

```
realize_core/
├── storage/
│   ├── fabric.py            # FABRIC + git integration (pygit2)
│   └── ...
├── synapse/                 # NEW
│   ├── indexer.py
│   ├── toc.py               # L1
│   ├── search.py            # L2 (FTS5 + sqlite-vec)
│   ├── tool_catalog.py      # L3
│   ├── mission_memory.py    # L4
│   ├── graph.py             # graph query primitives
│   └── watcher.py           # watchdog integration
├── runtimes/                # NEW (Runtime Adapter Layer)
│   ├── base.py              # AgentRuntime Protocol
│   ├── internal.py          # wraps existing realize_core/agents/
│   ├── hermes.py
│   ├── claude_code.py
│   ├── codex.py
│   ├── gemini_cli.py
│   ├── openclaw.py
│   └── grok.py
├── routing/                 # NEW (Smart Kanban Router)
│   ├── router.py
│   ├── rules.py
│   └── learning.py
├── dreaming/                # NEW
│   ├── reflex.py
│   ├── curator.py
│   ├── synthesis.py
│   ├── genesis.py
│   ├── trust_policy.py
│   ├── proposal.py
│   ├── inbox.py
│   └── gepa_adapter.py
├── channels/
│   ├── voice.py             # NEW
│   └── ...
├── soul/                    # extend existing per-agent SOUL
│   ├── user.py              # NEW user-level SOUL
│   └── agent.py             # existing
└── ...

ventures/
├── _brand/                  # NEW brand-level shared content
└── <venture-key>/
    ├── .git/                # NEW per-venture git repo
    └── F-A-B-R-I-C/...

dashboard/
└── src/
    ├── workspace/           # NEW three-pane workspace UI
    ├── graph/               # NEW Cytoscape.js knowledge map
    ├── dream-inbox/         # NEW
    └── ...

mobile/                      # NEW React Native + Expo app
└── ...

docs/
├── v5.5.0-design.md         # THIS DOCUMENT
├── fabric-semantic-tags.md  # NEW
├── fabric-schemas/          # NEW
│   ├── decision.json
│   └── ...
├── adr/                     # NEW architecture decision records
└── ...
```

---

## Closing

This is v3 of the master design. It consolidates all decisions through May 2026.

Major items deferred to v5.5.1 or v5.6.0 if scope pressure mounts:
- Synthesis and Genesis dreaming cycles (Reflex + Curator give most value)
- Cytoscape.js upgrade from react-force-graph
- Mobile iOS port
- Honcho dependency (use SOUL instead)

If you reject any decision here, mark it inline in the doc and re-derive downstream implications. The doc is meant to live in `docs/v5.5.0-design.md` and evolve with the codebase.

---

*End of master design document.*
