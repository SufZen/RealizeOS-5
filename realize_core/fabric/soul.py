"""
SOUL — User and Agent Identity.

Two levels of identity in RealizeOS:
- User SOUL: locale, languages, working hours, constraints, voice preferences
- Agent SOUL: role, personality, expertise, runtime preferences, cost limits

The User SOUL is new in v5.5.0. Agent SOUL extends the existing per-agent
persona system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class UserSoul:
    """
    User-level identity and preferences.

    Loaded from shared/user-soul.yaml. Influences how agents communicate,
    which runtimes they prefer, and what constraints apply globally.
    """

    locale: str = "en"
    languages: list[str] = field(default_factory=lambda: ["en"])
    working_hours: str = ""  # e.g., "09:00-19:00 Europe/Lisbon"
    timezone: str = ""
    voice: str = ""  # e.g., "formal-but-warm"

    default_runtime_preferences: dict = field(default_factory=dict)
    # e.g., {"code": "claude-code-cli", "research": "claude-opus"}

    constraints: list[str] = field(default_factory=list)
    # e.g., ["Never auto-send messages to clients without approval"]

    # Raw YAML data
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, path: Path) -> UserSoul:
        """Load UserSoul from a YAML file."""
        if not path.exists():
            logger.info(f"User SOUL file not found: {path}, using defaults")
            return cls()

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls()

            return cls(
                locale=data.get("locale", "en"),
                languages=data.get("languages", ["en"]),
                working_hours=data.get("working_hours", ""),
                timezone=data.get("timezone", ""),
                voice=data.get("voice", ""),
                default_runtime_preferences=data.get("default_runtime_preferences", {}),
                constraints=data.get("constraints", []),
                _raw=data,
            )
        except (yaml.YAMLError, OSError) as e:
            logger.warning(f"Failed to load User SOUL from {path}: {e}")
            return cls()

    def save(self, path: Path) -> None:
        """Save UserSoul to a YAML file."""
        data = {
            "locale": self.locale,
            "languages": self.languages,
            "working_hours": self.working_hours,
            "timezone": self.timezone,
            "voice": self.voice,
            "default_runtime_preferences": self.default_runtime_preferences,
            "constraints": self.constraints,
        }
        # Preserve any extra fields from the raw data
        for key, value in self._raw.items():
            if key not in data:
                data[key] = value

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

    def to_context(self) -> dict:
        """Convert to a dict suitable for agent context injection."""
        return {
            "locale": self.locale,
            "languages": self.languages,
            "working_hours": self.working_hours,
            "timezone": self.timezone,
            "voice": self.voice,
            "constraints": self.constraints,
            "runtime_preferences": self.default_runtime_preferences,
        }


@dataclass
class AgentSoul:
    """
    Agent-level identity and configuration.

    Extends the existing per-agent persona system with:
    - Home runtime preference
    - Scoped permissions
    - Cost limits
    - Capability declarations
    """

    name: str = ""
    role: str = ""
    personality: str = ""
    expertise: list[str] = field(default_factory=list)
    communication_style: str = ""

    # v5.5.0 extensions
    home_runtime: str = ""  # Preferred runtime for this agent
    scoped_permissions: list[str] = field(default_factory=list)
    cost_limit_per_invocation_eur: float = 0.0
    cost_limit_per_day_eur: float = 0.0
    capabilities: list[str] = field(default_factory=list)

    # Raw data
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_config(cls, config: dict) -> AgentSoul:
        """Create AgentSoul from an agent configuration dict."""
        return cls(
            name=config.get("name", ""),
            role=config.get("role", ""),
            personality=config.get("personality", ""),
            expertise=config.get("expertise", []),
            communication_style=config.get("communication_style", ""),
            home_runtime=config.get("home_runtime", ""),
            scoped_permissions=config.get("scoped_permissions", []),
            cost_limit_per_invocation_eur=float(config.get("cost_limit_per_invocation_eur", 0)),
            cost_limit_per_day_eur=float(config.get("cost_limit_per_day_eur", 0)),
            capabilities=config.get("capabilities", []),
            _raw=config,
        )

    @classmethod
    def load(cls, path: Path) -> AgentSoul:
        """Load AgentSoul from a YAML file (agent persona file)."""
        if not path.exists():
            return cls()

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls()
            return cls.from_config(data)
        except (yaml.YAMLError, OSError) as e:
            logger.warning(f"Failed to load Agent SOUL from {path}: {e}")
            return cls()

    def to_context(self) -> dict:
        """Convert to a dict suitable for runtime context injection."""
        return {
            "name": self.name,
            "role": self.role,
            "personality": self.personality,
            "expertise": self.expertise,
            "communication_style": self.communication_style,
            "home_runtime": self.home_runtime,
            "capabilities": self.capabilities,
        }
