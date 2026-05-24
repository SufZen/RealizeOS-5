"""
Dream Inbox — The user-facing proposal queue.

Manages DreamProposals from all Dreaming cycles:
- Queue and persist proposals
- Approve/reject proposals
- Apply approved proposals to FABRIC
- Expire old proposals
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from realize_core.dreaming.policy import DreamProposal, ProposalStatus, TrustPolicy
from realize_core.fabric.event_log import EventLog
from realize_core.fabric.event_types import dream_event

logger = logging.getLogger(__name__)


class DreamInbox:
    """
    User-facing queue for Dreaming cycle proposals.

    Proposals are persisted as JSONL and can be approved/rejected
    from the dashboard or CLI.
    """

    def __init__(
        self,
        inbox_path: Path | str,
        policy: TrustPolicy | None = None,
        event_log: EventLog | None = None,
    ):
        self._inbox_path = Path(inbox_path)
        self._inbox_path.parent.mkdir(parents=True, exist_ok=True)
        self._policy = policy or TrustPolicy()
        self._event_log = event_log
        self._proposals: dict[str, DreamProposal] = {}
        self._load()

    def _load(self) -> None:
        """Load proposals from JSONL file."""
        if not self._inbox_path.exists():
            return

        for line in self._inbox_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                proposal = DreamProposal.from_dict(data)
                self._proposals[proposal.proposal_id] = proposal
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load proposal: {e}")

    def _save(self) -> None:
        """Persist proposals to JSONL file."""
        lines = [
            json.dumps(p.to_dict(), ensure_ascii=False)
            for p in self._proposals.values()
        ]
        self._inbox_path.write_text(
            "\n".join(lines) + ("\n" if lines else ""),
            encoding="utf-8",
        )

    def submit(self, proposal: DreamProposal) -> str:
        """
        Submit a proposal to the inbox.

        If the Trust Policy says full-auto, the proposal is auto-approved.
        If denied, it's immediately rejected.
        Otherwise, it goes to pending.
        """
        if self._policy.is_denied(proposal.action):
            proposal.status = ProposalStatus.REJECTED
            proposal.rejection_reason = "Denied by trust policy"
            logger.info(f"Proposal {proposal.proposal_id} denied by policy: {proposal.action}")
        elif self._policy.is_auto(proposal.action):
            proposal.status = ProposalStatus.APPROVED
            proposal.reviewed_by = "trust-policy-auto"
            proposal.reviewed_at = datetime.now()
            logger.info(f"Proposal {proposal.proposal_id} auto-approved: {proposal.action}")
        else:
            proposal.status = ProposalStatus.PENDING
            logger.info(f"Proposal {proposal.proposal_id} queued for review: {proposal.action}")

        self._proposals[proposal.proposal_id] = proposal
        self._save()

        if self._event_log:
            self._event_log.append(dream_event(
                action="proposal_submitted",
                cycle_type=proposal.cycle_type,
                venture=proposal.venture,
                proposal_id=proposal.proposal_id,
                action_type=proposal.action,
                status=proposal.status.value,
            ))

        return proposal.proposal_id

    def submit_batch(self, proposals: list[DreamProposal]) -> list[str]:
        """Submit multiple proposals."""
        return [self.submit(p) for p in proposals]

    def approve(self, proposal_id: str, reviewed_by: str = "user") -> bool:
        """Approve a pending proposal."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != ProposalStatus.PENDING:
            return False

        proposal.status = ProposalStatus.APPROVED
        proposal.reviewed_at = datetime.now()
        proposal.reviewed_by = reviewed_by
        self._save()

        logger.info(f"Proposal {proposal_id} approved by {reviewed_by}")
        return True

    def reject(
        self,
        proposal_id: str,
        reason: str = "",
        reviewed_by: str = "user",
    ) -> bool:
        """Reject a pending proposal."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != ProposalStatus.PENDING:
            return False

        proposal.status = ProposalStatus.REJECTED
        proposal.reviewed_at = datetime.now()
        proposal.reviewed_by = reviewed_by
        proposal.rejection_reason = reason
        self._save()

        logger.info(f"Proposal {proposal_id} rejected: {reason}")
        return True

    def get(self, proposal_id: str) -> DreamProposal | None:
        """Get a proposal by ID."""
        return self._proposals.get(proposal_id)

    def pending(self) -> list[DreamProposal]:
        """Get all pending proposals (for the Dream Inbox UI)."""
        return sorted(
            [p for p in self._proposals.values() if p.status == ProposalStatus.PENDING],
            key=lambda p: p.created_at,
            reverse=True,
        )

    def approved(self) -> list[DreamProposal]:
        """Get approved proposals (ready to apply to FABRIC)."""
        return [p for p in self._proposals.values() if p.status == ProposalStatus.APPROVED]

    def history(self, limit: int = 50) -> list[DreamProposal]:
        """Get all proposals sorted by creation time."""
        return sorted(
            self._proposals.values(),
            key=lambda p: p.created_at,
            reverse=True,
        )[:limit]

    def stats(self) -> dict:
        """Get proposal statistics."""
        counts = {}
        for p in self._proposals.values():
            counts[p.status.value] = counts.get(p.status.value, 0) + 1

        return {
            "total": len(self._proposals),
            "pending": counts.get("pending", 0),
            "approved": counts.get("approved", 0),
            "rejected": counts.get("rejected", 0),
            "applied": counts.get("applied", 0),
            "expired": counts.get("expired", 0),
        }

    def expire_old(self, max_age_days: int = 30) -> int:
        """Expire pending proposals older than max_age_days."""
        cutoff = datetime.now() - timedelta(days=max_age_days)
        expired = 0

        for p in self._proposals.values():
            if p.status == ProposalStatus.PENDING and p.created_at < cutoff:
                p.status = ProposalStatus.EXPIRED
                expired += 1

        if expired > 0:
            self._save()
            logger.info(f"Expired {expired} old proposals")

        return expired
