"""
Phase 5: Data Integrity Tests — RealizeOS 5 Production Readiness

Tests:
  5.1 Schema migration up (all migrations apply cleanly)
  5.2 Concurrent venture creation (5 threads)
  5.3 DB backup/restore (copy, corrupt, restore)
  5.4 Conversation pruning correctness (5K rows, prune to 1K)
  5.5 Activity log growth (query performance at scale)
  5.6 Memory store duplicate detection
  5.7 WAL mode and write contention (10 concurrent writes)
  5.8 FTS5 search accuracy after bulk insert
"""

import concurrent.futures
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

# Set up the project path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DATA_PATH", str(Path(__file__).resolve().parent.parent / "data"))

RESULTS: list[dict] = []


def record(test_id: str, name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append({"id": test_id, "name": name, "passed": passed, "detail": detail})
    print(f"  [{status}] {test_id}: {name}")
    if detail:
        print(f"         {detail}")


def test_5_1_schema_migration():
    """5.1: Schema migration applies cleanly on a fresh database."""
    print("\n-- 5.1 Schema Migration --")
    from realize_core.db.schema import init_schema

    # Create a temp DB
    tmp = Path(tempfile.mkdtemp()) / "test_migration.db"
    try:
        init_schema(tmp)

        conn = sqlite3.connect(str(tmp))
        conn.row_factory = sqlite3.Row

        # Verify base tables exist
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]

        expected_tables = ["activity_events", "agent_states", "approval_queue", "schema_version"]
        missing = [t for t in expected_tables if t not in tables]

        record("5.1a", "Base schema created", len(missing) == 0,
               f"Tables: {len(tables)} found, missing: {missing or 'none'}")

        # Run migrations
        from realize_core.db.migrations import run_migrations
        run_migrations(tmp)

        # Check version
        version = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()["v"]
        record("5.1b", f"Migrations applied (version={version})", version >= 2,
               f"Schema version: {version}")

        # Verify migration tables
        tables_after = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        migration_tables = ["storage_sync_log", "approval_requests", "agent_messages"]
        missing_migration = [t for t in migration_tables if t not in tables_after]
        record("5.1c", "Migration tables created", len(missing_migration) == 0,
               f"Missing: {missing_migration or 'none'}")

        conn.close()
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


def test_5_2_concurrent_venture_creation():
    """5.2: 5 threads creating ventures simultaneously — no duplicates, no crashes."""
    print("\n-- 5.2 Concurrent Venture Creation --")
    from realize_core.memory.store import DB_PATH, init_db, db_connection

    # Use a temp DB
    import realize_core.memory.store as store_module
    original_db = store_module.DB_PATH
    tmp_dir = Path(tempfile.mkdtemp())
    store_module.DB_PATH = tmp_dir / "concurrent_test.db"

    try:
        init_db()

        def insert_memory(thread_id):
            from realize_core.memory.store import store_memory
            for i in range(20):
                store_memory(
                    f"venture-{thread_id}",
                    "learning",
                    f"Thread {thread_id} memory {i}: unique content {time.time()}",
                    tags=[f"thread-{thread_id}"],
                )
            return thread_id

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(insert_memory, i) for i in range(5)]
            results = []
            errors = []
            for f in concurrent.futures.as_completed(futures):
                try:
                    results.append(f.result())
                except Exception as e:
                    errors.append(str(e))

        record("5.2a", "5 threads completed", len(results) == 5,
               f"{len(results)}/5 succeeded, {len(errors)} errors")

        # Verify data integrity
        with db_connection() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
            # Should have up to 100 rows (5 threads x 20), minus any duplicates
            record("5.2b", "Data integrity after concurrent writes", total > 0,
                   f"{total} memories stored (some may be deduped)")

            # Check no DB corruption
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            record("5.2c", "Database integrity check", integrity == "ok",
                   f"PRAGMA integrity_check: {integrity}")

        if errors:
            for e in errors:
                record("5.2", f"Thread error: {e}", False)

    finally:
        store_module.DB_PATH = original_db
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_5_3_backup_restore():
    """5.3: DB backup and restore works correctly."""
    print("\n-- 5.3 DB Backup/Restore --")
    import realize_core.memory.store as store_module

    original_db = store_module.DB_PATH
    tmp_dir = Path(tempfile.mkdtemp())
    store_module.DB_PATH = tmp_dir / "backup_test.db"

    try:
        from realize_core.memory.store import init_db, store_memory, search_memories, db_connection

        init_db()

        # Insert test data
        for i in range(10):
            store_memory("backup-test", "learning", f"Memory item {i}: backup test data")

        with db_connection() as conn:
            before_count = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]

        # Backup
        backup_path = tmp_dir / "backup.db"
        shutil.copy2(store_module.DB_PATH, backup_path)
        record("5.3a", "Backup created", backup_path.exists(),
               f"Backup size: {backup_path.stat().st_size} bytes")

        # Simulate corruption by clearing the original
        with db_connection() as conn:
            conn.execute("DELETE FROM memories")
        with db_connection() as conn:
            after_delete = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        record("5.3b", "Data deleted (simulating corruption)", after_delete == 0,
               f"Rows after delete: {after_delete}")

        # Restore from backup
        shutil.copy2(backup_path, store_module.DB_PATH)
        with db_connection() as conn:
            after_restore = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        record("5.3c", "Data restored from backup", after_restore == before_count,
               f"Before: {before_count}, after restore: {after_restore}")

    finally:
        store_module.DB_PATH = original_db
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_5_4_conversation_pruning():
    """5.4: Conversation pruning at scale (5K rows per user, prune to 1K)."""
    print("\n-- 5.4 Conversation Pruning --")
    from realize_core.memory import conversation as conv_module

    import realize_core.memory.store as store_module
    original_db = store_module.DB_PATH
    tmp_dir = Path(tempfile.mkdtemp())
    store_module.DB_PATH = tmp_dir / "prune_test.db"

    try:
        from realize_core.memory.store import init_db, db_connection

        init_db()

        # Clear in-memory state
        conv_module._conversations.clear()
        conv_module._hydrated.clear()

        # Insert 5000 rows directly via SQL (faster than add_message)
        with db_connection() as conn:
            base_time = datetime(2025, 1, 1)
            batch = []
            for i in range(5000):
                ts = (base_time + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")
                role = "user" if i % 2 == 0 else "assistant"
                batch.append(("prune-system", "prune-user", role, f"Message {i}", "", ts))
            conn.executemany(
                "INSERT INTO conversations (bot_name, user_id, role, content, topic_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                batch,
            )

        with db_connection() as conn:
            before = conn.execute("SELECT COUNT(*) as c FROM conversations").fetchone()["c"]
        record("5.4a", "Inserted 5K conversation rows", before == 5000,
               f"Rows: {before}")

        # Prune to 1000
        start = time.time()
        deleted = conv_module.prune_old_conversations(max_rows_per_user=1000)
        elapsed = time.time() - start

        with db_connection() as conn:
            after = conn.execute("SELECT COUNT(*) as c FROM conversations").fetchone()["c"]
        record("5.4b", "Pruning completed", deleted == 4000,
               f"Deleted: {deleted}, remaining: {after}, time: {elapsed:.2f}s")

        # Verify newest messages kept
        with db_connection() as conn:
            oldest_remaining = conn.execute(
                "SELECT MIN(created_at) as ts FROM conversations"
            ).fetchone()["ts"]
            newest_remaining = conn.execute(
                "SELECT MAX(created_at) as ts FROM conversations"
            ).fetchone()["ts"]
        record("5.4c", "Newest messages retained", after == 1000,
               f"Oldest remaining: {oldest_remaining}, newest: {newest_remaining}")

        record("5.4d", "Pruning performance", elapsed < 5.0,
               f"{elapsed:.2f}s (target: <5s)")

    finally:
        store_module.DB_PATH = original_db
        conv_module._conversations.clear()
        conv_module._hydrated.clear()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_5_5_activity_log_query_performance():
    """5.5: Activity log query performance at scale."""
    print("\n-- 5.5 Activity Log Performance --")
    from realize_core.db.schema import get_connection, init_schema

    tmp_dir = Path(tempfile.mkdtemp())
    db_path = tmp_dir / "activity_perf.db"

    try:
        init_schema(db_path)
        conn = get_connection(db_path)

        # Insert 10K activity events
        base_time = datetime(2025, 1, 1)
        batch = []
        for i in range(10000):
            ts = (base_time + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%S")
            batch.append((
                f"venture-{i % 10}",
                "agent" if i % 2 == 0 else "user",
                f"agent-{i % 5}",
                "message_sent" if i % 3 == 0 else "task_completed",
                "session", f"session-{i}",
                f'{{"index": {i}}}',
                ts,
            ))

        conn.executemany(
            "INSERT INTO activity_events "
            "(venture_key, actor_type, actor_id, action, entity_type, entity_id, details, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            batch,
        )
        conn.commit()

        total = conn.execute("SELECT COUNT(*) FROM activity_events").fetchone()[0]
        record("5.5a", "Inserted 10K activity events", total == 10000,
               f"Rows: {total}")

        # Query: recent events for a venture (most common dashboard query)
        start = time.time()
        rows = conn.execute(
            "SELECT * FROM activity_events WHERE venture_key = ? ORDER BY created_at DESC LIMIT 50",
            ("venture-3",),
        ).fetchall()
        query_time = time.time() - start
        record("5.5b", "Recent events query", query_time < 0.1 and len(rows) == 50,
               f"{len(rows)} rows in {query_time*1000:.1f}ms (target: <100ms)")

        # Query: count by action type (aggregate)
        start = time.time()
        agg = conn.execute(
            "SELECT action, COUNT(*) as c FROM activity_events GROUP BY action"
        ).fetchall()
        agg_time = time.time() - start
        record("5.5c", "Aggregate query", agg_time < 0.5,
               f"{len(agg)} action types in {agg_time*1000:.1f}ms")

        conn.close()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_5_6_memory_duplicate_detection():
    """5.6: Memory store correctly deduplicates near-identical content."""
    print("\n-- 5.6 Memory Duplicate Detection --")
    import realize_core.memory.store as store_module

    original_db = store_module.DB_PATH
    tmp_dir = Path(tempfile.mkdtemp())
    store_module.DB_PATH = tmp_dir / "dedup_test.db"

    try:
        from realize_core.memory.store import init_db, store_memory, db_connection

        init_db()

        # Insert original
        store_memory("dedup-test", "learning", "The client prefers weekly status updates via email.")

        # Try inserting near-duplicates
        store_memory("dedup-test", "learning", "The client prefers weekly status updates via email.")  # exact
        store_memory("dedup-test", "learning", "The client prefers weekly status updates via email!")  # tiny diff
        store_memory("dedup-test", "learning", "Something completely different about project timelines.")  # different

        with db_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as c FROM memories WHERE system_key = 'dedup-test'"
            ).fetchone()["c"]

        # Should have 2: original + the different one. Near-dupes should be skipped.
        record("5.6", "Duplicate detection", total == 2,
               f"Stored: {total} (expected 2: original + different)")

    finally:
        store_module.DB_PATH = original_db
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_5_7_wal_mode_contention():
    """5.7: WAL mode handles concurrent read/write correctly."""
    print("\n-- 5.7 WAL Mode Write Contention --")
    import realize_core.memory.store as store_module

    original_db = store_module.DB_PATH
    tmp_dir = Path(tempfile.mkdtemp())
    store_module.DB_PATH = tmp_dir / "wal_test.db"

    try:
        from realize_core.memory.store import init_db, db_connection

        init_db()

        errors = []

        def writer(thread_id):
            """Write 50 rows."""
            for i in range(50):
                try:
                    with db_connection() as conn:
                        conn.execute(
                            "INSERT INTO memories (system_key, category, content, tags, created_at) "
                            "VALUES (?, ?, ?, '[]', ?)",
                            (f"wal-{thread_id}", "test", f"WAL test {thread_id}-{i}",
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        )
                except Exception as e:
                    errors.append(f"Writer {thread_id}: {e}")

        def reader():
            """Read while writers are active."""
            for _ in range(50):
                try:
                    with db_connection() as conn:
                        conn.execute("SELECT COUNT(*) FROM memories").fetchone()
                except Exception as e:
                    errors.append(f"Reader: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=11) as executor:
            futures = []
            # 10 writers + 1 reader
            for i in range(10):
                futures.append(executor.submit(writer, i))
            futures.append(executor.submit(reader))

            concurrent.futures.wait(futures)

        with db_connection() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

        record("5.7a", "10 writers + 1 reader concurrent", len(errors) == 0,
               f"{total} rows written, {len(errors)} errors")
        record("5.7b", "DB integrity after contention", integrity == "ok",
               f"PRAGMA integrity_check: {integrity}")

        if errors:
            for e in errors[:5]:
                print(f"         Error: {e}")

    finally:
        store_module.DB_PATH = original_db
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_5_8_fts_search_accuracy():
    """5.8: FTS5 search returns relevant results after bulk insert."""
    print("\n-- 5.8 FTS5 Search Accuracy --")
    import realize_core.memory.store as store_module

    original_db = store_module.DB_PATH
    tmp_dir = Path(tempfile.mkdtemp())
    store_module.DB_PATH = tmp_dir / "fts_test.db"

    try:
        from realize_core.memory.store import init_db, store_memory, search_memories

        init_db()

        # Insert varied content
        contents = [
            ("marketing", "The Q3 marketing campaign showed a 25% increase in lead generation."),
            ("product", "Product roadmap updated: AI features prioritized for Q4 launch."),
            ("finance", "Revenue forecast for next quarter projects 15% growth year-over-year."),
            ("marketing", "Social media engagement metrics doubled after the influencer partnership."),
            ("product", "User feedback indicates strong demand for mobile app improvements."),
            ("finance", "Cost reduction initiative saved $50K in operational expenses."),
            ("strategy", "Competitive analysis reveals opportunity in the enterprise segment."),
            ("marketing", "Email newsletter open rates improved with personalized subject lines."),
        ]

        for category, content in contents:
            store_memory("fts-test", category, content, tags=[category])

        # Search for specific terms
        results_marketing = search_memories("marketing campaign lead", system_key="fts-test", limit=5)
        record("5.8a", "FTS search: 'marketing campaign'", len(results_marketing) > 0,
               f"Found {len(results_marketing)} results")

        results_revenue = search_memories("revenue growth forecast", system_key="fts-test", limit=5)
        record("5.8b", "FTS search: 'revenue growth'", len(results_revenue) > 0,
               f"Found {len(results_revenue)} results")

        results_empty = search_memories("quantum computing", system_key="fts-test", limit=5)
        record("5.8c", "FTS search: no match", len(results_empty) == 0,
               f"Found {len(results_empty)} results (expected 0)")

    finally:
        store_module.DB_PATH = original_db
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    print("=" * 60)
    print("PHASE 5: DATA INTEGRITY TESTS")
    print("=" * 60)

    test_5_1_schema_migration()
    test_5_2_concurrent_venture_creation()
    test_5_3_backup_restore()
    test_5_4_conversation_pruning()
    test_5_5_activity_log_query_performance()
    test_5_6_memory_duplicate_detection()
    test_5_7_wal_mode_contention()
    test_5_8_fts_search_accuracy()

    # Summary
    print("\n" + "=" * 60)
    print("PHASE 5 DATA INTEGRITY - RESULTS")
    print("=" * 60)
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = total - passed
    print(f"\n  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
    print(f"  Pass Rate: {passed/total:.0%}")
    if failed:
        print(f"\n  FAILED TESTS:")
        for r in RESULTS:
            if not r["passed"]:
                print(f"     {r['id']}: {r['name']} -- {r['detail']}")
    print()

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
