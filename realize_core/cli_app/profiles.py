"""TOML-backed config-profile manager.

Profiles live in ``~/.realize-os/config.toml``.  Each profile stores an
``endpoint`` and an optional ``api_key_env`` (the *name* of the env-var
holding the API key — never the secret itself).

Schema::

    default_profile = "default"

    [profiles.default]
    endpoint = "http://localhost:8080"
    api_key_env = "REALIZE_API_KEY"
    default_system = ""

    [profiles.prod]
    endpoint = "https://my-vps:8080"
    api_key_env = "REALIZE_PROD_KEY"
    default_system = "realization-il"
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".realize-os"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class Profile:
    """One named CLI profile."""

    name: str
    endpoint: str = "http://localhost:8080"
    api_key_env: str = "REALIZE_API_KEY"
    default_system: str = ""

    def to_dict(self) -> dict[str, str]:
        """Serialise to a TOML-compatible dict (excludes *name*)."""
        return {
            "endpoint": self.endpoint,
            "api_key_env": self.api_key_env,
            "default_system": self.default_system,
        }


@dataclass
class ProfileManager:
    """Read/write ``~/.realize-os/config.toml``."""

    config_dir: Path = field(default_factory=lambda: CONFIG_DIR)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    def _load_raw(self) -> dict[str, Any]:
        if not self.config_file.exists():
            return {}
        with self.config_file.open("rb") as f:
            return tomllib.load(f)

    def _save_raw(self, data: dict[str, Any]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with self.config_file.open("wb") as f:
            tomli_w.dump(data, f)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_profiles(self) -> list[Profile]:
        """Return all profiles sorted by name, default first."""
        raw = self._load_raw()
        profiles_dict: dict[str, dict[str, str]] = raw.get("profiles", {})
        default_name = raw.get("default_profile", "default")

        profiles: list[Profile] = []
        for name, vals in profiles_dict.items():
            profiles.append(
                Profile(
                    name=name,
                    endpoint=vals.get("endpoint", "http://localhost:8080"),
                    api_key_env=vals.get("api_key_env", "REALIZE_API_KEY"),
                    default_system=vals.get("default_system", ""),
                )
            )

        # Sort: default first, then alphabetical
        profiles.sort(key=lambda p: (p.name != default_name, p.name))
        return profiles

    def get_profile(self, name: str | None = None) -> Profile:
        """Return a named profile, or the default."""
        raw = self._load_raw()
        default_name = raw.get("default_profile", "default")
        target = name or default_name
        profiles_dict: dict[str, dict[str, str]] = raw.get("profiles", {})
        vals = profiles_dict.get(target, {})
        if not vals and target != "default":
            logger.warning("Profile '%s' not found — falling back to defaults", target)
        return Profile(
            name=target,
            endpoint=vals.get("endpoint", "http://localhost:8080"),
            api_key_env=vals.get("api_key_env", "REALIZE_API_KEY"),
            default_system=vals.get("default_system", ""),
        )

    def add_profile(
        self,
        name: str,
        *,
        endpoint: str = "http://localhost:8080",
        api_key_env: str = "REALIZE_API_KEY",
        default_system: str = "",
    ) -> Profile:
        """Create or overwrite a profile and persist."""
        raw = self._load_raw()
        profiles_dict = raw.setdefault("profiles", {})
        p = Profile(name=name, endpoint=endpoint, api_key_env=api_key_env, default_system=default_system)
        profiles_dict[name] = p.to_dict()
        # If this is the first profile, set as default
        if "default_profile" not in raw:
            raw["default_profile"] = name
        self._save_raw(raw)
        return p

    def set_default(self, name: str) -> None:
        """Set *name* as the default profile.  Raises ValueError if missing."""
        raw = self._load_raw()
        profiles_dict: dict[str, Any] = raw.get("profiles", {})
        if name not in profiles_dict:
            raise ValueError(f"Profile '{name}' does not exist")
        raw["default_profile"] = name
        self._save_raw(raw)

    def show_profile(self, name: str | None = None) -> Profile:
        """Show a profile's details (alias for get_profile)."""
        return self.get_profile(name)

    def has_any_profile(self) -> bool:
        """Return True if at least one profile exists."""
        raw = self._load_raw()
        return bool(raw.get("profiles"))
