"""
Tests for the Dreaming Subsystem.
"""

from datetime import datetime, timedelta

import pytest
from realize_core.dreaming.inbox import DreamInbox
from realize_core.dreaming.policy import (
    DreamProposal,
    ProposalStatus,
    TrustPolicy,
)
from realize_core.dreaming.reflex import ReflexCycle
from realize_core.fabric.entity import FabricEntity

# ─── Trust Policy ─────────────────────────────────────────────────────────────

class TestTrustPolicy:
    def test_default_policy(self):
        policy = TrustPolicy()
        assert policy.is_auto("add_tag")
        assert policy.is_auto("add_ref")
        assert policy.needs_approval("create_insight")
        assert policy.is_denied("delete_entity")
        assert policy.is_denied("send_message")

    def test_custom_overrides(self):
        policy = TrustPolicy(overrides={
            "add_tag": "propose",
            "create_insight": "full-auto",
        })
        assert policy.needs_approval("add_tag")  # Was auto, now propose
        assert policy.is_auto("create_insight")  # Was propose, now auto

    def test_unknown_action_defaults_to_propose(self):
        policy = TrustPolicy()
        assert policy.needs_approval("unknown_new_action")

    def test_load_missing_file(self, tmp_path):
        policy = TrustPolicy.load(tmp_path / "nonexistent.yaml")
        # Should fall back to defaults
        assert policy.is_auto("add_tag")

    def test_load_yaml_file(self, tmp_path):
        import yaml
        path = tmp_path / "trust-policy.yaml"
        path.write_text(yaml.dump({
            "trust_policy": {
                "add_tag": "deny",
                "create_insight": "full-auto",
            }
        }))
        policy = TrustPolicy.load(path)
        assert policy.is_denied("add_tag")
        assert policy.is_auto("create_insight")

    def test_all_actions(self):
        policy = TrustPolicy()
        actions = policy.all_actions
        assert "add_tag" in actions
        assert actions["add_tag"] == "full-auto"
        assert actions["delete_entity"] == "deny"


# ─── Dream Proposal ──────────────────────────────────────────────────────────

class TestDreamProposal:
    def test_auto_id(self):
        proposal = DreamProposal(action="add_tag")
        assert proposal.proposal_id.startswith("dream-")
        assert len(proposal.proposal_id) > 10

    def test_serialization(self):
        proposal = DreamProposal(
            cycle_type="reflex",
            action="add_tag",
            entity_id="dec-2026-05-pricing-001",
            title="Add pricing tag",
            confidence=0.8,
        )
        d = proposal.to_dict()
        assert d["action"] == "add_tag"
        assert d["confidence"] == 0.8

        restored = DreamProposal.from_dict(d)
        assert restored.action == proposal.action
        assert restored.entity_id == proposal.entity_id


# ─── Reflex Cycle ─────────────────────────────────────────────────────────────

class TestReflexCycle:
    @pytest.fixture
    def cycle(self):
        return ReflexCycle(policy=TrustPolicy())

    def test_suggest_tags_from_content(self, cycle):
        entity = FabricEntity(
            id="dec-2026-05-pricing-001",
            type="decision",
            title="Pricing Model Decision",
            venture="biz",
            body="We need to update our pricing model to support monthly subscription payments.",
            tags=[],
            frontmatter={},
        )
        proposals = cycle.analyze(entity)
        tag_proposals = [p for p in proposals if p.action == "add_tag"]
        assert len(tag_proposals) >= 1
        assert "pricing" in tag_proposals[0].diff.get("add_tags", [])

    def test_no_duplicate_tags(self, cycle):
        entity = FabricEntity(
            id="dec-2026-05-pricing-001",
            type="decision",
            title="Pricing Model",
            venture="biz",
            body="The pricing strategy needs updating.",
            tags=["pricing"],  # Already tagged
            frontmatter={},
        )
        proposals = cycle.analyze(entity)
        tag_proposals = [p for p in proposals if p.action == "add_tag"]
        # Should not suggest "pricing" since it's already a tag
        for p in tag_proposals:
            assert "pricing" not in p.diff.get("add_tags", [])

    def test_missing_decision_status(self, cycle):
        entity = FabricEntity(
            id="dec-2026-05-test-001",
            type="decision",
            title="Test Decision",
            venture="biz",
            body="Some decision.",
            frontmatter={},
        )
        proposals = cycle.analyze(entity)
        annotate = [p for p in proposals if p.action == "annotate_entity"]
        assert any("status" in p.diff.get("suggest_field", "") for p in annotate)

    def test_missing_commitment_deadline(self, cycle):
        entity = FabricEntity(
            id="commitment-2026-05-test-001",
            type="commitment",
            title="Send report",
            venture="biz",
            body="I'll send the report.",
            frontmatter={},
        )
        proposals = cycle.analyze(entity)
        annotate = [p for p in proposals if p.action == "annotate_entity"]
        assert any("deadline" in p.diff.get("suggest_field", "") for p in annotate)


# ─── Dream Inbox ──────────────────────────────────────────────────────────────

class TestDreamInbox:
    @pytest.fixture
    def inbox(self, tmp_path):
        return DreamInbox(
            inbox_path=tmp_path / "dream-inbox.jsonl",
            policy=TrustPolicy(),
        )

    def test_submit_auto_approved(self, inbox):
        proposal = DreamProposal(action="add_tag", title="Tag proposal")
        pid = inbox.submit(proposal)
        assert inbox.get(pid).status == ProposalStatus.APPROVED

    def test_submit_pending(self, inbox):
        proposal = DreamProposal(action="create_insight", title="Insight proposal")
        pid = inbox.submit(proposal)
        assert inbox.get(pid).status == ProposalStatus.PENDING

    def test_submit_denied(self, inbox):
        proposal = DreamProposal(action="delete_entity", title="Delete proposal")
        pid = inbox.submit(proposal)
        assert inbox.get(pid).status == ProposalStatus.REJECTED
        assert "Denied by trust policy" in inbox.get(pid).rejection_reason

    def test_approve_and_reject(self, inbox):
        p1 = DreamProposal(action="create_insight", title="Good idea")
        p2 = DreamProposal(action="create_insight", title="Bad idea")
        pid1 = inbox.submit(p1)
        pid2 = inbox.submit(p2)

        assert inbox.approve(pid1) is True
        assert inbox.reject(pid2, reason="Not relevant") is True

        assert inbox.get(pid1).status == ProposalStatus.APPROVED
        assert inbox.get(pid2).status == ProposalStatus.REJECTED

    def test_pending_list(self, inbox):
        for i in range(5):
            inbox.submit(DreamProposal(action="create_insight", title=f"Insight {i}"))

        pending = inbox.pending()
        assert len(pending) == 5

    def test_stats(self, inbox):
        inbox.submit(DreamProposal(action="add_tag", title="Auto"))
        inbox.submit(DreamProposal(action="create_insight", title="Pending"))
        inbox.submit(DreamProposal(action="delete_entity", title="Denied"))

        stats = inbox.stats()
        assert stats["total"] == 3
        assert stats["approved"] == 1
        assert stats["pending"] == 1
        assert stats["rejected"] == 1

    def test_persistence(self, tmp_path):
        path = tmp_path / "inbox.jsonl"
        inbox1 = DreamInbox(inbox_path=path)
        inbox1.submit(DreamProposal(action="create_insight", title="Persistent"))

        # Reload from disk
        inbox2 = DreamInbox(inbox_path=path)
        assert len(inbox2.pending()) == 1

    def test_batch_submit(self, inbox):
        proposals = [
            DreamProposal(action="add_tag", title=f"Tag {i}")
            for i in range(3)
        ]
        pids = inbox.submit_batch(proposals)
        assert len(pids) == 3

    def test_expire_old(self, tmp_path):
        inbox = DreamInbox(inbox_path=tmp_path / "inbox.jsonl")

        old = DreamProposal(action="create_insight", title="Old proposal")
        old.created_at = datetime.now() - timedelta(days=60)
        inbox._proposals[old.proposal_id] = old
        inbox._save()

        new = DreamProposal(action="create_insight", title="New proposal")
        inbox.submit(new)

        expired_count = inbox.expire_old(max_age_days=30)
        assert expired_count == 1
        assert inbox.get(old.proposal_id).status == ProposalStatus.EXPIRED
        assert inbox.get(new.proposal_id).status == ProposalStatus.PENDING

    def test_history(self, inbox):
        for i in range(5):
            inbox.submit(DreamProposal(action="add_tag", title=f"Item {i}"))

        history = inbox.history(limit=3)
        assert len(history) == 3
