# Feature Specification: Close the Dreaming Loop — Scheduled Curator, Apply-Loop, Reflex

**Feature Branch**: `feat/agentic-governance` (feature `004-close-dreaming-loop`)

**Created**: 2026-06-13

**Status**: Draft

**Input**: User description: "Make the engine act, not just think — automatically generate proposals (Curator), write approved proposals back to FABRIC safely and reversibly (apply-loop), and learn from missions (Reflex)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Apply approved proposals to FABRIC (Priority: P1)

When a proposal is approved (by the operator, or auto-approved by the trust policy), its change is written into FABRIC, the proposal is marked `applied`, and the change is recorded as a reversible git commit plus an event-log entry.

**Why this priority**: Today approval does nothing — `DreamInbox.approved()` has no consumer. Without the apply-loop the entire Dreaming subsystem (and the email digest) is decorative.

**Independent Test**: Approve an `add_tag` proposal for a known entity, run the apply-loop, and assert the tag is present in the entity's FABRIC frontmatter, a `dream:`-prefixed git commit exists, the proposal `status` is `applied` with the commit SHA recorded, and an event is logged.

**Acceptance Scenarios**:

1. **Given** an approved `add_tag` proposal, **When** the apply-loop runs, **Then** the tag is written to the entity, the proposal becomes `applied` with `applied_commit` set, and a `dream:` git commit + event-log entry are created.
2. **Given** an approved proposal whose `action` is on the hard deny-list (`delete_entity`, `modify_decision`, `send_message`) OR whose target is `F-foundations` or a committed `decision`, **When** the apply-loop runs, **Then** it is NOT applied; it is blocked and logged with a reason.
3. **Given** dry-run mode, **When** the apply-loop runs, **Then** it reports what it would write but makes zero changes.

---

### User Story 2 - Scheduled Curator (Priority: P1)

The Curator runs automatically on a schedule, per venture, generating FABRIC-hygiene and enrichment proposals into the Dream Inbox — so the operator's email digest has real content without any manual trigger.

**Why this priority**: Without scheduling, proposals only appear when someone runs the CLI; the "supervise by exception" model never produces anything to supervise.

**Independent Test**: With the Curator flag enabled and a venture containing stale commitments / untagged entities, advance the scheduler and assert ≥1 pending proposal appears in that venture's Dream Inbox with no manual trigger.

**Acceptance Scenarios**:

1. **Given** the Curator is enabled and a venture has hygiene candidates, **When** the scheduled run fires, **Then** ≥1 proposal is submitted to the Dream Inbox for that venture.
2. **Given** the Curator flag is OFF (default), **When** the system starts, **Then** no Curator schedule is registered and behavior is unchanged.

---

### User Story 3 - Reflex after missions (Priority: P2)

After a message/mission creates or modifies a FABRIC entity, the Reflex cycle proposes low-risk enrichments (tags, refs, missing fields) without blocking or delaying the user's response.

**Why this priority**: Keeps context fresh at the moment of change, but it is additive — the loop is already valuable with Curator + apply.

**Acceptance Scenarios**:

1. **Given** Reflex is enabled and a message produced/modified an entity, **When** the response completes, **Then** Reflex enrichment proposals are submitted asynchronously and the user response is unaffected.

---

### Edge Cases

- Apply handler missing for an action → skip with a logged "unsupported action" reason; never crash.
- FABRIC write fails mid-apply → no partial commit; proposal stays `approved`; error logged.
- Git commit fails → the write is rolled back / not marked applied; error logged.
- Curator/Reflex raises → isolated; never crashes the scheduler or the request pipeline.
- A proposal references an entity that no longer exists → skip + log.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The apply-loop MUST act only on proposals with `status == approved`.
- **FR-002**: The apply-loop MUST dispatch by `action` to a handler performing the corresponding FABRIC write via `fabric/crud.py`. v1 supports the safe, reversible action set: `add_tag`, `add_ref`, `annotate_entity`, `update_summary`, `flag_stale_commitment`, `flag_orphan`. Unsupported actions are skipped with a logged reason (left for a later increment).
- **FR-003**: The apply-loop MUST refuse to apply any hard-deny action (`delete_entity`, `modify_decision`, `send_message`) and any write targeting `F-foundations` or a committed `decision` entity — regardless of `status` — enforced at apply time, not only at proposal time.
- **FR-004**: Each applied change MUST be a git commit with a `dream:` prefix (reversible) and MUST set `status = applied` with the commit SHA recorded on the proposal.
- **FR-005**: Each apply, skip, and failure MUST be recorded to the event log.
- **FR-006**: The apply-loop MUST support a dry-run mode that computes intended writes but performs none.
- **FR-007**: The Curator MUST run on a configurable schedule (default daily), per venture, behind `features.dreaming_curator` (default OFF); when OFF, no schedule is registered and existing behavior is unchanged.
- **FR-008**: Reflex MUST run after entity-producing messages when `features.dreaming_reflex` (default OFF) is enabled, proposing only low-risk enrichments, asynchronously, never blocking or delaying the user response.
- **FR-009**: CLI MUST allow manual apply of approved proposals (`realize-os fabric apply [--dry-run]`) and manual Curator run (existing `realize-os fabric dream`).
- **FR-010**: A failure in any cycle (curator, reflex, apply) MUST be isolated and never crash the request pipeline or the scheduler.

### Key Entities *(include if feature involves data)*

- **DreamProposal** (existing): reuse; ensure `applied_commit` and `applied_at` are populated on apply (add fields if absent; `ProposalStatus.APPLIED` already exists).
- **ApplyResult**: per-proposal outcome — `proposal_id`, `outcome` (applied | skipped | blocked | failed), `reason`, `commit_sha`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An approved `add_tag` proposal results in the tag present in the entity's FABRIC frontmatter, a `dream:` git commit, and `status=applied` with `applied_commit` set.
- **SC-002**: A proposal targeting `F-foundations` or a committed `decision` is never applied (blocked + logged), even when `status=approved` — 100% of such cases.
- **SC-003**: With the Curator enabled, a scheduled run produces ≥1 Dream Inbox proposal for a venture with hygiene candidates, with no manual trigger.
- **SC-004**: Dry-run performs zero FABRIC writes and zero git commits while reporting intended actions.
- **SC-005**: An injected failure in apply/curator/reflex never crashes the API or scheduler (the process stays healthy).
- **SC-006**: Every applied change is reversible via git — reverting the `dream:` commit and rebuilding restores the prior state.

## Assumptions

- Reuses `fabric/crud.py` (writes), FABRIC git versioning (`pygit2`), `DreamInbox.approved()`, `CuratorCycle`, `ReflexCycle`, and the existing trust policy hard-denies in `dreaming/policy.py` (`delete_entity`/`modify_decision`/`send_message` are already `DENY`).
- Scheduling uses `extensions/cron.py` (APScheduler) for true daily timing, default OFF — chosen over the interval `CronScheduler` to avoid the dual-scheduler drift flagged in the 2026-06-13 audit; a single scheduler choice will be finalized in the plan.
- v1 apply handlers cover only the safe action set above; creative/structural actions (`merge_entities`, `create_insight`, `suggest_decision`) are surfaced for review but deferred for application to a later increment.
- This builds on the email digest (003), which surfaces the proposals this loop generates and applies.
