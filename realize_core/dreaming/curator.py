"""
Curator Cycle — Periodic knowledge graph maintenance.

Runs on a schedule (e.g., nightly). Performs maintenance tasks:
- Flag stale commitments past deadline
- Detect orphan entities (no inbound refs)
- Update contact trust scores based on commitment history
- Suggest archiving completed/stale entities
"""

from __future__ import annotations

import logging
from datetime import datetime

from realize_core.dreaming.policy import DreamProposal, TrustPolicy
from realize_core.fabric.synapse import Synapse

logger = logging.getLogger(__name__)


class CuratorCycle:
    """
    Periodic knowledge graph curator.

    Analyzes the entire knowledge graph via Synapse and generates
    maintenance proposals.
    """

    def __init__(
        self,
        synapse: Synapse,
        policy: TrustPolicy | None = None,
    ):
        self._synapse = synapse
        self._policy = policy or TrustPolicy()

    def run(self, venture: str = "") -> list[DreamProposal]:
        """
        Run a full curator cycle.

        Returns all proposals generated across all maintenance checks.
        """
        proposals: list[DreamProposal] = []

        proposals.extend(self._check_stale_commitments(venture))
        proposals.extend(self._check_orphans(venture))
        proposals.extend(self._check_entity_health(venture))

        logger.info(f"Curator cycle complete for venture '{venture or 'all'}': {len(proposals)} proposal(s)")
        return proposals

    def _check_stale_commitments(self, venture: str) -> list[DreamProposal]:
        """Flag open commitments past their deadline."""
        proposals = []

        commitments = self._synapse.by_type("commitment", scope=venture or None)
        now = datetime.now()

        for c in commitments:
            fm = c.get("frontmatter", {})
            status = fm.get("status", "open")
            deadline = fm.get("deadline", "")

            if status not in ("open", "in-progress"):
                continue

            if not deadline:
                continue

            try:
                deadline_dt = datetime.fromisoformat(deadline)
                if deadline_dt < now:
                    days_overdue = (now - deadline_dt).days
                    proposals.append(
                        DreamProposal(
                            cycle_type="curator",
                            action="flag_stale_commitment",
                            entity_id=c.get("id", ""),
                            entity_type="commitment",
                            venture=venture or c.get("venture", ""),
                            title=f"Overdue commitment: {c.get('title', 'Untitled')}",
                            description=f"Commitment is {days_overdue} day(s) past deadline ({deadline})",
                            diff={"days_overdue": days_overdue, "deadline": deadline},
                            confidence=1.0,
                            rationale="Deadline has passed with status still open",
                        )
                    )
            except (ValueError, TypeError):
                continue

        return proposals

    def _check_orphans(self, venture: str) -> list[DreamProposal]:
        """Detect entities with no inbound references."""
        proposals = []

        orphans = self._synapse.orphans(scope=venture or None)

        for orphan in orphans:
            # Skip contacts (they're often standalone)
            if orphan.get("type") == "contact":
                continue

            proposals.append(
                DreamProposal(
                    cycle_type="curator",
                    action="flag_orphan",
                    entity_id=orphan.get("id", ""),
                    entity_type=orphan.get("type", ""),
                    venture=venture or orphan.get("venture", ""),
                    title=f"Orphan entity: {orphan.get('title', 'Untitled')}",
                    description="This entity has no inbound references from other entities",
                    confidence=0.6,
                    rationale="Orphan entities may indicate missing connections or stale content",
                )
            )

        return proposals

    def _check_entity_health(self, venture: str) -> list[DreamProposal]:
        """Check for common entity health issues."""
        proposals = []

        toc = self._synapse.toc(venture=venture or None)

        for entry in toc:
            # Flag entities with no tags
            tags = entry.get("tags", [])
            if not tags and entry.get("type") not in ("contact",):
                proposals.append(
                    DreamProposal(
                        cycle_type="curator",
                        action="annotate_entity",
                        entity_id=entry.get("id", ""),
                        entity_type=entry.get("type", ""),
                        venture=venture or entry.get("venture", ""),
                        title=f"Untagged entity: {entry.get('title', 'Untitled')}",
                        description="Entity has no tags, making it harder to discover",
                        confidence=0.5,
                        rationale="Tags improve discoverability and agent context relevance",
                    )
                )

        return proposals
