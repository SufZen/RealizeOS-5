"""
File protection tier system for Developer Mode.

Classifies every file/directory into three tiers:
  - PROTECTED (red)  — Core engine, security. AI tools must NOT modify.
  - GUARDED (yellow) — Config, agents. Editable with auto-backup.
  - OPEN (green)     — Extensions, user content. Freely editable.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "devmode_config.yaml"


class ProtectionTier(StrEnum):
    """File protection classification."""

    PROTECTED = "protected"
    GUARDED = "guarded"
    OPEN = "open"


class FileProtection:
    """
    Classify files into protection tiers based on the active protection level.

    Usage::

        fp = FileProtection("standard")
        tier = fp.classify("realize_core/prompt/builder.py")
        # => ProtectionTier.PROTECTED
    """

    def __init__(self, level: str = "standard", root: Path | None = None):
        self.level = level
        self.root = root or Path.cwd()
        self._config = self._load_config()
        self._rules = self._config.get("protection_levels", {}).get(level, {})
        if not self._rules:
            logger.warning("Protection level '%s' not found, falling back to 'standard'", level)
            self._rules = self._config.get("protection_levels", {}).get("standard", {})

    @staticmethod
    def _load_config() -> dict[str, Any]:
        """Load the devmode configuration YAML."""
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def classify(self, path: str | Path) -> ProtectionTier:
        """
        Classify a file path into a protection tier.

        Args:
            path: Relative path from the project root.

        Returns:
            The protection tier for the given path.
        """
        path_str = str(Path(path)).replace("\\", "/")

        # Check from most restrictive to least
        for tier_name in ("protected", "guarded", "open"):
            patterns = self._rules.get(tier_name, [])
            for pattern in patterns:
                pattern_clean = pattern.rstrip("/")
                if path_str == pattern_clean or path_str.startswith(pattern_clean + "/"):
                    return ProtectionTier(tier_name)

        # Default: GUARDED (safe fallback)
        return ProtectionTier.GUARDED

    def get_tier_files(self, tier: ProtectionTier) -> list[str]:
        """Get all path patterns for a given tier."""
        return self._rules.get(tier.value, [])

    def get_all_tiers(self) -> dict[ProtectionTier, list[str]]:
        """Get all tiers and their path patterns."""
        return {
            ProtectionTier.PROTECTED: self._rules.get("protected", []),
            ProtectionTier.GUARDED: self._rules.get("guarded", []),
            ProtectionTier.OPEN: self._rules.get("open", []),
        }

    @property
    def level_description(self) -> str:
        """Human-readable description of the active protection level."""
        return self._rules.get("description", f"Protection level: {self.level}")

    @classmethod
    def available_levels(cls) -> list[str]:
        """List available protection levels."""
        config = cls._load_config()
        return list(config.get("protection_levels", {}).keys())

    @classmethod
    def get_supported_tools(cls) -> dict[str, dict[str, Any]]:
        """Get all supported AI tools and their configuration."""
        config = cls._load_config()
        return config.get("tools", {})
