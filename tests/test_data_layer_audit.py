"""
Regression tests for the Data Layer Audit — RealizeOS V5.

Covers all fixes applied during the audit:
- Database PRAGMAs (busy_timeout, WAL, synchronous)
- Memory pruning and duplicate detection
- FTS5 fallback SQL safety
- KB indexer robustness (encoding, file types, stale entries, file size)
- Conversation pruning and topic_id scoped deletion
- Preference learner cache TTL
- Storage file size limits
"""

import time
from datetime import datetime, timedelta

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    """Set up an isolated memory database."""
    test_db = tmp_path / "test_memory.db"
    monkeypatch.setattr("realize_core.memory.store.DB_PATH", test_db)
    from realize_core.memory.store import init_db

    init_db()

    from realize_core.memory.preference_learner import clear_preference_cache

    clear_preference_cache()

    from realize_core.memory.conversation import clear_all

    clear_all()
    yield test_db


@pytest.fixture
def db_path(tmp_path):
    """Create a temp database with schema."""
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "test_realize.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


@pytest.fixture
def kb_with_mixed_files(tmp_path):
    """Create a KB directory with markdown, yaml, txt, and a large file."""
    sys_dir = tmp_path / "systems" / "v1" / "F-foundations"
    sys_dir.mkdir(parents=True)
    (sys_dir / "identity.md").write_text("# Identity\nWe are a tech company.")
    (sys_dir / "config.yaml").write_text("name: venture1\ntype: b2b")
    (sys_dir / "notes.txt").write_text("Some plain text notes about the venture.")

    # Create a file that exceeds MAX_INDEX_FILE_SIZE (1MB)
    large_dir = tmp_path / "systems" / "v1" / "I-insights"
    large_dir.mkdir(parents=True)
    (large_dir / "huge-file.md").write_text("x" * (1_048_577))  # 1MB + 1 byte

    # Non-UTF-8 file
    encoding_dir = tmp_path / "systems" / "v1" / "B-brain"
    encoding_dir.mkdir(parents=True)
    (encoding_dir / "latin1.md").write_bytes(b"# T\xe9ste\nCaract\xe8res sp\xe9ciaux.")

    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    (shared_dir / "info.md").write_text("# Shared Info\nShared across ventures.")

    return tmp_path


# ---------------------------------------------------------------------------
# Database PRAGMAs
# ---------------------------------------------------------------------------


class TestDatabasePragmas:
    def test_schema_connection_has_busy_timeout(self, db_path):
        from realize_core.db.schema import get_connection

        conn = get_connection(db_path)
        bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert bt == 5000, f"Expected busy_timeout=5000, got {bt}"
        conn.close()

    def test_schema_connection_has_wal_mode(self, db_path):
        from realize_core.db.schema import get_connection

        conn = get_connection(db_path)
        jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert jm == "wal", f"Expected WAL mode, got {jm}"
        conn.close()

    def test_schema_connection_has_synchronous_normal(self, db_path):
        from realize_core.db.schema import get_connection

        conn = get_connection(db_path)
        sync = conn.execute("PRAGMA synchronous").fetchone()[0]
        assert sync == 1, f"Expected synchronous=NORMAL(1), got {sync}"
        conn.close()

    def test_schema_connection_has_foreign_keys(self, db_path):
        from realize_core.db.schema import get_connection

        conn = get_connection(db_path)
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1, "Expected foreign_keys=ON"
        conn.close()

    def test_memory_connection_has_busy_timeout(self, memory_db):
        from realize_core.memory.store import _get_conn

        conn = _get_conn()
        bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert bt == 5000
        conn.close()

    def test_kb_indexer_connection_has_pragmas(self, tmp_path):
        from realize_core.kb.indexer import _get_conn

        db_path = tmp_path / "test_kb.db"
        conn = _get_conn(db_path)
        bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert bt == 5000
        assert jm == "wal"
        conn.close()


# ---------------------------------------------------------------------------
# Memory Pruning and Duplicate Detection
# ---------------------------------------------------------------------------


class TestMemoryPruning:
    def test_prune_removes_old_memories(self, memory_db):
        from realize_core.memory.store import _get_conn, prune_old_memories

        # Insert memories with old timestamps
        conn = _get_conn()
        old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
        for i in range(60):
            conn.execute(
                "INSERT INTO memories (system_key, category, content, tags, created_at) VALUES (?, ?, ?, ?, ?)",
                ("sys-1", "fact", f"Old memory {i}", "[]", old_date),
            )
        conn.commit()
        conn.close()

        deleted = prune_old_memories(retention_days=90, min_per_category=50)
        assert deleted == 10  # 60 total - 50 min = 10 deletable

    def test_prune_keeps_minimum(self, memory_db):
        from realize_core.memory.store import _get_conn, prune_old_memories

        conn = _get_conn()
        old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
        for i in range(30):
            conn.execute(
                "INSERT INTO memories (system_key, category, content, tags, created_at) VALUES (?, ?, ?, ?, ?)",
                ("sys-1", "fact", f"Memory {i}", "[]", old_date),
            )
        conn.commit()
        conn.close()

        deleted = prune_old_memories(retention_days=90, min_per_category=50)
        assert deleted == 0  # Only 30 total, less than min_per_category

    def test_duplicate_detection_skips_similar(self, memory_db):
        from realize_core.memory.store import _get_conn, store_memory

        store_memory("sys-1", "fact", "The sky is blue and beautiful")
        store_memory("sys-1", "fact", "The sky is blue and beautiful today")  # Very similar

        conn = _get_conn()
        count = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        conn.close()
        assert count == 1  # Second one skipped as near-duplicate

    def test_different_content_not_skipped(self, memory_db):
        from realize_core.memory.store import _get_conn, store_memory

        store_memory("sys-1", "fact", "The sky is blue")
        store_memory("sys-1", "fact", "Python is a programming language")

        conn = _get_conn()
        count = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        conn.close()
        assert count == 2  # Different content, both stored


# ---------------------------------------------------------------------------
# FTS5 Safety
# ---------------------------------------------------------------------------


class TestFTS5SafeSearch:
    def test_fts_fallback_escapes_special_chars(self, kb_with_mixed_files):
        """LIKE query with special chars should not cause SQL injection."""
        from realize_core.kb.indexer import index_kb_files, semantic_search

        db_path = kb_with_mixed_files / "test_index.db"
        index_kb_files(kb_root=str(kb_with_mixed_files), db_path=db_path, force=True)

        # These queries contain characters that could be exploited in LIKE
        dangerous_queries = [
            "test%' OR '1'='1",
            "test_underscore",
            "test\\backslash",
            "100% complete",
        ]
        for query in dangerous_queries:
            # Should not raise, should return empty or safe results
            results = semantic_search(query, db_path=db_path, kb_root=str(kb_with_mixed_files))
            assert isinstance(results, list)


# ---------------------------------------------------------------------------
# KB Indexer Robustness
# ---------------------------------------------------------------------------


class TestKBIndexerRobustness:
    def test_indexes_yaml_files(self, kb_with_mixed_files):
        from realize_core.kb.indexer import _get_conn, index_kb_files

        db_path = kb_with_mixed_files / "test_index.db"
        count = index_kb_files(kb_root=str(kb_with_mixed_files), db_path=db_path, force=True)
        assert count > 0

        conn = _get_conn(db_path)
        yaml_rows = conn.execute("SELECT * FROM kb_files WHERE path LIKE '%.yaml'").fetchall()
        conn.close()
        assert len(yaml_rows) > 0, "YAML files should be indexed"

    def test_indexes_txt_files(self, kb_with_mixed_files):
        from realize_core.kb.indexer import _get_conn, index_kb_files

        db_path = kb_with_mixed_files / "test_index.db"
        index_kb_files(kb_root=str(kb_with_mixed_files), db_path=db_path, force=True)

        conn = _get_conn(db_path)
        txt_rows = conn.execute("SELECT * FROM kb_files WHERE path LIKE '%.txt'").fetchall()
        conn.close()
        assert len(txt_rows) > 0, "TXT files should be indexed"

    def test_skips_large_files(self, kb_with_mixed_files):
        from realize_core.kb.indexer import _get_conn, index_kb_files

        db_path = kb_with_mixed_files / "test_index.db"
        index_kb_files(kb_root=str(kb_with_mixed_files), db_path=db_path, force=True)

        conn = _get_conn(db_path)
        huge = conn.execute("SELECT * FROM kb_files WHERE path LIKE '%huge%'").fetchall()
        conn.close()
        assert len(huge) == 0, "Files > 1MB should be skipped"

    def test_handles_encoding_errors(self, kb_with_mixed_files):
        from realize_core.kb.indexer import _get_conn, index_kb_files

        db_path = kb_with_mixed_files / "test_index.db"
        count = index_kb_files(kb_root=str(kb_with_mixed_files), db_path=db_path, force=True)
        # Should not crash on Latin-1 encoded file
        assert count > 0

        conn = _get_conn(db_path)
        latin = conn.execute("SELECT * FROM kb_files WHERE path LIKE '%latin1%'").fetchall()
        conn.close()
        assert len(latin) > 0, "Files with encoding errors should still be indexed with replacement chars"

    def test_cleans_stale_entries(self, kb_with_mixed_files):
        from realize_core.kb.indexer import _get_conn, index_kb_files

        db_path = kb_with_mixed_files / "test_index.db"
        index_kb_files(kb_root=str(kb_with_mixed_files), db_path=db_path, force=True)

        # Delete a file from disk
        identity_file = kb_with_mixed_files / "systems" / "v1" / "F-foundations" / "identity.md"
        identity_file.unlink()

        # Re-index should clean up the stale entry
        index_kb_files(kb_root=str(kb_with_mixed_files), db_path=db_path, force=False)

        conn = _get_conn(db_path)
        identity_rows = conn.execute("SELECT * FROM kb_files WHERE path LIKE '%identity.md'").fetchall()
        conn.close()
        assert len(identity_rows) == 0, "Stale entries should be cleaned up"

    def test_fts_update_trigger_exists(self, tmp_path):
        """KB indexer DB should have the FTS UPDATE trigger."""
        from realize_core.kb.indexer import _get_conn, _init_index_db

        db_path = tmp_path / "test.db"
        _init_index_db(db_path)
        conn = _get_conn(db_path)
        triggers = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
        trigger_names = {r["name"] for r in triggers}
        conn.close()
        assert "kb_au" in trigger_names, "FTS UPDATE trigger should exist"


# ---------------------------------------------------------------------------
# Conversation Pruning
# ---------------------------------------------------------------------------


class TestConversationPruning:
    def test_clear_history_scoped_to_topic(self, memory_db):
        from realize_core.memory.conversation import add_message, clear_history, get_history

        add_message("bot-1", "user-1", "user", "Hello topic A", topic_id="topic-a")
        add_message("bot-1", "user-1", "user", "Hello topic B", topic_id="topic-b")

        clear_history("bot-1", "user-1", topic_id="topic-a")

        # Topic A should be cleared
        assert len(get_history("bot-1", "user-1", topic_id="topic-a")) == 0
        # Topic B should still exist
        assert len(get_history("bot-1", "user-1", topic_id="topic-b")) == 1


# ---------------------------------------------------------------------------
# Preference Cache TTL
# ---------------------------------------------------------------------------


class TestPreferenceCacheExpiry:
    def test_cache_expires_after_ttl(self, memory_db, monkeypatch):
        from realize_core.memory.preference_learner import _preference_cache, analyze_preferences

        # Manually seed the cache with an old entry
        _preference_cache["sys-1:dashboard-user"] = (
            time.time() - 7200,  # 2 hours ago
            {"response_style": "old_value"},
        )

        # Less than 3 history entries → will return empty, but the important
        # thing is it doesn't return the stale cached value
        result = analyze_preferences("sys-1", "dashboard-user")
        assert result.get("response_style") != "old_value"


# ---------------------------------------------------------------------------
# Storage File Size Limits
# ---------------------------------------------------------------------------


class TestStorageSizeLimits:
    @pytest.mark.asyncio
    async def test_local_storage_rejects_oversized_file(self, tmp_path):
        from realize_core.storage.local import MAX_FILE_SIZE, LocalStorageProvider

        provider = LocalStorageProvider(root_dir=tmp_path / "storage")
        oversized = b"x" * (MAX_FILE_SIZE + 1)

        with pytest.raises(ValueError, match="exceeds limit"):
            await provider.write("test/big-file.bin", oversized)

    @pytest.mark.asyncio
    async def test_local_storage_accepts_normal_file(self, tmp_path):
        from realize_core.storage.local import LocalStorageProvider

        provider = LocalStorageProvider(root_dir=tmp_path / "storage")
        data = b"normal file content"

        result = await provider.write("test/normal.txt", data)
        assert result.key == "test/normal.txt"


# ---------------------------------------------------------------------------
# Memory FTS UPDATE Trigger
# ---------------------------------------------------------------------------


class TestMemoryFTSTrigger:
    def test_fts_update_trigger_exists(self, memory_db):
        from realize_core.memory.store import _get_conn

        conn = _get_conn()
        triggers = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
        trigger_names = {r["name"] for r in triggers}
        conn.close()
        assert "memories_au" in trigger_names, "FTS UPDATE trigger for memories should exist"
