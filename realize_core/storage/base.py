"""
Storage provider base interfaces for RealizeOS pluggable storage layer.

Defines the abstract contract for storage backends:
- BaseStorageProvider: Abstract base with CRUD + list + exists operations
- StorageObject: Lightweight metadata for stored objects

The default implementation uses local filesystem / SQLite.
Cloud implementations (S3, GCS, Azure Blob) can be added as plugins.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StorageBackend(StrEnum):
    """Supported storage backend types."""
    LOCAL = "local"
    S3 = "s3"
    GCS = "gcs"
    AZURE_BLOB = "azure_blob"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StorageObject:
    """
    Metadata for a stored object.

    Returned by list() and exists() operations without
    loading the full object content.
    """
    key: str
    size_bytes: int = 0
    content_type: str = ""
    last_modified: datetime | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def extension(self) -> str:
        """File extension derived from the key (e.g. '.yaml')."""
        if "." in self.key:
            return "." + self.key.rsplit(".", 1)[-1]
        return ""


# ---------------------------------------------------------------------------
# Abstract base — storage provider contract
# ---------------------------------------------------------------------------

class BaseStorageProvider(ABC):
    """
    Abstract base class for RealizeOS storage providers.

    Implementations must provide basic CRUD operations plus
    listing and existence checks. All keys are slash-delimited
    paths (e.g. 'ventures/my-biz/agents/writer.md').

    The provider is responsible for key validation and encoding.
    """

    @property
    @abstractmethod
    def backend(self) -> StorageBackend:
        """The backend type this provider implements."""
        ...

    @abstractmethod
    async def read(self, key: str) -> bytes:
        """
        Read raw bytes for a given key.

        Args:
            key: The storage key / path.

        Returns:
            Raw bytes of the stored object.

        Raises:
            FileNotFoundError: If the key does not exist.
            IOError: On read failure.
        """
        ...

    @abstractmethod
    async def write(
        self,
        key: str,
        data: bytes,
        content_type: str = "",
        metadata: dict[str, str] | None = None,
    ) -> StorageObject:
        """
        Write raw bytes to a given key (creates or overwrites).

        Args:
            key: The storage key / path.
            data: Raw bytes to write.
            content_type: MIME type hint (e.g. 'text/yaml').
            metadata: Optional key-value metadata to attach.

        Returns:
            StorageObject representing the written object.

        Raises:
            IOError: On write failure.
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete an object by key.

        Args:
            key: The storage key / path.

        Returns:
            True if deleted, False if the key didn't exist.

        Raises:
            IOError: On delete failure.
        """
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check whether an object exists at the given key.

        Args:
            key: The storage key / path.

        Returns:
            True if the object exists.
        """
        ...

    @abstractmethod
    async def list(
        self,
        prefix: str = "",
        recursive: bool = False,
    ) -> list[StorageObject]:
        """
        List objects under a prefix.

        Args:
            prefix: Key prefix to filter by (e.g. 'ventures/my-biz/').
            recursive: If False, list only immediate children.

        Returns:
            List of StorageObject metadata entries.
        """
        ...

    # ------------------------------------------------------------------
    # Convenience helpers (non-abstract)
    # ------------------------------------------------------------------

    async def read_text(self, key: str, encoding: str = "utf-8") -> str:
        """Read a stored object as a decoded text string."""
        raw = await self.read(key)
        return raw.decode(encoding)

    async def write_text(
        self,
        key: str,
        text: str,
        encoding: str = "utf-8",
        metadata: dict[str, str] | None = None,
    ) -> StorageObject:
        """Write a text string to storage."""
        return await self.write(
            key,
            text.encode(encoding),
            content_type="text/plain",
            metadata=metadata,
        )
