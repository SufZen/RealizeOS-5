# Feature Specification: Email Dream-Inbox Digest Channel

**Feature Branch**: `feat/agentic-governance` (feature `003-email-digest-channel`)

**Created**: 2026-06-13

**Status**: Draft

**Input**: User description: "Email-first supervision by exception — a daily workday digest of the Dreaming proposals awaiting my decision, grouped by venture, plus immediate alerts for urgent items."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Daily digest of pending proposals (Priority: P1)

Each workday morning the operator receives a single email summarizing the Dream Inbox proposals awaiting their decision, grouped by venture, so they can supervise by exception without opening the dashboard.

**Why this priority**: This is the core "email-first, approve-by-exception" value. Without it the operator must poll the app, which re-creates the bottleneck the whole initiative removes.

**Independent Test**: Seed N pending proposals across two ventures, run the digest job, and assert exactly one email is sent to the configured address containing each proposal's venture, action, title, confidence, and approve/reject links, grouped by venture.

**Acceptance Scenarios**:

1. **Given** ≥1 pending proposal, **When** the daily digest runs, **Then** exactly one email is sent to the configured recipient listing all pending proposals grouped by venture, each with title, action, confidence, and per-proposal approve/reject links.
2. **Given** proposals of differing confidence/impact, **When** the digest is composed, **Then** high-impact or low-confidence items appear in a "Needs your attention" section at the top.

---

### User Story 2 - Immediate alert for urgent items (Priority: P2)

When a proposal or event is flagged urgent, the operator gets an immediate email rather than waiting for the morning digest.

**Why this priority**: Time-sensitive items (e.g. a DENY-class action attempted, or an explicitly urgent proposal) must not wait up to 24h.

**Independent Test**: Emit an urgent proposal and assert an email is sent within the alert window regardless of the daily schedule, and that the item is de-duplicated against the next morning digest.

**Acceptance Scenarios**:

1. **Given** an item flagged urgent, **When** it is created, **Then** an immediate email is sent and the item is marked so it is not duplicated in the next digest.

---

### User Story 3 - Suppress when empty (Priority: P3)

If nothing is pending at digest time, no email is sent.

**Why this priority**: Avoids notification fatigue and preserves trust that an email means "something needs you".

**Acceptance Scenarios**:

1. **Given** zero pending proposals, **When** the digest runs, **Then** no email is sent and the run is recorded in the event log.

---

### Edge Cases

- Gmail send failure → retry with backoff, log to the event log, never crash the scheduler.
- Missing recipient or Google credentials → digest stays inert with a clear startup warning (no crash).
- Very large inbox → cap to top K per venture with a "+N more" link into the dashboard.
- Time zone / workdays → run only on configured workdays in the configured time zone.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an `EmailDigestChannel` implementing the `BaseChannel` contract (`start`/`stop`/`send_message`) as a push-only (outbound) channel.
- **FR-002**: System MUST compose a deterministic (non-LLM) digest from `DreamInbox.pending()`, grouped by venture, including per proposal: `cycle_type`, `action`, `title`, `confidence`, `created_at`, and approve/reject deep links.
- **FR-003**: System MUST send the digest via the existing `gmail_send` primitive to a configurable recipient.
- **FR-004**: System MUST run the digest on a configurable schedule (default: daily 08:00 Europe/Lisbon, workdays only) with no manual trigger required.
- **FR-005**: System MUST suppress the email when zero items are pending.
- **FR-006**: System MUST send an immediate email for items flagged urgent, de-duplicated against the next digest.
- **FR-007**: System MUST be disabled by default behind a feature flag + config; when enabled without a valid recipient/credentials it MUST warn and stay inert.
- **FR-008**: System MUST record each send and each suppression to the event log for audit.
- **FR-009**: Approve/reject links MUST target the existing `/api/dreams/{proposal_id}/approve|reject` endpoints (or their dashboard routes).
- **FR-010**: The digest MUST surface a "Needs your attention" section for high-impact or low-confidence items at the top.

### Key Entities *(include if feature involves data)*

- **DigestItem**: a read-only view over a `DreamProposal` — `proposal_id`, `venture`, `cycle_type`, `action`, `title`, `confidence`, `created_at`, approve/reject links.
- **DigestConfig**: `recipient`, `schedule` (time + time zone + workdays), `enabled`, urgent thresholds, top-K cap.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With ≥1 pending proposal, a correctly-grouped digest email arrives at the configured address within 1 minute of the scheduled time.
- **SC-002**: With 0 pending proposals, no email is sent (100% suppression).
- **SC-003**: The operator can approve or reject a proposal directly from the email links without first opening the app.
- **SC-004**: A Gmail send failure never crashes the scheduler; it is retried and logged.
- **SC-005**: Enabling/disabling and changing recipient/schedule require only configuration — no code change.

## Assumptions

- Reuses `DreamInbox` (`dreaming/inbox.py`), `gmail_send` (`tools/google_workspace.py`), `BaseChannel` (`channels/base.py`), and a scheduler (`channels/scheduler.py` `CronScheduler` or `extensions/cron.py`) — exact scheduler chosen in the plan, but only ONE scheduler is wired to avoid drift.
- Defaults (owner decision, 2026-06-13): recipient `info@realization.co.il`; daily 08:00 Europe/Lisbon, workdays; deterministic rendering; suppress when empty.
- Dream Inbox proposals already carry `venture`, `action`, `title`, `confidence`, `created_at` (verified in the 2026-06-13 audit) and approve/reject endpoints exist.
- This feature only READS the Dream Inbox; it does not approve/apply proposals (that is the separate apply-loop gap).
