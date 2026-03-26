"""
Prompt Builder: Reads KB markdown files and assembles multi-layer system prompts.

Layers (assembled in order):
1. Identity layer (shared/identity.md + preferences)
2. Venture layer (F-foundations/venture-identity.md + venture-voice.md)
3. Routing context (A-agents/_README.md)
4. Agent layer (selected agent definition .md file)
5. Extra context files (user-loaded)
6. Dynamic KB context (RAG: semantic search results)
7. Memory layer (I-insights/learning-log.md)
8. Cross-system context (when cross_system feature enabled)
9. Session layer (active creative session state)
10. Proactive behavior instructions (when proactive_mode enabled)
11. Channel format instructions

Token optimization features:
- estimate_tokens(): Fast token count estimation (chars / 3.5)
- truncate_to_budget(): Smart per-layer budget with priority preservation
- deduplicate_layers(): Detect and remove redundant content across layers
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from realize_core.agents.persona import AgentPersona

logger = logging.getLogger(__name__)

# Cache for file contents (refreshed on reload)
_file_cache: dict[str, str] = {}

# Default format instructions per channel
CHANNEL_FORMAT_INSTRUCTIONS = {
    "telegram": (
        "## Writing Style\n"
        "You are responding inside Telegram. Write like a sharp, thoughtful person "
        "texting a smart colleague -- not like a formatted report.\n\n"
        "How to write:\n"
        "- Lead with the answer, not context or preamble\n"
        "- Write in flowing sentences and short paragraphs (2-3 sentences)\n"
        "- Use bold sparingly -- only for critical terms\n"
        "- Use bullet points only when listing 4+ distinct items\n"
        "- No section headers, no horizontal rules, no numbered lists for prose\n"
        "- No emoji headers or decorative emoji\n"
        "- No markdown headers (# ## ###)\n\n"
        "What NOT to do:\n"
        "- No opening ceremonies ('Here is my analysis...', 'Great question...')\n"
        "- No closing ceremonies ('In summary...', 'Let me know if...')\n"
        "- No meta-commentary about your own response\n\n"
        "Length: Under 300 words for most responses."
    ),
    "api": (
        "## Response Format\n"
        "Format your response as clean, readable text. "
        "You may use markdown for structure (headers, lists, bold, italic). "
        "Keep responses focused and well-organized. "
        "Lead with the answer, not preamble."
    ),
    "slack": (
        "## Response Format\n"
        "You are responding in Slack. Use Slack mrkdwn formatting. "
        "Keep messages concise and scannable. Use threads for long responses."
    ),
}


def _read_kb_file(kb_path: Path, relative_path: str, max_chars: int = 6000) -> str:
    """
    Read a file from the knowledge base, with caching and truncation.

    Args:
        kb_path: Root path of the KB
        relative_path: Path relative to kb_path
        max_chars: Maximum characters to include

    Returns:
        File content string, or empty string if file not found.
    """
    if relative_path in _file_cache:
        content = _file_cache[relative_path]
    else:
        file_path = kb_path / relative_path
        try:
            content = file_path.read_text(encoding="utf-8")
            _file_cache[relative_path] = content
        except FileNotFoundError:
            logger.debug(f"KB file not found: {file_path}")
            return ""
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return ""

    if len(content) > max_chars:
        content = content[:max_chars] + f"\n\n[...truncated at {max_chars} chars]"

    return content


def clear_cache():
    """Clear the file cache (call after KB update)."""
    _file_cache.clear()


# ---------------------------------------------------------------------------
# Token optimization
# ---------------------------------------------------------------------------

# Average ratio of characters to tokens for English text across major models.
# GPT-4/Claude average ~3.5 chars per token; we use this as a fast estimator.
_CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """
    Fast token count estimation without loading a tokenizer.

    Uses the empirical average of ~3.5 characters per token for English text.
    This is within 10% of tiktoken/sentencepiece for typical prompts.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


# Layer priority: higher number = cut last (more important).
# Uses layer heading patterns to identify each layer.
_LAYER_PRIORITIES: dict[str, int] = {
    "## Identity": 9,  # Core identity — never cut
    "## Agent Persona": 8,  # Persona — critical for personality
    "## Active Agent": 8,  # Agent definition — critical
    "## Writing Style": 8,  # Channel format — critical
    "## Response Format": 8,  # Channel format — critical
    "## Venture Goal": 7,  # Goal — important for alignment
    "## Collaboration": 7,  # Proactive instructions
    "## Venture Identity": 6,  # Brand context
    "## Venture Voice": 6,
    "## Team Routing": 5,  # Routing table
    "## Active Creative": 5,  # Session context
    "## Relevant Knowledge": 4,  # RAG results — can trim
    "## Loaded Context": 3,  # Extra files — can trim
    "## Recent Learning": 3,  # Memory — can trim
    "## Cross-System": 2,  # Cross-venture — lowest priority
    "## User Preferences": 4,  # Preferences
    "## Push-Back": 6,  # Pushback protocol
}


def _get_layer_priority(layer_text: str) -> int:
    """Determine the priority of a prompt layer from its heading."""
    for heading, priority in _LAYER_PRIORITIES.items():
        if heading in layer_text[:100]:
            return priority
    return 5  # default mid-priority


def truncate_to_budget(
    layers: list[str],
    token_budget: int,
    separator: str = "\n\n---\n\n",
) -> list[str]:
    """
    Smart truncation: trim lowest-priority layers first to fit within budget.

    Steps:
    1. Calculate total tokens
    2. If under budget, return as-is
    3. Sort layers by priority (lowest first)
    4. Trim lowest-priority layers until under budget
    5. Within a trimmed layer, keep the header and first paragraph

    Args:
        layers: List of prompt layer strings
        token_budget: Maximum total tokens
        separator: Layer separator (for overhead calculation)

    Returns:
        Trimmed list of layers that fits within the budget.
    """
    if not layers:
        return layers

    sep_tokens = estimate_tokens(separator) * (len(layers) - 1)
    total_tokens = sum(estimate_tokens(layer) for layer in layers) + sep_tokens

    if total_tokens <= token_budget:
        return layers

    logger.info(f"Token budget exceeded: {total_tokens} > {token_budget}, trimming...")

    # Create (index, priority, tokens) tuples and sort by priority ascending
    indexed = [(i, _get_layer_priority(layer), estimate_tokens(layer), layer) for i, layer in enumerate(layers)]
    indexed.sort(key=lambda x: x[1])  # Sort by priority (lowest first)

    tokens_to_cut = total_tokens - token_budget
    trimmed: dict[int, str] = {}  # index -> trimmed content

    for idx, priority, layer_tokens, layer_text in indexed:
        if tokens_to_cut <= 0:
            break

        if priority >= 8:
            # Never cut critical layers (identity, agent, format)
            continue

        # Trim the layer: keep header + first paragraph
        lines = layer_text.split("\n")
        if len(lines) <= 3:
            # Too short to trim meaningfully — remove entirely
            tokens_saved = layer_tokens
            trimmed[idx] = ""  # Mark for removal
        else:
            # Keep header (first 2 lines) + truncation marker
            kept = "\n".join(lines[:2]) + "\n\n[...trimmed to save tokens]"
            tokens_saved = layer_tokens - estimate_tokens(kept)
            if tokens_saved > 0:
                trimmed[idx] = kept
            else:
                trimmed[idx] = ""
                tokens_saved = layer_tokens

        tokens_to_cut -= tokens_saved
        logger.debug(f"Trimmed layer at index {idx} (priority={priority}), saved ~{tokens_saved} tokens")

    # Rebuild layers in original order
    result = []
    for i, layer in enumerate(layers):
        if i in trimmed:
            if trimmed[i]:  # Trimmed but not removed
                result.append(trimmed[i])
            # else: removed entirely
        else:
            result.append(layer)

    return result


def deduplicate_layers(layers: list[str], similarity_threshold: float = 0.7) -> list[str]:
    """
    Remove redundant content across prompt layers.

    Detects when two layers share a high proportion of identical lines
    and removes the lower-priority duplicate.

    Args:
        layers: List of prompt layer strings
        similarity_threshold: Minimum ratio of shared lines to trigger dedup (0-1)

    Returns:
        Deduplicated list of layers.
    """
    if len(layers) <= 1:
        return layers

    # Extract significant lines (3+ words, not headers/separators)
    def extract_lines(text: str) -> set[str]:
        lines = set()
        for line in text.split("\n"):
            stripped = line.strip().lower()
            if len(stripped.split()) >= 3 and not stripped.startswith("#") and stripped != "---":
                lines.add(stripped)
        return lines

    line_sets = [(i, extract_lines(layer), layer) for i, layer in enumerate(layers)]
    remove_indices: set[int] = set()

    for i, (idx_a, lines_a, _) in enumerate(line_sets):
        if idx_a in remove_indices or not lines_a:
            continue
        for j in range(i + 1, len(line_sets)):
            idx_b, lines_b, _ = line_sets[j]
            if idx_b in remove_indices or not lines_b:
                continue

            overlap = lines_a & lines_b
            smaller = min(len(lines_a), len(lines_b))
            if smaller > 0 and len(overlap) / smaller >= similarity_threshold:
                # Remove the one with lower priority
                pri_a = _get_layer_priority(layers[idx_a])
                pri_b = _get_layer_priority(layers[idx_b])
                victim = idx_b if pri_a >= pri_b else idx_a
                remove_indices.add(victim)
                logger.debug(f"Deduplicated layer {victim} (overlap={len(overlap)}/{smaller} lines)")

    return [layer for i, layer in enumerate(layers) if i not in remove_indices]


def warm_cache(kb_path: Path, systems: dict, shared_config: dict = None):
    """Pre-read all system KB files into cache at startup."""
    count = 0

    # Warm shared paths
    if shared_config:
        for key in ["identity", "preferences"]:
            path = shared_config.get(key)
            if path and _read_kb_file(kb_path, path):
                count += 1

    # Warm per-system paths
    for system_key, system_config in systems.items():
        for path_key in ["brand_identity", "brand_voice", "state_map", "agents_readme"]:
            path = system_config.get(path_key)
            if path and _read_kb_file(kb_path, path):
                count += 1
        for agent_key, agent_path in system_config.get("agents", {}).items():
            if agent_path and _read_kb_file(kb_path, agent_path):
                count += 1

    logger.info(f"Prompt cache warmed: {count} files pre-loaded")


def _build_identity_layer(kb_path: Path, shared_config: dict) -> str:
    """Build the shared identity layer."""
    identity_path = shared_config.get("identity", "shared/identity.md")
    prefs_path = shared_config.get("preferences", "shared/user-preferences.md")

    identity = _read_kb_file(kb_path, identity_path, max_chars=3000)
    preferences = _read_kb_file(kb_path, prefs_path, max_chars=2000)

    parts = []
    if identity:
        parts.append(f"## Identity\n{identity}")
    if preferences:
        parts.append(f"## User Preferences\n{preferences}")

    return "\n\n".join(parts)


def _build_brand_layer(kb_path: Path, system_config: dict) -> str:
    """Build the venture layer for a specific system."""
    parts = []

    brand_identity_path = system_config.get("brand_identity")
    if brand_identity_path:
        content = _read_kb_file(kb_path, brand_identity_path, max_chars=3000)
        if content:
            parts.append(f"## Venture Identity — {system_config.get('name', 'System')}\n{content}")

    brand_voice_path = system_config.get("brand_voice")
    if brand_voice_path:
        content = _read_kb_file(kb_path, brand_voice_path, max_chars=2000)
        if content:
            parts.append(f"## Venture Voice\n{content}")

    return "\n\n".join(parts)


def _build_agent_layer(kb_path: Path, system_config: dict, agent_key: str) -> str:
    """Load a specific agent definition."""
    agent_path = system_config.get("agents", {}).get(agent_key)
    if not agent_path:
        logger.warning(f"Agent {agent_key} not found in system config")
        return ""

    content = _read_kb_file(kb_path, agent_path, max_chars=4000)
    if content:
        return f"## Active Agent: {agent_key}\n{content}"
    return ""


def _build_routing_context(kb_path: Path, system_config: dict) -> str:
    """Load the agents readme (routing table) for orchestrator awareness."""
    agents_readme = system_config.get("agents_readme")
    if not agents_readme:
        return ""
    readme = _read_kb_file(kb_path, agents_readme, max_chars=3000)
    if readme:
        return f"## Team Routing Guide\n{readme}"
    return ""


def _build_memory_layer(kb_path: Path, system_config: dict) -> str:
    """Load recent memory (learning log) for context."""
    memory_dir = system_config.get("memory_dir", system_config.get("insights_dir", ""))
    if not memory_dir:
        return ""

    learning_log = _read_kb_file(kb_path, f"{memory_dir}/learning-log.md", max_chars=1500)

    parts = []
    if learning_log:
        parts.append(f"## Recent Learning\n{learning_log}")

    return "\n\n".join(parts)


def _build_dynamic_kb_context(
    kb_path: Path,
    system_key: str,
    user_message: str,
    extra_context_files: list[str] | None = None,
    max_results: int = 3,
    max_chars_per_result: int = 600,
) -> str:
    """
    Query the KB index for content relevant to the user's message.
    Skips files already loaded as static extra_context_files.
    Only triggers for messages longer than 20 characters.
    """
    if not user_message or len(user_message) < 20:
        return ""

    try:
        from realize_core.kb.indexer import semantic_search

        results = semantic_search(user_message, system_key=system_key, top_k=max_results + 2)
        if not results:
            return ""

        loaded_paths = set(extra_context_files or [])
        parts = []
        for r in results:
            if len(parts) >= max_results:
                break
            if r["path"] in loaded_paths:
                continue
            content = _read_kb_file(kb_path, r["path"], max_chars=max_chars_per_result)
            if content:
                parts.append(f"**{r['title']}** ({r['path']})\n{content}")

        if parts:
            return "## Relevant Knowledge Base Context\n" + "\n\n---\n".join(parts)
    except Exception as e:
        logger.debug(f"Dynamic KB context skipped: {e}")

    return ""


def _build_session_layer(session) -> str:
    """Build session context for the system prompt."""
    if not session:
        return ""

    parts = ["## Active Creative Session"]
    parts.append(f"**Task:** {session.task_type} | **Stage:** {session.stage}")
    parts.append(f"**Brief:** {session.brief}")

    if session.pipeline:
        pipeline_display = []
        for i, agent in enumerate(session.pipeline):
            if i < session.pipeline_index:
                pipeline_display.append(f"[done] {agent}")
            elif i == session.pipeline_index:
                pipeline_display.append(f"[ACTIVE] {agent}")
            else:
                pipeline_display.append(f"[next] {agent}")
        parts.append(f"**Pipeline:** {' -> '.join(pipeline_display)}")

    if hasattr(session, "drafts") and session.drafts:
        parts.append(f"**Drafts:** {len(session.drafts)} version(s)")
        if hasattr(session, "latest_draft"):
            latest = session.latest_draft()
            if latest:
                draft_preview = latest["content"][:2000]
                parts.append(f"**Latest draft (v{latest['version']}, by {latest['agent']}):**\n{draft_preview}")

    if hasattr(session, "review") and session.review:
        parts.append(f"**Last Review:** {session.review.get('verdict', 'pending')}")

    if hasattr(session, "context_files") and session.context_files:
        parts.append(f"**User-loaded context files:** {', '.join(session.context_files)}")

    return "\n".join(parts)


def _build_proactive_instructions(agent_key: str, session=None) -> str:
    """Build instructions that make agents proactive."""
    instructions = [
        "## Collaboration Instructions\n"
        "You are part of an AI operations team managed through this conversation. "
        "Be proactive and collaborative:\n"
        "- If a request is vague, ASK clarifying questions before starting work.\n"
        "- After completing work, SUGGEST logical next steps.\n"
        "- If the task would benefit from another agent's input, SAY SO.\n"
        "- If the user provides feedback, incorporate it and explain what you changed.\n"
        "- When relevant, suggest knowledge base files that could improve the output."
    ]

    if session:
        stage_instructions = {
            "briefing": (
                "\n**Current stage: BRIEFING** — Confirm you understand the request. "
                "Ask clarifying questions (audience, tone, format). "
                "Only start drafting once the brief is clear."
            ),
            "drafting": (
                "\n**Current stage: DRAFTING** — Create your best work. "
                "After delivering, offer options: review, iterate, or advance."
            ),
            "iterating": ("\n**Current stage: ITERATING** — Incorporate feedback, explain changes."),
            "reviewing": (
                "\n**Current stage: REVIEWING** — Review thoroughly: voice, accuracy, structure. "
                "Give a clear verdict: APPROVED or REVISIONS NEEDED."
            ),
        }
        if session.stage in stage_instructions:
            instructions.append(stage_instructions[session.stage])

    instructions.append(
        "\n## Push-Back Protocol\n"
        "Challenge decisions when your analysis contradicts the user's direction.\n"
        "- If data suggests a different approach, present the alternative before proceeding\n"
        "- Say 'I don't know' rather than guessing when lacking information\n"
        "- Flag when a request conflicts with previously stated preferences\n"
        "- Honest pushback is a core responsibility"
    )

    # Agent-specific proactive behavior
    if agent_key in ("writer", "content_creator", "copywriter"):
        instructions.append(
            "\nAs a content agent, always clarify: target audience, channel/format, "
            "tone register, and any specific references to include."
        )
    elif agent_key in ("analyst", "deal_analyst", "strategist"):
        instructions.append(
            "\nAs an analyst, always ask for: key constraints, data sources, "
            "success criteria, and timeline before analyzing."
        )

    return "\n".join(instructions)


def _build_cross_system_context(
    kb_path: Path,
    system_key: str,
    all_systems: dict,
) -> str:
    """
    Build cross-system awareness context.
    Reads state maps and venture identity summaries from ALL systems
    except the currently active one, giving the agent portfolio-wide context.
    """
    if not all_systems or len(all_systems) <= 1:
        return ""

    parts = ["## Cross-System Awareness\nYou have context across all ventures in this portfolio:"]

    for other_key, other_config in all_systems.items():
        if other_key == system_key:
            continue

        other_name = other_config.get("name", other_key)
        section = [f"\n### {other_name} ({other_key})"]

        # Read state map for current status
        state_map_path = other_config.get("state_map", "")
        if state_map_path:
            state = _read_kb_file(kb_path, state_map_path, max_chars=800)
            if state:
                section.append(f"**Current State:**\n{state}")

        # Read venture identity summary (first ~500 chars)
        brand_path = other_config.get("brand_identity", "")
        if brand_path:
            brand = _read_kb_file(kb_path, brand_path, max_chars=500)
            if brand:
                section.append(f"**Venture Summary:**\n{brand}")

        if len(section) > 1:
            parts.append("\n".join(section))

    if len(parts) <= 1:
        return ""

    return "\n\n".join(parts)


def _build_persona_layer(persona: "AgentPersona | None") -> str:
    """Build the persona prompt layer from an AgentPersona."""
    if persona is None:
        return ""
    try:
        from realize_core.agents.persona import persona_to_prompt
        return persona_to_prompt(persona)
    except Exception as e:
        logger.warning("Failed to build persona layer: %s", e)
        return ""


def _build_goal_layer(kb_path: Path, system_config: dict, system_key: str) -> str:
    """Build the venture goal prompt layer."""
    try:
        from realize_core.prompt.goal import load_goal, goal_to_prompt
        goal_text = load_goal(kb_path, system_config, system_key)
        if goal_text:
            system_name = system_config.get("name", "")
            return goal_to_prompt(goal_text, system_name)
    except Exception as e:
        logger.warning("Failed to build goal layer: %s", e)
    return ""


def _build_brand_profile_layer(
    kb_path: Path,
    system_config: dict,
) -> str:
    """
    Build the brand profile prompt layer from brand.yaml.

    Looks for brand.yaml in the venture directory and converts it
    to a prompt-friendly format.
    """
    try:
        from realize_core.prompt.brand import resolve_brand, brand_to_prompt

        # Try loading from system_config (inline brand data)
        brand = resolve_brand(config=system_config)
        if brand:
            return brand_to_prompt(brand)

        # Try loading from venture directory
        venture_dir = system_config.get("venture_dir", "")
        if venture_dir:
            brand = resolve_brand(venture_dir=kb_path / venture_dir)
            if brand:
                return brand_to_prompt(brand)

    except Exception as e:
        logger.warning("Failed to build brand profile layer: %s", e)
    return ""


def build_system_prompt(
    kb_path: Path,
    system_config: dict,
    system_key: str,
    agent_key: str = "orchestrator",
    user_message: str = "",
    session=None,
    extra_context_files: list[str] | None = None,
    shared_config: dict = None,
    channel: str = "api",
    features: dict = None,
    all_systems: dict = None,
    token_budget: int | None = None,
    persona_override: "AgentPersona | None" = None,
) -> str:
    """
    Assemble the full system prompt from KB layers.

    Args:
        kb_path: Root path of the knowledge base
        system_config: System configuration dict (from build_systems_dict)
        system_key: System identifier
        agent_key: Which agent to activate
        user_message: Current user message (for RAG context injection)
        session: Active creative session (if any)
        extra_context_files: Additional KB files to load
        shared_config: Shared configuration (identity, preferences paths)
        channel: Channel name for format instructions
        features: Feature flags dict (from get_features())
        all_systems: All system configs (for cross-system context)
        token_budget: Maximum token budget for the prompt (None = unlimited)

    Returns:
        Assembled system prompt string.
    """
    shared_config = shared_config or {"identity": "shared/identity.md", "preferences": "shared/user-preferences.md"}
    features = features or {}
    layers = []

    # Layer 1: Identity
    identity = _build_identity_layer(kb_path, shared_config)
    if identity:
        layers.append(identity)

    # Layer 1.5: Agent Persona (SOUL)
    persona_layer = _build_persona_layer(persona_override)
    if persona_layer:
        layers.append(persona_layer)

    # Layer 1.6: Venture Goal
    goal_layer = _build_goal_layer(kb_path, system_config, system_key)
    if goal_layer:
        layers.append(goal_layer)

    # Layer 1.7: Brand Profile (from brand.yaml)
    brand_profile = _build_brand_profile_layer(kb_path, system_config)
    if brand_profile:
        layers.append(brand_profile)

    # Layer 2: Venture
    brand = _build_brand_layer(kb_path, system_config)
    if brand:
        layers.append(brand)

    # Layer 3: Routing context
    routing = _build_routing_context(kb_path, system_config)
    if routing:
        layers.append(routing)

    # Layer 4: Agent definition
    agent = _build_agent_layer(kb_path, system_config, agent_key)
    if agent:
        layers.append(agent)

    # Layer 5: Extra context files (user-loaded)
    if extra_context_files:
        for ctx_file in extra_context_files:
            content = _read_kb_file(kb_path, ctx_file, max_chars=2000)
            if content:
                layers.append(f"## Loaded Context: {ctx_file}\n{content}")

    # Layer 6: Dynamic KB context (RAG)
    dynamic_kb = _build_dynamic_kb_context(kb_path, system_key, user_message, extra_context_files)
    if dynamic_kb:
        layers.append(dynamic_kb)

    # Layer 7: Memory
    memory = _build_memory_layer(kb_path, system_config)
    if memory:
        layers.append(memory)

    # Layer 8: Cross-system context (when enabled)
    if features.get("cross_system") and all_systems:
        cross_system = _build_cross_system_context(kb_path, system_key, all_systems)
        if cross_system:
            layers.append(cross_system)

    # Layer 9: Session
    session_ctx = _build_session_layer(session)
    if session_ctx:
        layers.append(session_ctx)

    # Layer 10: Proactive instructions (conditional on feature flag)
    if features.get("proactive_mode", True):
        proactive = _build_proactive_instructions(agent_key, session)
        if proactive:
            layers.append(proactive)

    # Layer 11: Learned user preferences
    try:
        from realize_core.memory.preference_learner import get_preference_prompt_layer

        pref_layer = get_preference_prompt_layer(system_key)
        if pref_layer:
            layers.append(pref_layer)
    except Exception:
        pass

    # Layer 12: Channel format instructions
    format_instructions = CHANNEL_FORMAT_INSTRUCTIONS.get(channel, CHANNEL_FORMAT_INSTRUCTIONS["api"])
    layers.append(format_instructions)

    # ── Token optimization ────────────────────────────────────────
    # 1. Deduplicate overlapping layers
    layers = deduplicate_layers(layers)

    # 2. Truncate to budget if specified
    if token_budget and token_budget > 0:
        layers = truncate_to_budget(layers, token_budget)

    return "\n\n---\n\n".join(layers)
