"""
Base Handler: The core message processing pipeline for RealizeOS.

Provides composable building blocks for handling incoming messages across
any channel (API, Telegram, Slack, etc.). Each channel adapter calls these
shared functions to process messages through the standard flow.
"""

import logging
from pathlib import Path

from realize_core.agents.tool_loop import emit_event
from realize_core.llm.router import classify_task, route_to_llm
from realize_core.memory.conversation import add_message, get_history, to_llm_messages
from realize_core.pipeline.creative import (
    execute_pipeline_step,
)
from realize_core.pipeline.session import CreativeSession, get_session
from realize_core.prompt.builder import build_system_prompt

logger = logging.getLogger(__name__)

#: Added to the system prompt when an agent's tools could not be used this turn.
NO_LIVE_DATA_NOTE = (
    "You have no access to live tools or data in this turn. If the question needs data you cannot see, "
    "say so plainly and do not claim to have read or checked anything."
)
TOOLS_UNAVAILABLE_MESSAGE = "No AI provider with tool support is available, so this answer used no live tools or data."
TOOLS_ERROR_MESSAGE = "Using tools failed for this answer, so it was given without live tools or data."

# Knowledge-question prefixes (skip skill detection for these)
INFO_PREFIXES = (
    "summarize",
    "explain",
    "what is",
    "what are",
    "describe",
    "tell me about",
    "how does",
    "how do",
    "overview of",
    "define",
)


def select_agent(agent_routing: dict, message: str, default: str = "orchestrator") -> str:
    """Select the best agent based on keyword scoring."""
    msg_lower = message.lower()
    scores = {}
    for agent, keywords in agent_routing.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > 0:
            scores[agent] = score
    if not scores:
        return default
    return max(scores, key=scores.get)


async def check_and_execute_skill(
    system_key: str,
    user_id: str,
    message: str,
    kb_path=None,
    system_config: dict = None,
    shared_config: dict = None,
    channel: str = "api",
    emit=None,
) -> tuple[bool, str | None]:
    """
    Check for skill auto-trigger and execute if found.

    ``emit`` receives the skill's trail (tool steps, held approvals) and then
    ``message_saved`` with the stored answer's id, like plain chat.

    Returns (handled, result) where handled=True means the caller should
    use result as the response.
    """
    from realize_core.skills.detector import detect_skill
    from realize_core.skills.executor import execute_skill

    skill = detect_skill(message, system_key)

    msg_lower = message.lower().strip()
    is_knowledge_question = any(msg_lower.startswith(p) for p in INFO_PREFIXES)

    if not skill or (is_knowledge_question and skill.get("_version", 1) == 1):
        return False, None

    from realize_core.security.agent_access import outside_agent_active

    if outside_agent_active():
        # An outside agent doesn't start skills by phrasing (STORY-37): it asks for
        # the run with trigger_skill, which a person approves first.
        name = skill.get("name", "unnamed")
        logger.info("Skill %s not auto-run for an outside agent in %s", name, system_key)
        result = (
            f"This matches the workflow '{name}'. An outside agent runs workflows with the trigger_skill "
            "(or run_workflow) tool; a person approves the run before it starts."
        )
        add_message(system_key, user_id, "user", message)
        message_id = add_message(system_key, user_id, "assistant", result)
        if message_id is not None:
            await emit_event(emit, {"type": "message_saved", "message_id": message_id})
        return True, result

    logger.info(f"Skill triggered: {skill.get('name', 'unnamed')} for {system_key}")
    result = await execute_skill(
        skill=skill,
        user_message=message,
        system_key=system_key,
        user_id=user_id,
        kb_path=kb_path,
        system_config=system_config,
        shared_config=shared_config,
        channel=channel,
        emit=emit,
    )

    if result is not None:
        add_message(system_key, user_id, "user", message)
        message_id = add_message(system_key, user_id, "assistant", result)
        if message_id is not None:
            await emit_event(emit, {"type": "message_saved", "message_id": message_id})
        return True, result

    return False, None


async def standard_llm_handling(
    system_key: str,
    agent_key: str,
    user_id: str,
    message: str,
    kb_path=None,
    system_config: dict = None,
    shared_config: dict = None,
    extra_context_files: list[str] = None,
    channel: str = "api",
    features: dict = None,
    all_systems: dict = None,
    emit=None,
) -> str:
    """
    Standard single-agent LLM handling: build prompt, classify, route, respond.

    This is the main message processing function for non-skill, non-session messages.
    With ``features.agent_tools`` on, the agent answers through the tool loop
    (it may call registry tools, governed by the approval gate).

    ``emit`` receives the "what I used" trail as it happens: one ``source``
    event per numbered KB source in the prompt, the tool loop's events, and
    finally ``message_saved`` with the stored assistant message id.
    """
    sources: list[dict] = []
    system_prompt = build_system_prompt(
        kb_path=kb_path,
        system_config=system_config or {},
        system_key=system_key,
        agent_key=agent_key,
        user_message=message,
        extra_context_files=extra_context_files,
        shared_config=shared_config,
        channel=channel,
        features=features,
        all_systems=all_systems,
        sources_out=sources,
    )
    for source in sources:
        await emit_event(emit, {"type": "source", **source})

    history = get_history(system_key, user_id)
    add_message(system_key, user_id, "user", message)
    messages = to_llm_messages(history) + [{"role": "user", "content": message}]

    response = None
    if (features or {}).get("agent_tools"):
        from realize_core.governance.context import tool_call_context

        with tool_call_context(system_key=system_key, agent_key=agent_key, user_id=user_id, channel=channel):
            response, tools_lost = await _answer_with_tools(
                system_prompt, messages, agent_key, kb_path, system_config or {}, emit=emit, message=message
            )
        if tools_lost:
            system_prompt = f"{system_prompt}\n\n{NO_LIVE_DATA_NOTE}"
    if response is None:
        task_class = classify_task(message, system_key=system_key)
        response = await route_to_llm(system_prompt, messages, task_class)

    message_id = add_message(system_key, user_id, "assistant", response)
    if message_id is not None:
        await emit_event(emit, {"type": "message_saved", "message_id": message_id})
    return response


def agent_tool_schemas(agent_key: str, kb_path, system_config: dict) -> list[dict]:
    """Tool schemas an agent may use: available registry tools, persona-gated.

    A ``<agent>.persona.yaml`` next to the agent (``tools_allowlist`` /
    ``tools_denylist``, by tool name such as ``google_sheets``) narrows the set.
    Write actions are offered only while the governance gate is installed
    (``features.enforce_gates``); without it agents get read-only tools, so
    nothing can change external systems without the approval path.
    """
    from types import SimpleNamespace

    from realize_core.agents.persona import resolve_persona
    from realize_core.tools.gating import get_gated_schemas
    from realize_core.tools.tool_registry import get_tool_registry

    persona = None
    agents_dir = system_config.get("agents_dir")
    if kb_path is not None and agents_dir:
        persona = resolve_persona(SimpleNamespace(key=agent_key, persona=None), Path(kb_path) / agents_dir)
    registry = get_tool_registry()
    schemas = get_gated_schemas(registry.get_available_tools(), persona)
    if not registry.has_gate:
        schemas = [s for s in schemas if registry.is_destructive(s["name"]) is False]
    return schemas


def _tool_loop_route(message: str):
    """(provider, model) for the agent tool loop, following tier routing.

    The tier comes from the user message (``message_tier``, ``standard`` when
    no category matches). The provider ``resolve_tier`` picks for it (an
    ``LLM_MODEL_<TIER>`` pin, else the primary) is used with that model when it
    is available and that model supports tools (checked per model: on Ollama a
    pinned model may lack tools that the default model has). Otherwise the
    first tool-capable provider (``tool_capable_provider``) runs with its own
    model for the tier.
    """
    from realize_core.agents import tool_loop
    from realize_core.llm.base_provider import Capability
    from realize_core.llm.registry import get_registry
    from realize_core.llm.router import _tier_model, message_tier, resolve_tier

    tier = message_tier(message)
    registry = get_registry()
    name, model_id = resolve_tier(tier)
    provider = registry.get_provider_by_name(name) if name else None
    try:
        usable = bool(
            provider
            and provider.is_available()
            and (
                provider.supports_model(model_id, Capability.TOOLS) if model_id else provider.supports(Capability.TOOLS)
            )
        )
    except Exception as e:
        logger.debug(f"Tool support check failed for {name}: {e}")
        usable = False
    if usable:
        return provider, model_id
    provider = tool_loop.tool_capable_provider()
    if provider is None:
        return None, None
    try:
        model = _tier_model(registry, provider, tier)
    except Exception as e:
        logger.debug(f"No {tier} model for {getattr(provider, 'name', provider)}: {e}")
        model = None
    return provider, model


async def _answer_with_tools(
    system_prompt, messages, agent_key, kb_path, system_config, emit=None, message: str = ""
) -> tuple[str | None, bool]:
    """Answer via the agent tool loop.

    Returns ``(answer, tools_lost)``. ``answer`` None means "use plain routing
    instead"; ``tools_lost`` means the agent had tools but could not use them
    this turn, so the plain answer must not pretend it read live data. That
    case is never silent: it is logged and reported as a trail ``notice``.
    """
    from realize_core.agents.tool_loop import run_tool_loop

    tools = agent_tool_schemas(agent_key, kb_path, system_config)
    if not tools:
        return None, False
    provider, model = _tool_loop_route(message)
    if provider is None:
        logger.warning("Agent %s has %d tools but no tool-capable LLM provider is available", agent_key, len(tools))
        await _notice(emit, "tools_unavailable", TOOLS_UNAVAILABLE_MESSAGE)
        return None, True
    result = await run_tool_loop(system_prompt, messages, tools, provider=provider, model=model, emit=emit)
    if result.stop_reason == "error":
        logger.warning("Tool loop for agent %s failed on %s; answering without tools", agent_key, provider.name)
        await _notice(emit, "tools_error", TOOLS_ERROR_MESSAGE)
        return None, True
    return result.text, False


async def _notice(emit, code: str, message: str) -> None:
    """Report an answer-quality notice on the "what I used" trail."""
    await emit_event(emit, {"type": "notice", "code": code, "message": message})


async def handle_session_message(
    session: CreativeSession,
    user_id: str,
    message: str,
    kb_path=None,
    system_config: dict = None,
    shared_config: dict = None,
    extra_context_files: list[str] = None,
    channel: str = "api",
) -> str:
    """Handle a message within an active creative session."""
    response = await execute_pipeline_step(
        session=session,
        user_id=user_id,
        message=message,
        kb_path=kb_path,
        system_config=system_config,
        shared_config=shared_config,
        extra_context_files=extra_context_files,
        channel=channel,
    )

    if session.stage == "briefing":
        session.stage = "drafting"
        session.save()
    elif session.stage == "drafting":
        session.stage = "iterating"
        session.save()

    response += f"\n\n{session.summary()}"
    return response


async def handle_review(
    system_key: str,
    user_id: str,
    kb_path=None,
    system_config: dict = None,
    shared_config: dict = None,
    reviewer_agent: str = "reviewer",
    reviewer_context: list[str] = None,
    review_criteria: str = "quality, voice consistency, and accuracy",
    channel: str = "api",
) -> str:
    """Run reviewer/gatekeeper review on the latest assistant output."""
    from realize_core.llm.router import route_completion

    session = get_session(system_key, user_id)

    content_to_review = None
    prior_stage = session.stage if session else None
    if session and session.drafts:
        latest = session.latest_draft()
        content_to_review = latest["content"]
        session.stage = "reviewing"
        session.active_agent = reviewer_agent
        session.save()
    else:
        history = get_history(system_key, user_id)
        for msg in reversed(history):
            if msg["role"] == "assistant":
                content_to_review = msg["content"]
                break

    if not content_to_review:
        return "No previous output to review. Create something first!"

    system_prompt = build_system_prompt(
        kb_path=kb_path,
        system_config=system_config or {},
        system_key=system_key,
        agent_key=reviewer_agent,
        extra_context_files=reviewer_context or [],
        shared_config=shared_config,
        session=session,
        channel=channel,
    )

    review_messages = [
        {
            "role": "user",
            "content": (
                f"Please review this output for {review_criteria}:\n\n"
                f"---\n{content_to_review}\n---\n\n"
                f"Provide: (1) Verdict: APPROVED or REVISIONS NEEDED, (2) Specific feedback."
            ),
        }
    ]

    result = await route_completion(system_prompt, review_messages, tier="standard", system_key=system_key)
    if not result.ok:
        # Never store a failure as review content.
        logger.warning("Review for %s failed: %s", system_key, result.error)
        if session and session.stage == "reviewing":
            session.stage = prior_stage
            session.save()
        return f"I could not run the review right now ({result.error or 'the LLM call failed'}). Please try again."
    response = result.text

    if session:
        session.review = {"verdict": "reviewed", "content": response}
        if "approved" in response.lower():
            session.stage = "approved"
        else:
            session.stage = "iterating"
        session.save()
        response += f"\n\n{session.summary()}"

    return response


async def process_message(
    system_key: str,
    user_id: str,
    message: str,
    kb_path=None,
    system_config: dict = None,
    shared_config: dict = None,
    channel: str = "api",
    features: dict = None,
    all_systems: dict = None,
    emit=None,
    requested_agent: str | None = None,
    selected: dict | None = None,
) -> str:
    """
    Main entry point: process an incoming message through the full pipeline.

    ``requested_agent`` is an agent the caller chose (the chat page's agent
    picker); it replaces keyword routing when it is one of this venture's
    agents. ``selected``, when given, receives ``agent_key``: the agent that
    actually answered (after the missing-file and paused-agent fallbacks).

    Flow:
    1. Log message_received (activity log)
    2. Check for active creative session
    3. Check for skill trigger
    4. Select agent and route to LLM
    5. Track agent status transitions (lifecycle)
    """
    features = features or {}

    # --- Activity: log message received ---
    if features.get("activity_log"):
        try:
            from realize_core.activity.logger import log_event

            log_event(
                venture_key=system_key,
                actor_type="user",
                actor_id=user_id,
                action="message_received",
                entity_type="message",
                details=f'{{"channel": "{channel}", "length": {len(message)}}}',
            )
        except Exception:
            pass

    # Step 0: a skill paused at a human step? This message is the answer —
    # unless it comes from an outside agent: a person answers in the approval
    # queue (STORY-37, people decide).
    from realize_core.security.agent_access import outside_agent_active

    if not outside_agent_active():
        resumed = await _resume_paused_skill(
            system_key, user_id, message, kb_path, system_config, shared_config, channel
        )
        if resumed is not None:
            return resumed

    # Step 1: Active session?
    session = get_session(system_key, user_id)
    if session and session.stage not in ("completed", "approved"):
        return await handle_session_message(
            session=session,
            user_id=user_id,
            message=message,
            kb_path=kb_path,
            system_config=system_config,
            shared_config=shared_config,
            channel=channel,
        )

    # Step 2: Skill trigger?
    handled, result = await check_and_execute_skill(
        system_key=system_key,
        user_id=user_id,
        message=message,
        kb_path=kb_path,
        system_config=system_config,
        shared_config=shared_config,
        channel=channel,
        emit=emit,
    )
    if handled:
        if features.get("activity_log"):
            try:
                from realize_core.activity.logger import log_event

                log_event(
                    venture_key=system_key,
                    actor_type="system",
                    actor_id="skill_executor",
                    action="skill_executed",
                    entity_type="skill",
                )
            except Exception:
                pass
        return result

    # Step 3: Agent routing
    agent_routing = {}
    if system_config:
        agent_routing = system_config.get("agent_routing", {})
        if not agent_routing:
            for agent_key in system_config.get("agents", {}):
                keywords = agent_key.replace("_", " ").split()
                agent_routing[agent_key] = keywords

    venture_agents = (system_config or {}).get("agents", {})
    if requested_agent and (requested_agent == "orchestrator" or requested_agent in venture_agents):
        agent_key = requested_agent
        route_method = "requested"
    else:
        if requested_agent:
            logger.warning("Requested agent %r is not in %s; routing automatically", requested_agent, system_key)
        agent_key = select_agent(agent_routing, message)
        route_method = "keyword" if agent_key != "orchestrator" else "default"
    routed_to = agent_key

    # --- Safety: verify agent definition exists, fallback to orchestrator ---
    if system_config and agent_key != "orchestrator":
        agents = system_config.get("agents", {})
        if agent_key in agents:
            agent_path = kb_path / agents[agent_key] if kb_path else None
            if agent_path and not agent_path.exists():
                logger.warning(f"Agent file missing for {agent_key}: {agent_path}, falling back to orchestrator")
                agent_key = "orchestrator"

    # --- Lifecycle: skip paused agents, fallback to orchestrator ---
    if features.get("agent_lifecycle"):
        try:
            from realize_core.scheduler.lifecycle import is_paused

            if is_paused(agent_key, system_key):
                logger.info(f"Agent {agent_key} is paused, falling back to orchestrator")
                agent_key = "orchestrator"
                # If orchestrator is also paused, still proceed (don't block)
        except Exception:
            pass

    if selected is not None:
        selected["agent_key"] = agent_key

    from realize_core.agents.routing_log import record_decision

    record_decision(system_key, agent_key, "fallback" if agent_key != routed_to else route_method)

    # --- Activity: log agent routing ---
    if features.get("activity_log"):
        try:
            from realize_core.activity.logger import log_event

            log_event(
                venture_key=system_key,
                actor_type="system",
                actor_id="router",
                action="agent_routed",
                entity_type="agent",
                entity_id=agent_key,
            )
        except Exception:
            pass

    # --- Lifecycle: mark agent running ---
    if features.get("agent_lifecycle"):
        try:
            from realize_core.scheduler.lifecycle import mark_running

            mark_running(agent_key, system_key)
        except Exception:
            pass

    try:
        response = await standard_llm_handling(
            system_key=system_key,
            agent_key=agent_key,
            user_id=user_id,
            message=message,
            kb_path=kb_path,
            system_config=system_config,
            shared_config=shared_config,
            channel=channel,
            features=features,
            all_systems=all_systems,
            emit=emit,
        )

        # --- Activity: log LLM call ---
        if features.get("activity_log"):
            try:
                from realize_core.activity.logger import log_event

                task_class = classify_task(message, system_key=system_key)
                log_event(
                    venture_key=system_key,
                    actor_type="agent",
                    actor_id=agent_key,
                    action="llm_called",
                    entity_type="task",
                    details=f'{{"task_type": "{task_class}", "response_length": {len(response)}}}',
                )
            except Exception:
                pass

        # --- Lifecycle: mark agent idle ---
        if features.get("agent_lifecycle"):
            try:
                from realize_core.scheduler.lifecycle import mark_idle

                mark_idle(agent_key, system_key)
            except Exception:
                pass

        return response

    except Exception as e:
        # --- Lifecycle: mark agent error ---
        if features.get("agent_lifecycle"):
            try:
                from realize_core.scheduler.lifecycle import mark_error

                mark_error(agent_key, system_key, str(e)[:500])
            except Exception:
                pass
        raise


async def _resume_paused_skill(system_key, user_id, message, kb_path, system_config, shared_config, channel):
    """If this user's skill is waiting on a human step in this venture, resume it.

    The answer must be accepted first: if the question's approval item is no
    longer pending (expired, or already answered or rejected from the
    dashboard), the paused run is dropped instead of resumed.
    """
    from realize_core.skills.executor import claim_skill_run, peek_skill_resume_context, resume_pending_skill

    pending = peek_skill_resume_context(user_id, system_key)
    if not pending:
        return None
    approval_id = pending.get("approval_id")
    if approval_id:
        # An answer is input, not an approval: the item becomes 'answered'.
        from realize_core.governance.gates import answer_request

        if answer_request(approval_id, message[:200], answered_by=user_id, channel="chat") is None:
            claim_skill_run(pending["id"])
            result = "That question is no longer open (it expired or was already decided), so the skill was stopped."
            add_message(system_key, user_id, "user", message)
            add_message(system_key, user_id, "assistant", result)
            return result
    result = await resume_pending_skill(
        user_id, message, kb_path, system_config, shared_config, channel, run_id=pending["id"]
    )
    if result is None:
        return None  # resumed from the dashboard in the meantime
    add_message(system_key, user_id, "user", message)
    add_message(system_key, user_id, "assistant", result)
    return result
