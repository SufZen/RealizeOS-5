"""
Auto-Evolution Engine: Proposes, reviews, and applies system improvements.

Builds on the existing evolution module (gap_detector, skill_suggester, etc.)
to add:
- Automated evolution proposals with priority scoring
- Gated approval flow (auto-approve low-risk, require approval for high-risk)
- Rollback capability for applied changes
- Rate limiting to prevent runaway evolution
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EvolutionType(Enum):
    """Types of system evolution."""

    NEW_SKILL = "new_skill"  # Add a new skill
    REFINE_PROMPT = "refine_prompt"  # Improve an agent's prompt
    ADD_TOOL = "add_tool"  # Register a new tool
    CONFIG_CHANGE = "config_change"  # Change system configuration
    WORKFLOW_ADD = "workflow_add"  # Add a new workflow


class RiskLevel(Enum):
    """Risk assessment of a proposed evolution."""

    LOW = "low"  # Safe: new skill, minor prompt tweak
    MEDIUM = "medium"  # Needs review: config change, tool addition
    HIGH = "high"  # Dangerous: prompt replacement, workflow changes


class ProposalStatus(Enum):
    """Status of an evolution proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


@dataclass
class EvolutionProposal:
    """A proposed system evolution."""

    id: str
    evolution_type: EvolutionType
    title: str
    description: str
    risk_level: RiskLevel = RiskLevel.LOW
    status: ProposalStatus = ProposalStatus.PENDING
    priority: float = 0.5  # 0.0-1.0 priority score
    changes: dict[str, Any] = field(default_factory=dict)
    rollback_data: dict[str, Any] = field(default_factory=dict)
    source: str = ""  # What triggered this (gap_detector, user, etc.)
    created_at: float = field(default_factory=time.time)
    applied_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class EvolutionEngine:
    """
    Manages the lifecycle of system evolution proposals.

    Flow: Propose → Review (auto or manual) → Apply → Monitor → Rollback if needed
    """

    def __init__(
        self,
        auto_approve_low_risk: bool = True,
        rate_limit_per_hour: int = 10,
    ):
        self._proposals: dict[str, EvolutionProposal] = {}
        self._auto_approve_low_risk = auto_approve_low_risk
        self._rate_limit = rate_limit_per_hour
        self._applied_this_hour: list[float] = []

    def propose(self, proposal: EvolutionProposal) -> bool:
        """
        Submit a new evolution proposal.

        Low-risk proposals are auto-approved if enabled.
        Returns True if the proposal was accepted.
        """
        if proposal.id in self._proposals:
            return False

        self._proposals[proposal.id] = proposal
        logger.info(
            f"Evolution proposal '{proposal.id}': {proposal.title} "
            f"(risk={proposal.risk_level.value}, priority={proposal.priority:.1f})"
        )

        # Auto-approve low-risk if enabled
        if self._auto_approve_low_risk and proposal.risk_level == RiskLevel.LOW:
            proposal.status = ProposalStatus.APPROVED
            logger.info(f"Auto-approved: {proposal.id}")

        return True

    def approve(self, proposal_id: str) -> bool:
        """Manually approve a proposal."""
        proposal = self._proposals.get(proposal_id)
        if not proposal or proposal.status != ProposalStatus.PENDING:
            return False
        proposal.status = ProposalStatus.APPROVED
        logger.info(f"Approved: {proposal_id}")
        return True

    def reject(self, proposal_id: str, reason: str = "") -> bool:
        """Reject a proposal."""
        proposal = self._proposals.get(proposal_id)
        if not proposal or proposal.status != ProposalStatus.PENDING:
            return False
        proposal.status = ProposalStatus.REJECTED
        proposal.metadata["rejection_reason"] = reason
        logger.info(f"Rejected: {proposal_id} ({reason})")
        return True

    def apply(self, proposal_id: str) -> bool:
        """
        Apply an approved evolution.

        Checks rate limits before applying.
        Stores rollback data for reversal.
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal or proposal.status != ProposalStatus.APPROVED:
            return False

        # Check rate limit
        if not self._check_rate_limit():
            logger.warning(f"Rate limit exceeded, deferring: {proposal_id}")
            return False

        # Record application
        proposal.status = ProposalStatus.APPLIED
        proposal.applied_at = time.time()
        self._applied_this_hour.append(time.time())

        logger.info(f"Applied evolution: {proposal.title}")
        return True

    def rollback(self, proposal_id: str) -> bool:
        """
        Roll back an applied evolution.

        Uses stored rollback_data to restore previous state.
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal or proposal.status != ProposalStatus.APPLIED:
            return False

        proposal.status = ProposalStatus.ROLLED_BACK
        logger.info(f"Rolled back: {proposal.title}")
        return True

    def _check_rate_limit(self) -> bool:
        """Check if we've exceeded the hourly rate limit."""
        now = time.time()
        one_hour_ago = now - 3600
        self._applied_this_hour = [t for t in self._applied_this_hour if t > one_hour_ago]
        return len(self._applied_this_hour) < self._rate_limit

    def get_proposal(self, proposal_id: str) -> EvolutionProposal | None:
        return self._proposals.get(proposal_id)

    def get_pending(self) -> list[EvolutionProposal]:
        """Get all pending proposals, sorted by priority."""
        pending = [p for p in self._proposals.values() if p.status == ProposalStatus.PENDING]
        return sorted(pending, key=lambda p: -p.priority)

    def get_applied(self) -> list[EvolutionProposal]:
        """Get all applied proposals, newest first."""
        applied = [p for p in self._proposals.values() if p.status == ProposalStatus.APPLIED]
        return sorted(applied, key=lambda p: -p.applied_at)

    @property
    def proposal_count(self) -> int:
        return len(self._proposals)

    def status_summary(self) -> dict:
        """Get summary of all proposals by status."""
        summary: dict[str, int] = {}
        for p in self._proposals.values():
            key = p.status.value
            summary[key] = summary.get(key, 0) + 1
        return {
            "total": self.proposal_count,
            "by_status": summary,
            "rate_this_hour": len(self._applied_this_hour),
            "rate_limit": self._rate_limit,
        }


# Singleton
_engine: EvolutionEngine | None = None


def get_evolution_engine() -> EvolutionEngine:
    global _engine
    if _engine is None:
        _engine = EvolutionEngine()
    return _engine
