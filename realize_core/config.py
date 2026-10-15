"""
RealizeOS Configuration Loader.

Loads system configuration from a YAML file (realize-os.yaml) instead of
hardcoded dictionaries. Supports environment variable interpolation.
"""

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# --- API Keys (from environment) ---
# Import-time snapshots, kept for backward compatibility. Code should call
# anthropic_api_key() / google_ai_api_key(): Setup changes os.environ at
# runtime, and a key saved there must apply without a restart.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "")


def anthropic_api_key() -> str:
    """The current Anthropic API key (read from the environment on every call)."""
    return os.getenv("ANTHROPIC_API_KEY", "")


def google_ai_api_key() -> str:
    """The current Google AI API key (read from the environment on every call)."""
    return os.getenv("GOOGLE_AI_API_KEY", "")


def llm_primary() -> str:
    """Preferred LLM provider name from LLM_PRIMARY (lower-cased; empty if unset)."""
    return os.getenv("LLM_PRIMARY", "").strip().lower()


def llm_fallback() -> list[str]:
    """Explicit provider fallback order from LLM_FALLBACK (comma list; empty if unset)."""
    return [n.strip().lower() for n in os.getenv("LLM_FALLBACK", "").split(",") if n.strip()]


def llm_tier_model(tier: str) -> str:
    """LiteLLM model string pinned to a routing tier by LLM_MODEL_<TIER> (empty if unset)."""
    return os.getenv(f"LLM_MODEL_{tier.upper()}", "").strip()


def ollama_base_url() -> str:
    """Ollama server URL: OLLAMA_BASE_URL, else OLLAMA_HOST, else localhost."""
    url = (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://localhost:11434").strip()
    if "://" not in url:  # OLLAMA_HOST is conventionally written host:port
        url = f"http://{url}"
    return url.rstrip("/")


def ollama_model() -> str:
    """Default Ollama model tag (OLLAMA_MODEL)."""
    return os.getenv("OLLAMA_MODEL") or "llama3.1:8b"


def anthropic_workspace_id() -> str:
    """Anthropic workspace ID sent as a request header (ANTHROPIC_WORKSPACE_ID); empty if unset."""
    return os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()


# --- Model Definitions (override via environment variables) ---
# Defaults are always the newest model in each line. Users who want an older
# model set CLAUDE_SONNET_MODEL / CLAUDE_OPUS_MODEL. IDs have no date suffix.
DEFAULT_CLAUDE_SONNET_MODEL = "claude-sonnet-5-5"
DEFAULT_CLAUDE_OPUS_MODEL = "claude-opus-5-5"

MODELS = {
    "gemini_flash": os.getenv("GEMINI_FLASH_MODEL", "gemini-2.5-flash"),
    "claude_sonnet": os.getenv("CLAUDE_SONNET_MODEL") or DEFAULT_CLAUDE_SONNET_MODEL,
    "claude_opus": os.getenv("CLAUDE_OPUS_MODEL") or DEFAULT_CLAUDE_OPUS_MODEL,
}

# --- Rate Limits ---
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))  # LLM calls per minute
# HTTP requests per minute per caller. Separate from the LLM limit: the
# dashboard alone made more than 30 requests a minute (QA 5.14 S-3 / D-4).
API_RATE_LIMIT_PER_MINUTE = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "120"))
COST_LIMIT_PER_HOUR_USD = float(os.getenv("COST_LIMIT_PER_HOUR_USD", "5.0"))

# --- Feature Flags ---
BROWSER_ENABLED = os.getenv("BROWSER_ENABLED", "false").lower() == "true"
MCP_ENABLED = os.getenv("MCP_ENABLED", "false").lower() == "true"

# --- Paths ---
KB_PATH = Path(os.getenv("KB_PATH", ".")).resolve()
DATA_PATH = Path(os.getenv("DATA_PATH", "./data")).resolve()


# --- Persisted store locations ---
_legacy_store_warned: set[Path] = set()


def data_dir() -> Path:
    """The persisted data directory (``DATA_PATH``, read at call time)."""
    return Path(os.getenv("DATA_PATH", "./data")).resolve()


def persisted_path(name: str, legacy_dir: str | Path, *, state: bool = True) -> Path:
    """Where a file-based store lives.

    Before 5.15 the operational DB, KB index and Synapse defaulted to the
    working directory or KB root, which a container doesn't persist (and the
    production image mounts read-only). Now:

    1. An existing file at the legacy location keeps being used, so no
       install loses data on upgrade.
    2. State (``state=True``) otherwise goes under ``DATA_PATH``.
    3. A rebuildable index (``state=False``) stays next to its source when
       that folder is writable, else goes under ``DATA_PATH``.
    """
    legacy = Path(legacy_dir) / name
    if legacy.exists():
        resolved = legacy.resolve()
        if data_dir() not in resolved.parents and resolved not in _legacy_store_warned:
            _legacy_store_warned.add(resolved)
            logger.warning(
                "Using %s outside DATA_PATH (%s); make sure it is on persistent storage.", resolved, data_dir()
            )
        return legacy
    if not state and os.access(legacy_dir, os.W_OK):
        return legacy
    return data_dir() / name


def synapse_dir(kb_path: str | Path) -> Path:
    """Folder for the Synapse index and the Dream Inbox.

    An existing ``<kb>/.synapse`` keeps being used; otherwise ``DATA_PATH/synapse``.
    """
    if (Path(kb_path) / ".synapse").exists():
        return persisted_path(".synapse", kb_path)
    return data_dir() / "synapse"


def _interpolate_env(value: str) -> str:
    """Replace ${ENV_VAR} placeholders with environment variable values."""

    def replacer(match):
        var_name = match.group(1)
        return os.getenv(var_name, "")

    return re.sub(r"\$\{(\w+)\}", replacer, value)


def load_config(config_path: str | Path | None = None) -> dict:
    """
    Load RealizeOS configuration from a YAML file.

    Args:
        config_path: Path to realize-os.yaml. Defaults to ./realize-os.yaml.

    Returns:
        Parsed configuration dictionary with env vars interpolated.
    """
    import yaml

    config_path = Path(config_path) if config_path is not None else Path(os.getenv("REALIZE_CONFIG", "realize-os.yaml"))

    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}. Using defaults.")
        return _default_config()

    try:
        with open(config_path, encoding="utf-8") as f:
            raw = f.read()
    except Exception as e:
        logger.warning(f"Cannot read config file {config_path}: {e}. Using defaults.")
        return _default_config()

    # Interpolate environment variables
    raw = _interpolate_env(raw)

    try:
        config = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        logger.warning(f"Corrupted YAML in {config_path}: {e}. Using defaults.")
        return _default_config()

    if not isinstance(config, dict):
        logger.warning(f"Config is not a dict (got {type(config).__name__}). Using defaults.")
        return _default_config()

    # Ensure required sections exist
    if "systems" not in config:
        config["systems"] = []
        logger.warning("Config missing 'systems' section, using empty list")

    # Validate required fields in each system
    for i, sys_conf in enumerate(config.get("systems", [])):
        if not isinstance(sys_conf, dict):
            logger.warning(f"System #{i} is not a dict, skipping")
            continue
        if "key" not in sys_conf:
            logger.warning(f"System #{i} missing required 'key' field")
        if "directory" not in sys_conf:
            sys_key = sys_conf.get("key", f"system-{i}")
            sys_conf["directory"] = f"systems/{sys_key}"
            logger.info(f"System '{sys_key}': auto-set directory to {sys_conf['directory']}")

    logger.info(f"Loaded config from {config_path}: {len(config.get('systems', []))} system(s)")
    return config


def _default_config() -> dict:
    """Return a minimal default configuration."""
    return {
        "name": "RealizeOS",
        "systems": [],
        "shared": {
            "identity": "shared/identity.md",
            "preferences": "shared/user-preferences.md",
        },
        "features": {
            "review_pipeline": True,
            "auto_memory": True,
            "proactive_mode": True,
            "cross_system": False,
        },
    }


def build_systems_dict(config: dict, kb_path: Path | None = None) -> dict:
    """
    Convert the YAML config systems list into a lookup dictionary
    compatible with the prompt builder and router.

    Args:
        config: Parsed YAML configuration.
        kb_path: Base path for knowledge base files.

    Returns:
        Dictionary mapping system_key to system config.
    """
    kb_path = kb_path or KB_PATH
    systems = {}
    # Profession and market packs (spec 010): their agents join each venture's own.
    features = config.get("features")
    packs_on = isinstance(features, dict) and bool(features.get("packs"))

    for sys_conf in config.get("systems", []):
        key = sys_conf["key"]
        sys_dir = sys_conf.get("directory", f"systems/{key}")

        locale = sys_conf.get("locale", "")

        systems[key] = {
            "name": sys_conf.get("name", key.title()),
            "system_dir": sys_dir,
            "description": sys_conf.get("description", ""),
            "locale": locale,
            # FABRIC directory paths
            "foundations": f"{sys_dir}/F-foundations",
            "agents_dir": f"{sys_dir}/A-agents",
            "agents_readme": f"{sys_dir}/A-agents/_README.md",
            "brain_dir": f"{sys_dir}/B-brain",
            "routines_dir": f"{sys_dir}/R-routines",
            "insights_dir": f"{sys_dir}/I-insights",
            "creations_dir": f"{sys_dir}/C-creations",
            # Key files
            "brand_identity": f"{sys_dir}/F-foundations/venture-identity.md",
            "brand_voice": f"{sys_dir}/F-foundations/venture-voice.md",
            "state_map": f"{sys_dir}/R-routines/state-map.md",
            "memory_dir": f"{sys_dir}/I-insights",
            # Agent definitions (auto-discover from A-agents/)
            "agents": _discover_agents(kb_path / sys_dir / "A-agents"),
            # Routing (task_type → agent pipeline)
            "routing": sys_conf.get("routing", {}),
            # Agent routing (agent → keyword list for message-based selection)
            "agent_routing": sys_conf.get("agent_routing", {}),
        }
        if packs_on:
            _add_pack_agents(systems[key], kb_path / sys_dir, kb_path)
        _check_packs_off(systems[key], key, kb_path / sys_dir, packs_on)

    return systems


def _check_packs_off(system: dict, key: str, venture_dir: Path, packs_on: bool) -> None:
    """Warn about a venture that gets its agents or skills from packs while ``features.packs`` is off.

    The warning is logged once per change (startup, or the reload that turned
    the flag off) and listed in the venture's ``warnings``, which the venture
    list and the status endpoint return.
    """
    from realize_core.packs import flag_off

    message = None if packs_on else flag_off.packs_off_warning(key, venture_dir, system["agents"])
    flag_off.report(venture_dir, message)
    if message:
        system["warnings"] = [message]


def _add_pack_agents(system: dict, venture_dir: Path, kb_path: Path) -> None:
    """Add the agents of the venture's linked packs (``features.packs``, spec 010).

    The venture's own ``A-agents/`` files win. ``agent_provenance`` records
    where each pack agent came from (layer, pack, verification); the pack's
    routing guide is used when the venture has none.
    """
    from realize_core.packs.agents import pack_agents

    added = pack_agents(venture_dir, kb_path, system["agents"])
    system["agents"] = {**system["agents"], **added.agents}
    system["agent_provenance"] = added.provenance
    if added.readme:
        system["agents_readme"] = added.readme


def discover_workspace_state(root: Path | None = None, config: dict | None = None) -> dict:
    """
    Inspect the current workspace and highlight partial setup issues.

    Returns a dictionary that can be reused by status, audit, and health tooling.
    """
    root = (root or Path.cwd()).resolve()
    config_path = Path(os.getenv("REALIZE_CONFIG", "realize-os.yaml"))
    if not config_path.is_absolute():
        config_path = root / config_path

    config = config or load_config(config_path)
    configured_keys = [
        str(system.get("key", "")).strip()
        for system in config.get("systems", [])
        if isinstance(system, dict) and str(system.get("key", "")).strip()
    ]

    systems_dir = root / "systems"
    discovered_system_dirs = []
    if systems_dir.exists():
        discovered_system_dirs = sorted(
            entry.name for entry in systems_dir.iterdir() if entry.is_dir() and not entry.name.startswith(".")
        )

    unconfigured_system_dirs = [name for name in discovered_system_dirs if name not in configured_keys]
    from realize_core.llm.registry import any_provider_available

    has_provider = any_provider_available()
    has_runtime_databases = any((root / filename).exists() for filename in ("realize_data.db", "kb_index.db"))

    warnings = []
    if not config_path.exists():
        warnings.append("Config file missing: realize-os.yaml")
    if discovered_system_dirs and not configured_keys:
        warnings.append("FABRIC systems exist on disk but none are configured in realize-os.yaml")
    elif unconfigured_system_dirs:
        warnings.append(
            "Some FABRIC system directories are not registered in realize-os.yaml: "
            + ", ".join(unconfigured_system_dirs)
        )
    if not has_provider:
        warnings.append("No LLM provider is available")

    return {
        "root": str(root),
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "configured_system_count": len(configured_keys),
        "configured_system_keys": configured_keys,
        "discovered_system_dirs": discovered_system_dirs,
        "unconfigured_system_dirs": unconfigured_system_dirs,
        "has_provider": has_provider,
        "has_runtime_databases": has_runtime_databases,
        "partially_initialized": bool(warnings),
        "warnings": warnings,
    }


def validate_systems(config: dict, kb_path: Path | None = None) -> list[str]:
    """
    Validate that configured systems have the expected FABRIC structure.

    Returns a list of warning messages (empty if everything is valid).
    """
    kb_path = kb_path or KB_PATH
    warnings = []
    features = config.get("features")
    packs_on = isinstance(features, dict) and bool(features.get("packs"))

    for sys_conf in config.get("systems", []):
        key = sys_conf.get("key", "unknown")
        sys_dir = kb_path / sys_conf.get("directory", f"systems/{key}")

        # Check FABRIC directories exist
        if not sys_dir.exists():
            warnings.append(f"System '{key}': directory {sys_dir} does not exist")
            continue

        fabric_dirs = ["F-foundations", "A-agents", "B-brain", "R-routines", "I-insights", "C-creations"]
        for d in fabric_dirs:
            if not (sys_dir / d).exists():
                warnings.append(f"System '{key}': missing FABRIC directory {d}/")

        # Check that routing agent references match actual agent files
        agents_dir = sys_dir / "A-agents"
        if agents_dir.exists():
            available_agents = {f.stem.replace("-", "_") for f in agents_dir.glob("*.md") if not f.name.startswith("_")}
            # Also check .yaml agent files
            available_agents |= {f.stem.replace("-", "_") for f in agents_dir.glob("*.yaml")}
            if packs_on:
                from realize_core.packs.agents import pack_agents

                available_agents |= set(pack_agents(sys_dir, kb_path, {}).agents)

            for route_type, agent_list in sys_conf.get("routing", {}).items():
                if isinstance(agent_list, list):
                    for agent_name in agent_list:
                        agent_key = agent_name.replace("-", "_")
                        if agent_key not in available_agents:
                            warnings.append(
                                f"System '{key}': routing '{route_type}' references "
                                f"agent '{agent_name}' but no matching file found in A-agents/"
                            )

    return warnings


def get_features(config: dict) -> dict:
    """
    Extract feature flags from the config.
    Gracefully handles unknown flags by returning them as-is.
    """
    defaults = {
        "review_pipeline": True,
        "auto_memory": True,
        "proactive_mode": True,
        "cross_system": False,
        "email_digest": False,
        "dreaming_curator": False,
        "dreaming_reflex": False,
        # Governance enforcement (RISKIEST surface — default OFF).
        # enforce_gates: install the trust-ladder tool gate at the tool-dispatch
        #   chokepoint. When false, tool execution is byte-for-byte unchanged.
        # enforce_guardrails: reserved placeholder; guardrail post-response
        #   wiring is currently deferred (no-op when set).
        "enforce_gates": False,
        "enforce_guardrails": False,
        # agent_tools: agents may call registry tools (Google, Sheets, MCP, ...)
        #   while answering. Without enforce_gates only read-only tools are offered.
        "agent_tools": False,
        # cite_sources: tell the model to cite numbered KB sources inline ([S1])
        #   on channels that show them as footnotes (api, dashboard, mcp).
        "cite_sources": False,
        # packs: resolve profession and market packs (ADR 0005, spec 010) on top
        #   of the core. When false only the firm layer and core apply.
        "packs": False,
        # wedge: the free self-serve tender register MCP tools (STORY-46).
        #   Configure booking_url and per-market partners under wedge: in the config.
        "wedge": False,
        # agent_tokens: accept venture-scoped agent tokens (rzag_...) on MCP and
        #   REST (STORY-37). Inert until an owner creates a token; turning it off
        #   makes every agent token stop working at once.
        "agent_tokens": True,
    }
    features = config.get("features", {})
    merged = {**defaults, **features}
    return merged


def get_email_digest_config(config: dict) -> dict:
    """
    Extract the email digest configuration, merged over sane defaults.

    The digest is only active when ``features.email_digest`` is true; this
    helper just resolves the settings (recipient, schedule, etc.) and is safe
    to call regardless of the flag.
    """
    defaults = {
        "recipient": "info@realization.co.il",
        "base_url": "",
        "schedule": "daily",
        "hour": 8,
        "workdays_only": True,
        "timezone": "Europe/Lisbon",
    }
    section = config.get("email_digest", {})
    if not isinstance(section, dict):
        section = {}
    return {**defaults, **section}


def get_runtimes_config(config: dict) -> dict:
    """
    Extract the ``runtimes`` configuration section.

    Runtimes are governed agent peers registered into the Runtime Registry at
    startup. The internal runtime is always registered; external runtimes are
    only registered when explicitly configured here. Example block::

        runtimes:
          hermes:
            base_url: "http://your-vps-host:8642/v1"  # OpenAI-compatible gateway
            api_key: "${HERMES_API_KEY}"              # optional; env-ref supported
            model: "hermes"                           # optional; defaults to "hermes"

    Returns an empty dict when no ``runtimes`` section is present.
    """
    section = config.get("runtimes", {})
    if not isinstance(section, dict):
        return {}
    return section


def get_dreaming_config(config: dict) -> dict:
    """
    Extract the scheduled-Curator configuration, merged over sane defaults.

    The scheduled Curator is only active when ``features.dreaming_curator`` is
    true; this helper just resolves the settings (schedule, etc.) and is safe to
    call regardless of the flag.
    """
    defaults = {
        "schedule": "daily",
        "hour": 3,
        "timezone": "Europe/Lisbon",
        "reflex_interval_minutes": 60,
    }
    section = config.get("dreaming", {})
    if not isinstance(section, dict):
        section = {}
    return {**defaults, **section}


def get_ingestion_config(config: dict) -> dict:
    """
    Extract the KB-ingestion configuration, merged over safe defaults.

    ``allow_private_urls`` (default False) lets URL ingestion reach private
    network hosts (RFC 1918 / ULA) — for self-hosters ingesting intranet
    pages. Loopback and cloud-metadata addresses stay blocked regardless.
    """
    defaults = {"allow_private_urls": False}
    section = config.get("ingestion", {})
    if not isinstance(section, dict):
        section = {}
    return {**defaults, **section}


def _discover_agents(agents_dir: Path) -> dict:
    """Auto-discover agent definitions from markdown files in the agents directory."""
    agents: dict[str, str] = {}
    if not agents_dir.exists():
        return agents

    for md_file in agents_dir.glob("*.md"):
        if md_file.name.startswith("_"):
            continue  # Skip _README.md and other meta files
        agent_key = md_file.stem.replace("-", "_")
        agents[agent_key] = str(md_file.relative_to(agents_dir.parent.parent.parent))

    return agents
