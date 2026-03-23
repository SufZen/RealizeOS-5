"""
Storage provider factory — creates the appropriate storage provider
based on the current configuration.

Centralises provider instantiation so all routes and modules use the
same singleton instances.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from realize_core.storage.base import BaseStorageProvider, StorageBackend

logger = logging.getLogger(__name__)

# Module-level singletons (reset on reconfigure)
_primary: BaseStorageProvider | None = None
_sync_manager = None  # type: Any


def get_storage_provider(config: dict | None = None) -> BaseStorageProvider:
    """
    Get (or create) the primary storage provider.

    Uses the configuration from ``.storage-config.json`` or
    the provided ``config`` dict.

    Returns a ``LocalStorageProvider`` or ``S3StorageProvider`` depending
    on the ``provider`` field.
    """
    global _primary

    if _primary is not None and config is None:
        return _primary

    config = config or _load_default_config()
    provider_type = config.get("provider", "local")

    if provider_type == "s3":
        _primary = _create_s3(config)
    else:
        _primary = _create_local(config)

    return _primary


def get_sync_manager():
    """
    Get the sync manager (if S3 sync is configured).

    Returns ``None`` if sync is not enabled.
    """
    global _sync_manager

    if _sync_manager is not None:
        return _sync_manager

    config = _load_default_config()
    if not config.get("sync_enabled"):
        return None

    if config.get("provider") != "s3":
        return None

    try:
        local = _create_local(config)
        s3 = _create_s3(config)

        # Get a DB connection for sync logging
        db_conn = None
        try:
            from realize_core.db.schema import get_connection

            db_conn = get_connection()
        except Exception as exc:
            logger.debug("Sync log DB unavailable: %s", exc)

        from realize_core.storage.sync import SyncManager

        _sync_manager = SyncManager(source=local, target=s3, db_conn=db_conn)
        return _sync_manager
    except Exception as exc:
        logger.warning("Failed to create sync manager: %s", exc)
        return None


def reconfigure(config: dict) -> BaseStorageProvider:
    """
    Reconfigure the storage layer with a new config dict.

    Resets singletons and creates new provider(s).
    """
    global _primary, _sync_manager
    _primary = None
    _sync_manager = None
    return get_storage_provider(config)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_default_config() -> dict:
    """Load config from .storage-config.json, falling back to local."""
    import json

    config_path = Path(os.getcwd()) / ".storage-config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"provider": "local"}


def _create_local(config: dict) -> BaseStorageProvider:
    """Create a LocalStorageProvider."""
    from realize_core.storage.local import LocalStorageProvider

    root_dir = config.get("local_root", os.path.join(os.getcwd(), "data", "storage"))
    return LocalStorageProvider(root_dir=root_dir)


def _create_s3(config: dict) -> BaseStorageProvider:
    """Create an S3StorageProvider."""
    from realize_core.storage.s3 import S3StorageProvider

    return S3StorageProvider(
        bucket=config.get("s3_bucket", ""),
        region=config.get("s3_region", "us-east-1"),
        endpoint_url=config.get("s3_endpoint_url") or None,
        access_key_id=config.get("s3_access_key") or None,
        secret_access_key=config.get("s3_secret_key") or None,
        prefix=config.get("s3_prefix", ""),
    )
