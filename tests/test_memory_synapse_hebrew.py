"""Memory and Synapse search share the KB's multilingual FTS: Hebrew, prefixes, safe queries, migration.

Also: the ``/api/kb/reindex`` alias, the Hebrew-aware token estimate, and the
KB lookup for short questions.
"""

from __future__ import annotations

import logging
import sqlite3
import textwrap

import pytest
from fastapi.testclient import TestClient
from realize_core.utils import fts

SYNTAX_QUERIES = ["budget (draft", '"unbalanced', "a AND", "NOT", "תקציב*", "x:y", "-", "NEAR(a b)", "OR OR", "'; DROP"]
TOKENIZERS = [fts.TRIGRAM_TOKENIZE, fts.PLAIN_TRIGRAM_TOKENIZE, fts.FALLBACK_TOKENIZE]


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@pytest.fixture(params=TOKENIZERS)
def memory(request, tmp_path, monkeypatch):
    from realize_core.memory import store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(store, "fts_tokenizer", lambda: request.param)
    store.init_db()
    store.store_memory("tower-b", "decision", "אישרנו את התקציב לשלב ב: נשארו 1.2 מיליון נטו")
    store.store_memory("tower-b", "learning", "הקבלן איחר באספקת הפלדה בשבועיים")
    store.store_memory("other", "decision", "התקציב של הקרן אושר בישיבת ההנהלה")
    store.store_memory("tower-b", "decision", "Phase B budget approved, 1.2M net remaining")
    store.store_memory("tower-b", "preference", "תקציב שנתי נבדק מדי רבעון")
    return store


class TestMemorySearch:
    def test_hebrew_question_finds_the_memory(self, memory):
        rows = memory.search_memories("כמה נשאר לנו נטו בתקציב?", system_key="tower-b")
        assert any("נשארו 1.2 מיליון" in r["content"] for r in rows)

    def test_prefixed_word_finds_the_bare_word(self, memory):
        rows = memory.search_memories("ובתקציב", system_key="tower-b")
        assert any("תקציב שנתי" in r["content"] for r in rows)

    def test_english_still_works(self, memory):
        rows = memory.search_memories("what budget was approved?", system_key="tower-b")
        assert any("Phase B budget" in r["content"] for r in rows)

    def test_best_match_comes_first(self, memory):
        rows = memory.search_memories("הקבלן איחר באספקת הפלדה", system_key="tower-b")
        assert "הקבלן" in rows[0]["content"]

    @pytest.mark.parametrize("query", [*SYNTAX_QUERIES, "", "   ", "מה"])
    def test_any_text_returns_a_list(self, memory, query):
        assert isinstance(memory.search_memories(query), list)

    def test_no_searchable_word_returns_nothing(self, memory):
        assert memory.search_memories("מה") == []

    def test_venture_scope_holds_with_hebrew_queries(self, memory):
        everyone = {r["system_key"] for r in memory.search_memories("התקציב")}
        assert everyone == {"tower-b", "other"}  # the unscoped search sees both
        assert {r["system_key"] for r in memory.search_memories("התקציב", system_key="other")} == {"other"}
        assert {r["system_key"] for r in memory.search_memories("התקציב", system_keys=["tower-b"])} == {"tower-b"}
        assert memory.search_memories("התקציב", system_keys=[]) == []
        assert memory.search_memories("התקציב", system_keys=["nobody"]) == []

    @pytest.mark.parametrize("query", SYNTAX_QUERIES)
    def test_syntax_never_leaks_across_ventures(self, memory, query):
        rows = memory.search_memories(query + " התקציב", system_keys=["tower-b"])
        assert {r["system_key"] for r in rows} <= {"tower-b"}

    def test_limit_counts_only_visible_rows(self, memory):
        rows = memory.search_memories("התקציב", system_keys=["tower-b"], limit=1)
        assert [r["system_key"] for r in rows] == ["tower-b"]

    def test_new_memories_are_searchable_after_init(self, memory):
        memory.store_memory("tower-b", "feedback", "הלקוח ביקש שינוי בלוח הזמנים")
        assert memory.search_memories("לוח הזמנים", system_key="tower-b")


class TestMemoryMigration:
    def _legacy_db(self, path):
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT, system_key TEXT NOT NULL, category TEXT NOT NULL,
                content TEXT NOT NULL, tags TEXT DEFAULT '[]', created_at TEXT NOT NULL);
            CREATE VIRTUAL TABLE memories_fts USING fts5(
                content, system_key, category, content='memories', content_rowid='id');
            CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, system_key, category)
                VALUES (new.id, new.content, new.system_key, new.category);
            END;
            """
        )
        conn.execute(
            "INSERT INTO memories (system_key, category, content, created_at) VALUES (?, ?, ?, ?)",
            ("tower-b", "decision", "אישרנו את התקציב לשלב ב", "2026-01-01 00:00:00"),
        )
        conn.commit()
        conn.close()

    def test_unicode61_table_is_rebuilt_with_its_rows(self, tmp_path, monkeypatch):
        from realize_core.memory import store

        db = tmp_path / "memory.db"
        self._legacy_db(db)
        monkeypatch.setattr(store, "DB_PATH", db)
        conn = sqlite3.connect(db)
        assert fts.table_tokenizer(conn, "memories_fts") == "unicode61"
        conn.close()
        store.init_db()
        conn = sqlite3.connect(db)
        assert fts.table_tokenizer(conn, "memories_fts") == fts.fts_tokenizer()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == store.MEMORY_SCHEMA_VERSION
        conn.close()
        # "בתקציב" (in the budget) finds "התקציב"'s stem: only the new tokenizer matches substrings.
        assert [r["content"] for r in store.search_memories("בתקציב")] == ["אישרנו את התקציב לשלב ב"]

    def test_init_is_idempotent_and_keeps_inserting(self, tmp_path, monkeypatch):
        from realize_core.memory import store

        db = tmp_path / "memory.db"
        self._legacy_db(db)
        monkeypatch.setattr(store, "DB_PATH", db)
        store.init_db()
        store.init_db()
        store.store_memory("tower-b", "decision", "אושר הסכם עם הספק החדש")
        assert len(store.search_memories("הסכם הספק")) == 1
        assert len(store.search_memories("התקציב")) == 1

    def test_second_open_does_not_rebuild(self, tmp_path, monkeypatch, caplog):
        from realize_core.memory import store

        monkeypatch.setattr(store, "DB_PATH", tmp_path / "memory.db")
        store.init_db()
        with caplog.at_level(logging.INFO, logger=store.logger.name):
            store.init_db()
        assert "FTS rebuilt" not in caplog.text


# ---------------------------------------------------------------------------
# Synapse
# ---------------------------------------------------------------------------


def _entity(id_, title, body, venture="tower-b", type_="decision"):
    from realize_core.fabric.entity import FabricEntity

    return FabricEntity(id=id_, slug=id_, title=title, body=body, venture=venture, type=type_)


@pytest.fixture(params=TOKENIZERS)
def synapse(request, tmp_path, monkeypatch):
    from realize_core.fabric import synapse_db

    monkeypatch.setattr(synapse_db, "fts_tokenizer", lambda: request.param)
    db = synapse_db.SynapseDB(tmp_path / "synapse.db")
    db.upsert_entity(_entity("d1", "החלטת תקציב", "אישרנו את התקציב לשלב ב, נשארו 1.2 מיליון"))
    db.upsert_entity(_entity("d2", "ספק הפלדה", "הקבלן איחר באספקה בשבועיים", type_="learning"))
    db.upsert_entity(_entity("d3", "תקציב הקרן", "אושר בישיבת ההנהלה", venture="other"))
    db.upsert_entity(_entity("d4", "Budget", "Phase B budget approved"))
    yield db
    db.close()


class TestSynapseSearch:
    def test_hebrew_question_finds_the_entity(self, synapse):
        rows = synapse.fts_search("כמה נשאר לנו בתקציב?", scope="tower-b")
        assert rows[0]["id"] == "d1"

    def test_body_text_is_searchable(self, synapse):
        assert [r["id"] for r in synapse.fts_search("באספקה")] == ["d2"]

    def test_filters(self, synapse):
        assert {r["id"] for r in synapse.fts_search("התקציב")} == {"d1", "d3"}
        assert {r["id"] for r in synapse.fts_search("התקציב", scope="other")} == {"d3"}
        assert {r["id"] for r in synapse.fts_search("תקציב", scope="tower-b", entity_type="learning")} == set()
        assert [r["id"] for r in synapse.fts_search("הקבלן", entity_type="learning")] == ["d2"]

    def test_english(self, synapse):
        assert [r["id"] for r in synapse.fts_search("budget approved")] == ["d4"]

    @pytest.mark.parametrize("query", [*SYNTAX_QUERIES, "", "מה"])
    def test_any_text_returns_a_list(self, synapse, query):
        assert isinstance(synapse.fts_search(query), list)

    def test_replaced_entity_is_not_duplicated(self, synapse):
        synapse.upsert_entity(_entity("d2", "ספק הפלדה", "הקבלן עמד בלוח הזמנים", type_="learning"))
        assert synapse.fts_search("באספקה") == []
        assert [r["id"] for r in synapse.fts_search("הקבלן")] == ["d2"]


class TestSynapseMigration:
    def _legacy_db(self, path):
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE entities (
                id TEXT PRIMARY KEY, type TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
                slug TEXT NOT NULL DEFAULT '', venture TEXT NOT NULL DEFAULT '', path TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '', layer TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual', created_by TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 1.0, verified INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT NOT NULL DEFAULT '', last_updated TEXT NOT NULL DEFAULT '',
                refs_json TEXT NOT NULL DEFAULT '[]', tags_json TEXT NOT NULL DEFAULT '[]',
                frontmatter_json TEXT NOT NULL DEFAULT '{}');
            CREATE VIRTUAL TABLE entities_fts USING fts5(
                id, title, summary, body, venture, type, tokenize='porter unicode61');
            """
        )
        conn.execute(
            "INSERT INTO entities (id, type, title, venture, summary) VALUES ('d1', 'decision', ?, 'tower-b', ?)",
            ("החלטת תקציב", "אישרנו"),
        )
        conn.execute(
            "INSERT INTO entities_fts (id, title, summary, body, venture, type) VALUES (?, ?, ?, ?, ?, ?)",
            ("d1", "החלטת תקציב", "אישרנו", "אישרנו את התקציב לשלב ב עם הקבלן הראשי", "tower-b", "decision"),
        )
        conn.commit()
        conn.close()

    def test_porter_table_becomes_the_current_tokenizer_and_keeps_its_bodies(self, tmp_path):
        from realize_core.fabric.synapse_db import SYNAPSE_SCHEMA_VERSION, SynapseDB

        db_path = tmp_path / "synapse.db"
        self._legacy_db(db_path)
        db = SynapseDB(db_path)
        try:
            conn = sqlite3.connect(db_path)
            assert fts.table_tokenizer(conn, "entities_fts") == fts.fts_tokenizer()
            assert conn.execute("PRAGMA user_version").fetchone()[0] == SYNAPSE_SCHEMA_VERSION
            conn.close()
            # Found through the body text, which only the old FTS table held.
            assert [r["id"] for r in db.fts_search("בקבלן", scope="tower-b")] == ["d1"]
            db.upsert_entity(_entity("d2", "ספק", "אספקת הפלדה"))
            assert [r["id"] for r in db.fts_search("הפלדה")] == ["d2"]
        finally:
            db.close()

    def test_unreadable_fts_is_rebuilt_from_entities(self, tmp_path):
        from realize_core.fabric import synapse_db

        db_path = tmp_path / "synapse.db"
        self._legacy_db(db_path)

        class Flaky(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql.startswith("SELECT id, title, summary, body"):
                    raise sqlite3.DatabaseError("malformed")
                return super().execute(sql, *args)

        conn = sqlite3.connect(db_path, factory=Flaky)
        conn.row_factory = sqlite3.Row
        synapse_db._ensure_entities_fts(conn)
        assert fts.table_tokenizer(conn, "entities_fts") == fts.fts_tokenizer()
        assert conn.execute("SELECT id FROM entities_fts WHERE entities_fts MATCH 'אישרנו'").fetchall()
        conn.close()

    def test_reopening_does_not_rebuild(self, tmp_path, caplog):
        from realize_core.fabric import synapse_db

        db_path = tmp_path / "synapse.db"
        synapse_db.SynapseDB(db_path).close()
        with caplog.at_level(logging.INFO, logger=synapse_db.logger.name):
            synapse_db.SynapseDB(db_path).close()
        assert "FTS rebuilt" not in caplog.text


# ---------------------------------------------------------------------------
# /api/kb/reindex
# ---------------------------------------------------------------------------

API_KEY = "test-api-key-1234567890abcdef"
USERS_YAML = textwrap.dedent(
    """
    users:
      - email: dana@acme.io
        role: operator
        ventures: [acme]
        password_hash: "$2b$12$dana"
      - email: viewer@acme.io
        role: viewer
        password_hash: "$2b$12$viewer"
    """
)


def _app():
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = {"acme": {"name": "Acme", "agents": {}}}
    app.state.config = {"features": {}}
    return app


@pytest.fixture
def indexed(monkeypatch):
    """index_kb_files replaced by a recorder (no real indexing)."""
    from realize_core.kb import indexer

    calls: list[dict] = []

    def fake(kb_path, force=False, systems_config=None):
        calls.append({"force": force, "systems": systems_config})
        return 7

    monkeypatch.setattr(indexer, "index_kb_files", fake)
    return calls


class TestKbReindexRoute:
    def test_route_exists_and_requires_auth(self, monkeypatch, indexed):
        monkeypatch.setenv("REALIZE_API_KEY", API_KEY)
        monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
        client = TestClient(_app())
        assert client.post("/api/kb/reindex").status_code == 401
        assert client.post("/api/settings/reindex").status_code == 401
        assert indexed == []

    def test_with_the_key_it_reindexes_like_settings_reindex(self, monkeypatch, indexed):
        monkeypatch.setenv("REALIZE_API_KEY", API_KEY)
        monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
        client = TestClient(_app())
        headers = {"X-API-Key": API_KEY}
        alias = client.post("/api/kb/reindex", headers=headers, json={"venture_key": "acme"})
        original = client.post("/api/settings/reindex", headers=headers)
        assert alias.status_code == original.status_code == 200
        assert alias.json() == original.json()
        assert alias.json()["files_indexed"] == 7
        assert alias.json()["message"] == "Reindexed 7 documents."
        assert [c["force"] for c in indexed] == [True, True]

    def test_cli_path_matches_the_route(self):
        import inspect

        from realize_core.cli_app.commands import kb

        assert '"/api/kb/reindex"' in inspect.getsource(kb.kb_reindex)

    @pytest.mark.parametrize(("user", "role"), [("dana@acme.io", "operator"), ("viewer@acme.io", "viewer")])
    def test_same_access_rules_as_settings_reindex(self, tmp_path, monkeypatch, indexed, user, role):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "users.yaml").write_text(USERS_YAML, encoding="utf-8")
        monkeypatch.delenv("REALIZE_API_KEY", raising=False)
        monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
        app = _app()

        @app.middleware("http")
        async def as_principal(request, call_next):
            request.state.user_id = user
            request.state.role = role
            request.state.scopes = []
            return await call_next(request)

        client = TestClient(app)
        for path in ("/api/settings/reindex", "/api/kb/reindex"):
            assert client.post(path).status_code == 403
        assert indexed == []

    def test_scope_rules_classify_both_paths_alike(self):
        from realize_core.security.venture_scope import is_global_write, is_system_area, required_permission

        for path in ("/api/settings/reindex", "/api/kb/reindex"):
            assert is_system_area(path)
            assert is_global_write("POST", path)
            assert required_permission("POST", path) == "system:manage"


# ---------------------------------------------------------------------------
# estimate_tokens + short-question KB lookup
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_hebrew_counts_more_tokens_per_char_than_english(self):
        from realize_core.prompt.builder import estimate_tokens

        assert estimate_tokens("x" * 300) == 85  # 300 / 3.5, unchanged
        assert estimate_tokens("א" * 300) == 200  # 300 / 1.5
        assert estimate_tokens("ب" * 30) == 20  # Arabic too

    def test_mixed_text_adds_both(self):
        from realize_core.prompt.builder import estimate_tokens

        assert estimate_tokens("א" * 15 + "x" * 35) == 20

    def test_empty_and_tiny(self):
        from realize_core.prompt.builder import estimate_tokens

        assert estimate_tokens("") == 0
        assert estimate_tokens("a") == 1


class TestShortQuestionKbLookup:
    def _context(self, tmp_path, monkeypatch, message):
        from realize_core.kb import indexer
        from realize_core.prompt import builder

        (tmp_path / "budget.md").write_text("התקציב הנותר הוא 1.2 מיליון", encoding="utf-8")
        calls: list[str] = []

        def fake_search(query, system_key=None, top_k=5, **_):
            calls.append(query)
            return [{"path": "budget.md", "title": "תקציב"}]

        monkeypatch.setattr(indexer, "semantic_search", fake_search)
        out = builder._build_dynamic_kb_context(tmp_path, "tower-b", message)
        return out, calls

    def test_short_hebrew_question_searches_the_kb(self, tmp_path, monkeypatch):
        out, calls = self._context(tmp_path, monkeypatch, "כמה נשאר?")
        assert calls == ["כמה נשאר?"]
        assert "1.2 מיליון" in out

    def test_three_letter_word_searches(self, tmp_path, monkeypatch):
        _, calls = self._context(tmp_path, monkeypatch, "מכר")
        assert calls == ["מכר"]

    @pytest.mark.parametrize("message", ["", "  ", "אב", " a b ", "?!"])
    def test_less_than_three_characters_does_not(self, tmp_path, monkeypatch, message):
        out, calls = self._context(tmp_path, monkeypatch, message)
        assert calls == []
        assert out == ""
