"""
Dreaming Subsystem — The Genesis Layer of RealizeOS.

The Dreaming subsystem runs background intelligence cycles that
maintain, curate, and evolve the knowledge graph.

Three dreaming cycles:
1. Reflex: Immediate post-mission cleanup (tag, link, summarize)
2. Curator: Periodic maintenance (stale commitments, orphan detection, trust scoring)
3. Synthesis: Deep pattern recognition across entities (future: Genesis cycle)
"""

from realize_core.dreaming.policy import TrustPolicy, DreamProposal, ProposalStatus
from realize_core.dreaming.reflex import ReflexCycle
from realize_core.dreaming.curator import CuratorCycle
from realize_core.dreaming.inbox import DreamInbox

__all__ = [
    "TrustPolicy",
    "DreamProposal",
    "ProposalStatus",
    "ReflexCycle",
    "CuratorCycle",
    "DreamInbox",
]
