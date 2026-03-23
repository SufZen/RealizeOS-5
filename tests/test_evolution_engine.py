"""Tests for realize_core.evolution.engine — auto-evolution engine."""

from realize_core.evolution.engine import (
    EvolutionEngine,
    EvolutionProposal,
    EvolutionType,
    ProposalStatus,
    RiskLevel,
    get_evolution_engine,
)


class TestEvolutionType:
    def test_all_types(self):
        assert len(EvolutionType) == 5


class TestRiskLevel:
    def test_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.HIGH.value == "high"


class TestProposalStatus:
    def test_all_statuses(self):
        assert len(ProposalStatus) == 5


class TestEvolutionProposal:
    def test_defaults(self):
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.NEW_SKILL,
            title="New weather skill",
            description="Add weather lookup",
        )
        assert p.risk_level == RiskLevel.LOW
        assert p.status == ProposalStatus.PENDING
        assert p.priority == 0.5


class TestEvolutionEngine:
    def test_propose(self):
        engine = EvolutionEngine()
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.NEW_SKILL,
            title="Test",
            description="",
        )
        assert engine.propose(p)
        assert engine.proposal_count == 1

    def test_propose_duplicate(self):
        engine = EvolutionEngine()
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.NEW_SKILL,
            title="Test",
            description="",
        )
        engine.propose(p)
        assert not engine.propose(p)  # Duplicate

    def test_auto_approve_low_risk(self):
        engine = EvolutionEngine(auto_approve_low_risk=True)
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.NEW_SKILL,
            title="Test",
            description="",
            risk_level=RiskLevel.LOW,
        )
        engine.propose(p)
        assert p.status == ProposalStatus.APPROVED

    def test_no_auto_approve_medium_risk(self):
        engine = EvolutionEngine(auto_approve_low_risk=True)
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.CONFIG_CHANGE,
            title="Change config",
            description="",
            risk_level=RiskLevel.MEDIUM,
        )
        engine.propose(p)
        assert p.status == ProposalStatus.PENDING

    def test_manual_approve(self):
        engine = EvolutionEngine(auto_approve_low_risk=False)
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.NEW_SKILL,
            title="Test",
            description="",
        )
        engine.propose(p)
        assert engine.approve("p1")
        assert p.status == ProposalStatus.APPROVED

    def test_reject(self):
        engine = EvolutionEngine()
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.CONFIG_CHANGE,
            title="Test",
            description="",
            risk_level=RiskLevel.HIGH,
        )
        engine.propose(p)
        assert engine.reject("p1", reason="Too risky")
        assert p.status == ProposalStatus.REJECTED
        assert p.metadata["rejection_reason"] == "Too risky"

    def test_apply(self):
        engine = EvolutionEngine()
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.NEW_SKILL,
            title="Test",
            description="",
        )
        engine.propose(p)  # Auto-approved (low risk)
        assert engine.apply("p1")
        assert p.status == ProposalStatus.APPLIED
        assert p.applied_at > 0

    def test_apply_unapproved_fails(self):
        engine = EvolutionEngine(auto_approve_low_risk=False)
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.NEW_SKILL,
            title="Test",
            description="",
        )
        engine.propose(p)
        assert not engine.apply("p1")  # Still pending

    def test_rollback(self):
        engine = EvolutionEngine()
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.NEW_SKILL,
            title="Test",
            description="",
        )
        engine.propose(p)
        engine.apply("p1")
        assert engine.rollback("p1")
        assert p.status == ProposalStatus.ROLLED_BACK

    def test_rollback_non_applied_fails(self):
        engine = EvolutionEngine()
        p = EvolutionProposal(
            id="p1",
            evolution_type=EvolutionType.NEW_SKILL,
            title="Test",
            description="",
        )
        engine.propose(p)
        assert not engine.rollback("p1")  # Not applied

    def test_rate_limit(self):
        engine = EvolutionEngine(rate_limit_per_hour=2)
        for i in range(3):
            p = EvolutionProposal(
                id=f"p{i}",
                evolution_type=EvolutionType.NEW_SKILL,
                title=f"Test {i}",
                description="",
            )
            engine.propose(p)
            if i < 2:
                assert engine.apply(f"p{i}")
            else:
                assert not engine.apply(f"p{i}")  # Rate limited

    def test_get_pending(self):
        engine = EvolutionEngine(auto_approve_low_risk=False)
        for i, prio in enumerate([0.3, 0.9, 0.5]):
            engine.propose(
                EvolutionProposal(
                    id=f"p{i}",
                    evolution_type=EvolutionType.NEW_SKILL,
                    title=f"Test {i}",
                    description="",
                    priority=prio,
                )
            )
        pending = engine.get_pending()
        assert len(pending) == 3
        assert pending[0].priority == 0.9  # Highest priority first

    def test_get_applied(self):
        engine = EvolutionEngine()
        engine.propose(
            EvolutionProposal(
                id="p1",
                evolution_type=EvolutionType.NEW_SKILL,
                title="A",
                description="",
            )
        )
        engine.apply("p1")
        applied = engine.get_applied()
        assert len(applied) == 1

    def test_status_summary(self):
        engine = EvolutionEngine()
        engine.propose(
            EvolutionProposal(
                id="p1",
                evolution_type=EvolutionType.NEW_SKILL,
                title="A",
                description="",
            )
        )
        summary = engine.status_summary()
        assert summary["total"] == 1
        assert "approved" in summary["by_status"]


class TestSingleton:
    def test_singleton(self):
        import realize_core.evolution.engine as mod

        mod._engine = None
        e1 = get_evolution_engine()
        e2 = get_evolution_engine()
        assert e1 is e2
        mod._engine = None
