"""
Background sync manager for RealizeOS storage layer.

Synchronises objects between two storage providers (e.g. local ↔ S3).
Tracks each sync operation in the ``storage_sync_log`` database table
created by migration ``002_v5_tables``.

Features:
- Full sync (mirror everything from source to target)
- Incremental sync (only changed / new files)
- Single-file push / pull
- Sync log with status tracking
- Graceful error handling per file
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from realize_core.storage.base import BaseStorageProvider, StorageObject

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & dataclasses
# ---------------------------------------------------------------------------


class SyncDirection(StrEnum):
    PUSH = "push"  # source → target
    PULL = "pull"  # target → source


class SyncStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SyncResult:
    """Result of a sync operation."""

    total_files: int = 0
    synced: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0

    def __repr__(self) -> str:
        return (
            f"SyncResult(total={self.total_files}, synced={self.synced}, skipped={self.skipped}, failed={self.failed})"
        )


@dataclass
class SyncLogEntry:
    """A record from the storage_sync_log table."""

    id: str
    sync_type: str
    source_backend: str
    target_backend: str
    file_key: str
    file_size_bytes: int | None
    status: str
    error_message: str | None
    created_at: str
    completed_at: str | None


# ---------------------------------------------------------------------------
# Sync Manager
# ---------------------------------------------------------------------------


class SyncManager:
    """
    Manages bidirectional synchronisation between two storage providers.

    Designed to run as a background task. Operations are logged
    to the ``storage_sync_log`` table for observability.

    Args:
        source: The primary storage provider (typically local).
        target: The secondary storage provider (typically S3).
        db_conn: SQLite connection for sync logging.
                 Pass ``None`` to disable logging.
    """

    def __init__(
        self,
        source: BaseStorageProvider,
        target: BaseStorageProvider,
        db_conn: sqlite3.Connection | None = None,
    ) -> None:
        self._source = source
        self._target = target
        self._db = db_conn
        self._running = False
        self._lock = asyncio.Lock()
        logger.info(
            "SyncManager initialised: %s ↔ %s",
            source.backend,
            target.backend,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def source(self) -> BaseStorageProvider:
        return self._source

    @property
    def target(self) -> BaseStorageProvider:
        return self._target

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Sync log helpers
    # ------------------------------------------------------------------

    def _log_sync(
        self,
        sync_type: str,
        file_key: str,
        file_size: int | None = None,
        status: str = SyncStatus.PENDING,
        error_msg: str | None = None,
    ) -> str:
        """Insert a sync log entry and return its ID."""
        entry_id = uuid.uuid4().hex[:16]

        if self._db is None:
            return entry_id

        try:
            self._db.execute(
                """
                INSERT INTO storage_sync_log
                    (id, sync_type, source_backend, target_backend,
                     file_key, file_size_bytes, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    sync_type,
                    str(self._source.backend),
                    str(self._target.backend),
                    file_key,
                    file_size,
                    status,
                    error_msg,
                ),
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("Failed to write sync log: %s", exc)

        return entry_id

    def _update_log(
        self,
        entry_id: str,
        status: str,
        error_msg: str | None = None,
    ) -> None:
        """Update a sync log entry status."""
        if self._db is None:
            return

        try:
            now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")
            self._db.execute(
                """
                UPDATE storage_sync_log
                SET status = ?, error_message = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, error_msg, now, entry_id),
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("Failed to update sync log: %s", exc)

    # ------------------------------------------------------------------
    # Single-file operations
    # ------------------------------------------------------------------

    async def push_file(self, key: str) -> bool:
        """
        Push a single file from source to target.

        Returns True if successful, False on failure.
        """
        entry_id = self._log_sync("upload", key)

        try:
            self._update_log(entry_id, SyncStatus.IN_PROGRESS)
            data = await self._source.read(key)
            await self._target.write(key, data)
            self._update_log(entry_id, SyncStatus.COMPLETED)
            logger.debug("Pushed: %s (%d bytes)", key, len(data))
            return True
        except FileNotFoundError:
            self._update_log(entry_id, SyncStatus.SKIPPED, "Source file not found")
            logger.warning("Push skipped — source not found: %s", key)
            return False
        except Exception as exc:
            self._update_log(entry_id, SyncStatus.FAILED, str(exc))
            logger.error("Push failed for %s: %s", key, exc)
            return False

    async def pull_file(self, key: str) -> bool:
        """
        Pull a single file from target to source.

        Returns True if successful, False on failure.
        """
        entry_id = self._log_sync("download", key)

        try:
            self._update_log(entry_id, SyncStatus.IN_PROGRESS)
            data = await self._target.read(key)
            await self._source.write(key, data)
            self._update_log(entry_id, SyncStatus.COMPLETED)
            logger.debug("Pulled: %s (%d bytes)", key, len(data))
            return True
        except FileNotFoundError:
            self._update_log(entry_id, SyncStatus.SKIPPED, "Target file not found")
            logger.warning("Pull skipped — target not found: %s", key)
            return False
        except Exception as exc:
            self._update_log(entry_id, SyncStatus.FAILED, str(exc))
            logger.error("Pull failed for %s: %s", key, exc)
            return False

    async def delete_remote(self, key: str) -> bool:
        """
        Delete a file from the target storage.

        Returns True if deleted, False otherwise.
        """
        entry_id = self._log_sync("delete", key)

        try:
            self._update_log(entry_id, SyncStatus.IN_PROGRESS)
            deleted = await self._target.delete(key)
            status = SyncStatus.COMPLETED if deleted else SyncStatus.SKIPPED
            self._update_log(entry_id, status)
            return deleted
        except Exception as exc:
            self._update_log(entry_id, SyncStatus.FAILED, str(exc))
            logger.error("Remote delete failed for %s: %s", key, exc)
            return False

    # ------------------------------------------------------------------
    # Full and incremental sync
    # ------------------------------------------------------------------

    async def full_sync(
        self,
        prefix: str = "",
        direction: SyncDirection = SyncDirection.PUSH,
        delete_orphans: bool = False,
    ) -> SyncResult:
        """
        Perform a full sync between source and target.

        Args:
            prefix: Optional key prefix to scope the sync.
            direction: PUSH (source → target) or PULL (target → source).
            delete_orphans: If True, delete objects in the destination
                            that are not present in the source.

        Returns:
            SyncResult with counts and any error messages.
        """
        async with self._lock:
            self._running = True
            try:
                return await self._do_sync(prefix, direction, delete_orphans)
            finally:
                self._running = False

    async def _do_sync(
        self,
        prefix: str,
        direction: SyncDirection,
        delete_orphans: bool,
    ) -> SyncResult:
        """Internal sync implementation."""
        result = SyncResult()

        if direction == SyncDirection.PUSH:
            from_provider = self._source
            to_provider = self._target
        else:
            from_provider = self._target
            to_provider = self._source

        # List all objects in source
        try:
            source_objects = await from_provider.list(prefix, recursive=True)
        except Exception as exc:
            result.failed = 1
            result.errors.append(f"Failed to list source: {exc}")
            self._log_sync("full_sync", prefix or "*", status=SyncStatus.FAILED, error_msg=str(exc))
            return result

        result.total_files = len(source_objects)
        sync_id = self._log_sync("full_sync", prefix or "*")
        self._update_log(sync_id, SyncStatus.IN_PROGRESS)

        # Build destination index for comparison
        try:
            dest_objects = await to_provider.list(prefix, recursive=True)
        except Exception as exc:
            result.failed = 1
            result.errors.append(f"Failed to list destination: {exc}")
            self._update_log(sync_id, SyncStatus.FAILED, str(exc))
            return result

        dest_index: dict[str, StorageObject] = {o.key: o for o in dest_objects}

        # Sync each file
        for src_obj in source_objects:
            dest_obj = dest_index.get(src_obj.key)

            # Skip if destination is up-to-date (same size and newer)
            if dest_obj is not None:
                if (
                    dest_obj.size_bytes == src_obj.size_bytes
                    and dest_obj.last_modified is not None
                    and src_obj.last_modified is not None
                    and dest_obj.last_modified >= src_obj.last_modified
                ):
                    result.skipped += 1
                    continue

            # Copy the file
            try:
                data = await from_provider.read(src_obj.key)
                await to_provider.write(
                    src_obj.key,
                    data,
                    content_type=src_obj.content_type,
                    metadata=src_obj.metadata,
                )
                result.synced += 1
                logger.debug("Synced: %s", src_obj.key)
            except Exception as exc:
                result.failed += 1
                result.errors.append(f"{src_obj.key}: {exc}")
                logger.error("Sync failed for %s: %s", src_obj.key, exc)

        # Delete orphans in destination
        if delete_orphans:
            source_keys = {o.key for o in source_objects}
            for dest_obj in dest_objects:
                if dest_obj.key not in source_keys:
                    try:
                        await to_provider.delete(dest_obj.key)
                        logger.debug("Deleted orphan: %s", dest_obj.key)
                    except Exception as exc:
                        result.errors.append(f"Orphan delete {dest_obj.key}: {exc}")

        final_status = SyncStatus.COMPLETED if result.success else SyncStatus.FAILED
        self._update_log(
            sync_id,
            final_status,
            "; ".join(result.errors) if result.errors else None,
        )

        logger.info(
            "Full sync %s complete: %s",
            direction,
            result,
        )
        return result

    async def incremental_sync(
        self,
        prefix: str = "",
        direction: SyncDirection = SyncDirection.PUSH,
    ) -> SyncResult:
        """
        Sync only files that are new or modified.

        Equivalent to ``full_sync(delete_orphans=False)``
        but explicitly named for clarity.
        """
        return await self.full_sync(
            prefix=prefix,
            direction=direction,
            delete_orphans=False,
        )

    # ------------------------------------------------------------------
    # Sync log queries
    # ------------------------------------------------------------------

    def get_sync_history(
        self,
        limit: int = 50,
        status: str | None = None,
    ) -> list[SyncLogEntry]:
        """
        Retrieve recent sync log entries.

        Args:
            limit: Maximum entries to return.
            status: Optional status filter.

        Returns:
            List of SyncLogEntry objects, newest first.
        """
        if self._db is None:
            return []

        query = "SELECT * FROM storage_sync_log"
        params: list = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        try:
            cursor = self._db.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
        except Exception as exc:
            logger.warning("Failed to query sync history: %s", exc)
            return []

        return [SyncLogEntry(**dict(zip(columns, row))) for row in rows]

    def get_sync_stats(self) -> dict[str, int]:
        """
        Return aggregate counts by status.

        Returns:
            Dict like {'completed': 42, 'failed': 3, ...}
        """
        if self._db is None:
            return {}

        try:
            cursor = self._db.execute(
                """
                SELECT status, COUNT(*) as cnt
                FROM storage_sync_log
                GROUP BY status
                """
            )
            return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as exc:
            logger.warning("Failed to query sync stats: %s", exc)
            return {}

    def __repr__(self) -> str:
        return f"SyncManager(source={self._source.backend}, target={self._target.backend})"
