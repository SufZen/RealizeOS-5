"""
Skill Executor Engine for RealizeOS: Multi-step workflow runner.

Supports composable, tool-aware workflows with step types:
- agent  — Call an LLM agent with context injection
- tool   — Execute a web/Google/browser tool directly
- condition — Branch based on a previous step's result
- human  — Ask the user for input/confirmation before proceeding

Also supports SKILL.md format (V5): the markdown body is used as
detailed instructions for the LLM agent.

Each step's result feeds into the next step's context.
"""

import json
import logging
from datetime import date

logger = logging.getLogger(__name__)


def store_skill_resume_context(
    user_id: str,
    skill_name: str,
    ctx,
    remaining_steps: list,
    *,
    step_id: str = "",
    approval_id: str | None = None,
    kind: str = "human",
) -> str:
    """Store a durable resume point for a paused skill and return its id.

    ``kind`` is ``human`` (waiting for an answer, which chat or the dashboard
    gives) or ``tool`` (a tool step the gate held; only the approval decision
    resumes it). ``approval_id`` is the approval item that resumes it.
    """
    import uuid

    from realize_core.skills import resume_store

    run_id = approval_id or str(uuid.uuid4())
    resume_store.save(
        run_id,
        approval_id=approval_id,
        user_id=user_id,
        system_key=ctx.system_key,
        skill_name=skill_name,
        step_id=step_id,
        kind=kind,
        context=ctx.to_dict(),
        remaining_steps=remaining_steps,
    )
    logger.info(
        "Stored %s resume point %s for user %s, skill=%s, %d steps remaining",
        kind,
        run_id,
        user_id,
        skill_name,
        len(remaining_steps),
    )
    return run_id


def _as_pending(row: dict | None) -> dict | None:
    """A resume_store row in the shape callers use (``context`` is a SkillContext)."""
    if row is None:
        return None
    return {**row, "context": SkillContext.from_dict(row["context"])}


def peek_skill_resume_context(user_id: str, system_key: str | None = None) -> dict | None:
    """The user's newest skill waiting for an answer (optionally in one venture), not removed."""
    from realize_core.skills import resume_store

    return _as_pending(resume_store.find(user_id=user_id, system_key=system_key, kind="human"))


def pop_skill_resume_context(user_id: str, system_key: str | None = None) -> dict | None:
    """Remove and return the user's newest skill waiting for an answer."""
    from realize_core.skills import resume_store

    pending = resume_store.find(user_id=user_id, system_key=system_key, kind="human")
    return _as_pending(resume_store.claim(pending["id"])) if pending else None


def claim_skill_run(run_id: str) -> dict | None:
    """Remove and return one resume point by id (None if already resumed or stopped)."""
    from realize_core.skills import resume_store

    return _as_pending(resume_store.claim(run_id))


def skill_run_for_approval(approval_id: str) -> dict | None:
    """The resume point an approval item resumes, if a skill is waiting on it."""
    from realize_core.skills import resume_store

    return _as_pending(resume_store.find(approval_id=approval_id))


async def resume_pending_skill(
    user_id: str,
    answer: str,
    kb_path=None,
    system_config=None,
    shared_config=None,
    channel: str = "api",
    *,
    run_id: str | None = None,
) -> str | None:
    """Continue a skill paused at a human step, using *answer* as that step's result.

    Resumes ``run_id`` when given, else the user's newest skill waiting for an
    answer. Returns the skill's output, or None when there is nothing to resume.
    """
    pending = claim_skill_run(run_id) if run_id else pop_skill_resume_context(user_id)
    if pending is None:
        return None
    ctx = pending["context"]
    step_id = pending.get("step_id") or "human"
    ctx.step_results[step_id] = answer
    logger.info("Resuming skill %s for %s after step %s", pending.get("skill_name"), user_id, step_id)
    return await _run_v2_steps(
        pending.get("remaining_steps", []),
        ctx,
        pending.get("skill_name", ""),
        kb_path,
        system_config,
        shared_config,
        channel,
    )


async def resume_after_held_tool(
    run_id: str,
    execution: dict,
    kb_path=None,
    system_config=None,
    shared_config=None,
    channel: str = "dashboard",
) -> str | None:
    """Continue a skill whose tool step was held, once the approved action has run.

    The step's result is what the tool actually returned. If the approved
    action failed, the skill stops there: nothing that depended on it runs.
    Returns the skill's output (or the stop message), or None when nothing waits.
    """
    pending = claim_skill_run(run_id)
    if pending is None:
        return None
    step_id = pending.get("step_id") or "tool"
    if not execution.get("success"):
        reason = execution.get("error") or "the approved action did not complete"
        return f"⚠️ The workflow stopped at step '{step_id}': {reason}. Nothing after this step ran."
    ctx = pending["context"]
    ctx.step_results[step_id] = execution.get("output", "")
    logger.info("Resuming skill %s after approved step %s", pending.get("skill_name"), step_id)
    return await _run_v2_steps(
        pending.get("remaining_steps", []),
        ctx,
        pending.get("skill_name", ""),
        kb_path,
        system_config,
        shared_config,
        channel,
    )


class SkillContext:
    """Holds accumulated context across skill steps."""

    def __init__(self, user_message: str, system_key: str, user_id: str):
        self.user_message = user_message
        self.system_key = system_key
        self.user_id = user_id
        self.step_results: dict[str, str] = {}
        self.variables: dict[str, str] = {"doc_title": user_message}
        self.progress_messages: list[str] = []
        self.annotations: dict[str, dict] = {}

    def to_dict(self) -> dict:
        """Plain data for a durable resume point."""
        return {
            "user_message": self.user_message,
            "system_key": self.system_key,
            "user_id": self.user_id,
            "step_results": self.step_results,
            "variables": self.variables,
            "progress_messages": self.progress_messages,
            "annotations": self.annotations,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillContext":
        """Rebuild a context saved with :meth:`to_dict`."""
        ctx = cls(data.get("user_message", ""), data.get("system_key", ""), data.get("user_id", ""))
        ctx.step_results = dict(data.get("step_results") or {})
        ctx.variables = dict(data.get("variables") or ctx.variables)
        ctx.progress_messages = list(data.get("progress_messages") or [])
        ctx.annotations = dict(data.get("annotations") or {})
        return ctx

    def inject(self, template: str) -> str:
        """Replace {variable} placeholders in a template string."""
        result = template
        for step_id, value in self.step_results.items():
            result = result.replace(f"{{{step_id}}}", str(value))
        for var, value in self.variables.items():
            result = result.replace(f"{{{var}}}", str(value))
        result = result.replace("{user_message}", self.user_message)
        result = result.replace("{today}", date.today().isoformat())
        return result


async def _call_llm(system_prompt: str, messages: list[dict], system_key: str) -> str:
    """LLM call for skill steps — through the router (rate/cost limits, provider fallback)."""
    from realize_core.llm.router import classify_task, route_to_llm

    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    task_type = classify_task(last_user if isinstance(last_user, str) else "", system_key=system_key)
    return await route_to_llm(system_prompt, messages, task_type, system_key=system_key)


async def execute_skill(
    skill: dict,
    user_message: str,
    system_key: str,
    user_id: str,
    kb_path=None,
    system_config: dict = None,
    shared_config: dict = None,
    channel: str = "api",
    emit=None,
) -> str:
    """
    Execute a skill (v1 pipeline or v2 multi-step workflow).

    Args:
        skill: Skill definition dict (from detector)
        user_message: The user's message that triggered the skill
        system_key: Active system key
        user_id: User identifier
        kb_path: Knowledge base root path
        system_config: System configuration dict
        shared_config: Shared config (identity, preferences paths)
        channel: Channel for format instructions
        emit: Optional trail listener; v2 tool steps report what they used

    Returns:
        Skill execution result text
    """
    skill_name = skill.get("name", "unnamed")
    version = skill.get("_version", 1)
    skill_format = skill.get("_format", "yaml")

    logger.info(f"Executing skill: {skill_name} (v{version}, format={skill_format}) for system={system_key}")

    # V5: SKILL.md format — use markdown instructions
    if skill_format == "skill_md":
        return await _execute_skill_md(
            skill,
            user_message,
            system_key,
            user_id,
            kb_path,
            system_config,
            shared_config,
            channel,
        )

    if version == 1:
        return await _execute_v1_pipeline(
            skill,
            user_message,
            system_key,
            user_id,
            kb_path,
            system_config,
            shared_config,
            channel,
        )
    else:
        return await _execute_v2_steps(
            skill,
            user_message,
            system_key,
            user_id,
            kb_path,
            system_config,
            shared_config,
            channel,
            emit=emit,
        )


async def _execute_v1_pipeline(
    skill: dict,
    user_message: str,
    system_key: str,
    user_id: str,
    kb_path,
    system_config,
    shared_config,
    channel,
) -> str:
    """Execute a v1 skill (trigger -> agent pipeline)."""
    from realize_core.prompt.builder import build_system_prompt

    pipeline = skill.get("pipeline", ["orchestrator"])
    results = []

    for i, agent_key in enumerate(pipeline):
        # Build prompt for this agent
        system_prompt = build_system_prompt(
            kb_path=kb_path,
            system_config=system_config or {},
            system_key=system_key,
            agent_key=agent_key,
            user_message=user_message,
            shared_config=shared_config,
            channel=channel,
        )

        # Build message with context from previous agents
        if results:
            context = "\n\n".join([f"## Previous agent output\n{r}" for r in results])
            message_content = f"{context}\n\n## User request\n{user_message}"
        else:
            message_content = user_message

        messages = [{"role": "user", "content": message_content}]

        response = await _call_llm(system_prompt, messages, system_key)
        results.append(response)
        logger.info(f"Pipeline step {i + 1}/{len(pipeline)}: {agent_key} completed")

    return results[-1] if results else "No output from pipeline."


async def _execute_v2_steps(
    skill: dict,
    user_message: str,
    system_key: str,
    user_id: str,
    kb_path,
    system_config,
    shared_config,
    channel,
    emit=None,
) -> str:
    """Execute a v2 skill (multi-step workflow)."""
    steps = skill.get("steps", [])
    if not steps:
        return "Skill has no steps defined."

    ctx = SkillContext(user_message, system_key, user_id)
    # Skill-level variables (e.g. a venture's spreadsheet ids) for {placeholders}.
    ctx.variables.update({str(k): str(v) for k, v in (skill.get("variables") or {}).items()})
    return await _run_v2_steps(
        steps, ctx, skill.get("name", ""), kb_path, system_config, shared_config, channel, emit=emit
    )


async def _run_v2_steps(
    steps: list, ctx, skill_name: str, kb_path, system_config, shared_config, channel, emit=None
) -> str:
    """Run v2 steps in order; pauses (and stores a resume point) at a human step.

    A step that fails (:class:`StepFailedError`) stops the workflow: nothing after
    it runs, and the result says where it stopped and why.
    """
    outputs = []

    for i, step in enumerate(steps):
        step_id = step.get("id", f"step_{i}")
        step_type = step.get("type", "agent")

        logger.info(f"Executing step {i + 1}/{len(steps)}: {step_id} ({step_type})")

        # Check condition for conditional steps
        condition = step.get("condition")
        if condition:
            condition_value = ctx.inject(condition)
            if "no" in condition_value.lower() or "skip" in condition_value.lower():
                logger.info(f"Skipping step {step_id} (condition not met)")
                continue

        if step_type == "agent":
            result = await _execute_agent_step(
                step,
                ctx,
                kb_path,
                system_config,
                shared_config,
                channel,
            )
        elif step_type == "tool":
            try:
                result = await _execute_tool_step(step, ctx, emit=emit)
            except StepHeldError as held:
                # Nothing after a held step may run before the operator decides:
                # dependants would act on an operation that has not happened.
                store_skill_resume_context(
                    ctx.user_id,
                    skill_name,
                    ctx,
                    steps[i + 1 :],
                    step_id=step_id,
                    approval_id=held.request_id,
                    kind="tool",
                )
                return str(held)
            except StepFailedError as failure:
                logger.warning("Skill %s stopped at step %s: %s", skill_name, step_id, failure)
                return f"⚠️ The workflow stopped at step '{step_id}': {failure}. Nothing after this step ran."
        elif step_type == "condition":
            result = await _execute_condition_step(step, ctx)
            if result == "__SKIP__":
                continue
            elif result == "__STOP__":
                break
        elif step_type == "delegate":
            result = await _execute_delegate_step(
                step,
                ctx,
                kb_path,
                system_config,
                shared_config,
                channel,
            )
        elif step_type == "human":
            result = await _execute_human_step(step, ctx)
            if result.startswith("__HUMAN_INPUT_NEEDED__"):
                question = result.replace("__HUMAN_INPUT_NEEDED__\n", "")
                approval_id = _create_skill_input_approval(ctx, skill_name, question)
                store_skill_resume_context(
                    ctx.user_id, skill_name, ctx, steps[i + 1 :], step_id=step_id, approval_id=approval_id
                )
                return question
        else:
            result = f"Unknown step type: {step_type}"

        ctx.step_results[step_id] = result
        outputs.append(result)
        ctx.progress_messages.append(f"Step {i + 1}/{len(steps)} ({step_id}): done")

    return outputs[-1] if outputs else "Skill completed with no output."


async def _execute_agent_step(step, ctx, kb_path, system_config, shared_config, channel) -> str:
    """Execute an agent step: call an LLM agent with context injection."""
    from realize_core.prompt.builder import build_system_prompt

    agent_key = step.get("agent", "orchestrator")
    inject_context = step.get("inject_context", [])
    custom_prompt = step.get("prompt") or step.get("instructions")

    system_prompt = build_system_prompt(
        kb_path=kb_path,
        system_config=system_config or {},
        system_key=ctx.system_key,
        agent_key=agent_key,
        shared_config=shared_config,
        channel=channel,
    )

    parts = []
    if inject_context:
        parts.append("## Context from previous steps\n")
        for ref in inject_context:
            if ref in ctx.step_results:
                parts.append(f"### {ref}\n{ctx.step_results[ref]}\n")
            elif ref in ctx.variables:
                parts.append(f"### {ref}\n{ctx.variables[ref]}\n")

    if custom_prompt:
        parts.append(ctx.inject(custom_prompt))
    else:
        parts.append(ctx.user_message)

    if step.get("review"):
        latest_output = list(ctx.step_results.values())[-1] if ctx.step_results else ""
        parts.append(f"\n\nPlease review this output:\n{latest_output}")

    assembled = "\n\n".join(parts)
    messages = [{"role": "user", "content": assembled}]

    return await _call_llm(system_prompt, messages, ctx.system_key)


async def _execute_delegate_step(step, ctx, kb_path, system_config, shared_config, channel) -> str:
    """
    Execute a delegate step: route work to another agent with full context.

    The delegate step passes accumulated context to the target agent and
    returns the result back into the delegation chain.

    Step schema:
        { "type": "delegate", "agent": "writer", "instructions": "...", "inject_context": [...] }
    """
    target_agent = step.get("agent")
    if not target_agent:
        return "Error: delegate step missing 'agent' field"

    instructions = step.get("instructions") or step.get("prompt")
    inject_context = step.get("inject_context", [])

    logger.info(f"Delegating to agent '{target_agent}' from step context")

    # Build the delegated agent step as a regular agent step
    agent_step = {
        "type": "agent",
        "agent": target_agent,
        "inject_context": inject_context,
    }
    if instructions:
        agent_step["prompt"] = ctx.inject(instructions)

    return await _execute_agent_step(
        agent_step,
        ctx,
        kb_path,
        system_config,
        shared_config,
        channel,
    )


def _parse_json_text(text: str):
    """Parse JSON that an agent step wrote, tolerating ```json fences and prose around it.

    Raises:
        ValueError: No JSON array or object could be read.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    try:
        return json.loads(cleaned)
    except ValueError:
        pass
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except ValueError:
                continue
    raise ValueError("no JSON array or object found")


class StepFailedError(Exception):
    """A skill step that can't produce a usable result; the workflow stops here."""


class StepHeldError(Exception):
    """A tool step the governance gate held for approval; the workflow pauses here."""

    def __init__(self, request_id: str, message: str):
        super().__init__(message)
        self.request_id = request_id


def _param_schema(registry, tool_name: str, key: str) -> dict:
    """The JSON schema of one input parameter of ``tool_name`` (empty when unknown)."""
    tool = registry.get_tool_for_action(tool_name)
    for schema in tool.get_schemas() if tool else []:
        if schema.name == tool_name:
            return (schema.input_schema or {}).get("properties", {}).get(key, {}) or {}
    return {}


def _check_shape(value, schema: dict) -> bool:
    """True when ``value`` has the container shape the schema asks for (array/object, rows)."""
    kind = schema.get("type")
    if kind == "array":
        if not isinstance(value, list) or not value:
            return False
        item_kind = (schema.get("items") or {}).get("type")
        if item_kind == "array":
            return all(isinstance(item, list) for item in value)
        if item_kind == "object":
            return all(isinstance(item, dict) for item in value)
        return True
    if kind == "object":
        return isinstance(value, dict)
    return True


async def _execute_tool_step(step, ctx, emit=None) -> str:
    """Execute a tool step through the registry (so the approval gate applies).

    String params are filled from ``{placeholders}``. Params listed in the
    step's ``json_params`` are parsed as JSON and must have the shape the
    tool's schema asks for (e.g. rows for ``sheets_append``), so an agent step
    can hand structured data to a tool.

    ``emit`` receives the same trail events as the chat tool loop
    (``tool_call``, ``approval_requested``, ``tool_result``).

    Returns the tool output, or a "waiting for approval" note when the gate
    held the action.

    Raises:
        StepFailedError: no or unknown tool, unusable JSON, blocked by policy, or
            the tool failed. The workflow stops instead of continuing on an
            error string.
    """
    import time

    from realize_core.agents.tool_loop import EVENT_PREVIEW_CHARS, emit_event
    from realize_core.tools.tool_registry import get_tool_registry

    step_id = step.get("id", "tool")
    tool_name = step.get("action", step.get("tool"))
    if not tool_name:
        raise StepFailedError("no tool specified in step")

    # Through the registry: the governance gate applies, and every registered
    # integration (Google, Sheets, ClickUp, MCP, web) is reachable.
    registry = get_tool_registry()
    if registry.get_tool_for_action(tool_name) is None:
        raise StepFailedError(f"unknown tool '{tool_name}'")

    raw_params = step.get("params", {})
    json_params = set(step.get("json_params") or [])
    params = {}
    for key, value in raw_params.items():
        params[key] = ctx.inject(str(value)) if isinstance(value, str) else value
        if key in json_params and isinstance(params[key], str):
            try:
                params[key] = _parse_json_text(params[key])
            except ValueError:
                raise StepFailedError(f"'{key}' for {tool_name} is not valid JSON") from None
            if not _check_shape(params[key], _param_schema(registry, tool_name, key)):
                raise StepFailedError(f"'{key}' for {tool_name} doesn't have the expected shape")

    await emit_event(emit, {"type": "tool_call", "id": step_id, "name": tool_name, "input": params})

    from realize_core.governance.context import tool_call_context

    started = time.perf_counter()
    with tool_call_context(system_key=ctx.system_key, agent_key="skill", user_id=ctx.user_id, channel="skill"):
        result = await registry.execute(tool_name, params)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)

    request_id = result.metadata.get("request_id") if result.metadata.get("requires_human") else None
    held = request_id is not None
    if held:
        await emit_event(
            emit, {"type": "approval_requested", "id": step_id, "name": tool_name, "request_id": request_id}
        )
    await emit_event(
        emit,
        {
            "type": "tool_result",
            "id": step_id,
            "name": tool_name,
            "success": result.success and not held,
            "held": held,
            "output": "" if held else (result.output or "")[:EVENT_PREVIEW_CHARS],
            "error": result.error,
            "duration_ms": duration_ms,
        },
    )

    if held:
        raise StepHeldError(
            request_id,
            f"⏳ '{tool_name}' was not run — it is waiting for operator approval (request {request_id}). "
            "The rest of the workflow continues once it is approved.",
        )
    if result.metadata.get("requires_human") or not result.success:
        reason = "blocked by governance policy" if result.metadata.get("requires_human") else (result.error or "")
        logger.warning("Tool step %s failed: %s", tool_name, reason)
        raise StepFailedError(f"{tool_name}: {reason[:300]}")
    output = result.output or ""
    if len(output) > 6000:
        output = output[:6000] + "\n... (truncated)"
    return output


async def _execute_condition_step(step, ctx) -> str:
    """Execute a condition step: branch based on previous results."""
    check = step.get("check", "")
    check_value = ctx.inject(check) if check else ""

    branches = step.get("branches", {})
    matched_branch = None

    for pattern, branch_action in branches.items():
        if pattern.lower() in check_value.lower():
            matched_branch = branch_action
            break

    if not matched_branch:
        matched_branch = branches.get("default", "continue")

    if matched_branch == "skip":
        return "__SKIP__"
    elif matched_branch == "stop":
        return "__STOP__"

    return f"Condition evaluated: matched '{matched_branch}'"


def _create_skill_input_approval(ctx, skill_name: str, question: str) -> str | None:
    """Create an approval item for a human step so it can be answered from the dashboard."""
    try:
        from realize_core.governance.gates import create_approval_request

        return create_approval_request(
            venture_key=ctx.system_key,
            agent_key=f"skill:{skill_name}" if skill_name else "skill",
            action_type="skill_input",
            payload={"question": question, "skill": skill_name},
            expires_minutes=24 * 60,
            requested_by=ctx.user_id,
            session_ref=f"{ctx.system_key}|{ctx.user_id}" if ctx.system_key and ctx.user_id else None,
        )
    except Exception:
        logger.warning("Could not create approval item for skill %s", skill_name, exc_info=True)
        return None


async def _execute_human_step(step, ctx) -> str:
    """Execute a human-in-the-loop step. Returns question for the user."""
    question = step.get("question", step.get("prompt", "Please confirm to continue."))
    question = ctx.inject(question)
    return f"__HUMAN_INPUT_NEEDED__\n{question}"


# ---------------------------------------------------------------------------
# SKILL.md execution path (V5)
# ---------------------------------------------------------------------------


async def _execute_skill_md(
    skill: dict,
    user_message: str,
    system_key: str,
    user_id: str,
    kb_path,
    system_config,
    shared_config,
    channel,
) -> str:
    """
    Execute a SKILL.md format skill.

    Uses the markdown body (``_instructions``) as detailed instructions
    appended to the agent's system prompt.  The ``agent`` field from
    the frontmatter determines which agent persona to use.
    """
    from realize_core.prompt.builder import build_system_prompt

    agent_key = skill.get("agent", "orchestrator")
    instructions = skill.get("_instructions", "")
    skill_name = skill.get("name", "unnamed")

    # Build base system prompt for the chosen agent
    system_prompt = build_system_prompt(
        kb_path=kb_path,
        system_config=system_config or {},
        system_key=system_key,
        agent_key=agent_key,
        user_message=user_message,
        shared_config=shared_config,
        channel=channel,
    )

    # Append the SKILL.md instructions as additional context
    if instructions:
        system_prompt = (
            f"{system_prompt}\n\n"
            f"## Active Skill: {skill_name}\n"
            f"Follow these detailed instructions for this task:\n\n"
            f"{instructions}"
        )

    messages = [{"role": "user", "content": user_message}]

    response = await _call_llm(system_prompt, messages, system_key)

    logger.info(f"SKILL.md execution complete: {skill_name}")
    return response
