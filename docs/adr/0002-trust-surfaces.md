# ADR 0002 — Two Trust Surfaces: Knowledge (Dreaming) vs Tools (Governance)

- **Status:** Accepted
- **Date:** 2026-06-14
- **Branch:** `feat/agentic-governance`
- **Deciders:** Asaf (owner)
- **Relates to:** Constitution §V (Trust Is Earned), master design §9 (Dreaming + Trust Policy), §3.6 (Identity & Policy); supersedes ADR 0001 decision #1.

## Context

The ADR 0001 audit flagged "two parallel trust systems" as a footgun (gap #4) and
proposed to **unify** them — make `governance/` the single enforcement point and
have `dreaming/policy.py` defer to it or merge. On closer inspection during
implementation, the two systems do **not** in fact govern the same thing. They
govern two different layers of the OS, and merging them would conflate distinct
concerns and risk regressions in both — now-working, now-tested — paths.

There are two trust surfaces:

| Surface | Module | Governs | Levels | Read from |
| --- | --- | --- | --- | --- |
| **Knowledge (Dreaming)** | `realize_core/dreaming/policy.py` (`TrustPolicy`) | Self-evolving **KNOWLEDGE-WRITE** proposals from Dreaming cycles — `add_tag`, `update_summary`, `create_insight`, `modify_decision`, `delete_entity`, ... | `FULL_AUTO` / `PROPOSE` / `DENY` | per-venture `systems/<venture>/trust-policy.yaml` merged over `shared/trust-policy.yaml` and built-in defaults, via `TrustPolicy.load_for_venture()` |
| **Tools (Governance)** | `realize_core/governance/trust_ladder.py` (`check_trust`) | **TOOL execution** at runtime — `gmail_send` → `send_email`, `calendar_create_event`, `stripe_create_invoice` → `financial_action`, ... — now enforced by `governance/tool_gate.py` | `BLOCK` / `APPROVE` / `AUTO`, resolved from a 5-tier ladder at the system's current trust level | `config['trust']` (`level` + per-action `actions`) in `realize-os.yaml` |

The vocabulary overlaps superficially (both mention `send_message` / `send_email`),
which is what made them look mergeable. But the *objects* they protect are
different: one protects the **knowledge graph** from autonomous self-edits; the
other protects the **outside world** from autonomous tool calls.

## Decision

**Keep the two surfaces separate. Reconcile by documentation + a single read-only
overview, not by a code merge.** Concretely:

1. **Do not merge** `dreaming/policy.py` into `governance/`, and do not make either
   defer to the other. Each keeps its own vocabulary, levels, config source, and
   enforcement point. This supersedes ADR 0001 decision #1.
2. **Document the two-surface model** (this ADR) so the separation is intentional
   and discoverable rather than an accident of history.
3. **Provide one read-only overview**:
   `realize_core/governance/policy_overview.py::effective_policy(config, kb_path, venture)`
   returns both surfaces in one snapshot:
   - `"knowledge"`: the Dreaming policy as `{action: level}` (from
     `TrustPolicy(...).all_actions`).
   - `"tools"`: `{governance_action: decision}` (from `check_trust(action, config)`
     over the known governance actions).
   - `"trust_level"` and a human-readable `"summary"`.

   It uses **only public APIs**, never raises, and has **no side effects** — so it
   resolves the "no single place to see the effective policy" footgun without
   changing either system's behavior.

## Rationale — why separate, not merged

- **Different blast radius.** A Dreaming `FULL_AUTO` lets an agent edit the
  *knowledge graph*; a Governance `AUTO` lets an agent act on the *outside world*
  (send email, charge a card). Collapsing them would force a single level to mean
  two very different risks.
- **Different config lifecycles.** Knowledge policy is per-venture and merge-layered
  (`load_for_venture`); tool policy is a system-wide 5-tier ladder keyed off a
  single current trust level. They are tuned by different people at different
  cadences.
- **Different enforcement points.** Knowledge writes flow through the Dream Inbox
  (propose → review → apply); tool calls flow through `tool_gate.py` before
  execution. A merge would entangle two independently-tested pipelines.
- **Lower risk.** Both systems are now wired, working, and tested (ADR 0001 gaps
  3, 5, and the Dreaming loop are closed). A structural merge would put working,
  tested behavior at risk for no functional gain.

## Shared principles (the actual reconciliation)

Although the surfaces are separate, they share the same governing intent:

- **Constitution §V — Trust Is Earned.** Both default to caution and grant autonomy
  as a graduated signal: Dreaming defaults most actions to `PROPOSE`; the ladder
  starts new tool actions at `block`/`approve` and only reaches `auto` at higher
  trust levels.
- **Shared hard-deny intent.** Both encode irreversible / high-stakes actions as a
  hard stop by default: Dreaming `DENY`s `delete_entity`, `modify_decision`,
  `send_message`; the ladder `block`s or never-`auto`s `financial_action`,
  `phone_call`, `social_post`. Neither surface should ever silently auto-approve a
  destructive or externally-visible action.
- **One place to view both.** `policy_overview.effective_policy()` is the single
  read-only surface where an operator or dashboard sees both at once.

## Consequences

- **Positive:** removes the ADR 0001 footgun ("an approval in one is invisible to
  the other") by giving one combined view, while preserving the clean separation of
  concerns and avoiding a risky merge of two tested subsystems.
- **Positive:** the two-surface model is now explicit; future contributors won't
  re-attempt a merge or assume a single level governs everything.
- **Neutral:** `effective_policy()` is read-only and additive — it introduces no new
  enforcement path and changes neither system's behavior.
- **Negative / risk:** the two surfaces can still drift in *vocabulary* (e.g.
  `send_message` vs `send_email`). This is accepted; the overview makes any drift
  visible, and a future ADR may introduce a shared naming convention if needed.

## References

- ADR 0001 — `docs/adr/0001-agentic-governance-completion.md` (decision #1, gap #4).
- Knowledge surface — `realize_core/dreaming/policy.py` (`TrustPolicy`, `TrustLevel`).
- Tools surface — `realize_core/governance/trust_ladder.py` (`check_trust`,
  `TrustDecision`, `ACTION_MAP`), enforced by `realize_core/governance/tool_gate.py`.
- Overview — `realize_core/governance/policy_overview.py` (`effective_policy`).
- Constitution: `.specify/memory/constitution.md` §V.
