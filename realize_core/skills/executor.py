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

# Storage for skill contexts awaiting user confirmation
_pending_skill_contexts: dict[str, dict] = {}


def store_skill_resume_context(user_id: str, skill_name: str, ctx, remaining_steps: list):
    """Store skill context for resumption after user confirms an action."""
    _pending_skill_contexts[user_id] = {
        "skill_name": skill_name,
        "context": ctx,
        "remaining_steps": remaining_steps,
    }
    logger.info(f"Stored skill resume context for user {user_id}, skill={skill_name}, "
                f"{len(remaining_steps)} steps remaining")


def pop_skill_resume_context(user_id: str) -> dict | None:
    """Pop and return the stored skill context for a user, if any."""
    return _pending_skill_contexts.pop(user_id, None)


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


async def execute_skill(
    skill: dict,
    user_message: str,
    system_key: str,
    user_id: str,
    kb_path=None,
    system_config: dict = None,
    shared_config: dict = None,
    channel: str = "api",
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

    Returns:
        Skill execution result text
    """
    skill_name = skill.get("name", "unnamed")
    version = skill.get("_version", 1)
    skill_format = skill.get("_format", "yaml")

    logger.info(f"Executing skill: {skill_name} (v{version}, format={skill_format}) "
                f"for system={system_key}")

    # V5: SKILL.md format — use markdown instructions
    if skill_format == "skill_md":
        return await _execute_skill_md(
            skill, user_message, system_key, user_id,
            kb_path, system_config, shared_config, channel,
        )

    if version == 1:
        return await _execute_v1_pipeline(
            skill, user_message, system_key, user_id,
            kb_path, system_config, shared_config, channel,
        )
    else:
        return await _execute_v2_steps(
            skill, user_message, system_key, user_id,
            kb_path, system_config, shared_config, channel,
        )


async def _execute_v1_pipeline(
    skill: dict,
    user_message: str,
    system_key: str,
    user_id: str,
    kb_path, system_config, shared_config, channel,
) -> str:
    """Execute a v1 skill (trigger -> agent pipeline)."""
    from realize_core.llm.claude_client import call_claude
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

        response = await call_claude(
            system_prompt=system_prompt,
            messages=messages,
        )
        results.append(response)
        logger.info(f"Pipeline step {i+1}/{len(pipeline)}: {agent_key} completed")

    return results[-1] if results else "No output from pipeline."


async def _execute_v2_steps(
    skill: dict,
    user_message: str,
    system_key: str,
    user_id: str,
    kb_path, system_config, shared_config, channel,
) -> str:
    """Execute a v2 skill (multi-step workflow)."""
    steps = skill.get("steps", [])
    if not steps:
        return "Skill has no steps defined."

    ctx = SkillContext(user_message, system_key, user_id)
    outputs = []

    for i, step in enumerate(steps):
        step_id = step.get("id", f"step_{i}")
        step_type = step.get("type", "agent")

        logger.info(f"Executing step {i+1}/{len(steps)}: {step_id} ({step_type})")

        # Check condition for conditional steps
        condition = step.get("condition")
        if condition:
            condition_value = ctx.inject(condition)
            if "no" in condition_value.lower() or "skip" in condition_value.lower():
                logger.info(f"Skipping step {step_id} (condition not met)")
                continue

        if step_type == "agent":
            result = await _execute_agent_step(
                step, ctx, kb_path, system_config, shared_config, channel,
            )
        elif step_type == "tool":
            result = await _execute_tool_step(step, ctx)
        elif step_type == "condition":
            result = await _execute_condition_step(step, ctx)
            if result == "__SKIP__":
                continue
            elif result == "__STOP__":
                break
        elif step_type == "delegate":
            result = await _execute_delegate_step(
                step, ctx, kb_path, system_config, shared_config, channel,
            )
        elif step_type == "human":
            result = await _execute_human_step(step, ctx)
            if result.startswith("__HUMAN_INPUT_NEEDED__"):
                # Store context for resumption
                remaining = steps[i+1:]
                store_skill_resume_context(user_id, skill.get("name", ""), ctx, remaining)
                return result.replace("__HUMAN_INPUT_NEEDED__\n", "")
        else:
            result = f"Unknown step type: {step_type}"

        ctx.step_results[step_id] = result
        outputs.append(result)
        ctx.progress_messages.append(f"Step {i+1}/{len(steps)} ({step_id}): done")

    return outputs[-1] if outputs else "Skill completed with no output."


async def _execute_agent_step(step, ctx, kb_path, system_config, shared_config, channel) -> str:
    """Execute an agent step: call an LLM agent with context injection."""
    from realize_core.llm.claude_client import call_claude
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

    return await call_claude(system_prompt=system_prompt, messages=messages)


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
        agent_step, ctx, kb_path, system_config, shared_config, channel,
    )


async def _execute_tool_step(step, ctx) -> str:
    """Execute a tool step: call a registered tool function."""
    tool_name = step.get("action", step.get("tool"))
    if not tool_name:
        return "Error: no tool specified in step"

    raw_params = step.get("params", {})
    params = {}
    for key, value in raw_params.items():
        params[key] = ctx.inject(str(value)) if isinstance(value, str) else value

    # Try to find the tool function in registered tool modules
    try:
        from realize_core.tools.web import TOOL_FUNCTIONS as WEB_TOOLS
        all_funcs = dict(WEB_TOOLS)
    except ImportError:
        all_funcs = {}

    try:
        from realize_core.tools.google_workspace import TOOL_FUNCTIONS as GOOGLE_TOOLS
        all_funcs.update(GOOGLE_TOOLS)
    except ImportError:
        pass

    func = all_funcs.get(tool_name)
    if not func:
        return f"Error: unknown tool '{tool_name}'"

    try:
        result = await func(**params)
        result_str = json.dumps(result, indent=2, default=str, ensure_ascii=False)
        if len(result_str) > 6000:
            result_str = result_str[:6000] + "\n... (truncated)"
        return result_str
    except Exception as e:
        logger.error(f"Tool step error ({tool_name}): {e}", exc_info=True)
        return f"Error executing {tool_name}: {str(e)[:300]}"


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
    kb_path, system_config, shared_config, channel,
) -> str:
    """
    Execute a SKILL.md format skill.

    Uses the markdown body (``_instructions``) as detailed instructions
    appended to the agent's system prompt.  The ``agent`` field from
    the frontmatter determines which agent persona to use.
    """
    from realize_core.llm.claude_client import call_claude
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

    response = await call_claude(
        system_prompt=system_prompt,
        messages=messages,
    )

    logger.info(f"SKILL.md execution complete: {skill_name}")
    return response
