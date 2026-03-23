"""
Local filesystem storage provider for RealizeOS.

Default storage backend that persists objects to the local filesystem.
Keys map directly to file paths relative to a configurable root directory.
Metadata is stored as sidecar JSON files.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path

from realize_core.storage.base import (
    BaseStorageProvider,
    StorageBackend,
    StorageObject,
)

logger = logging.getLogger(__name__)


class LocalStorageProvider(BaseStorageProvider):
    """
    Filesystem-backed storage provider.

    Objects are stored as plain files under ``root_dir``.
    Metadata is persisted in a sidecar ``.<filename>.meta.json`` file
    next to each stored object.

    Args:
        root_dir: Base directory for all stored objects.
                  Created automatically if it doesn't exist.
    """

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        logger.info("LocalStorageProvider initialized at %s", self._root)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def backend(self) -> StorageBackend:
        return StorageBackend.LOCAL

    @property
    def root_dir(self) -> Path:
        """Root directory for stored objects."""
        return self._root

    # ------------------------------------------------------------------
    # Key → Path helpers
    # ------------------------------------------------------------------

    def _resolve(self, key: str) -> Path:
        """
        Resolve a storage key to an absolute file path.

        Validates that the resolved path is within the root directory
        to prevent path traversal attacks.
        """
        # Normalize key separators
        key = key.strip("/").replace("\\", "/")
        if not key:
            raise ValueError("Storage key must not be empty")

        resolved = (self._root / key).resolve()

        # Guard against path traversal
        try:
            resolved.relative_to(self._root)
        except ValueError:
            raise ValueError(f"Key '{key}' resolves outside root directory")

        return resolved

    def _meta_path(self, file_path: Path) -> Path:
        """Return the sidecar metadata path for a given file."""
        return file_path.parent / f".{file_path.name}.meta.json"

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    def _read_meta(self, file_path: Path) -> dict[str, str]:
        """Load metadata from sidecar JSON, returning empty dict if absent."""
        meta_file = self._meta_path(file_path)
        if meta_file.exists():
            try:
                return json.loads(meta_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Corrupt metadata file: %s", meta_file)
        return {}

    def _write_meta(
        self,
        file_path: Path,
        metadata: dict[str, str] | None,
        content_type: str = "",
    ) -> None:
        """Persist metadata to sidecar JSON."""
        meta = dict(metadata or {})
        if content_type:
            meta["_content_type"] = content_type
        meta["_updated_at"] = datetime.now(UTC).isoformat()

        meta_file = self._meta_path(file_path)
        meta_file.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _delete_meta(self, file_path: Path) -> None:
        """Remove sidecar metadata if it exists."""
        meta_file = self._meta_path(file_path)
        if meta_file.exists():
            meta_file.unlink()

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    async def read(self, key: str) -> bytes:
        """Read raw bytes from the local filesystem."""
        path = self._resolve(key)

        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Object not found: {key}")

        try:
            return path.read_bytes()
        except OSError as exc:
            raise OSError(f"Failed to read '{key}': {exc}") from exc

    async def write(
        self,
        key: str,
        data: bytes,
        content_type: str = "",
        metadata: dict[str, str] | None = None,
    ) -> StorageObject:
        """Write raw bytes to the local filesystem."""
        path = self._resolve(key)

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            path.write_bytes(data)
        except OSError as exc:
            raise OSError(f"Failed to write '{key}': {exc}") from exc

        # Auto-detect content type from extension if not provided
        if not content_type:
            guessed, _ = mimetypes.guess_type(path.name)
            content_type = guessed or ""

        # Persist metadata
        self._write_meta(path, metadata, content_type)

        stat = path.stat()
        return StorageObject(
            key=key,
            size_bytes=stat.st_size,
            content_type=content_type,
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            metadata=dict(metadata or {}),
        )

    async def delete(self, key: str) -> bool:
        """Delete a file from the local filesystem."""
        path = self._resolve(key)

        if not path.exists():
            return False

        try:
            path.unlink()
            self._delete_meta(path)
            return True
        except OSError as exc:
            raise OSError(f"Failed to delete '{key}': {exc}") from exc

    async def exists(self, key: str) -> bool:
        """Check whether a file exists in the local filesystem."""
        path = self._resolve(key)
        return path.exists() and path.is_file()

    async def list(
        self,
        prefix: str = "",
        recursive: bool = False,
    ) -> list[StorageObject]:
        """
        List objects under a key prefix.

        For non-recursive listing, only immediate children of the
        prefix directory are returned. Sidecar metadata files
        (``.*meta.json``) are excluded from results.
        """
        prefix = prefix.strip("/")
        search_dir = self._root / prefix if prefix else self._root

        if not search_dir.exists() or not search_dir.is_dir():
            return []

        results: list[StorageObject] = []
        pattern = "**/*" if recursive else "*"

        for item in search_dir.glob(pattern):
            # Skip directories, hidden/meta files
            if not item.is_file():
                continue
            if item.name.startswith(".") and item.name.endswith(".meta.json"):
                continue

            # Build relative key
            rel = item.relative_to(self._root)
            key = str(rel).replace(os.sep, "/")

            stat = item.stat()
            meta = self._read_meta(item)
            ct = meta.pop("_content_type", "")
            meta.pop("_updated_at", None)

            results.append(
                StorageObject(
                    key=key,
                    size_bytes=stat.st_size,
                    content_type=ct,
                    last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                    metadata=meta,
                )
            )

        # Sort by key for deterministic output
        results.sort(key=lambda o: o.key)
        return results

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def copy(self, src_key: str, dst_key: str) -> StorageObject:
        """Copy an object from one key to another within local storage."""
        data = await self.read(src_key)
        src_path = self._resolve(src_key)
        meta = self._read_meta(src_path)
        ct = meta.pop("_content_type", "")
        meta.pop("_updated_at", None)
        return await self.write(dst_key, data, content_type=ct, metadata=meta)

    def __repr__(self) -> str:
        return f"LocalStorageProvider(root={self._root})"
