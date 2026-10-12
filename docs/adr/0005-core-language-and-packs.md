# ADR 0005 — One Core Language, Profession and Market Packs

- **Status:** Accepted
- **Date:** 2026-10-13
- **Branch:** `docs/aec-core-and-packs`
- **Deciders:** Asaf (owner)
- **Amends:** [ADR 0004](0004-field-practice-engine.md), decision 2 (focus) and the "Hebrew-first" wording in decision 3. Decisions 1 and 4 of ADR 0004 stand unchanged.
- **Relates to:** [spec 010](../../.specify/specs/010-core-language-and-packs/spec.md) (the core language and pack format), [spec 002](../../.specify/specs/002-fabric-entity-schemas/spec.md) (soft FABRIC schemas), and the private strategy board of 12–13 October 2026.

## Context

ADR 0004 fixed the focus for 6–12 months on real-estate development, architecture and construction in Israel ↔ Portugal/EU, with a Hebrew-first surface. Working through the strategy board surfaced two problems with that framing:

1. **The target users differ more by profession than by country.** A developer checking a payment claim, an architect logging a client change and an investor reconciling a quarterly report do different work. A developer in Lisbon and one in Tel Aviv do much the same work. A single "AEC template" serves none of them well.
2. **A fixed geography limits the product for no structural reason.** Israel is where the first clients are, but the professions are similar across countries. AI agents can already read any country's regulations in any language. What they can't do is make that knowledge trustworthy or organise it around a firm's own rules.

The current code has the parts but not the structure. Templates (`realize_core/templates/marketplace.py`) carry a manifest with `version`, `vertical` and `requires`, but scaffolding copies them into a venture once and never updates them. Extensions (`realize_core/extensions/`) add code: tools, channels, integrations, hooks. FABRIC holds the firm's own knowledge, and a venture's `locale` drives Hebrew and RTL. Nothing layers or composes.

## Decision

1. **Four layers.** RealizeOS is organised as a shared **core**, **profession packs**, **market packs** and the **firm layer**. Where they disagree, the more specific layer wins: firm over market, market over profession, profession over core. Every resolved value records which layer it came from.
2. **One core language.** The core defines a small set of typed objects that every pack and every agent speaks (spec 010): project, party, document and source, requirement, money event, milestone, change, decision and approval, issue and risk. Packs extend these objects and never fork them.
3. **Packs are content.** A pack is files: agents, skills, soft schemas, a glossary, rule cards, document templates and measures. Executable code stays in the core and in extensions. This keeps the core small (ADR 0004 filter 5) and lets partners and agents author packs.
4. **Packs are linked, not copied.** A venture references packs by id and version, and upgrades are explicit. The existing template scaffolding keeps working (`python cli.py` paths are preserved) and writes the pack references.
5. **Market-agnostic product, verified market knowledge.** The product doesn't assume a country or a language. Market knowledge carries a verification level on a five-step ladder:
   - **0 · General knowledge:** no market pack, labelled unverified.
   - **1 · Drafted:** drafted by an agent from public sources, with links and dates.
   - **2 · Reviewed:** a local professional has corrected and approved it.
   - **3 · Maintained:** a partner in that market keeps it current.
   - **4 · Field-proven:** used in a paid engagement.

   Every answer that relies on market facts shows the level. Hebrew and RTL remain first-class; they are the first locale, not the only one.
6. **Focus is a set of beachhead cells.** A target market is one profession in one market. The owner keeps a coverage matrix (reach) and, separately, names the two or three cells where paid engagements and case studies happen first. Both are reviewed each quarter. The first market pack is Israel and the first profession pack is the developer, because the first engagements are there.
7. **First value is self-serve, compounding value is practice-led.** One free workflow runs in the user's own agent in any market (verification level 0 or higher). The brain, governance, verified market packs and adoption stay with the practice and its local partners.
8. **The obvious-choice check.** Alongside the seven story filters, every customer-facing story answers six questions:
   - Does it save measurable time in the first week?
   - Does it work in the agent and channel the user already has?
   - Does it reduce a risk they already fear?
   - Does it get better with every project?
   - Can they leave with it?
   - Does it cost less than the hours it replaces?

## Alternatives considered

| Alternative | Why not |
|---|---|
| **Keep one AEC template per country** | Multiplies work by markets × professions, and every copy drifts. No shared language means no decision can travel between parties. |
| **One generic template with prompts per profession** | Puts domain method in prompts, where it can't be versioned, verified or reviewed by a professional. Agents already do generic well. |
| **Packs as code plugins** | Every pack would need engineering review and tests, and the surface would grow with every market. Partners couldn't author them. |
| **Stay Israel-only until proven** | The structure costs little extra if it is designed in now, and costs a rewrite later. The go-to-market can still start narrow (decision 6). |
| **Let agents answer market questions from their own knowledge, no packs** | That is level 0, and it stays available. On its own it gives no sources, dates, review or accountability, which is what professionals pay for. |

## Consequences

- **What stays:** SQLite only, SSE only, file-based FABRIC, MCP as the primary agent surface, human-centered governance, the seven filters, the freeze list, and the practice model.
- **New work** (stories STORY-41 to STORY-46):
  - Core language v0 schemas.
  - Pack manifest and run-time cascade.
  - Splitting the developer template into a developer pack and an Israel market pack.
  - Decision log v0.
  - An agent-drafted second market pack.
  - The self-serve wedge pilot.
- **Templates:** generic templates stay frozen (ADR 0004). The real-estate developer and architecture templates become the seeds of profession packs.
- **Risks:**
  - Over-designing the core. Mitigation: the core holds only what every profession in every market needs, and it grows from packs that came out of real engagements.
  - Pack sprawl. Mitigation: a pack is labelled field-proven only after a paid engagement, and the beachhead cells decide which packs get built.
  - Trusting AI-drafted market knowledge too early. Mitigation: the verification ladder is visible on every answer.
- **Validation:** the bet holds if an agent can draft a second market pack for the developer profession where a local professional corrects fewer than one in five drafted facts and no core code changes (STORY-45).
- **Open:** the owner's coverage matrix currently marks 26 cells as beachhead, which describes reach rather than a starting point. The two or three first cells still need to be named; the proposal is Developer·Israel, Consultant·Israel and Developer·Portugal.
