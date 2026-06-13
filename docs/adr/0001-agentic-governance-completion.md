# ADR 0001 — Complete and Wire the Agentic Governance Engine

- **Status:** Proposed
- **Date:** 2026-06-13
- **Branch:** `feat/agentic-governance`
- **Deciders:** Asaf (owner)
- **Relates to:** Constitution §V (Trust Is Earned), §VI (Spec-Driven), master design §9 (Dreaming), §4 (Mission Engine), §3.6 (Identity & Policy)

## Context

The goal is an internal operating system where per-venture agent teams execute real work under a shared governance layer, the owner supervises **by exception** (email-first), and task categories earn more autonomy as a measurable trust signal proves them — without the owner becoming a full-time approver.

A code audit of `realize_core/` (v5.5.2) shows that **almost all of this already exists as shipped modules** — but the modules are **not wired into the live execution pipeline**, and two parallel trust systems coexist. The work is therefore **integration and configuration**, not new subsystem design.

### What already exists (do not rebuild)

| Capability | Where | Status |
| --- | --- | --- |
| Trust policy (FULL_AUTO / PROPOSE / DENY) | `dreaming/policy.py` | Implemented |
| 5-tier trust ladder + approval gates | `governance/trust_ladder.py`, `governance/gates.py` | Implemented |
| Dreaming cycles (Curator, Reflex) | `dreaming/curator.py`, `dreaming/reflex.py` | Implemented |
| Dream Inbox (JSONL store + approve/reject + API) | `dreaming/inbox.py`, `realize_api/routes/dreams.py` | Implemented |
| Event log / audit trail | `fabric/event_log.py` | Implemented |
| Memory + index ("the reindex") | `fabric/synapse.py` (L1–L4) | Implemented |
| Self-evolution (gap detection, prompt/skill refine) | `evolution/*` | Implemented |
| RBAC + agent guardrails + persona tool gating | `security/users.py`, `agents/guardrails.py`, `tools/gating.py` | Implemented |
| Runtime Adapter contract + registry + internal adapter | `runtimes/*` | Implemented |
| Gmail send primitive | `tools/google_workspace.py::gmail_send` | Implemented |
| Channel base + cron scheduler | `channels/base.py`, `channels/scheduler.py` | Implemented |

### The real gaps (this initiative)

The audit identified that the above modules are **not connected**. The gaps, in priority order:

1. **Email digest channel — missing.** No `channels/email.py`. The Dream Inbox is never surfaced by email (master design §9.6). `gmail_send` and `DreamInbox.pending()` exist; a channel + scheduled digest is needed.
2. **Dreaming loop not scheduled / not closed.** Curator runs only on manual CLI/API trigger; Reflex is never called post-mission; **approved proposals are never applied to FABRIC** (`DreamInbox.approved()` has no consumer) and `expire_old()` is never scheduled. The loop generates proposals but never mutates the graph.
3. **Enforcement not wired.** `governance/gates.py::is_gated()`, `governance/trust_ladder.py::check_trust()`, and `agents/guardrails.py::check_guardrails()` are never called from `base_handler.py::process_message()`. Gates exist but do not stop anything yet.
4. **Two parallel trust systems.** `dreaming/policy.py` (3-level, JSONL, for dream proposals) and `governance/{trust_ladder,gates}.py` (5-tier, SQLite `approval_queue`, for tool actions) overlap in vocabulary (e.g. `send_email`) with no reconciliation. They must be unified behind one policy surface.
5. **Per-venture trust/permission config — missing.** `TrustPolicy.load()` reads one global `shared/trust-policy.yaml`; `realize-os.yaml` systems have no `trust:` stanza. Ventures cannot have different policies.
6. **Runtime registry empty + no HermesAdapter.** `RuntimeRegistry` is created but `InternalAdapter` is never registered, and there is no `HermesAdapter`. Hermes is not yet a governed peer runtime.

## Decision

Treat this as an **integration + configuration** effort on `feat/agentic-governance`, aligned to the existing constitution and master design — not a redesign. Concretely:

1. **Unify the trust surface.** Make `governance/` the single enforcement point; have `dreaming/policy.py` defer to it (or merge), so one per-category policy governs both tool actions and dream proposals. (Separate spec + ADR if it touches a contract.)
2. **Close the Dreaming loop:** schedule the Curator (daily) and fire Reflex post-mission; implement the **apply loop** (approved/auto proposals → FABRIC writes via `fabric/crud.py`, set `status=applied`); schedule `expire_old()`.
3. **Wire enforcement** into `base_handler.py::process_message()` / the LLM router: `check_trust` / `is_gated` before tool execution, `check_guardrails` on responses.
4. **Add the Email digest channel** (`channels/email.py` + a deterministic digest coroutine over `DreamInbox.pending()` + scheduler wiring). This is the first build (gap 1).
5. **Per-venture trust config:** `TrustPolicy.load_for_venture()` reading `systems/<venture>/trust-policy.yaml` with fallback to shared.
6. **Register `InternalAdapter` at startup; add `HermesAdapter`** (HTTP to Hermes :8642) implementing the `AgentRuntime` protocol.
7. **Pilot on Realization PT**, then merge to `main` on success (kill-switch metric: useful Dreaming proposals 3 days running, >70% approval on DEFAULT_PROPOSE).

Each item above gets its own `.specify/specs/NNN-*` spec before implementation, per Constitution §VI. Email digest is `003`.

## Consequences

- **Positive:** far lower risk and faster value than a build; reuses shipped, tested modules; the owner's private setup becomes the proof for the product (these are generic platform features that ship in the next release).
- **Positive:** unifying the two trust systems removes a real footgun (today an approval in one is invisible to the other).
- **Negative / risk:** wiring enforcement into the live pipeline changes runtime behavior; must be gated behind config flags and validated in the pilot before `main`. Applying proposals to FABRIC mutates the knowledge graph — ship behind the trust policy with `decision`/`F-foundations` hard-denied (already in `_DEFAULT_POLICY`).
- **Negative:** the dual-scheduler situation (`heartbeat` wired vs `channels/scheduler` + `extensions/cron` unwired) needs a single chosen scheduler to avoid drift.

## References

- Audit (2026-06-13): file-level evidence in the session record.
- Master design: `docs/v5.5.0/realizeos-v5.5.0-master-design.md` §9 (Dreaming + Trust Policy), §4 (Mission Engine), §3.6 (Identity & Policy), §6 (Channels).
- Constitution: `.specify/memory/constitution.md` §V, §VI, §VII.
