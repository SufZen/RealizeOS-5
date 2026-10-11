# ADR 0004 — RealizeOS Is the Engine of a Field Practice

- **Status:** Accepted
- **Date:** 2026-10-11
- **Branch:** `docs/direction-2026-10`
- **Deciders:** Asaf (owner)
- **Relates to:** `_bmad/direction-2026-10.md` (full reasoning) and `_bmad/project-context.md` § Product Direction (internal planning docs, not published). Supersedes ADR-001 Platform Strategy (internal, March 2026).

## Context

ADR-001 (March 2026) positioned RealizeOS as an "intelligence-depth platform". It argued that multi-entity identity, layered prompts, creative pipelines and self-evolution were defensible, and that channel breadth was not.

By October 2026 that premise no longer holds:

- Agents rebuild applications on demand, so features are not a moat.
- General agents (Claude Cowork, Grok Bot, ChatGPT) already work across files, browsers and connectors and run scheduled tasks. They improve every month.
- Grok Bot now routes each task to the best model across labs. Model routing, one of our "intelligence" features, is a commodity.

Our working hypothesis is that what they don't provide well is a specific company's owned memory and rules, governed action with an accountable human in the loop, domain method for a particular field, and a practice that delivers change inside an organization. These are hypotheses, not established moats; the durable value we can defend is a verified delivery method, accumulated client decisions, trusted operation and adoption. The business is already selling those things: a free core, a paid Audit Sprint, installation, and a real-estate and AEC audience.

## Decision

1. **Role.** RealizeOS is the engine of Realization's field practice (audit → implement → operate → partners). It is the client-owned company brain (FABRIC) and the governed action layer that the practice installs and maintains. The core stays free under BSL 1.1. Revenue comes from outcomes and continuity, not licenses.
2. **Focus.** For the next 6–12 months we build only for real-estate development, architecture and planning firms, and construction (AEC), Israel ↔ Portugal/EU. Generic templates keep working but get no new investment.
3. **Interface: agents in, people out.** The MCP server is the primary surface for agents. People get a slim, Hebrew-first surface (approvals, trail, projects, the value report) and WhatsApp. We stop building general chat and channel features.
4. **Story filters.** Every story passes the seven filters in the constitution's Product Direction section (`_bmad/project-context.md`), or records why it does not. Maintenance and security work (isolation, data loss, CI, security, dependencies) is exempt from the client-case filter and states the risk it prevents instead.

## Alternatives considered

| Alternative | Why not |
|---|---|
| **Standalone software product** (license or hosted revenue first) | It competes head-on with general agents that are better funded and improve faster. The BSL core already gives distribution; a license business would need exactly the feature breadth that no longer protects anything. |
| **Dual track, equal weight** (product company and practice in parallel) | It splits a very small team. The practice is what generates the field cases that make the product worth having, so it has to come first. |
| **Stay horizontal** ("AI operations for any multi-venture business") | Horizontal is where the general agents are strongest. Depth in one field gives packs, language and trust that we expect to be harder to copy, a claim the first paid engagements have to confirm. |
| **Own app stays the primary interface** | Our chat and channels would always trail the labs' apps. People should meet RealizeOS where they already work (their agent, WhatsApp, a few focused pages). |
| **MCP only, no people-facing surface** | Approvals, the trail and the value report have to be seen by non-technical people, often in Hebrew, often on a phone. |

## Consequences

- **Roadmap.** The post-webinar phases of the 5.7.0 release plan (`_bmad/release-5.7.0-plan.md`) are reordered:
  - New STORY-37 bring-your-own-agent, STORY-38 value report, STORY-39 engagement kit and STORY-40 surface diet.
  - STORY-27 drops the LLM goal planner. STORY-36 (trust page) moves up. STORY-32 (Microsoft 365) waits for a paying client.
- **Freeze.** These areas get no new feature investment but keep working and keep their tests. Security and dependency maintenance still apply:
  - General chat beyond what demos need
  - More sophisticated model routing
  - Telegram and new channels
  - Expanding Dreaming and Evolution
  - Generic templates
  - The README roadmap items: voice, mobile, Cytoscape graph, host-satellite sync, full workspace redesign

  Removing anything happens only through STORY-40, with usage evidence and the owner's approval. Tests for a removed feature are retired with it; coverage of supported behaviour must not drop.
- **Architecture is unchanged.** SQLite only, SSE only, file-based FABRIC and human-centered governance all stand. If anything, the decision strengthens them, because ownership and governance are now the product.
- **Marketing** talks about owned memory, control and field results, not feature lists. The README is updated after the webinar as part of STORY-40.
- **Risk.** The practice depends on people, so growth is bounded by delivery capacity. The engagement kit (STORY-39) and partners are how that bound is raised without returning to a feature race.
- **Validation.** Before committing to every post-webinar story, we measure three paid Audit Sprints (conversion, client-visible outcome, maintenance effort). STORY-37 proves one real client agent end to end (scoped reads, held writes, approval, restart, export) before a second is added. Value-report numbers come from observed baselines and confirmed savings, not estimates.
