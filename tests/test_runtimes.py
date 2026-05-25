"""
Tests for the Runtime Adapter System.
"""


import pytest
from realize_core.runtimes.contract import (
    Capability,
    CapabilitySet,
    Context,
    CostClass,
    CostEstimate,
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
    TextEvent,
)
from realize_core.runtimes.registry import RuntimeRegistry

# ─── Mock Runtime ─────────────────────────────────────────────────────────────

class MockRuntime:
    """A minimal mock runtime for testing the registry."""

    runtime_id = "mock-runtime"
    display_name = "Mock Runtime"
    version = "0.1.0"
    runtime_version = "1.0.0"

    def __init__(self, healthy: bool = True, caps: list[str] | None = None):
        self._healthy = healthy
        self._caps = caps or ["code.edit", "writing.technical"]

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(
            capabilities=[
                Capability(name=c, confidence=0.9, cost_class=CostClass.MODERATE)
                for c in self._caps
            ],
            languages=["en"],
            modalities=[Modality.TEXT, Modality.CODE],
            streaming=True,
            cancellation=True,
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            ready=self._healthy,
            degraded=not self._healthy,
            runtime_version=self.runtime_version,
        )

    async def warmup(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def cost_estimate(self, task: Task, context: Context) -> CostEstimate:
        return CostEstimate(
            estimated_tokens=1000,
            estimated_duration_sec=3.0,
            estimated_cost_eur=0.01,
            confidence=0.8,
        )

    async def invoke(self, mission_step: MissionStep, context: Context):
        run_id = "test-run-001"
        yield ProgressEvent(run_id=run_id, message="Starting...")
        yield TextEvent(run_id=run_id, delta="Hello from mock runtime!")
        yield FinalResultEvent(
            run_id=run_id,
            output={"text": "Hello from mock runtime!"},
            status="success",
        )

    async def cancel(self, run_id: str) -> bool:
        return True

    async def export_skills(self) -> list[Skill] | None:
        return None

    async def import_skill(self, skill: Skill) -> bool:
        return False


# ─── Contract Tests ───────────────────────────────────────────────────────────

class TestContract:
    def test_data_types(self):
        """Verify all data types can be instantiated."""
        cap = Capability(name="code.edit", confidence=0.9)
        assert cap.name == "code.edit"

        caps = CapabilitySet(capabilities=[cap])
        assert len(caps.capabilities) == 1

        health = HealthStatus(ready=True)
        assert health.ready

        task = Task(description="Write code", required_capabilities=["code.edit"])
        assert task.description == "Write code"

        step = MissionStep(step_id="s1", mission_id="m-001", description="Edit file")
        assert step.step_id == "s1"

        ctx = Context(venture_id="test")
        assert ctx.venture_id == "test"

    def test_enums(self):
        assert CostClass.CHEAP.value == "cheap"
        assert Modality.CODE.value == "code"
        assert ToolProtocol.MCP.value == "mcp"


# ─── Registry Tests ──────────────────────────────────────────────────────────

class TestRegistry:
    @pytest.fixture
    def registry(self):
        return RuntimeRegistry()

    @pytest.mark.asyncio
    async def test_register_healthy(self, registry):
        runtime = MockRuntime(healthy=True)
        result = await registry.register(runtime)
        assert result is True
        assert "mock-runtime" in registry.runtime_ids
        assert "mock-runtime" in registry.active_runtimes

    @pytest.mark.asyncio
    async def test_register_unhealthy(self, registry):
        runtime = MockRuntime(healthy=False)
        result = await registry.register(runtime)
        assert result is False  # Health check returns not ready

    @pytest.mark.asyncio
    async def test_deregister(self, registry):
        runtime = MockRuntime()
        await registry.register(runtime)
        assert "mock-runtime" in registry.runtime_ids

        await registry.deregister("mock-runtime")
        assert "mock-runtime" not in registry.runtime_ids

    @pytest.mark.asyncio
    async def test_get_runtime(self, registry):
        runtime = MockRuntime()
        await registry.register(runtime)

        entry = registry.get("mock-runtime")
        assert entry is not None
        assert entry.runtime_id == "mock-runtime"
        assert entry.status == "ready"

    @pytest.mark.asyncio
    async def test_health_check(self, registry):
        runtime = MockRuntime()
        await registry.register(runtime)

        health = await registry.health_check("mock-runtime")
        assert health.ready is True

    @pytest.mark.asyncio
    async def test_status_summary(self, registry):
        runtime = MockRuntime()
        await registry.register(runtime)

        summary = registry.status_summary()
        assert len(summary) == 1
        assert summary[0]["runtime_id"] == "mock-runtime"
        assert summary[0]["status"] == "ready"


# ─── Task Matching Tests ─────────────────────────────────────────────────────

class TestTaskMatching:
    @pytest.fixture
    def registry(self):
        return RuntimeRegistry()

    @pytest.mark.asyncio
    async def test_match_by_capability(self, registry):
        runtime = MockRuntime(caps=["code.edit", "code.review"])
        await registry.register(runtime)

        task = Task(description="Edit code", required_capabilities=["code.edit"])
        matches = registry.match_runtimes(task)
        assert len(matches) == 1
        assert matches[0][0] == "mock-runtime"
        assert matches[0][1] > 0

    @pytest.mark.asyncio
    async def test_no_match_missing_capability(self, registry):
        runtime = MockRuntime(caps=["code.edit"])
        await registry.register(runtime)

        task = Task(description="Generate image", required_capabilities=["vision.generate"])
        matches = registry.match_runtimes(task)
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_match_with_preferred(self, registry):
        runtime = MockRuntime(caps=["code.edit", "code.review", "reasoning.long"])
        await registry.register(runtime)

        task = Task(
            description="Review and refactor code",
            required_capabilities=["code.edit"],
            preferred_capabilities=["code.review", "reasoning.long"],
        )
        matches = registry.match_runtimes(task)
        assert len(matches) == 1
        # Score should be higher due to preferred matches
        assert matches[0][1] > 1.0

    @pytest.mark.asyncio
    async def test_match_generic_task(self, registry):
        runtime = MockRuntime()
        await registry.register(runtime)

        task = Task(description="Do something")  # No specific capabilities
        matches = registry.match_runtimes(task)
        assert len(matches) == 1


# ─── Event Tests ──────────────────────────────────────────────────────────────

class TestEvents:
    def test_event_types(self):
        p = ProgressEvent(run_id="r1", message="Starting")
        assert p.kind == "progress"

        t = TextEvent(run_id="r1", delta="Hello")
        assert t.kind == "text"

        f = FinalResultEvent(run_id="r1", status="success")
        assert f.kind == "final"

        e = ErrorEvent(run_id="r1", error_type="timeout", retryable=True)
        assert e.kind == "error"
        assert e.retryable

    @pytest.mark.asyncio
    async def test_invoke_yields_events(self):
        runtime = MockRuntime()
        step = MissionStep(step_id="s1", mission_id="m-001", description="Test")
        ctx = Context()

        events = []
        async for event in runtime.invoke(step, ctx):
            events.append(event)

        assert len(events) == 3
        assert events[0].kind == "progress"
        assert events[1].kind == "text"
        assert events[2].kind == "final"
