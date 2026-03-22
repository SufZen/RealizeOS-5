"""
S3-compatible storage provider for RealizeOS.

Supports any S3-compatible endpoint (AWS S3, MinIO, DigitalOcean Spaces,
Backblaze B2, Cloudflare R2, etc.) via the ``boto3`` library.

Usage:
    provider = S3StorageProvider(
        bucket="realize-os",
        region="us-east-1",
        endpoint_url="https://s3.amazonaws.com",     # optional
        access_key_id="AKIAEXAMPLE",
        secret_access_key="wJal...",
    )
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from realize_core.storage.base import (
    BaseStorageProvider,
    StorageBackend,
    StorageObject,
)

logger = logging.getLogger(__name__)


def _import_boto3():
    """Lazy-import boto3 to avoid hard dependency at import time."""
    try:
        import boto3  # type: ignore[import-untyped]
        from botocore.exceptions import ClientError  # type: ignore[import-untyped]
        return boto3, ClientError
    except ImportError:
        raise ImportError(
            "The 'boto3' package is required for S3 storage. "
            "Install it with: pip install boto3"
        )


class S3StorageProvider(BaseStorageProvider):
    """
    S3-compatible storage provider.

    Objects are stored in a single bucket with keys used
    as the full object path. Metadata is stored as S3 object
    metadata (user-defined headers).

    Args:
        bucket: S3 bucket name.
        region: AWS region (e.g. 'us-east-1').
        endpoint_url: Custom S3 endpoint for S3-compatible services.
        access_key_id: AWS access key ID (or equivalent).
        secret_access_key: AWS secret access key (or equivalent).
        prefix: Optional key prefix to scope all operations.
    """

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        prefix: str = "",
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url
        self._prefix = prefix.strip("/")

        boto3, client_error_cls = _import_boto3()
        self._client_error = client_error_cls

        kwargs: dict[str, Any] = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key_id:
            kwargs["aws_access_key_id"] = access_key_id
        if secret_access_key:
            kwargs["aws_secret_access_key"] = secret_access_key

        self._client = boto3.client("s3", **kwargs)
        logger.info(
            "S3StorageProvider initialized: bucket=%s region=%s endpoint=%s",
            bucket, region, endpoint_url or "default",
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def backend(self) -> StorageBackend:
        return StorageBackend.S3

    @property
    def bucket(self) -> str:
        return self._bucket

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    def _full_key(self, key: str) -> str:
        """Prepend the configured prefix to a key."""
        key = key.strip("/")
        if not key:
            raise ValueError("Storage key must not be empty")
        if self._prefix:
            return f"{self._prefix}/{key}"
        return key

    def _strip_prefix(self, full_key: str) -> str:
        """Remove the prefix from a full S3 key."""
        if self._prefix and full_key.startswith(f"{self._prefix}/"):
            return full_key[len(self._prefix) + 1:]
        return full_key

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    async def read(self, key: str) -> bytes:
        """Download an object from S3."""
        full = self._full_key(key)

        try:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=full,
            )
            return response["Body"].read()
        except self._client_error as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise FileNotFoundError(f"Object not found: {key}")
            raise OSError(f"S3 read failed for '{key}': {exc}") from exc

    async def write(
        self,
        key: str,
        data: bytes,
        content_type: str = "",
        metadata: dict[str, str] | None = None,
    ) -> StorageObject:
        """Upload an object to S3."""
        full = self._full_key(key)

        put_kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": full,
            "Body": data,
        }

        if content_type:
            put_kwargs["ContentType"] = content_type

        if metadata:
            # S3 user-defined metadata keys must not include
            # reserved prefixes (handled automatically by boto3).
            put_kwargs["Metadata"] = metadata

        try:
            self._client.put_object(**put_kwargs)
        except Exception as exc:
            raise OSError(f"S3 write failed for '{key}': {exc}") from exc

        return StorageObject(
            key=key,
            size_bytes=len(data),
            content_type=content_type,
            last_modified=datetime.now(UTC),
            metadata=dict(metadata or {}),
        )

    async def delete(self, key: str) -> bool:
        """Delete an object from S3."""
        full = self._full_key(key)

        # Check existence first (S3 delete is idempotent)
        if not await self.exists(key):
            return False

        try:
            self._client.delete_object(
                Bucket=self._bucket,
                Key=full,
            )
            return True
        except Exception as exc:
            raise OSError(f"S3 delete failed for '{key}': {exc}") from exc

    async def exists(self, key: str) -> bool:
        """Check whether an object exists in S3."""
        full = self._full_key(key)

        try:
            self._client.head_object(
                Bucket=self._bucket,
                Key=full,
            )
            return True
        except self._client_error as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey"):
                return False
            raise OSError(f"S3 exists check failed for '{key}': {exc}") from exc

    async def list(
        self,
        prefix: str = "",
        recursive: bool = False,
    ) -> list[StorageObject]:
        """
        List objects under a prefix in S3.

        Uses ``list_objects_v2`` with pagination. For non-recursive listing,
        uses the ``Delimiter='/'`` parameter to return only immediate children.
        """
        prefix = prefix.strip("/")
        search_prefix = self._full_key(prefix) + "/" if prefix else (
            f"{self._prefix}/" if self._prefix else ""
        )

        list_kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Prefix": search_prefix,
            "MaxKeys": 1000,
        }

        if not recursive:
            list_kwargs["Delimiter"] = "/"

        results: list[StorageObject] = []
        continuation_token: str | None = None

        while True:
            if continuation_token:
                list_kwargs["ContinuationToken"] = continuation_token

            try:
                response = self._client.list_objects_v2(**list_kwargs)
            except Exception as exc:
                raise OSError(f"S3 list failed for prefix '{prefix}': {exc}") from exc

            for obj in response.get("Contents", []):
                s3_key = obj["Key"]
                # Skip the prefix-directory marker itself
                if s3_key == search_prefix:
                    continue

                key = self._strip_prefix(s3_key)
                last_mod = obj.get("LastModified")
                if last_mod and last_mod.tzinfo is None:
                    last_mod = last_mod.replace(tzinfo=UTC)

                results.append(
                    StorageObject(
                        key=key,
                        size_bytes=obj.get("Size", 0),
                        last_modified=last_mod,
                    )
                )

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

        results.sort(key=lambda o: o.key)
        return results

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def copy(self, src_key: str, dst_key: str) -> StorageObject:
        """Server-side copy within the same bucket."""
        src_full = self._full_key(src_key)
        dst_full = self._full_key(dst_key)

        try:
            self._client.copy_object(
                Bucket=self._bucket,
                CopySource={"Bucket": self._bucket, "Key": src_full},
                Key=dst_full,
            )
        except Exception as exc:
            raise OSError(
                f"S3 copy failed: {src_key} → {dst_key}: {exc}"
            ) from exc

        # Read the metadata of the new object
        try:
            head = self._client.head_object(
                Bucket=self._bucket,
                Key=dst_full,
            )
        except Exception:
            head = {}

        return StorageObject(
            key=dst_key,
            size_bytes=head.get("ContentLength", 0),
            content_type=head.get("ContentType", ""),
            last_modified=head.get("LastModified"),
            metadata=head.get("Metadata", {}),
        )

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        method: str = "get_object",
    ) -> str:
        """
        Generate a presigned URL for temporary access to an object.

        Args:
            key: The storage key.
            expires_in: URL expiry in seconds (default 1 hour).
            method: S3 client method ('get_object' or 'put_object').

        Returns:
            Presigned URL string.
        """
        full = self._full_key(key)

        try:
            return self._client.generate_presigned_url(
                method,
                Params={"Bucket": self._bucket, "Key": full},
                ExpiresIn=expires_in,
            )
        except Exception as exc:
            raise OSError(
                f"Failed to generate presigned URL for '{key}': {exc}"
            ) from exc

    def __repr__(self) -> str:
        return (
            f"S3StorageProvider(bucket={self._bucket!r}, "
            f"region={self._region!r}, prefix={self._prefix!r})"
        )
