"""
Base Handler: The core message processing pipeline for RealizeOS.

Provides composable building blocks for handling incoming messages across
any channel (API, Telegram, Slack, etc.). Each channel adapter calls these
shared functions to process messages through the standard flow.
"""

import logging

from realize_core.llm.router import classify_task, route_to_llm
from realize_core.memory.conversation import add_message, get_history
from realize_core.pipeline.creative import (
    execute_pipeline_step,
)
from realize_core.pipeline.session import CreativeSession, get_session
from realize_core.prompt.builder import build_system_prompt

logger = logging.getLogger(__name__)

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
) -> tuple[bool, str | None]:
    """
    Check for skill auto-trigger and execute if found.

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
    )

    if result is not None:
        add_message(system_key, user_id, "user", message)
        add_message(system_key, user_id, "assistant", result)
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
) -> str:
    """
    Standard single-agent LLM handling: build prompt, classify, route, respond.

    This is the main message processing function for non-skill, non-session messages.
    """
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
    )

    history = get_history(system_key, user_id)
    add_message(system_key, user_id, "user", message)
    messages = history + [{"role": "user", "content": message}]

    task_class = classify_task(message, system_key=system_key)
    response = await route_to_llm(system_prompt, messages, task_class)

    add_message(system_key, user_id, "assistant", response)
    return response


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
    from realize_core.llm.claude_client import call_claude

    session = get_session(system_key, user_id)

    content_to_review = None
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

    response = await call_claude(system_prompt=system_prompt, messages=review_messages)

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
) -> str:
    """
    Main entry point: process an incoming message through the full pipeline.

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

    agent_key = select_agent(agent_routing, message)

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
