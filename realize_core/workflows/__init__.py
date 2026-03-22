"""
Workflow Engine: YAML-defined workflows with a programmatic runner.

Supports:
- Workflow definitions in YAML
- Pluggable node types (prompt, tool, condition, loop)
- Method registry for reusable operations
- Trigger integration (webhook, cron, manual)
"""
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ===========================================================================
# Workflow definitions
# ===========================================================================


class NodeType(Enum):
    """Types of workflow nodes."""
    PROMPT = "prompt"          # Send to LLM
    TOOL = "tool"              # Execute a tool
    CONDITION = "condition"    # Branch based on condition
    LOOP = "loop"              # Repeat steps
    METHOD = "method"          # Call a registered method
    TRANSFORM = "transform"   # Transform data
    PARALLEL = "parallel"     # Run nodes in parallel


class WorkflowStatus(Enum):
    """Execution status of a workflow."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowNode:
    """A single step in a workflow."""
    id: str
    node_type: NodeType
    config: dict[str, Any] = field(default_factory=dict)
    next_node: str = ""             # ID of next node
    on_error: str = ""              # ID of error-handler node
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    """A complete workflow definition."""
    name: str
    description: str = ""
    nodes: list[WorkflowNode] = field(default_factory=list)
    entry_node: str = ""             # Starting node ID
    trigger: str = "manual"          # manual, webhook, cron, event
    trigger_config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def node_map(self) -> dict[str, WorkflowNode]:
        return {n.id: n for n in self.nodes}


@dataclass
class WorkflowContext:
    """Runtime context for a workflow execution."""
    workflow_name: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    variables: dict[str, Any] = field(default_factory=dict)
    results: list[dict[str, Any]] = field(default_factory=list)
    current_node: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""

    @property
    def duration_ms(self) -> int:
        end = self.completed_at or time.time()
        return int((end - self.started_at) * 1000) if self.started_at else 0


# ===========================================================================
# Method Registry
# ===========================================================================


class MethodRegistry:
    """
    Registry for reusable operations callable by workflows.

    Methods are named async functions that accept (context, params) and return results.
    """

    def __init__(self):
        self._methods: dict[str, Callable] = {}

    def register(self, name: str, method: Callable):
        """Register a named method."""
        self._methods[name] = method
        logger.debug(f"Registered method: {name}")

    def method(self, name: str):
        """Decorator to register a method."""
        def decorator(fn):
            self.register(name, fn)
            return fn
        return decorator

    def get(self, name: str) -> Callable | None:
        return self._methods.get(name)

    def has(self, name: str) -> bool:
        return name in self._methods

    @property
    def method_names(self) -> list[str]:
        return list(self._methods.keys())

    @property
    def count(self) -> int:
        return len(self._methods)


# ===========================================================================
# Workflow Loader
# ===========================================================================


def load_workflow(yaml_path: str | Path) -> WorkflowDefinition | None:
    """
    Load a workflow from a YAML file.

    Format:
    ```yaml
    name: weekly-review
    description: Generate a weekly review of all systems
    trigger: cron
    trigger_config:
      interval: weekly

    nodes:
      - id: fetch_data
        type: tool
        config:
          tool: web_search
          params:
            query: "site:mysite.com updates this week"
        next: summarize

      - id: summarize
        type: prompt
        config:
          prompt: "Summarize these updates: {fetch_data.output}"
          model: gemini_flash
        next: notify

      - id: notify
        type: method
        config:
          method: send_notification
          params:
            channel: telegram
            message: "{summarize.output}"
    ```
    """
    path = Path(yaml_path)
    if not path.exists():
        logger.warning(f"Workflow file not found: {path}")
        return None

    try:
        import yaml
    except ImportError:
        logger.warning("pyyaml not installed")
        return None

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    nodes = []
    for node_data in data.get("nodes", []):
        try:
            node_type = NodeType(node_data.get("type", "prompt"))
        except ValueError:
            node_type = NodeType.PROMPT

        nodes.append(WorkflowNode(
            id=node_data.get("id", ""),
            node_type=node_type,
            config=node_data.get("config", {}),
            next_node=node_data.get("next", ""),
            on_error=node_data.get("on_error", ""),
            metadata=node_data.get("metadata", {}),
        ))

    entry = data.get("entry_node", "")
    if not entry and nodes:
        entry = nodes[0].id

    return WorkflowDefinition(
        name=data.get("name", path.stem),
        description=data.get("description", ""),
        nodes=nodes,
        entry_node=entry,
        trigger=data.get("trigger", "manual"),
        trigger_config=data.get("trigger_config", {}),
        metadata=data.get("metadata", {}),
    )


def discover_workflows(directory: str | Path) -> list[WorkflowDefinition]:
    """Discover all workflow YAML files in a directory."""
    dir_path = Path(directory)
    if not dir_path.exists():
        return []

    workflows = []
    for yaml_file in sorted(dir_path.glob("*.yaml")) + sorted(dir_path.glob("*.yml")):
        wf = load_workflow(yaml_file)
        if wf:
            workflows.append(wf)
    return workflows


# ===========================================================================
# Workflow Runner
# ===========================================================================


class WorkflowRunner:
    """
    Executes workflow definitions step by step.

    Routes nodes to the appropriate handler based on NodeType.
    Supports variable substitution between steps.
    """

    def __init__(self, method_registry: MethodRegistry | None = None):
        self._method_registry = method_registry or MethodRegistry()
        self._node_handlers: dict[NodeType, Callable] = {
            NodeType.PROMPT: self._run_prompt,
            NodeType.TOOL: self._run_tool,
            NodeType.METHOD: self._run_method,
            NodeType.CONDITION: self._run_condition,
            NodeType.TRANSFORM: self._run_transform,
        }

    async def execute(
        self,
        workflow: WorkflowDefinition,
        initial_variables: dict[str, Any] | None = None,
    ) -> WorkflowContext:
        """
        Execute a workflow from start to finish.

        Args:
            workflow: The workflow definition to execute
            initial_variables: Variables to inject into the context

        Returns:
            WorkflowContext with execution results
        """
        ctx = WorkflowContext(
            workflow_name=workflow.name,
            status=WorkflowStatus.RUNNING,
            variables=initial_variables or {},
            started_at=time.time(),
        )

        node_map = workflow.node_map
        current_id = workflow.entry_node

        while current_id and ctx.status == WorkflowStatus.RUNNING:
            node = node_map.get(current_id)
            if not node:
                ctx.error = f"Node '{current_id}' not found"
                ctx.status = WorkflowStatus.FAILED
                break

            ctx.current_node = current_id
            logger.info(f"Workflow '{workflow.name}': executing node '{current_id}' ({node.node_type.value})")

            try:
                result = await self._execute_node(node, ctx)
                ctx.results.append({
                    "node_id": current_id,
                    "type": node.node_type.value,
                    "result": result,
                })

                # Store result as a variable for subsequent nodes
                ctx.variables[current_id] = result

                # Determine next node
                if isinstance(result, dict) and "next_node" in result:
                    current_id = result["next_node"]  # Condition branching
                else:
                    current_id = node.next_node

            except Exception as e:
                logger.error(f"Node '{current_id}' failed: {e}", exc_info=True)
                if node.on_error:
                    current_id = node.on_error
                else:
                    ctx.error = str(e)
                    ctx.status = WorkflowStatus.FAILED
                    break

        if ctx.status == WorkflowStatus.RUNNING:
            ctx.status = WorkflowStatus.COMPLETED

        ctx.completed_at = time.time()
        ctx.current_node = ""
        logger.info(
            f"Workflow '{workflow.name}' {ctx.status.value} "
            f"in {ctx.duration_ms}ms ({len(ctx.results)} steps)"
        )
        return ctx

    async def _execute_node(self, node: WorkflowNode, ctx: WorkflowContext) -> Any:
        """Execute a single node."""
        handler = self._node_handlers.get(node.node_type)
        if handler:
            return await handler(node, ctx)
        return {"output": f"Unknown node type: {node.node_type.value}"}

    async def _run_prompt(self, node: WorkflowNode, ctx: WorkflowContext) -> dict:
        """Execute a prompt node — send to LLM."""
        prompt = self._substitute(node.config.get("prompt", ""), ctx.variables)
        node.config.get("model", "")

        # Import and call LLM
        try:
            from realize_core.llm.router import route_and_query
            response = await route_and_query(prompt)
        except Exception:
            response = f"[LLM unavailable] Prompt: {prompt[:200]}"

        return {"output": response}

    async def _run_tool(self, node: WorkflowNode, ctx: WorkflowContext) -> dict:
        """Execute a tool node."""
        tool_name = node.config.get("tool", "")
        params = {
            k: self._substitute(str(v), ctx.variables)
            for k, v in node.config.get("params", {}).items()
        }

        try:
            from realize_core.tools.tool_registry import get_tool_registry
            registry = get_tool_registry()
            result = await registry.execute(tool_name, params)
            return {"output": result.output if hasattr(result, "output") else str(result)}
        except Exception as e:
            return {"output": f"Tool '{tool_name}' failed: {e}"}

    async def _run_method(self, node: WorkflowNode, ctx: WorkflowContext) -> dict:
        """Execute a registered method."""
        method_name = node.config.get("method", "")
        params = {
            k: self._substitute(str(v), ctx.variables)
            for k, v in node.config.get("params", {}).items()
        }

        method = self._method_registry.get(method_name)
        if not method:
            return {"output": f"Method '{method_name}' not found"}

        result = await method(ctx, params)
        return {"output": result}

    async def _run_condition(self, node: WorkflowNode, ctx: WorkflowContext) -> dict:
        """Evaluate a condition and branch."""
        condition = node.config.get("condition", "")
        true_branch = node.config.get("true", "")
        false_branch = node.config.get("false", "")

        # Simple variable-based condition evaluation
        value = self._substitute(condition, ctx.variables)
        is_true = bool(value) and value.lower() not in ("false", "0", "none", "")

        return {
            "output": f"Condition '{condition}' = {is_true}",
            "next_node": true_branch if is_true else false_branch,
        }

    async def _run_transform(self, node: WorkflowNode, ctx: WorkflowContext) -> dict:
        """Transform data between steps."""
        expression = node.config.get("expression", "")
        result = self._substitute(expression, ctx.variables)
        return {"output": result}

    def _substitute(self, template: str, variables: dict) -> str:
        """
        Substitute {node_id.output} patterns in a template.

        Supports:
            {node_id} → str(variables[node_id])
            {node_id.output} → variables[node_id]["output"]
            {node_id.key} → variables[node_id][key]
        """
        import re
        def replacer(match):
            key = match.group(1)
            if "." in key:
                parts = key.split(".", 1)
                var = variables.get(parts[0])
                if isinstance(var, dict):
                    return str(var.get(parts[1], match.group(0)))
                return match.group(0)
            var = variables.get(key)
            if var is not None:
                if isinstance(var, dict) and "output" in var:
                    return str(var["output"])
                return str(var)
            return match.group(0)

        return re.sub(r"\{(\w+(?:\.\w+)?)\}", replacer, template)


# ===========================================================================
# Singletons
# ===========================================================================


_method_registry: MethodRegistry | None = None
_runner: WorkflowRunner | None = None


def get_method_registry() -> MethodRegistry:
    global _method_registry
    if _method_registry is None:
        _method_registry = MethodRegistry()
    return _method_registry


def get_workflow_runner() -> WorkflowRunner:
    global _runner
    if _runner is None:
        _runner = WorkflowRunner(get_method_registry())
    return _runner
