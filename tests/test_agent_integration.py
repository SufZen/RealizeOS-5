import asyncio
import tempfile
import threading
from pathlib import Path

import pytest
from realize_core.agents.base import HandoffData, HandoffType, PipelineStage
from realize_core.agents.handoff import process_handoff
from realize_core.agents.pipeline import execute_pipeline
from realize_core.agents.registry import AgentRegistry


@pytest.fixture
def temp_agent_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def registry():
    return AgentRegistry()


def test_registry_atomic_reload(temp_agent_dir, registry):
    """Test registry reload atomicity under concurrent mock load."""
    agent1_path = temp_agent_dir / "agent1.yaml"
    agent1_path.write_text(
        "name: Agent 1\nkey: a1\ndescription: Test\ninputs: []\noutputs: []\ntools: []\ncritical_rules: []"
    )

    registry.load_from_directory(temp_agent_dir)
    assert "a1" in registry

    # We will simulate concurrent reads while reloading
    errors = []

    def reader():
        for _ in range(100):
            try:
                # the old or new dict should always have 'a1' (or 'a2') safely without KeyError during assignment
                a = registry.get("a1")
                if not a:
                    pass
            except Exception as e:
                errors.append(e)

    # background writer adding agent 2
    agent2_path = temp_agent_dir / "agent2.yaml"
    agent2_path.write_text(
        "name: Agent 2\nkey: a2\ndescription: Test\ninputs: []\noutputs: []\ntools: []\ncritical_rules: []"
    )

    t = threading.Thread(target=reader)
    t.start()

    registry.reload()

    t.join()
    assert len(errors) == 0
    assert "a2" in registry


@pytest.mark.asyncio
async def test_circular_handoff_detection():
    """Test bounded deque circular handoff detection."""
    from realize_core.agents.handoff import _audit_log

    # Clear audit log to isolate test
    _audit_log.clear()

    # Simulate sequence a -> b -> a
    process_handoff(
        HandoffData(source_agent="a", target_agent="b", handoff_type=HandoffType.STANDARD, context={}, history=[])
    )

    result = process_handoff(
        HandoffData(source_agent="b", target_agent="a", handoff_type=HandoffType.STANDARD, context={}, history=[])
    )

    # The circular check should escalate
    assert result.action == "escalate"
    assert "circular_handoff_detected" in result.handoff.context.get("escalation_reason", "")


@pytest.mark.asyncio
async def test_pipeline_timeout():
    """Test pipeline stage timeout enforcement."""
    # We will simulate an executor that sleeps for 5 seconds, and a pipeline max_duration of 1 sec.
    stages = [PipelineStage(name="slow_stage", agent_key="a1", handoff_type=HandoffType.STANDARD)]

    async def slow_executor(stage, input_text, context):
        await asyncio.sleep(2.0)
        return "Done"

    # Forcing a timeout attribute dynamically on the stage config
    stages[0].timeout_seconds = 0.5

    state = await execute_pipeline(
        pipeline_id="test_timeout",
        stages=stages,
        initial_input="test input",
        stage_executor=slow_executor,
        max_retries=1,
    )

    assert state.status.value == "failed"
    assert "timed out" in state.error.lower()
    assert state.results[0].error is not None
    assert "Timed out" in state.results[0].error
