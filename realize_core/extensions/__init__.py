"""
Extensions — unified extension registration, discovery, and lifecycle.

Public API:
- ``base`` — BaseExtension protocol, ExtensionManifest, ExtensionRegistration
- ``registry`` — ExtensionRegistry for managing extensions
- ``loader`` — ExtensionLoader for auto-discovery
- ``cron`` — CronExtension for scheduled tasks
- ``hooks`` — HooksExtension for event pub/sub
"""

from realize_core.extensions.base import (
    BaseExtension,
    ExtensionManifest,
    ExtensionRegistration,
    ExtensionStatus,
    ExtensionType,
)
from realize_core.extensions.cron import CronExtension
from realize_core.extensions.hooks import EventType, HooksExtension, HookSubscription
from realize_core.extensions.loader import ExtensionLoader
from realize_core.extensions.registry import ExtensionRegistry, get_extension_registry

__all__ = [
    # base
    "BaseExtension",
    "ExtensionManifest",
    "ExtensionRegistration",
    "ExtensionStatus",
    "ExtensionType",
    # registry
    "ExtensionRegistry",
    "get_extension_registry",
    # loader
    "ExtensionLoader",
    # cron
    "CronExtension",
    # hooks
    "EventType",
    "HooksExtension",
    "HookSubscription",
]
