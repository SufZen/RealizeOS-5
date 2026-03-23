"""
Extension Loader: Auto-discover extensions from config and filesystem.

Discovery sources (checked in order):
  1. ``realize-os.yaml`` → ``extensions:`` section
  2. Filesystem scan of ``extensions/`` directory
  3. Legacy ``plugins/`` directory (bridge to old system)

Each discovered extension directory must contain an ``extension.yaml``
manifest file describing the extension metadata.

Usage::

    loader = ExtensionLoader(registry=my_registry)
    count = await loader.discover_and_load(config_path="realize-os.yaml")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from realize_core.extensions.base import (
    ExtensionManifest,
    ExtensionType,
)

logger = logging.getLogger(__name__)

# Default directories to scan for extensions
DEFAULT_EXTENSION_DIRS = ["extensions", "plugins"]


def _safe_yaml_load(path: Path) -> dict | None:
    """Load a YAML file, returning None on error or missing PyYAML."""
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed — cannot load %s", path)
        return None

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
        return None
    except Exception as e:
        logger.warning("Failed to read %s: %s", path, e)
        return None


class ExtensionLoader:
    """
    Discovers and loads extensions from disk and config files.

    Works with an ``ExtensionRegistry`` to register discovered extensions
    and optionally load them immediately.
    """

    def __init__(
        self,
        registry: Any = None,  # ExtensionRegistry, kept as Any to avoid circular
        base_dir: Path | str | None = None,
    ) -> None:
        """
        Args:
            registry: The ExtensionRegistry to register discoveries into.
            base_dir: Project root directory (defaults to cwd).
        """
        # Deferred import to avoid circular
        if registry is None:
            from realize_core.extensions.registry import get_extension_registry

            registry = get_extension_registry()

        self._registry = registry
        self._base_dir = Path(base_dir) if base_dir else Path.cwd()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover_from_directory(
        self,
        directory: Path | str,
    ) -> list[ExtensionManifest]:
        """
        Scan a directory for extensions.

        Each subdirectory must contain an ``extension.yaml`` manifest.

        Args:
            directory: Path to scan.

        Returns:
            List of discovered manifests.
        """
        ext_dir = Path(directory)
        if not ext_dir.is_dir():
            logger.debug("Extension directory does not exist: %s", ext_dir)
            return []

        manifests = []
        for child in sorted(ext_dir.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue

            # Try extension.yaml, then plugin.yaml (legacy)
            manifest_path = child / "extension.yaml"
            if not manifest_path.exists():
                manifest_path = child / "plugin.yaml"
            if not manifest_path.exists():
                continue

            manifest = self._parse_manifest(manifest_path, child)
            if manifest:
                manifests.append(manifest)
                logger.debug(
                    "Discovered extension '%s' in %s",
                    manifest.name,
                    child,
                )

        return manifests

    def discover_from_config(
        self,
        config_path: Path | str | None = None,
    ) -> list[ExtensionManifest]:
        """
        Discover extensions listed in a realize-os.yaml config file.

        Expected config format::

            extensions:
              - name: stripe-tools
                version: "1.0.0"
                type: tool
                entry_point: "realize_core.tools.stripe.StripeExtension"
                config:
                  api_key: "sk_..."

        Args:
            config_path: Path to realize-os.yaml (defaults to base_dir/realize-os.yaml).

        Returns:
            List of discovered manifests.
        """
        if config_path is None:
            config_path = self._base_dir / "realize-os.yaml"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            logger.debug("No config at %s", config_path)
            return []

        data = _safe_yaml_load(config_path)
        if not data:
            return []

        ext_list = data.get("extensions", [])
        if not isinstance(ext_list, list):
            logger.warning("'extensions' in config is not a list")
            return []

        manifests = []
        for item in ext_list:
            if not isinstance(item, dict) or "name" not in item:
                continue

            ext_type_str = item.get("type", "tool")
            try:
                ext_type = ExtensionType(ext_type_str)
            except ValueError:
                logger.warning(
                    "Unknown extension type '%s' for '%s'",
                    ext_type_str,
                    item["name"],
                )
                ext_type = ExtensionType.TOOL

            manifest = ExtensionManifest(
                name=item["name"],
                version=item.get("version", "0.1.0"),
                extension_type=ext_type,
                description=item.get("description", ""),
                author=item.get("author", ""),
                entry_point=item.get("entry_point", ""),
                dependencies=item.get("dependencies", []),
                config_schema=item.get("config_schema", {}),
            )
            manifests.append(manifest)

        return manifests

    def discover_all(
        self,
        config_path: Path | str | None = None,
        extra_dirs: list[str | Path] | None = None,
    ) -> list[ExtensionManifest]:
        """
        Discover from all sources: config file + default directories + extras.

        Args:
            config_path: Path to realize-os.yaml.
            extra_dirs: Additional directories to scan.

        Returns:
            Deduplicated list of discovered manifests.
        """
        seen: dict[str, ExtensionManifest] = {}

        # 1. Config file
        for m in self.discover_from_config(config_path):
            seen[m.name] = m

        # 2. Default directories
        for dirname in DEFAULT_EXTENSION_DIRS:
            dir_path = self._base_dir / dirname
            for m in self.discover_from_directory(dir_path):
                if m.name not in seen:
                    seen[m.name] = m

        # 3. Extra directories
        for extra in extra_dirs or []:
            for m in self.discover_from_directory(extra):
                if m.name not in seen:
                    seen[m.name] = m

        logger.info(
            "Discovered %d extensions from all sources",
            len(seen),
        )
        return list(seen.values())

    async def discover_and_load(
        self,
        config_path: Path | str | None = None,
        extra_dirs: list[str | Path] | None = None,
        configs: dict[str, dict[str, Any]] | None = None,
    ) -> int:
        """
        Full pipeline: discover → register → load all.

        Args:
            config_path: Path to realize-os.yaml.
            extra_dirs: Additional directories to scan.
            configs: Per-extension config overrides.

        Returns:
            Number of successfully loaded extensions.
        """
        manifests = self.discover_all(config_path, extra_dirs)
        for manifest in manifests:
            self._registry.register(manifest)
        return await self._registry.load_all(configs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_manifest(
        manifest_path: Path,
        plugin_dir: Path,
    ) -> ExtensionManifest | None:
        """Parse a YAML manifest into an ExtensionManifest."""
        data = _safe_yaml_load(manifest_path)
        if not data or "name" not in data:
            logger.warning("Invalid manifest: %s", manifest_path)
            return None

        ext_type_str = data.get("type", "tool")
        try:
            ext_type = ExtensionType(ext_type_str)
        except ValueError:
            ext_type = ExtensionType.TOOL

        # If no entry_point, default to __init__.py in the directory
        entry_point = data.get("entry_point", "")
        if not entry_point:
            init_path = plugin_dir / "__init__.py"
            if init_path.exists():
                entry_point = f"extensions.{plugin_dir.name}"

        return ExtensionManifest(
            name=data["name"],
            version=data.get("version", "0.1.0"),
            extension_type=ext_type,
            description=data.get("description", ""),
            author=data.get("author", ""),
            entry_point=entry_point,
            dependencies=data.get("dependencies", []),
            config_schema=data.get("config_schema", {}),
        )
