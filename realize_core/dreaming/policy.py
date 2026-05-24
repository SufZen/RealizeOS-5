"""
Trust Policy — Controls what Dreaming cycles may do autonomously.

The fundamental safety constraint: Dreaming can READ anything but
WRITES go through the Trust Policy before reaching FABRIC.

Three trust levels:
1. Full-auto: Agent can write without approval (e.g., adding tags)
2. Propose: Agent proposes → user reviews in Dream Inbox
3. Deny: Agent is not allowed to perform this action
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class ProposalStatus(str, Enum):
    """Status of a dream proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    EXPIRED = "expired"


class TrustLevel(str, Enum):
    """Trust level for a dreaming action."""

    FULL_AUTO = "full-auto"
    PROPOSE = "propose"
    DENY = "deny"


# Default policy: most actions require proposal, only safe operations are auto
_DEFAULT_POLICY = {
    # Reflex cycle — low-risk enrichment
    "add_tag": TrustLevel.FULL_AUTO,
    "add_ref": TrustLevel.FULL_AUTO,
    "update_summary": TrustLevel.PROPOSE,
    "annotate_entity": TrustLevel.PROPOSE,

    # Curator cycle — maintenance
    "flag_stale_commitment": TrustLevel.FULL_AUTO,
    "flag_orphan": TrustLevel.FULL_AUTO,
    "update_trust_score": TrustLevel.PROPOSE,
    "suggest_archive": TrustLevel.PROPOSE,

    # Synthesis cycle — creative
    "create_insight": TrustLevel.PROPOSE,
    "create_hypothesis": TrustLevel.PROPOSE,
    "merge_entities": TrustLevel.PROPOSE,
    "suggest_decision": TrustLevel.PROPOSE,

    # Dangerous — never auto
    "delete_entity": TrustLevel.DENY,
    "modify_decision": TrustLevel.DENY,
    "send_message": TrustLevel.DENY,
}


@dataclass
class DreamProposal:
    """
    A proposed knowledge write from a Dreaming cycle.

    Goes to the Dream Inbox for user review unless the Trust Policy
    says full-auto.
    """

    proposal_id: str = ""
    cycle_type: str = ""  # "reflex" | "curator" | "synthesis"
    action: str = ""  # What the cycle wants to do
    entity_id: str = ""  # Target entity (empty for new entities)
    entity_type: str = ""
    venture: str = ""

    # What the proposal does
    title: str = ""
    description: str = ""
    diff: dict = field(default_factory=dict)  # Proposed changes

    # Trust
    confidence: float = 0.5
    rationale: str = ""
    evidence: list[str] = field(default_factory=list)

    # Status
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    reviewed_at: datetime | None = None
    reviewed_by: str = ""
    rejection_reason: str = ""

    def __post_init__(self):
        if not self.proposal_id:
            import uuid
            self.proposal_id = f"dream-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "cycle_type": self.cycle_type,
            "action": self.action,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "venture": self.venture,
            "title": self.title,
            "description": self.description,
            "diff": self.diff,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "evidence": self.evidence,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DreamProposal":
        return cls(
            proposal_id=data.get("proposal_id", ""),
            cycle_type=data.get("cycle_type", ""),
            action=data.get("action", ""),
            entity_id=data.get("entity_id", ""),
            entity_type=data.get("entity_type", ""),
            venture=data.get("venture", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            diff=data.get("diff", {}),
            confidence=data.get("confidence", 0.5),
            rationale=data.get("rationale", ""),
            evidence=data.get("evidence", []),
            status=ProposalStatus(data.get("status", "pending")),
        )


class TrustPolicy:
    """
    Controls what Dreaming cycles are allowed to do.

    Loaded from shared/trust-policy.yaml if available,
    falls back to built-in defaults.
    """

    def __init__(self, overrides: dict[str, str] | None = None):
        self._policy: dict[str, TrustLevel] = dict(_DEFAULT_POLICY)
        if overrides:
            for action, level in overrides.items():
                try:
                    self._policy[action] = TrustLevel(level)
                except ValueError:
                    logger.warning(f"Unknown trust level '{level}' for action '{action}'")

    @classmethod
    def load(cls, path: Path) -> "TrustPolicy":
        """Load policy from a YAML file."""
        if not path.exists():
            return cls()

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return cls(overrides=data.get("trust_policy", data))
        except (yaml.YAMLError, OSError) as e:
            logger.warning(f"Failed to load trust policy: {e}")

        return cls()

    def check(self, action: str) -> TrustLevel:
        """Check the trust level for a given action."""
        return self._policy.get(action, TrustLevel.PROPOSE)

    def is_auto(self, action: str) -> bool:
        """Check if an action can execute without human approval."""
        return self.check(action) == TrustLevel.FULL_AUTO

    def is_denied(self, action: str) -> bool:
        """Check if an action is explicitly denied."""
        return self.check(action) == TrustLevel.DENY

    def needs_approval(self, action: str) -> bool:
        """Check if an action requires human approval."""
        return self.check(action) == TrustLevel.PROPOSE

    @property
    def all_actions(self) -> dict[str, str]:
        """Get all actions and their trust levels."""
        return {action: level.value for action, level in self._policy.items()}
