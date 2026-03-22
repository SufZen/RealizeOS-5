"""
Extension base interfaces for RealizeOS unified extension system.

Defines the shared contracts for extensions (formerly "plugins"):
- BaseExtension: Protocol for extension lifecycle and metadata
- ExtensionType: Enum of supported extension categories
- ExtensionRegistration: Auto-discovery registration record

The extension system supports four types:
  - tool:        Adds new tool capabilities (e.g. Stripe, Twilio)
  - channel:     Adds new communication channels (e.g. Slack, Discord)
  - integration: Backend integrations (e.g. CRM sync, analytics)
  - hook:        Event hooks (on_message, on_venture_change, etc.)

Extensions are auto-discovered from config and filesystem at startup.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExtensionType(StrEnum):
    """Category of extension."""
    TOOL = "tool"
    CHANNEL = "channel"
    INTEGRATION = "integration"
    HOOK = "hook"


class ExtensionStatus(StrEnum):
    """Runtime status of an extension."""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExtensionManifest:
    """
    Static metadata for an extension, typically parsed from
    its ``extension.yaml`` or directory convention.
    """
    name: str
    version: str = "0.1.0"
    extension_type: ExtensionType = ExtensionType.TOOL
    description: str = ""
    author: str = ""
    entry_point: str = ""  # Python dotted path to the extension class
    dependencies: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtensionRegistration:
    """
    Registration record created during auto-discovery.

    Tracks the lifecycle state and resolved class reference
    for a discovered extension.
    """
    manifest: ExtensionManifest
    status: ExtensionStatus = ExtensionStatus.DISCOVERED
    instance: BaseExtension | None = None
    error_message: str = ""

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def extension_type(self) -> ExtensionType:
        return self.manifest.extension_type


# ---------------------------------------------------------------------------
# Protocol — runtime interface for extension implementations
# ---------------------------------------------------------------------------

@runtime_checkable
class BaseExtension(Protocol):
    """
    Protocol that all RealizeOS extensions must satisfy.

    Extensions are auto-discovered at startup and managed through
    a unified registry. Each extension goes through a lifecycle:
    discovered → loaded → active (or error / disabled).
    """

    @property
    def name(self) -> str:
        """Unique identifier for this extension."""
        ...

    @property
    def extension_type(self) -> ExtensionType:
        """The category of this extension."""
        ...

    @property
    def manifest(self) -> ExtensionManifest:
        """Static metadata / manifest for this extension."""
        ...

    async def on_load(self, config: dict[str, Any] | None = None) -> None:
        """
        Called when the extension is loaded.

        Use this for one-time initialization: validate config,
        establish connections, register tools/channels, etc.

        Args:
            config: Extension-specific configuration from realize-os.yaml.

        Raises:
            Exception: On initialization failure (extension set to ERROR state).
        """
        ...

    async def on_unload(self) -> None:
        """
        Called when the extension is being unloaded or the system shuts down.

        Use this for cleanup: close connections, flush buffers, etc.
        """
        ...

    def is_available(self) -> bool:
        """
        Whether this extension's dependencies are satisfied.

        Returns:
            True if the extension can be activated.
        """
        ...
