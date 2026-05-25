"""
Reflex Cycle — Immediate post-mission enrichment.

Runs automatically after a mission completes. Performs low-risk
knowledge enrichment:
- Tag inference from body content
- Reference linking between related entities
- Summary generation for long entities
- Commitment deadline flagging
"""

from __future__ import annotations

import logging

from realize_core.dreaming.policy import DreamProposal, TrustPolicy
from realize_core.fabric.entity import FabricEntity
from realize_core.fabric.refs import extract_refs

logger = logging.getLogger(__name__)


class ReflexCycle:
    """
    Post-mission reflex enrichment.

    Analyzes entities produced or modified by a mission and proposes
    automatic enrichments (tags, links, summaries).
    """

    def __init__(self, policy: TrustPolicy | None = None):
        self._policy = policy or TrustPolicy()

    def analyze(self, entity: FabricEntity) -> list[DreamProposal]:
        """
        Analyze an entity and generate enrichment proposals.

        Returns a list of DreamProposals for each suggested change.
        """
        proposals: list[DreamProposal] = []

        proposals.extend(self._suggest_tags(entity))
        proposals.extend(self._suggest_refs(entity))
        proposals.extend(self._check_missing_fields(entity))

        return proposals

    def _suggest_tags(self, entity: FabricEntity) -> list[DreamProposal]:
        """Suggest tags from body content that aren't in frontmatter."""
        proposals = []
        body_lower = entity.body.lower()

        # Common topic patterns to detect
        topic_indicators = {
            "pricing": ["pricing", "price", "cost model", "subscription", "payment"],
            "strategy": ["strategy", "strategic", "long-term plan", "roadmap"],
            "hiring": ["hiring", "recruitment", "candidate", "interview"],
            "risk": ["risk", "mitigation", "contingency", "fallback"],
            "legal": ["legal", "contract", "compliance", "regulation"],
            "finance": ["finance", "budget", "revenue", "cash flow"],
            "product": ["product", "feature", "release", "launch"],
            "sales": ["sales", "leads", "pipeline", "conversion"],
        }

        existing_tags = set(entity.tags)
        suggested = []

        for tag, keywords in topic_indicators.items():
            if tag in existing_tags:
                continue
            if any(kw in body_lower for kw in keywords):
                suggested.append(tag)

        if suggested and not self._policy.is_denied("add_tag"):
            proposals.append(DreamProposal(
                cycle_type="reflex",
                action="add_tag",
                entity_id=entity.id,
                entity_type=entity.type,
                venture=entity.venture,
                title=f"Add tags to {entity.title}",
                description=f"Suggested tags based on content analysis: {', '.join(suggested)}",
                diff={"add_tags": suggested},
                confidence=0.7,
                rationale="Keywords found in body content",
            ))

        return proposals

    def _suggest_refs(self, entity: FabricEntity) -> list[DreamProposal]:
        """Suggest references that might be missing from frontmatter."""
        proposals = []

        # Extract refs from body that aren't in frontmatter refs
        body_refs = extract_refs({}, entity.body)
        fm_refs = set(entity.refs)
        new_refs = [r for r in body_refs if r not in fm_refs]

        if new_refs and not self._policy.is_denied("add_ref"):
            proposals.append(DreamProposal(
                cycle_type="reflex",
                action="add_ref",
                entity_id=entity.id,
                entity_type=entity.type,
                venture=entity.venture,
                title=f"Add references to {entity.title}",
                description=f"Found {len(new_refs)} reference(s) in body not tracked in frontmatter",
                diff={"add_refs": new_refs},
                confidence=0.9,
                rationale="References detected in body text via wikilink/XML patterns",
            ))

        return proposals

    def _check_missing_fields(self, entity: FabricEntity) -> list[DreamProposal]:
        """Flag entities missing important fields for their type."""
        proposals = []

        # Decisions without status
        if entity.type == "decision" and "status" not in entity.frontmatter:
            proposals.append(DreamProposal(
                cycle_type="reflex",
                action="annotate_entity",
                entity_id=entity.id,
                entity_type=entity.type,
                venture=entity.venture,
                title=f"Missing status on decision: {entity.title}",
                description="Decision entity is missing a 'status' field (proposed/committed/deferred/reversed)",
                diff={"suggest_field": "status", "suggested_value": "proposed"},
                confidence=0.6,
                rationale="All decisions should have a status for tracking",
            ))

        # Commitments without deadline
        if entity.type == "commitment" and "deadline" not in entity.frontmatter:
            proposals.append(DreamProposal(
                cycle_type="reflex",
                action="annotate_entity",
                entity_id=entity.id,
                entity_type=entity.type,
                venture=entity.venture,
                title=f"Missing deadline on commitment: {entity.title}",
                description="Commitment entity is missing a 'deadline' field",
                diff={"suggest_field": "deadline"},
                confidence=0.7,
                rationale="Commitments need deadlines for accountability tracking",
            ))

        return proposals
