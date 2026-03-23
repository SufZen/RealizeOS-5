"""
Extension Registry: Unified registration, lookup, and lifecycle management.

The registry is the single source of truth for all extensions in the system.
It manages:
  - Registration (from auto-discovery or programmatic)
  - Lifecycle (load, activate, deactivate, unload)
  - Lookup (by name, type, status)
  - Status reporting (for dashboard/health checks)

Usage::

    registry = ExtensionRegistry()
    registry.register(manifest)
    await registry.load_extension("my-ext", config={"api_key": "..."})
    await registry.unload_extension("my-ext")
"""

from __future__ import annotations

import logging
from typing import Any

from realize_core.extensions.base import (
    BaseExtension,
    ExtensionManifest,
    ExtensionRegistration,
    ExtensionStatus,
    ExtensionType,
)

logger = logging.getLogger(__name__)


class ExtensionRegistry:
    """
    Central registry for all RealizeOS extensions.

    Manages extension discovery, registration, lifecycle, and lookup.
    Thread-safe for read operations; write operations should be
    serialized by the caller or used in a single-threaded startup phase.
    """

    def __init__(self) -> None:
        self._extensions: dict[str, ExtensionRegistration] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, manifest: ExtensionManifest) -> ExtensionRegistration:
        """
        Register an extension from its manifest.

        Creates a DISCOVERED-status registration record.
        If an extension with the same name already exists, it is
        replaced (useful for hot-reload scenarios).

        Args:
            manifest: Static metadata for the extension.

        Returns:
            The created registration record.
        """
        if manifest.name in self._extensions:
            logger.warning("Extension '%s' already registered, replacing", manifest.name)

        reg = ExtensionRegistration(manifest=manifest)
        self._extensions[manifest.name] = reg
        logger.info(
            "Registered extension '%s' (type=%s, status=%s)",
            manifest.name,
            manifest.extension_type,
            reg.status,
        )
        return reg

    def register_instance(
        self,
        extension: BaseExtension,
    ) -> ExtensionRegistration:
        """
        Register an already-instantiated extension.

        Useful for programmatic registration (e.g. built-in extensions
        that don't need auto-discovery).

        Args:
            extension: An object satisfying the BaseExtension protocol.

        Returns:
            The created registration record.
        """
        reg = ExtensionRegistration(
            manifest=extension.manifest,
            instance=extension,
            status=ExtensionStatus.LOADED,
        )
        self._extensions[extension.name] = reg
        logger.info(
            "Registered pre-loaded extension '%s' (type=%s)",
            extension.name,
            extension.extension_type,
        )
        return reg

    def unregister(self, name: str) -> bool:
        """
        Remove an extension from the registry.

        The extension should be unloaded before unregistering.

        Returns:
            True if the extension was found and removed.
        """
        reg = self._extensions.pop(name, None)
        if reg:
            logger.info("Unregistered extension '%s'", name)
            return True
        return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def load_extension(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> bool:
        """
        Load and initialize an extension by name.

        Resolves the entry_point, instantiates the class, and
        calls ``on_load(config)`` on the instance.

        Args:
            name: The registered extension name.
            config: Extension-specific configuration.

        Returns:
            True if the extension was loaded successfully.
        """
        reg = self._extensions.get(name)
        if not reg:
            logger.error("Cannot load unknown extension '%s'", name)
            return False

        if reg.status == ExtensionStatus.ACTIVE:
            logger.debug("Extension '%s' is already active", name)
            return True

        try:
            # Resolve and instantiate if needed
            if reg.instance is None:
                ext_class = self._resolve_entry_point(reg.manifest.entry_point)
                if ext_class is None:
                    reg.status = ExtensionStatus.ERROR
                    reg.error_message = f"Could not resolve entry point: {reg.manifest.entry_point}"
                    return False
                reg.instance = ext_class()

            # Call on_load
            await reg.instance.on_load(config)
            reg.status = ExtensionStatus.ACTIVE
            reg.error_message = ""
            logger.info("Loaded extension '%s'", name)
            return True

        except Exception as e:
            reg.status = ExtensionStatus.ERROR
            reg.error_message = str(e)[:500]
            logger.error(
                "Failed to load extension '%s': %s",
                name,
                e,
                exc_info=True,
            )
            return False

    async def unload_extension(self, name: str) -> bool:
        """
        Unload an extension, calling its ``on_unload()`` hook.

        Returns:
            True if the extension was unloaded.
        """
        reg = self._extensions.get(name)
        if not reg:
            return False

        if reg.instance is not None:
            try:
                await reg.instance.on_unload()
            except Exception as e:
                logger.warning(
                    "Error in on_unload for '%s': %s",
                    name,
                    e,
                )

        reg.status = ExtensionStatus.DISCOVERED
        reg.instance = None
        reg.error_message = ""
        logger.info("Unloaded extension '%s'", name)
        return True

    async def reload_extension(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> bool:
        """Unload then reload an extension (hot-reload)."""
        reg = self._extensions.get(name)
        # Stash the instance class for re-instantiation after unload
        instance_cls = type(reg.instance) if (reg and reg.instance) else None
        await self.unload_extension(name)

        # If the entry_point is empty (programmatic registration),
        # re-instantiate from the stashed class
        if reg and instance_cls and not reg.manifest.entry_point:
            reg.instance = instance_cls()

        return await self.load_extension(name, config)

    async def load_all(
        self,
        configs: dict[str, dict[str, Any]] | None = None,
    ) -> int:
        """
        Load all registered extensions.

        Args:
            configs: Map of extension name → config dict.

        Returns:
            Number of successfully loaded extensions.
        """
        configs = configs or {}
        loaded = 0
        for name in list(self._extensions.keys()):
            if await self.load_extension(name, configs.get(name)):
                loaded += 1
        logger.info(
            "Loaded %d/%d extensions",
            loaded,
            len(self._extensions),
        )
        return loaded

    async def unload_all(self) -> int:
        """Unload all active extensions. Returns count unloaded."""
        unloaded = 0
        for name in list(self._extensions.keys()):
            reg = self._extensions[name]
            if reg.status == ExtensionStatus.ACTIVE:
                await self.unload_extension(name)
                unloaded += 1
        return unloaded

    async def disable_extension(self, name: str) -> bool:
        """Disable an extension (prevents loading)."""
        reg = self._extensions.get(name)
        if not reg:
            return False
        if reg.status == ExtensionStatus.ACTIVE:
            await self.unload_extension(name)
        reg.status = ExtensionStatus.DISABLED
        logger.info("Disabled extension '%s'", name)
        return True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> ExtensionRegistration | None:
        """Get a registration by name."""
        return self._extensions.get(name)

    def get_instance(self, name: str) -> BaseExtension | None:
        """Get the live instance of a loaded extension."""
        reg = self._extensions.get(name)
        return reg.instance if reg else None

    def get_by_type(
        self,
        ext_type: ExtensionType,
    ) -> list[ExtensionRegistration]:
        """Get all registrations of a given type."""
        return [r for r in self._extensions.values() if r.extension_type == ext_type]

    def get_by_status(
        self,
        status: ExtensionStatus,
    ) -> list[ExtensionRegistration]:
        """Get all registrations with a given status."""
        return [r for r in self._extensions.values() if r.status == status]

    def get_active(self) -> list[ExtensionRegistration]:
        """Get all currently active extensions."""
        return self.get_by_status(ExtensionStatus.ACTIVE)

    @property
    def names(self) -> list[str]:
        """All registered extension names."""
        return list(self._extensions.keys())

    @property
    def count(self) -> int:
        """Total number of registered extensions."""
        return len(self._extensions)

    @property
    def active_count(self) -> int:
        """Number of currently active extensions."""
        return len(self.get_active())

    # ------------------------------------------------------------------
    # Status / health
    # ------------------------------------------------------------------

    def status_summary(self) -> dict[str, Any]:
        """Return a status summary for monitoring/dashboard."""
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}

        for reg in self._extensions.values():
            by_status[reg.status] = by_status.get(reg.status, 0) + 1
            by_type[reg.extension_type] = by_type.get(reg.extension_type, 0) + 1

        return {
            "total": self.count,
            "active": self.active_count,
            "by_status": by_status,
            "by_type": by_type,
            "extensions": {
                name: {
                    "type": reg.extension_type,
                    "status": reg.status,
                    "version": reg.manifest.version,
                    "error": reg.error_message or None,
                }
                for name, reg in self._extensions.items()
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_entry_point(entry_point: str) -> type | None:
        """
        Resolve a dotted entry point string to a class.

        Example: "realize_core.tools.stripe_tools.StripeExtension"
        → <class StripeExtension>
        """
        if not entry_point:
            return None

        import importlib

        parts = entry_point.rsplit(".", 1)
        if len(parts) != 2:
            logger.warning("Invalid entry point format: '%s'", entry_point)
            return None

        module_path, class_name = parts
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name, None)
            if cls is None:
                logger.warning(
                    "Class '%s' not found in module '%s'",
                    class_name,
                    module_path,
                )
            return cls
        except ImportError as e:
            logger.warning(
                "Cannot import module '%s': %s",
                module_path,
                e,
            )
            return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry: ExtensionRegistry | None = None


def get_extension_registry() -> ExtensionRegistry:
    """Get the global extension registry singleton."""
    global _registry
    if _registry is None:
        _registry = ExtensionRegistry()
    return _registry
