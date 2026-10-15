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
import re
from contextlib import AbstractContextManager, nullcontext
from datetime import date

logger = logging.getLogger(__name__)

#: A ``{name}`` placeholder in a skill template.
_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
#: Skill/step fields that pin which model answers an LLM step.
_ROUTE_FIELDS = ("model", "tier", "task_type")


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
    gone = _initiator_refusal(ctx)
    if gone:
        return _stopped_after(pending, step_id, gone)
    ctx.step_results[step_id] = answer
    logger.info("Resuming skill %s for %s after step %s", pending.get("skill_name"), user_id, step_id)
    with _as_run_for(ctx):
        return await _run_v2_steps(
            pending.get("remaining_steps", []),
            ctx,
            pending.get("skill_name", ""),
            kb_path,
            system_config,
            shared_config,
            channel,
        )


def _as_run_for(ctx: "SkillContext") -> AbstractContextManager:
    """Resume a paused run as what it was: an outside agent's run stays governed as the agent's.

    The marker comes from what the resume point stored, never from whoever
    resumes it (a person approving or answering), so it fails closed.
    """
    if not ctx.outside_agent:
        return nullcontext()
    from realize_core.security.agent_access import acting_for_outside_agent

    return acting_for_outside_agent(ctx.outside_agent)


def _stopped_after(pending: dict, step_id: str, reason: str) -> str:
    """The message for a paused run that is stopped instead of resumed (its agent is gone)."""
    logger.warning("Skill %s not resumed after step %s: %s", pending.get("skill_name"), step_id, reason)
    return f"⚠️ The workflow stopped after step '{step_id}': {reason}. Nothing after this step ran."


def _initiator_refusal(ctx: "SkillContext") -> str | None:
    """Why a run an outside agent started must stop now, or None (also None for anyone else's run)."""
    if not ctx.outside_agent:
        return None
    from realize_core.mcp_server.held_writes import live_requester

    principal, refusal = live_requester(ctx.outside_agent, ctx.system_key)
    if principal is not None:
        return None
    return (refusal or "the agent that started it is no longer active").removesuffix("; nothing was done")


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
        # A fixed line only: the tool's error can carry third-party text, and this
        # message goes into the conversation (the error itself is on the approval row).
        logger.warning("Approved step %s failed; skill %s stopped", step_id, pending.get("skill_name"))
        return f"⚠️ The workflow stopped at step '{step_id}': the approved action failed. Nothing after this step ran."
    ctx = pending["context"]
    gone = _initiator_refusal(ctx)
    if gone:
        return _stopped_after(pending, step_id, gone)
    ctx.step_results[step_id] = _bounded_tool_output(execution.get("output", ""))
    logger.info("Resuming skill %s after approved step %s", pending.get("skill_name"), step_id)
    with _as_run_for(ctx):
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
        #: The outside agent (``agent:...``) the run is for, kept when it pauses so
        #: the rest of the run is still governed as the agent's (review G-3).
        self.outside_agent: str | None = None
        #: The skill's own ``model`` / ``tier`` / ``task_type`` (steps may override).
        self.llm_route: dict[str, str] = {}
        #: Every step id of the running skill, so ``{step}`` can be told from other braces.
        self.known_steps: set[str] = set()
        #: The step being run (for error messages).
        self.current_step: str = ""

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
            "outside_agent": self.outside_agent,
            "llm_route": self.llm_route,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillContext":
        """Rebuild a context saved with :meth:`to_dict`."""
        ctx = cls(data.get("user_message", ""), data.get("system_key", ""), data.get("user_id", ""))
        ctx.step_results = dict(data.get("step_results") or {})
        ctx.variables = dict(data.get("variables") or ctx.variables)
        ctx.progress_messages = list(data.get("progress_messages") or [])
        ctx.annotations = dict(data.get("annotations") or {})
        outside_agent = data.get("outside_agent")
        ctx.outside_agent = outside_agent if isinstance(outside_agent, str) and outside_agent else None
        ctx.llm_route = _skill_route(data.get("llm_route") or {})
        return ctx

    def inject(self, template: str) -> str:
        """Replace {variable} placeholders in a template string, in one pass.

        Only the template is scanned: values (step results, variables, the
        user's message) are untrusted data and are inserted as they are, so a
        ``{name}`` inside them is neither expanded nor an error.

        Raises:
            StepFailedError: the template names a known step that has no
                result yet. Unknown ``{names}`` and JSON braces are left alone.
        """
        values: dict[str, str] = {"user_message": self.user_message, "today": date.today().isoformat()}
        values.update({var: str(value) for var, value in self.variables.items()})
        values.update({step_id: str(value) for step_id, value in self.step_results.items()})
        for name in _PLACEHOLDER.findall(template):
            if name in self.known_steps and name not in values:
                raise StepFailedError(f"unresolved placeholder {{{name}}} in step {self.current_step}")
        return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), template)


def _skill_route(source: dict) -> dict[str, str]:
    """The routing fields (``model``, ``tier``, ``task_type``) a skill or step sets."""
    return {k: str(source[k]) for k in _ROUTE_FIELDS if source.get(k)}


def _resolve_route(step: dict | None, skill_route: dict | None) -> dict[str, str]:
    """Which model answers a step, as one ``route_completion`` keyword (or none).

    Precedence: step.model > step.tier > skill.model > skill.tier > skill.task_type.
    Empty means "classify the user's message".

    Raises:
        StepFailedError: the winning tier is not a router tier.
    """
    from realize_core.llm.router import TIERS

    route: dict[str, str] = {}
    for source in (step or {}, skill_route or {}):
        if source.get("model"):
            route = {"model": str(source["model"])}
            break
        if source.get("tier"):
            route = {"tier": str(source["tier"])}
            break
    if not route and (skill_route or {}).get("task_type"):
        route = {"task_type": str(skill_route["task_type"])}
    if route.get("tier") and route["tier"] not in TIERS:
        raise StepFailedError(f"unknown tier '{route['tier']}' (use {', '.join(TIERS)})")
    return route


async def _call_llm(
    system_prompt: str,
    messages: list[dict],
    system_key: str,
    *,
    user_message: str | None = None,
    route: dict[str, str] | None = None,
    response_schema: dict | None = None,
) -> str:
    """LLM call for skill steps — through the router (rate/cost limits, provider fallback).

    ``route`` (from :func:`_resolve_route`) pins a model, tier or task type.
    Without one the task type is classified from ``user_message`` (the user's
    own words, never the assembled step prompt).
    """
    from realize_core.llm import router

    kwargs: dict = dict(route or {})
    if not kwargs:
        if user_message is None:
            last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
            user_message = last_user if isinstance(last_user, str) else ""
        kwargs["task_type"] = router.classify_task(user_message, system_key=system_key)
    if response_schema is not None:
        kwargs["response_schema"] = response_schema
    response = await router.route_completion(system_prompt, messages, system_key=system_key, **kwargs)
    if response.refused:
        # A refusal is the model's answer: show it, not the bare "refusal" error code.
        reason = (response.text or "").strip()
        raise StepFailedError(f"The model declined this step: {reason}" if reason else "The model declined this step.")
    if not response.ok:
        raise StepFailedError(response.error or response.text or "the LLM call failed")
    return response.text


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

    if skill.get("_layer"):
        # A skill from a profession or market pack: the trail says where it came from.
        from realize_core.agents.tool_loop import emit_event
        from realize_core.packs.skills import skill_trail_source

        await emit_event(emit, skill_trail_source(skill))

    if skill_format == "skill_md" or version == 1:
        # V5 SKILL.md (markdown instructions) or a v1 agent pipeline: one route for the skill.
        run = _execute_skill_md if skill_format == "skill_md" else _execute_v1_pipeline
        try:
            return await run(
                skill,
                user_message,
                system_key,
                user_id,
                kb_path,
                system_config,
                shared_config,
                channel,
            )
        except StepFailedError as failure:
            logger.warning("Skill %s stopped: %s", skill_name, failure)
            return f"⚠️ The skill '{skill_name}' stopped: {failure}."
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

        response = await _call_llm(
            system_prompt,
            messages,
            system_key,
            user_message=user_message,
            route=_resolve_route(None, _skill_route(skill)),
        )
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

    from realize_core.security.agent_access import outside_agent_marker

    ctx = SkillContext(user_message, system_key, user_id)
    ctx.outside_agent = outside_agent_marker()
    ctx.llm_route = _skill_route(skill)
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
    it runs, and the result says where it stopped and why. A run an outside
    agent started stops too, before the next step, once that agent is gone
    (token revoked or expired, agent tokens turned off, user removed).
    """
    outputs = []
    ctx.known_steps = {step.get("id", f"step_{i}") for i, step in enumerate(steps)} | set(ctx.step_results)

    for i, step in enumerate(steps):
        step_id = step.get("id", f"step_{i}")
        step_type = step.get("type", "agent")
        ctx.current_step = step_id

        gone = _initiator_refusal(ctx) if i else None  # a resume checks before its first step
        if gone:
            logger.warning("Skill %s stopped before step %s: %s", skill_name, step_id, gone)
            return f"⚠️ The workflow stopped before step '{step_id}': {gone}. Nothing after this point ran."

        logger.info(f"Executing step {i + 1}/{len(steps)}: {step_id} ({step_type})")

        try:
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
                    json_schema=_json_consumer_schema(step_id, steps[i + 1 :]),
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
        except StepFailedError as failure:
            logger.warning("Skill %s stopped at step %s: %s", skill_name, step_id, failure)
            return f"⚠️ The workflow stopped at step '{step_id}': {failure}. Nothing after this step ran."

        ctx.step_results[step_id] = result
        outputs.append(result)
        ctx.progress_messages.append(f"Step {i + 1}/{len(steps)} ({step_id}): done")

    return outputs[-1] if outputs else "Skill completed with no output."


async def _execute_agent_step(
    step, ctx, kb_path, system_config, shared_config, channel, *, json_schema: dict | None = None
) -> str:
    """Execute an agent step: call an LLM agent with context injection.

    ``json_schema`` (not None) marks a JSON step: a later tool step parses this
    step's output as JSON with that schema (``{}`` = shape unknown). See
    :func:`_complete_json_step`.
    """
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
    context_text = "\n".join(parts)

    instructions = ctx.inject(custom_prompt) if custom_prompt else ctx.user_message
    parts.append(instructions)

    if step.get("review"):
        latest_output = list(ctx.step_results.values())[-1] if ctx.step_results else ""
        parts.append(f"\n\nPlease review this output:\n{latest_output}")

    assembled = "\n\n".join(parts)
    route = _resolve_route(step, ctx.llm_route)
    if json_schema is not None:
        return await _complete_json_step(
            system_prompt, assembled, ctx, route, json_schema, prompt_text=instructions, context_text=context_text
        )
    messages = [{"role": "user", "content": assembled}]
    return await _call_llm(system_prompt, messages, ctx.system_key, user_message=ctx.user_message, route=route)


async def _complete_json_step(
    system_prompt: str, assembled: str, ctx, route: dict, schema: dict, *, prompt_text: str, context_text: str
) -> str:
    """Run a JSON step: ask for structured output, validate it, retry once.

    The provider gets the tool's parameter schema as ``response_schema``
    (wrapped in an object; see :func:`_response_schema`). The reply must parse
    as JSON, have the schema's shape and pass :func:`_reject_placeholder_echo`.
    A rejected reply is retried once with the reason appended to the request.

    Returns:
        The validated value as JSON text (what the tool step parses).

    An empty or untyped schema sends no ``response_schema``: the reply is
    only parsed and retried. A failed LLM call stops the step at once.

    Raises:
        StepFailedError: the retry was rejected too, or the LLM call failed.
    """
    response_schema = _response_schema(schema) if _is_typed(schema) else None
    message = assembled
    reason = ""
    for attempt in (1, 2):
        text = await _call_llm(
            system_prompt,
            [{"role": "user", "content": message}],
            ctx.system_key,
            user_message=ctx.user_message,
            route=route,
            response_schema=response_schema,
        )
        try:
            value = _validated_json(text, schema, prompt_text, context_text)
        except ValueError as err:
            reason = str(err)
            logger.warning("JSON step %s rejected (attempt %d): %s", ctx.current_step, attempt, reason)
            message = (
                f"{assembled}\n\nYour previous answer was rejected: {reason}. "
                "Return only the JSON, filled with the real values from the context above."
            )
            continue
        return json.dumps(value, ensure_ascii=False)
    raise StepFailedError(f"no usable JSON after one retry ({reason})")


def _json_consumer_schema(step_id: str, later_steps: list) -> dict | None:
    """The schema a later tool step parses this step's output with, or None if none does.

    A consumer is a tool step with a ``json_params`` key whose param references
    ``{step_id}``. Returns that tool parameter's schema (``{}`` when unknown).
    """
    from realize_core.tools.tool_registry import get_tool_registry

    token = f"{{{step_id}}}"
    for later in later_steps:
        if later.get("type", "agent") != "tool":
            continue
        tool_name = later.get("action", later.get("tool"))
        params = later.get("params") or {}
        for key in later.get("json_params") or []:
            if isinstance(params.get(key), str) and token in params[key]:
                return _param_schema(get_tool_registry(), tool_name, key) if tool_name else {}
    return None


#: A table cell: text or a number (an empty ``{}`` item schema becomes "object" on some providers).
_CELL_SCHEMA = {"anyOf": [{"type": "string"}, {"type": "number"}]}


_TYPING_KEYS = ("type", "anyOf", "oneOf", "allOf", "properties", "items", "enum", "const", "$ref")


def _is_typed(schema: dict | None) -> bool:
    """True when ``schema`` says anything about the value's type (``{}`` does not)."""
    return isinstance(schema, dict) and any(schema.get(k) not in (None, {}, []) for k in _TYPING_KEYS)


def _response_schema(schema: dict) -> dict:
    """A ``response_schema`` every provider accepts, derived from a tool parameter schema.

    The root is an object (``{"value": <schema>}`` unless the schema is one):
    some providers only accept object roots. Empty item schemas become
    text-or-number cells.
    """

    def fill(node):
        if isinstance(node, dict):
            out = {k: fill(v) for k, v in node.items()}
            if out.get("items") == {}:
                out["items"] = dict(_CELL_SCHEMA)
            return out
        if isinstance(node, list):
            return [fill(v) for v in node]
        return node

    inner = fill(schema)
    if inner.get("type") == "object":
        return inner
    return {"type": "object", "properties": {"value": inner}, "required": ["value"]}


def _validated_json(text: str, schema: dict, prompt_text: str, context_text: str):
    """Parse a JSON step's reply and check it is real data of the expected shape.

    Raises:
        ValueError: not JSON, the wrong shape, or an echo of the prompt's template.
    """
    value = _parse_json_text(text)
    if schema.get("type") != "object" and isinstance(value, dict) and set(value) == {"value"}:
        value = value["value"]  # the object wrapper from _response_schema
    if not _check_shape(value, schema):
        raise ValueError("the JSON doesn't have the expected shape")
    _reject_placeholder_echo(value, prompt_text, context_text)
    return value


def _string_leaves(value) -> list[str]:
    """Every string inside a JSON value (dict values, list items), in order."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [leaf for v in value.values() for leaf in _string_leaves(v)]
    if isinstance(value, list):
        return [leaf for v in value for leaf in _string_leaves(v)]
    return []


#: Bracketed example rows in a prompt (innermost ``[...]``) and the quoted labels in them.
_EXAMPLE_ROW = re.compile(r"\[[^\[\]]*\]")
_QUOTED = re.compile(r'"([^"\n]+)"')
#: Separators that split context data into whole values (cells, "label: value" parts, lines).
_CONTEXT_SPLIT = re.compile(r'[\n\r\t|,;:"\[\]{}]+')
_BARE_PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def _reject_placeholder_echo(value, prompt_text: str, context_text: str = "") -> None:
    """Fail when a JSON step copied its prompt's template instead of filling it in.

    Two deliberately narrow checks:

    1. Any string leaf that is a bare placeholder token, e.g. ``"{contractor}"``.
    2. The first row (``value[0]`` for a list, else ``value``) has string leaves,
       EVERY one of them is a label quoted in an example row of the prompt (a
       ``[...]`` group such as ``["contractor", "milestone", "verdict"]``), and
       NONE of them is a whole value in the injected context data (the context
       split on line breaks, ``|``, ``,``, ``;``, ``:``, quotes and brackets,
       compared case-sensitively). A label the data really holds is accepted.

    Raises:
        ValueError: the reason, which the retry shows the model.
    """
    for leaf in _string_leaves(value):
        if _BARE_PLACEHOLDER.fullmatch(leaf.strip()):
            raise ValueError(f"'{leaf}' is a placeholder, not a value")

    row = value[0] if isinstance(value, list) and value else value
    leaves = [leaf.strip() for leaf in _string_leaves(row)]
    labels = {label.strip() for group in _EXAMPLE_ROW.findall(prompt_text) for label in _QUOTED.findall(group)}
    if not leaves or not labels or not all(leaf in labels for leaf in leaves):
        return
    data_values = {part.strip(" -*#•") for part in _CONTEXT_SPLIT.split(context_text)}
    if any(leaf in data_values for leaf in leaves):
        return
    raise ValueError(f"the row repeats the example's template labels ({', '.join(leaves)}) instead of real values")


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
        **{k: step[k] for k in ("model", "tier") if step.get(k)},
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
    return _bounded_tool_output(result.output or "")


def _bounded_tool_output(output: str) -> str:
    """Tool output as a step result: capped, the same for direct and approved runs."""
    if len(output) > 6000:
        return output[:6000] + "\n... (truncated)"
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

    response = await _call_llm(
        system_prompt,
        messages,
        system_key,
        user_message=user_message,
        route=_resolve_route(None, _skill_route(skill)),
    )

    logger.info(f"SKILL.md execution complete: {skill_name}")
    return response
