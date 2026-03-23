"""
Creative Pipeline for RealizeOS.

Defines multi-agent workflows and manages pipeline execution.
Pipelines are loaded from system config (not hardcoded) — each system
defines its own agent sequences for different task types.
"""

import logging

from realize_core.pipeline.session import CreativeSession, create_session

logger = logging.getLogger(__name__)


def detect_task_type(system_config: dict, message: str) -> str:
    """
    Detect the task type from a message for pipeline selection.

    Uses the routing config from the system to match keywords to task types.

    Args:
        system_config: System configuration dict with routing info
        message: User's message text

    Returns:
        Task type string (e.g., "content", "strategy", "research")
    """
    msg_lower = message.lower()
    routing = system_config.get("routing", {})

    best_type = "general"
    best_score = 0

    # Score each task type by counting keyword matches in the routing config
    for task_type, agents in routing.items():
        # Use the task type name itself as keywords
        keywords = task_type.replace("_", " ").split()
        score = sum(1 for kw in keywords if kw in msg_lower)

        # Also check common patterns for well-known task types
        extra_patterns = _COMMON_PATTERNS.get(task_type, [])
        score += sum(1 for kw in extra_patterns if kw in msg_lower)

        if score > best_score:
            best_score = score
            best_type = task_type

    return best_type


# Common keyword patterns for well-known task types
_COMMON_PATTERNS = {
    "content": ["write", "post", "blog", "linkedin", "article", "newsletter", "draft", "copy"],
    "strategy": ["strategy", "analyze", "positioning", "market", "competitive", "planning"],
    "research": ["research", "investigate", "compare", "evaluate", "due diligence"],
    "general": [],
}


def get_pipeline(system_config: dict, task_type: str) -> list[str]:
    """
    Get the agent pipeline for a task type from the system config.

    Falls back to ["orchestrator"] if no pipeline is defined.
    """
    routing = system_config.get("routing", {})
    pipeline = routing.get(task_type, [])

    if not pipeline:
        return ["orchestrator"]

    return list(pipeline)


def start_pipeline(
    system_key: str,
    system_config: dict,
    user_id: str,
    message: str,
    task_type: str = None,
) -> CreativeSession:
    """
    Start a new creative pipeline session.

    Auto-detects task type if not provided, selects the appropriate pipeline,
    and creates a session.
    """
    if not task_type:
        task_type = detect_task_type(system_config, message)

    pipeline = get_pipeline(system_config, task_type)

    session = create_session(
        system_key=system_key,
        user_id=str(user_id),
        brief=message,
        task_type=task_type,
        pipeline=pipeline,
    )

    logger.info(f"Started pipeline: {task_type} -> {' -> '.join(pipeline)}")
    return session


async def execute_pipeline_step(
    session: CreativeSession,
    user_id: str,
    message: str,
    kb_path=None,
    system_config: dict = None,
    shared_config: dict = None,
    channel: str = "api",
    extra_context_files: list[str] = None,
) -> str:
    """
    Execute the current step in the creative pipeline.

    Builds a session-aware prompt and calls the appropriate LLM.
    """
    from realize_core.llm.router import route_to_llm
    from realize_core.memory.conversation import add_message
    from realize_core.prompt.builder import build_system_prompt

    system_key = session.system_key
    agent_key = session.active_agent

    # Merge session context files with any extra files
    all_context = list(session.context_files)
    if extra_context_files:
        for f in extra_context_files:
            if f not in all_context:
                all_context.append(f)

    # Build the system prompt with session context
    system_prompt = build_system_prompt(
        kb_path=kb_path,
        system_config=system_config or {},
        system_key=system_key,
        agent_key=agent_key,
        user_message=message,
        session=session,
        extra_context_files=all_context,
        shared_config=shared_config,
        channel=channel,
    )

    # Get conversation history
    from realize_core.memory.conversation import get_history

    history = get_history(system_key, str(user_id))
    messages = history + [{"role": "user", "content": message}]

    # Route to LLM
    task_type = session.task_type or "content"
    response = await route_to_llm(system_prompt, messages, task_type)

    # Save the response as a draft if in drafting stage
    if session.stage in ("drafting", "iterating"):
        session.add_draft(response, agent_key)

    # Add to conversation history
    add_message(system_key, str(user_id), "assistant", response)

    return response
