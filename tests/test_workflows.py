"""Tests for realize_core.workflows — workflow engine."""

import pytest
from realize_core.workflows import (
    MethodRegistry,
    NodeType,
    WorkflowContext,
    WorkflowDefinition,
    WorkflowNode,
    WorkflowRunner,
    WorkflowStatus,
    get_method_registry,
    get_workflow_runner,
)

# ===========================================================================
# NodeType / WorkflowStatus tests
# ===========================================================================


class TestNodeType:
    def test_all_types(self):
        assert len(NodeType) == 7

    def test_values(self):
        assert NodeType.PROMPT.value == "prompt"
        assert NodeType.TOOL.value == "tool"
        assert NodeType.CONDITION.value == "condition"


class TestWorkflowStatus:
    def test_all_statuses(self):
        assert len(WorkflowStatus) == 5


# ===========================================================================
# WorkflowDefinition tests
# ===========================================================================


class TestWorkflowDefinition:
    def test_node_map(self):
        wf = WorkflowDefinition(
            name="test",
            nodes=[
                WorkflowNode(id="a", node_type=NodeType.PROMPT),
                WorkflowNode(id="b", node_type=NodeType.TOOL),
            ],
            entry_node="a",
        )
        nm = wf.node_map
        assert "a" in nm
        assert "b" in nm
        assert nm["a"].node_type == NodeType.PROMPT


class TestWorkflowContext:
    def test_defaults(self):
        ctx = WorkflowContext(workflow_name="test")
        assert ctx.status == WorkflowStatus.PENDING
        assert ctx.variables == {}
        assert ctx.results == []

    def test_duration(self):
        ctx = WorkflowContext(workflow_name="test", started_at=100.0, completed_at=101.5)
        assert ctx.duration_ms == 1500


# ===========================================================================
# MethodRegistry tests
# ===========================================================================


class TestMethodRegistry:
    def test_register_and_get(self):
        reg = MethodRegistry()

        async def my_method(ctx, params):
            return "result"

        reg.register("test", my_method)
        assert reg.has("test")
        assert reg.get("test") is my_method
        assert reg.count == 1

    def test_decorator(self):
        reg = MethodRegistry()

        @reg.method("decorated")
        async def handler(ctx, params):
            return "done"

        assert reg.has("decorated")

    def test_method_names(self):
        reg = MethodRegistry()

        async def a(ctx, params):
            pass

        async def b(ctx, params):
            pass

        reg.register("alpha", a)
        reg.register("beta", b)
        assert set(reg.method_names) == {"alpha", "beta"}

    def test_get_missing(self):
        reg = MethodRegistry()
        assert reg.get("missing") is None


# ===========================================================================
# WorkflowRunner tests
# ===========================================================================


class TestWorkflowRunner:
    @pytest.mark.asyncio
    async def test_simple_transform(self):
        """Run a workflow with a single transform node."""
        wf = WorkflowDefinition(
            name="test-transform",
            nodes=[
                WorkflowNode(
                    id="step1",
                    node_type=NodeType.TRANSFORM,
                    config={"expression": "Hello World"},
                ),
            ],
            entry_node="step1",
        )

        runner = WorkflowRunner()
        ctx = await runner.execute(wf)
        assert ctx.status == WorkflowStatus.COMPLETED
        assert len(ctx.results) == 1
        assert ctx.results[0]["result"]["output"] == "Hello World"

    @pytest.mark.asyncio
    async def test_chained_steps(self):
        """Run a workflow with two chained steps."""
        wf = WorkflowDefinition(
            name="test-chain",
            nodes=[
                WorkflowNode(
                    id="step1",
                    node_type=NodeType.TRANSFORM,
                    config={"expression": "value_A"},
                    next_node="step2",
                ),
                WorkflowNode(
                    id="step2",
                    node_type=NodeType.TRANSFORM,
                    config={"expression": "Got: {step1.output}"},
                ),
            ],
            entry_node="step1",
        )

        runner = WorkflowRunner()
        ctx = await runner.execute(wf)
        assert ctx.status == WorkflowStatus.COMPLETED
        assert len(ctx.results) == 2
        assert ctx.results[1]["result"]["output"] == "Got: value_A"

    @pytest.mark.asyncio
    async def test_condition_true_branch(self):
        """Test condition node with true branch."""
        wf = WorkflowDefinition(
            name="test-condition",
            nodes=[
                WorkflowNode(
                    id="check",
                    node_type=NodeType.CONDITION,
                    config={
                        "condition": "yes",
                        "true": "success",
                        "false": "fail",
                    },
                ),
                WorkflowNode(id="success", node_type=NodeType.TRANSFORM, config={"expression": "Passed!"}),
                WorkflowNode(id="fail", node_type=NodeType.TRANSFORM, config={"expression": "Failed!"}),
            ],
            entry_node="check",
        )

        runner = WorkflowRunner()
        ctx = await runner.execute(wf)
        assert ctx.status == WorkflowStatus.COMPLETED
        assert "Passed!" in str(ctx.results)

    @pytest.mark.asyncio
    async def test_condition_false_branch(self):
        """Test condition node with false branch."""
        wf = WorkflowDefinition(
            name="test-condition-false",
            nodes=[
                WorkflowNode(
                    id="check",
                    node_type=NodeType.CONDITION,
                    config={
                        "condition": "false",
                        "true": "success",
                        "false": "fail",
                    },
                ),
                WorkflowNode(id="success", node_type=NodeType.TRANSFORM, config={"expression": "Passed!"}),
                WorkflowNode(id="fail", node_type=NodeType.TRANSFORM, config={"expression": "Failed!"}),
            ],
            entry_node="check",
        )

        runner = WorkflowRunner()
        ctx = await runner.execute(wf)
        assert ctx.status == WorkflowStatus.COMPLETED
        assert "Failed!" in str(ctx.results)

    @pytest.mark.asyncio
    async def test_missing_node_fails(self):
        """Workflow fails when a node references a non-existent next node."""
        wf = WorkflowDefinition(
            name="test-missing",
            nodes=[
                WorkflowNode(
                    id="step1",
                    node_type=NodeType.TRANSFORM,
                    config={"expression": "hi"},
                    next_node="nonexistent",
                ),
            ],
            entry_node="step1",
        )

        runner = WorkflowRunner()
        ctx = await runner.execute(wf)
        # step1 completes, but nonexistent fails
        assert ctx.status == WorkflowStatus.FAILED

    @pytest.mark.asyncio
    async def test_method_node(self):
        """Test executing a registered method."""
        reg = MethodRegistry()
        results = []

        @reg.method("test_action")
        async def test_action(ctx, params):
            results.append(params)
            return f"executed with {params}"

        wf = WorkflowDefinition(
            name="test-method",
            nodes=[
                WorkflowNode(
                    id="call",
                    node_type=NodeType.METHOD,
                    config={"method": "test_action", "params": {"key": "value"}},
                ),
            ],
            entry_node="call",
        )

        runner = WorkflowRunner(method_registry=reg)
        ctx = await runner.execute(wf)
        assert ctx.status == WorkflowStatus.COMPLETED
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_initial_variables(self):
        """Test that initial variables are available."""
        wf = WorkflowDefinition(
            name="test-vars",
            nodes=[
                WorkflowNode(
                    id="use_var",
                    node_type=NodeType.TRANSFORM,
                    config={"expression": "Name is: {user_name}"},
                ),
            ],
            entry_node="use_var",
        )

        runner = WorkflowRunner()
        ctx = await runner.execute(wf, {"user_name": "Asaf"})
        assert ctx.status == WorkflowStatus.COMPLETED
        assert ctx.results[0]["result"]["output"] == "Name is: Asaf"

    @pytest.mark.asyncio
    async def test_context_duration(self):
        """Test that duration is tracked."""
        wf = WorkflowDefinition(
            name="test-duration",
            nodes=[
                WorkflowNode(id="a", node_type=NodeType.TRANSFORM, config={"expression": "done"}),
            ],
            entry_node="a",
        )

        runner = WorkflowRunner()
        ctx = await runner.execute(wf)
        assert ctx.duration_ms >= 0


# ===========================================================================
# Singleton tests
# ===========================================================================


class TestSingletons:
    def test_method_registry_singleton(self):
        import realize_core.workflows as mod

        mod._method_registry = None
        r1 = get_method_registry()
        r2 = get_method_registry()
        assert r1 is r2
        mod._method_registry = None

    def test_runner_singleton(self):
        import realize_core.workflows as mod

        mod._runner = None
        mod._method_registry = None
        r1 = get_workflow_runner()
        r2 = get_workflow_runner()
        assert r1 is r2
        mod._runner = None
        mod._method_registry = None
