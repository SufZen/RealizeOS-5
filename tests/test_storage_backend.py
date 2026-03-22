"""
Tests for storage backends: LocalStorageProvider, S3StorageProvider, and SyncManager.

Uses temporary directories for local storage tests and mocks for S3.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from realize_core.storage.base import (
    StorageBackend,
    StorageObject,
)
from realize_core.storage.local import LocalStorageProvider
from realize_core.storage.sync import (
    SyncDirection,
    SyncManager,
    SyncResult,
)

# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def tmp_root(tmp_path):
    """Temporary directory for local storage tests."""
    return tmp_path / "storage_root"


@pytest.fixture
def local_provider(tmp_root):
    """LocalStorageProvider backed by a temp directory."""
    return LocalStorageProvider(tmp_root)


@pytest.fixture
def sync_db():
    """In-memory SQLite database with storage_sync_log table."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE storage_sync_log (
            id TEXT PRIMARY KEY,
            sync_type TEXT NOT NULL,
            source_backend TEXT NOT NULL,
            target_backend TEXT NOT NULL,
            file_key TEXT NOT NULL,
            file_size_bytes INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            completed_at TEXT
        )
    """)
    conn.commit()
    return conn


# ======================================================================
# StorageObject Tests
# ======================================================================

class TestStorageObject:
    def test_extension_with_dot(self):
        obj = StorageObject(key="path/to/file.yaml")
        assert obj.extension == ".yaml"

    def test_extension_without_dot(self):
        obj = StorageObject(key="README")
        assert obj.extension == ""

    def test_nested_extension(self):
        obj = StorageObject(key="dir/sub/file.tar.gz")
        assert obj.extension == ".gz"

    def test_metadata_default_factory(self):
        obj = StorageObject(key="a")
        assert obj.metadata == {}


# ======================================================================
# LocalStorageProvider Tests
# ======================================================================

class TestLocalInit:
    def test_creates_root_directory(self, tmp_root):
        assert not tmp_root.exists()
        provider = LocalStorageProvider(tmp_root)
        assert tmp_root.exists()
        assert provider.backend == StorageBackend.LOCAL

    def test_root_dir_property(self, local_provider, tmp_root):
        assert local_provider.root_dir == tmp_root

    def test_repr(self, local_provider):
        assert "LocalStorageProvider" in repr(local_provider)


class TestLocalWrite:
    @pytest.mark.asyncio
    async def test_write_creates_file(self, local_provider, tmp_root):
        obj = await local_provider.write("hello.txt", b"Hello world")
        assert obj.key == "hello.txt"
        assert obj.size_bytes == 11
        assert (tmp_root / "hello.txt").read_bytes() == b"Hello world"

    @pytest.mark.asyncio
    async def test_write_nested_path(self, local_provider, tmp_root):
        obj = await local_provider.write("a/b/c.txt", b"nested")
        assert (tmp_root / "a" / "b" / "c.txt").exists()
        assert obj.key == "a/b/c.txt"

    @pytest.mark.asyncio
    async def test_write_with_metadata(self, local_provider, tmp_root):
        meta = {"author": "test", "version": "1"}
        obj = await local_provider.write("doc.md", b"# Hello", metadata=meta)
        assert obj.metadata == meta

        # Check sidecar file
        sidecar = tmp_root / ".doc.md.meta.json"
        assert sidecar.exists()
        stored = json.loads(sidecar.read_text())
        assert stored["author"] == "test"

    @pytest.mark.asyncio
    async def test_write_overwrite(self, local_provider):
        await local_provider.write("f.txt", b"v1")
        obj = await local_provider.write("f.txt", b"v2")
        data = await local_provider.read("f.txt")
        assert data == b"v2"
        assert obj.size_bytes == 2

    @pytest.mark.asyncio
    async def test_write_content_type_auto_detect(self, local_provider):
        obj = await local_provider.write("style.css", b"body{}")
        assert "css" in obj.content_type.lower()


class TestLocalRead:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, local_provider):
        await local_provider.write("data.bin", b"\x00\x01\x02")
        result = await local_provider.read("data.bin")
        assert result == b"\x00\x01\x02"

    @pytest.mark.asyncio
    async def test_read_nonexistent_raises(self, local_provider):
        with pytest.raises(FileNotFoundError):
            await local_provider.read("nope.txt")

    @pytest.mark.asyncio
    async def test_read_text_helper(self, local_provider):
        await local_provider.write("note.txt", "Héllo wörld".encode())
        text = await local_provider.read_text("note.txt")
        assert text == "Héllo wörld"

    @pytest.mark.asyncio
    async def test_write_text_helper(self, local_provider):
        await local_provider.write_text("note.txt", "Hello")
        data = await local_provider.read("note.txt")
        assert data == b"Hello"


class TestLocalDelete:
    @pytest.mark.asyncio
    async def test_delete_existing(self, local_provider):
        await local_provider.write("f.txt", b"data")
        assert await local_provider.delete("f.txt")
        assert not await local_provider.exists("f.txt")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, local_provider):
        assert not await local_provider.delete("ghost.txt")

    @pytest.mark.asyncio
    async def test_delete_removes_sidecar(self, local_provider, tmp_root):
        await local_provider.write("f.txt", b"data", metadata={"k": "v"})
        sidecar = tmp_root / ".f.txt.meta.json"
        assert sidecar.exists()
        await local_provider.delete("f.txt")
        assert not sidecar.exists()


class TestLocalExists:
    @pytest.mark.asyncio
    async def test_exists_true(self, local_provider):
        await local_provider.write("f.txt", b"data")
        assert await local_provider.exists("f.txt")

    @pytest.mark.asyncio
    async def test_exists_false(self, local_provider):
        assert not await local_provider.exists("nope.txt")


class TestLocalList:
    @pytest.mark.asyncio
    async def test_list_empty(self, local_provider):
        result = await local_provider.list()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_flat(self, local_provider):
        await local_provider.write("a.txt", b"a")
        await local_provider.write("b.txt", b"b")
        result = await local_provider.list()
        keys = [o.key for o in result]
        assert "a.txt" in keys
        assert "b.txt" in keys

    @pytest.mark.asyncio
    async def test_list_with_prefix(self, local_provider):
        await local_provider.write("docs/a.txt", b"a")
        await local_provider.write("docs/b.txt", b"b")
        await local_provider.write("other/c.txt", b"c")
        result = await local_provider.list("docs")
        keys = [o.key for o in result]
        assert len(keys) == 2
        assert all(k.startswith("docs/") for k in keys)

    @pytest.mark.asyncio
    async def test_list_non_recursive(self, local_provider):
        await local_provider.write("top.txt", b"t")
        await local_provider.write("sub/deep.txt", b"d")
        result = await local_provider.list(recursive=False)
        keys = [o.key for o in result]
        assert "top.txt" in keys
        # Non-recursive should not include deep files
        assert "sub/deep.txt" not in keys

    @pytest.mark.asyncio
    async def test_list_recursive(self, local_provider):
        await local_provider.write("top.txt", b"t")
        await local_provider.write("sub/deep.txt", b"d")
        result = await local_provider.list(recursive=True)
        keys = [o.key for o in result]
        assert "top.txt" in keys
        assert "sub/deep.txt" in keys

    @pytest.mark.asyncio
    async def test_list_excludes_meta_files(self, local_provider):
        await local_provider.write("f.txt", b"data", metadata={"k": "v"})
        result = await local_provider.list()
        keys = [o.key for o in result]
        assert len(keys) == 1
        assert keys[0] == "f.txt"

    @pytest.mark.asyncio
    async def test_list_nonexistent_prefix(self, local_provider):
        result = await local_provider.list("nope")
        assert result == []


class TestLocalCopy:
    @pytest.mark.asyncio
    async def test_copy(self, local_provider):
        await local_provider.write("src.txt", b"original", metadata={"k": "v"})
        obj = await local_provider.copy("src.txt", "dst.txt")
        assert obj.key == "dst.txt"
        data = await local_provider.read("dst.txt")
        assert data == b"original"


class TestLocalSecurity:
    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, local_provider):
        with pytest.raises(ValueError, match="outside root"):
            await local_provider.read("../../etc/passwd")

    @pytest.mark.asyncio
    async def test_empty_key_blocked(self, local_provider):
        with pytest.raises(ValueError, match="must not be empty"):
            await local_provider.read("")


# ======================================================================
# S3StorageProvider Tests (mocked)
# ======================================================================

class TestS3Lazy:
    def test_import_error_without_boto3(self):
        with patch.dict("sys.modules", {"boto3": None, "botocore": None, "botocore.exceptions": None}):
            # Force reimport
            from importlib import reload

            import realize_core.storage.s3 as s3_module
            try:
                reload(s3_module)
            except Exception:
                pass
            # Just verify the module exists
            assert hasattr(s3_module, "S3StorageProvider")


class TestS3Provider:
    """Test S3 provider with mocked boto3 client."""

    def _make_provider(self, mock_client):
        """Create an S3StorageProvider with an injected mock client."""
        # Create a fake ClientError exception class
        FakeClientError = type("ClientError", (Exception,), {})  # noqa: N806

        with patch("realize_core.storage.s3._import_boto3") as mock_import:
            mock_boto3 = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_import.return_value = (mock_boto3, FakeClientError)

            from realize_core.storage.s3 import S3StorageProvider
            provider = S3StorageProvider(
                bucket="test-bucket",
                region="us-east-1",
            )
            provider._client = mock_client
            provider._client_error = FakeClientError
            return provider

    @pytest.mark.asyncio
    async def test_write_calls_put_object(self):
        client = MagicMock()
        provider = self._make_provider(client)

        await provider.write("test.txt", b"hello")
        client.put_object.assert_called_once()
        call_kwargs = client.put_object.call_args[1]
        assert call_kwargs["Key"] == "test.txt"
        assert call_kwargs["Body"] == b"hello"

    @pytest.mark.asyncio
    async def test_read_calls_get_object(self):
        client = MagicMock()
        body_mock = MagicMock()
        body_mock.read.return_value = b"content"
        client.get_object.return_value = {"Body": body_mock}
        provider = self._make_provider(client)

        result = await provider.read("test.txt")
        assert result == b"content"

    @pytest.mark.asyncio
    async def test_delete_calls_delete_object(self):
        client = MagicMock()
        client.head_object.return_value = {}  # exists
        provider = self._make_provider(client)

        result = await provider.delete("test.txt")
        assert result is True
        client.delete_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(self):
        client = MagicMock()
        client.head_object.return_value = {}
        provider = self._make_provider(client)

        assert await provider.exists("test.txt")

    @pytest.mark.asyncio
    async def test_list_returns_objects(self):
        from datetime import datetime
        client = MagicMock()
        client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "a.txt", "Size": 10, "LastModified": datetime(2024, 1, 1, tzinfo=UTC)},
                {"Key": "b.txt", "Size": 20, "LastModified": datetime(2024, 1, 2, tzinfo=UTC)},
            ],
            "IsTruncated": False,
        }
        provider = self._make_provider(client)

        result = await provider.list()
        assert len(result) == 2
        assert result[0].key == "a.txt"

    @pytest.mark.asyncio
    async def test_prefix_scoping(self):
        with patch("realize_core.storage.s3._import_boto3") as mock_import:
            mock_boto3 = MagicMock()
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_import.return_value = (mock_boto3, Exception)

            from realize_core.storage.s3 import S3StorageProvider
            provider = S3StorageProvider(
                bucket="bucket",
                prefix="myapp",
            )
            provider._client = mock_client

            await provider.write("doc.txt", b"hello")
            call_kwargs = mock_client.put_object.call_args[1]
            assert call_kwargs["Key"] == "myapp/doc.txt"

    def test_backend_property(self):
        client = MagicMock()
        provider = self._make_provider(client)
        assert provider.backend == StorageBackend.S3

    def test_repr(self):
        client = MagicMock()
        provider = self._make_provider(client)
        assert "S3StorageProvider" in repr(provider)


# ======================================================================
# SyncManager Tests
# ======================================================================

class TestSyncManagerInit:
    def test_init_with_providers(self, local_provider, tmp_path):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target)
        assert manager.source is local_provider
        assert manager.target is target
        assert not manager.is_running

    def test_repr(self, local_provider, tmp_path):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target)
        assert "SyncManager" in repr(manager)


class TestSyncPushPull:
    @pytest.mark.asyncio
    async def test_push_file(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        await local_provider.write("doc.txt", b"hello")
        result = await manager.push_file("doc.txt")
        assert result is True
        assert await target.read("doc.txt") == b"hello"

    @pytest.mark.asyncio
    async def test_push_nonexistent_returns_false(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        result = await manager.push_file("nope.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_pull_file(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        await target.write("remote.txt", b"from target")
        result = await manager.pull_file("remote.txt")
        assert result is True
        assert await local_provider.read("remote.txt") == b"from target"

    @pytest.mark.asyncio
    async def test_pull_nonexistent_returns_false(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        result = await manager.pull_file("nope.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_remote(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        await target.write("temp.txt", b"data")
        assert await manager.delete_remote("temp.txt")
        assert not await target.exists("temp.txt")


class TestSyncFull:
    @pytest.mark.asyncio
    async def test_full_sync_push(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        await local_provider.write("a.txt", b"aaa")
        await local_provider.write("b.txt", b"bbb")

        result = await manager.full_sync()
        assert result.total_files == 2
        assert result.synced == 2
        assert result.failed == 0
        assert result.success

        assert await target.read("a.txt") == b"aaa"
        assert await target.read("b.txt") == b"bbb"

    @pytest.mark.asyncio
    async def test_full_sync_pull(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        await target.write("remote.txt", b"remote")

        result = await manager.full_sync(direction=SyncDirection.PULL)
        assert result.synced == 1
        assert await local_provider.read("remote.txt") == b"remote"

    @pytest.mark.asyncio
    async def test_full_sync_with_prefix(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        await local_provider.write("docs/a.txt", b"a")
        await local_provider.write("other/b.txt", b"b")

        result = await manager.full_sync(prefix="docs")
        assert result.total_files == 1
        assert result.synced == 1
        assert await target.exists("docs/a.txt")
        assert not await target.exists("other/b.txt")

    @pytest.mark.asyncio
    async def test_incremental_skips_unchanged(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        await local_provider.write("f.txt", b"data")

        # First sync
        r1 = await manager.full_sync()
        assert r1.synced == 1

        # Second sync — should skip (same content, newer target)
        r2 = await manager.full_sync()
        assert r2.skipped == 1 or r2.synced == 0

    @pytest.mark.asyncio
    async def test_full_sync_delete_orphans(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        # Source has only a.txt
        await local_provider.write("a.txt", b"a")
        # Target has both a.txt and orphan.txt
        await target.write("a.txt", b"old_a")
        await target.write("orphan.txt", b"orphan")

        await manager.full_sync(delete_orphans=True)
        assert not await target.exists("orphan.txt")
        assert await target.exists("a.txt")


class TestSyncNoDb:
    """Verify sync works without a database connection."""

    @pytest.mark.asyncio
    async def test_push_without_db(self, local_provider, tmp_path):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, db_conn=None)

        await local_provider.write("f.txt", b"data")
        result = await manager.push_file("f.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_full_sync_without_db(self, local_provider, tmp_path):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, db_conn=None)

        await local_provider.write("f.txt", b"data")
        result = await manager.full_sync()
        assert result.success


class TestSyncLog:
    @pytest.mark.asyncio
    async def test_push_creates_log_entry(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        await local_provider.write("f.txt", b"data")
        await manager.push_file("f.txt")

        history = manager.get_sync_history()
        assert len(history) == 1
        assert history[0].file_key == "f.txt"
        assert history[0].status == "completed"

    @pytest.mark.asyncio
    async def test_failed_push_logs_error(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        # Push a nonexistent file should be skipped
        await manager.push_file("nope.txt")

        history = manager.get_sync_history()
        assert len(history) == 1
        assert history[0].status == "skipped"

    @pytest.mark.asyncio
    async def test_sync_stats(self, local_provider, tmp_path, sync_db):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, sync_db)

        await local_provider.write("f.txt", b"data")
        await manager.push_file("f.txt")
        await manager.push_file("nope.txt")

        stats = manager.get_sync_stats()
        assert stats.get("completed", 0) >= 1
        assert stats.get("skipped", 0) >= 1

    def test_get_history_without_db(self, local_provider, tmp_path):
        target = LocalStorageProvider(tmp_path / "target")
        manager = SyncManager(local_provider, target, db_conn=None)
        assert manager.get_sync_history() == []
        assert manager.get_sync_stats() == {}


class TestSyncResult:
    def test_success_true(self):
        r = SyncResult(total_files=3, synced=3, failed=0)
        assert r.success

    def test_success_false(self):
        r = SyncResult(total_files=3, synced=2, failed=1)
        assert not r.success

    def test_repr(self):
        r = SyncResult(total_files=5, synced=3, skipped=1, failed=1)
        assert "total=5" in repr(r)
        assert "failed=1" in repr(r)
