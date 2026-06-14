"""
Email Dream-Inbox Digest channel.

A push-only (outbound) :class:`BaseChannel` that emails a deterministic,
non-LLM digest of the pending Dream Inbox proposals — grouped by venture —
so the operator can supervise the Dreaming subsystem by exception without
opening the dashboard.

Design notes:
- ``start``/``stop`` are no-ops: this channel never listens, it only pushes.
- The Google client libraries are optional (extra ``gws``), so ``gmail_send``
  is imported lazily inside the send path. A missing dependency or missing
  credentials must NEVER crash the caller (scheduler) — failures are logged
  and surfaced as a ``False`` return / early return.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from realize_core.channels.base import BaseChannel, OutgoingMessage

if TYPE_CHECKING:
    from realize_core.dreaming.inbox import DreamInbox
    from realize_core.dreaming.policy import DreamProposal
    from realize_core.fabric.event_log import EventLog

logger = logging.getLogger(__name__)

# Proposals below this confidence are surfaced in the "NEEDS YOUR ATTENTION"
# section at the top of the digest.
_LOW_CONFIDENCE_THRESHOLD = 0.6

# Actions considered high-impact — they always land in the attention section
# regardless of confidence (destructive or decision-altering writes).
_HIGH_IMPACT_ACTIONS = frozenset(
    {
        "delete_entity",
        "modify_decision",
        "merge_entities",
        "suggest_decision",
        "send_message",
    }
)

_DEFAULT_SUBJECT = "RealizeOS Dream Inbox"


class EmailDigestChannel(BaseChannel):
    """Outbound-only channel that emails Dream Inbox digests via Gmail."""

    def __init__(self, recipient: str, base_url: str = "", system_key: str = ""):
        super().__init__(channel_name="email")
        self.recipient = recipient
        self.base_url = base_url.rstrip("/")
        self.system_key = system_key

    async def start(self) -> None:
        """No-op — this channel is push-only and never listens."""
        return None

    async def stop(self) -> None:
        """No-op — nothing to tear down for a push-only channel."""
        return None

    async def send_message(self, message: OutgoingMessage) -> None:
        """
        Send ``message.text`` to the configured recipient via ``gmail_send``.

        The subject is taken from ``message.metadata["subject"]`` or falls back
        to a default. Send failures are logged and swallowed — this method
        never raises (the scheduler must keep running).
        """
        if not self.recipient:
            self.logger.warning("EmailDigestChannel has no recipient configured; skipping send")
            return None

        subject = message.metadata.get("subject") or _DEFAULT_SUBJECT
        try:
            # Lazy import — google libs are an optional dependency.
            from realize_core.tools.google_workspace import gmail_send

            await gmail_send(to=self.recipient, subject=subject, body=message.text)
            self.logger.info("Sent email to %s (subject=%r)", self.recipient, subject)
        except Exception as exc:  # outbound send must never crash caller
            self.logger.error("Failed to send email to %s: %s", self.recipient, exc, exc_info=True)
        return None

    def health_check(self) -> dict:
        """Report whether a recipient is configured."""
        return {
            "name": self.channel_name,
            "healthy": bool(self.recipient),
            "details": {"recipient": self.recipient, "base_url": self.base_url},
        }


def _confidence_pct(confidence: float) -> str:
    """Render a 0..1 confidence as an integer percentage string."""
    try:
        return f"{round(float(confidence) * 100)}%"
    except (TypeError, ValueError):
        return "n/a"


def _created_date(proposal: DreamProposal) -> str:
    """Render the proposal creation date as YYYY-MM-DD (best effort)."""
    created = getattr(proposal, "created_at", None)
    if created is None:
        return ""
    try:
        return created.strftime("%Y-%m-%d")
    except (AttributeError, ValueError):
        return str(created)[:10]


def _needs_attention(proposal: DreamProposal) -> bool:
    """A proposal needs attention if it is low-confidence or high-impact."""
    if proposal.action in _HIGH_IMPACT_ACTIONS:
        return True
    try:
        return float(proposal.confidence) < _LOW_CONFIDENCE_THRESHOLD
    except (TypeError, ValueError):
        return False


def _render_item(proposal: DreamProposal, base_url: str) -> str:
    """Render a single proposal as a deterministic multi-line block."""
    title = proposal.title or "(untitled)"
    line = (
        f"  - [{proposal.cycle_type or '?'}] {proposal.action or '?'}: {title} "
        f"(confidence {_confidence_pct(proposal.confidence)}, created {_created_date(proposal)})"
    )
    approve = f"{base_url}/api/dreams/{proposal.proposal_id}/approve"
    reject = f"{base_url}/api/dreams/{proposal.proposal_id}/reject"
    return f"{line}\n      approve: {approve}\n      reject:  {reject}"


def build_dream_digest(
    proposals: list,
    base_url: str = "",
    top_k_per_venture: int = 10,
) -> str | None:
    """
    Build a deterministic plain-text digest from pending proposals.

    Returns ``None`` when ``proposals`` is empty. Otherwise returns a digest
    grouped by venture, with a "NEEDS YOUR ATTENTION" section at the top for
    low-confidence (<0.6) or high-impact items. Each venture is capped to
    ``top_k_per_venture`` items, with a "+N more" line when truncated.
    """
    if not proposals:
        return None

    base_url = base_url.rstrip("/")

    lines: list[str] = []
    lines.append(f"You have {len(proposals)} Dream Inbox proposal(s) awaiting your decision.")
    lines.append("")

    # ── Needs-your-attention section (rendered first, not grouped) ──
    attention = [p for p in proposals if _needs_attention(p)]
    if attention:
        lines.append("=== NEEDS YOUR ATTENTION ===")
        for proposal in attention:
            lines.append(_render_item(proposal, base_url))
        lines.append("")

    # ── Grouped-by-venture section (all proposals, capped per venture) ──
    grouped: dict[str, list] = defaultdict(list)
    for proposal in proposals:
        grouped[proposal.venture or "(no venture)"].append(proposal)

    lines.append("=== ALL PENDING PROPOSALS (by venture) ===")
    for venture in sorted(grouped):
        venture_items = grouped[venture]
        lines.append("")
        lines.append(f"## {venture} ({len(venture_items)})")
        for proposal in venture_items[:top_k_per_venture]:
            lines.append(_render_item(proposal, base_url))
        overflow = len(venture_items) - top_k_per_venture
        if overflow > 0:
            lines.append(f"  +{overflow} more — open the dashboard: {base_url}/dreams")

    return "\n".join(lines)


async def send_dream_digest(
    inbox: DreamInbox,
    recipient: str,
    base_url: str = "",
    event_log: EventLog | None = None,
    subject_prefix: str = "RealizeOS Dream Inbox",
) -> bool:
    """
    Compose and send the Dream Inbox digest.

    - Reads ``inbox.pending()``.
    - If nothing is pending: append a suppression event (when ``event_log`` is
      provided) and return ``False`` — NO email is sent.
    - Otherwise: build the digest text, send it via ``gmail_send`` (lazy
      import), append a send event, and return ``True``.

    Gmail failures are logged and result in a ``False`` return — this function
    never raises, so it is safe to call from a scheduler.
    """
    from realize_core.fabric.event_types import dream_event

    pending = inbox.pending()

    if not pending:
        logger.info("Dream digest: no pending proposals — suppressing email")
        if event_log is not None:
            event_log.append(
                dream_event(
                    action="digest_suppressed",
                    actor="email-digest",
                    reason="no_pending_proposals",
                    recipient=recipient,
                )
            )
        return False

    text = build_dream_digest(pending, base_url=base_url)
    if text is None:  # pragma: no cover — guarded by the pending check above
        return False

    subject = f"{subject_prefix} — {len(pending)} awaiting your decision"

    try:
        # Lazy import — google libs are an optional dependency.
        from realize_core.tools.google_workspace import gmail_send

        await gmail_send(to=recipient, subject=subject, body=text)
    except Exception as exc:  # scheduler must never crash
        logger.error("Dream digest: failed to send email to %s: %s", recipient, exc, exc_info=True)
        if event_log is not None:
            event_log.append(
                dream_event(
                    action="digest_failed",
                    actor="email-digest",
                    recipient=recipient,
                    error=str(exc)[:200],
                    pending=len(pending),
                )
            )
        return False

    logger.info("Dream digest: sent %d proposal(s) to %s", len(pending), recipient)
    if event_log is not None:
        event_log.append(
            dream_event(
                action="digest_sent",
                actor="email-digest",
                recipient=recipient,
                pending=len(pending),
            )
        )
    return True


async def send_urgent_alert(
    recipient: str,
    subject: str,
    body: str,
    event_log: EventLog | None = None,
) -> bool:
    """
    Send a single immediate "urgent" alert email via Gmail.

    Unlike the digest, this fires the moment something genuinely alarming
    happens (e.g. the apply-loop BLOCKS a hard-denied action that was somehow
    marked approved). It is sent immediately, one email per call.

    Returns ``False`` (and sends nothing) when ``recipient`` is empty. Gmail
    failures are logged and result in a ``False`` return — this function never
    raises, so it is safe to call from the apply-loop / scheduler.
    """
    from realize_core.fabric.event_types import dream_event

    if not recipient:
        logger.warning("Urgent alert: no recipient configured — skipping send")
        return False

    try:
        # Lazy import — google libs are an optional dependency.
        from realize_core.tools.google_workspace import gmail_send

        await gmail_send(to=recipient, subject=subject, body=body)
    except Exception as exc:  # caller (apply-loop) must never crash
        logger.error("Urgent alert: failed to send email to %s: %s", recipient, exc, exc_info=True)
        if event_log is not None:
            event_log.append(
                dream_event(
                    action="urgent_alert_failed",
                    actor="email-digest",
                    recipient=recipient,
                    subject=subject[:200],
                    error=str(exc)[:200],
                )
            )
        return False

    logger.info("Urgent alert: sent to %s (subject=%r)", recipient, subject)
    if event_log is not None:
        event_log.append(
            dream_event(
                action="urgent_alert_sent",
                actor="email-digest",
                recipient=recipient,
                subject=subject[:200],
            )
        )
    return True
