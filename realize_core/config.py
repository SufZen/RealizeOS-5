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
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "")

# --- Model Definitions (override via environment variables) ---
MODELS = {
    "gemini_flash": os.getenv("GEMINI_FLASH_MODEL", "gemini-2.5-flash"),
    "claude_sonnet": os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-6-20260217"),
    "claude_opus": os.getenv("CLAUDE_OPUS_MODEL", "claude-opus-4-6-20260205"),
}

# --- Rate Limits ---
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
COST_LIMIT_PER_HOUR_USD = float(os.getenv("COST_LIMIT_PER_HOUR_USD", "5.0"))

# --- Feature Flags ---
BROWSER_ENABLED = os.getenv("BROWSER_ENABLED", "false").lower() == "true"
MCP_ENABLED = os.getenv("MCP_ENABLED", "false").lower() == "true"

# --- Paths ---
KB_PATH = Path(os.getenv("KB_PATH", ".")).resolve()
DATA_PATH = Path(os.getenv("DATA_PATH", "./data")).resolve()


def _interpolate_env(value: str) -> str:
    """Replace ${ENV_VAR} placeholders with environment variable values."""

    def replacer(match):
        var_name = match.group(1)
        return os.getenv(var_name, "")

    return re.sub(r"\$\{(\w+)\}", replacer, value)


def load_config(config_path: str | Path = None) -> dict:
    """
    Load RealizeOS configuration from a YAML file.

    Args:
        config_path: Path to realize-os.yaml. Defaults to ./realize-os.yaml.

    Returns:
        Parsed configuration dictionary with env vars interpolated.
    """
    import yaml

    config_path = Path(config_path or os.getenv("REALIZE_CONFIG", "realize-os.yaml"))

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


def build_systems_dict(config: dict, kb_path: Path = None) -> dict:
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

    return systems


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
    has_provider = any(bool(os.getenv(key)) for key in ("ANTHROPIC_API_KEY", "GOOGLE_AI_API_KEY", "OPENAI_API_KEY"))
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
        warnings.append("No LLM provider API keys are configured")

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


def validate_systems(config: dict, kb_path: Path = None) -> list[str]:
    """
    Validate that configured systems have the expected FABRIC structure.

    Returns a list of warning messages (empty if everything is valid).
    """
    kb_path = kb_path or KB_PATH
    warnings = []

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
            available_agents = {
                f.stem.replace("-", "_")
                for f in agents_dir.glob("*.md")
                if not f.name.startswith("_")
            }
            # Also check .yaml agent files
            available_agents |= {
                f.stem.replace("-", "_")
                for f in agents_dir.glob("*.yaml")
            }

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
    }
    features = config.get("features", {})
    merged = {**defaults, **features}
    return merged


def _discover_agents(agents_dir: Path) -> dict:
    """Auto-discover agent definitions from markdown files in the agents directory."""
    agents = {}
    if not agents_dir.exists():
        return agents

    for md_file in agents_dir.glob("*.md"):
        if md_file.name.startswith("_"):
            continue  # Skip _README.md and other meta files
        agent_key = md_file.stem.replace("-", "_")
        agents[agent_key] = str(md_file.relative_to(agents_dir.parent.parent.parent))

    return agents
