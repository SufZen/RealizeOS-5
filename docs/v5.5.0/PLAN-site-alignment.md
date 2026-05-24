# PLAN A — Product repo site alignment (`SufZen/RealizeOS-5`)

> Part of the RealizeOS 5.5.0 relaunch, split across two repos. This plan is for the **product repo**. The companion **website** plan lives in `SufZen/realizeos-site` at `docs/relaunch/PLAN-5.5.0-website.md`.
>
> **Repo:** `/home/user/RealizeOS-5` · **Branch:** `claude/amazing-albattani-He3xD`

## Goal

Make the GitHub repo the website links to back up every site claim, and **produce the cross-repo handoff artifact `docs/v5.5.0/SITE-CLAIMS.md`** that the website agent consumes as its single source of truth. Light-touch — no architecture changes.

## Shared context

RealizeOS is moving from a paid, closed-source package model to an **open-source (BSL 1.1) product + services** model, timed to **v5.5.0** (free core; monetize via guided installation sessions + vertical consulting; relaunched website).

**v5.5.0 is already built and on remote `main`** (Sprints 1–8; `VERSION` already bumped `5.2.1 → 5.5.0` in commit `4596be3`). The local checkout may be behind — sync first. Shipped now (present as **available**):

- **FABRIC Entity System** (the Heart) — entities w/ provenance/trust, markdown↔entity round-trip, 3 reference mechanisms, soft JSON-Schema validation, `docs/fabric-schemas/` (Sprint 1).
- **Synapse knowledge index** — L1 Hot TOC, L2 FTS5 search, graph queries, L4 mission memory (Sprint 2).
- **Event Log + SOUL** — JSONL append-only audit w/ SSE; User/Agent SOUL identity (Sprint 3).
- **Runtime Adapter Layer + Registry + FABRIC REST API** — `AgentRuntime` Protocol, registry w/ health polling + task matching, `/api/fabric/*` (Sprint 4).
- **Mission Engine (Spine)** — 8-state mission/step machine, planning, runtime routing, cost tracking (Sprint 5).
- **Dreaming subsystem** — Trust Policy (full-auto/propose/deny), Reflex + Curator, Dream Inbox (Sprint 6).
- **FABRIC operator CLI** — `realize-os fabric` (lint, reindex, stats, search, toc, dream) (Sprint 8).
- **Dashboard pages** — `/missions`, `/knowledge` (Knowledge Map), `/dreams` (Dream Inbox), styled with the shared `--rz-*`/`.fx-*` design system (Sprint 7). Real screens — ideal site demo media.
- **Roadmap (NOT shipped — label as "coming," never available):** Voice channel (STT/TTS), full three-pane Workspace UI redesign, Cytoscape visual graph, React Native mobile companion, host-satellite sync.

**Positioning thesis:** "You own the Heart (FABRIC knowledge graph + event log + identity) forever; agent runtimes, models, channels, and even the dashboard are swappable adapters; local-first."

## Cross-repo handoff (your most important deliverable)

Produce `docs/v5.5.0/SITE-CLAIMS.md`, committed + pushed to `claude/amazing-albattani-He3xD`. It is the single source of truth for every product claim the site makes:
- Exact `VERSION` and headline numbers (runtime adapters, channels, Synapse tiers, FABRIC entity types, test count, etc.).
- **Verified** install commands — only those that actually work/publish.
- The **shipped-vs-roadmap matrix** (the lists above, confirmed against code).
- Dashboard **screenshots** of `/missions`, `/knowledge`, `/dreams` under `docs/v5.5.0/assets/` (or a note on how to capture them).

The website agent reads this file (local `/home/user/RealizeOS-5/docs/v5.5.0/SITE-CLAIMS.md` or via GitHub MCP `get_file_contents`). Tell the user when it's pushed so they can start the website agent.

## Steps

### A1. Sync & ground-truth (do first, unblocks the website plan)
1. Sync local checkout to remote `main` (it contains the shipped Sprint 1–8 work + `VERSION 5.5.0`), continue on `claude/amazing-albattani-He3xD`.
2. Verify each candidate install command actually works/publishes (npx `@realize-os/cli`, docker `ghcr.io/sufzen/realizeos-5`, `pip install realize-os`, curl/PowerShell). Note any not yet published.
3. Confirm exact headline numbers from code (runtime adapters registered, channels, Synapse tiers, FABRIC entity types in `docs/fabric-schemas/`, test count from CI).
4. Capture dashboard screenshots of `/missions`, `/knowledge`, `/dreams` (run the dashboard or use existing build) and commit under `docs/v5.5.0/assets/`.

### A2. Emit `docs/v5.5.0/SITE-CLAIMS.md`
Write the source-of-truth file: version + numbers, verified install commands, shipped-vs-roadmap matrix, screenshot paths. Commit + push.

### A3. README "What's new in 5.5.0"
Add a short section summarizing the AI-OS repositioning (own-the-Heart, runtime adapters, Synapse, Mission Engine, Dreaming, local-first) linking to `docs/v5.5.0/`. Label Voice/mobile/Workspace-redesign as roadmap. Mirror the site's wording.

### A4. `/design` showcase availability
The design-system README references `realizeos.ai/design` as the canonical visual spec and says an `index.html` is bundled. Confirm where that bundled page lives and document in `SITE-CLAIMS.md` what the site should serve at `/design`. (Building the route is the website plan's job; here just supply the asset/contents.)

### A5. Release-publish sanity
`VERSION` is already `5.5.0` and semantic-release is configured — confirm the tag/release actually publishes (the v5.2.0 line previously failed to publish artifacts; see CHANGELOG). Do **not** hand-bump versions.

### A6. Consistency pass
Ensure install commands, badges, and feature lists in the README exactly match `SITE-CLAIMS.md`.

## Verification
`SITE-CLAIMS.md` exists on the branch and is fetchable via GitHub MCP; every listed install command runs clean; screenshots render; README claims match `SITE-CLAIMS.md`; CI green; release publishes.

## Critical files
`VERSION`, `README.md`, `CHANGELOG.md`, `docs/v5.5.0/` (master-design, runtime-adapter-contract, fabric-* docs), `docs/fabric-schemas/`, dashboard source for screenshots, `docs/v5.5.0/SITE-CLAIMS.md` (new), `docs/v5.5.0/assets/` (new).

## Honesty rule
Only Sprint 1–8 capabilities are "available"; Voice, mobile, full Workspace redesign, visual graph, and host-satellite sync are roadmap. Commit and push to `claude/amazing-albattani-He3xD`. Do NOT open a PR unless asked.
