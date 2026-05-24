"""
Internal Runtime Adapter.

Wraps the existing realize_core/agents/ + base_handler.py as the first
AgentRuntime adapter. Zero behavior change for existing users — this is
simply a contract-conforming facade over the current system.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import AsyncIterator

from realize_core.runtimes.contract import (
    AgentRuntime,
    Capability,
    CapabilitySet,
    CostClass,
    CostEstimate,
    Context,
    HealthStatus,
    MissionStep,
    Modality,
    Skill,
    Task,
    ToolProtocol,
)
from realize_core.runtimes.events import (
    ErrorEvent,
    FinalResultEvent,
    ProgressEvent,
    RuntimeEvent,
    TextEvent,
)

logger = logging.getLogger(__name__)


class InternalAdapter:
    """
    Adapter wrapping the existing RealizeOS agent system as a runtime.

    This is the first and default runtime — it wraps the existing
    base_handler.py → agents pipeline → LLM router flow into the
    AgentRuntime contract.
    """

    runtime_id: str = "internal"
    display_name: str = "RealizeOS Internal Agents"
    version: str = "0.1.0"
    runtime_version: str | None = None

    def capabilities(self) -> CapabilitySet:
        """Declare internal agent capabilities."""
        return CapabilitySet(
            capabilities=[
                Capability(name="writing.creative", confidence=0.9, cost_class=CostClass.MODERATE),
                Capability(name="writing.business", confidence=0.9, cost_class=CostClass.MODERATE),
                Capability(name="writing.technical", confidence=0.8, cost_class=CostClass.MODERATE),
                Capability(name="reasoning.long", confidence=0.8, cost_class=CostClass.MODERATE),
                Capability(name="research.deep", confidence=0.7, cost_class=CostClass.MODERATE),
                Capability(name="data.analyze", confidence=0.7, cost_class=CostClass.MODERATE),
            ],
            languages=["en", "he", "pt", "it", "es"],
            modalities=[Modality.TEXT],
            tool_protocols=[ToolProtocol.MCP],
            streaming=False,  # Current system doesn't stream
            cancellation=False,
            parallelism=1,
            requires_internet=True,
            is_local=False,
        )

    async def health_check(self) -> HealthStatus:
        """Check that the internal agent system is ready."""
        try:
            # Verify core modules are importable
            from realize_core.base_handler import process_message  # noqa: F401
            from realize_core.llm.router import route_to_llm  # noqa: F401

            return HealthStatus(
                ready=True,
                degraded=False,
                runtime_version=self.version,
            )
        except ImportError as e:
            return HealthStatus(
                ready=False,
                error=f"Import error: {e}",
            )

    async def warmup(self) -> None:
        """No warmup needed for internal agents."""
        pass

    async def shutdown(self) -> None:
        """No shutdown needed for internal agents."""
        pass

    async def cost_estimate(self, task: Task, context: Context) -> CostEstimate:
        """Estimate cost based on expected token usage."""
        # Internal agents use the configured LLM provider via the router
        estimated_tokens = task.expected_output_tokens or 2000
        # Rough estimate: $0.003 per 1K tokens (blended)
        estimated_cost = (estimated_tokens / 1000) * 0.003

        return CostEstimate(
            estimated_tokens=estimated_tokens,
            estimated_duration_sec=5.0,
            estimated_cost_eur=estimated_cost,
            confidence=0.5,
        )

    async def invoke(
        self,
        mission_step: MissionStep,
        context: Context,
    ) -> AsyncIterator[RuntimeEvent]:
        """
        Execute a mission step using the internal agent system.

        Wraps the existing process_message() flow.
        """
        run_id = uuid.uuid4().hex[:16]
        started_at = datetime.now()

        yield ProgressEvent(
            run_id=run_id,
            message=f"Starting step: {mission_step.description}",
            percent_complete=0.0,
        )

        try:
            from realize_core.base_handler import process_message
            from realize_core.config import KB_PATH, build_systems_dict, load_config

            config = load_config()
            systems = build_systems_dict(config)

            venture_id = context.venture_id or ""
            system_config = systems.get(venture_id, {})

            # Execute through the existing pipeline
            response = await process_message(
                system_key=venture_id,
                user_id="mission-engine",
                message=mission_step.description,
                kb_path=KB_PATH,
                system_config=system_config,
                shared_config=config.get("shared", {}),
                channel="mission",
                features=config.get("features", {}),
                all_systems=systems,
            )

            elapsed = (datetime.now() - started_at).total_seconds()

            yield TextEvent(run_id=run_id, delta=response)

            yield FinalResultEvent(
                run_id=run_id,
                output={"text": response},
                cost_actual={
                    "actual_tokens": len(response.split()) * 2,  # rough estimate
                    "actual_duration_sec": elapsed,
                    "actual_cost_eur": 0.0,  # tracked separately by LLM router
                },
                status="success",
            )

        except Exception as e:
            logger.error(f"Internal adapter error: {e}")
            yield ErrorEvent(
                run_id=run_id,
                error_type="internal",
                message=str(e),
                retryable=True,
            )

    async def cancel(self, run_id: str) -> bool:
        """Internal agents don't support cancellation."""
        return False

    async def export_skills(self) -> list[Skill] | None:
        """Export skills from the internal skill library."""
        try:
            from realize_core.skills.detector import list_skills

            internal_skills = list_skills()
            return [
                Skill(
                    skill_id=s.get("name", ""),
                    name=s.get("name", ""),
                    description=s.get("description", ""),
                    capability_tags=s.get("tags", []),
                    body=s.get("template", ""),
                    source_runtime="internal",
                    portable=True,
                )
                for s in internal_skills
            ]
        except Exception:
            return None

    async def import_skill(self, skill: Skill) -> bool:
        """Not yet supported for internal agents."""
        return False
