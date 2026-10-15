"""Multilingual KB search: Hebrew questions find their documents, and venture scope always holds.

The webinar question "כמה נשאר לנו נטו בתקציב?" returned no sources: the
whole sentence went to FTS5 as one MATCH expression. Embeddings are off here
(no model download); keyword search alone must find the budget.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from realize_core.kb import indexer
from realize_core.utils import fts

ROOT = Path(__file__).resolve().parent.parent
DEMO_PROJECT = ROOT / "templates" / "demos" / "tower-b-he" / "B-brain" / "project"

VENTURE = "tower-b"
OTHER = "other-venture"


@pytest.fixture(autouse=True)
def _no_embedder(monkeypatch):
    monkeypatch.setattr(indexer, "_get_embedder", lambda: None)


@pytest.fixture(params=[fts.TRIGRAM_TOKENIZE, fts.PLAIN_TRIGRAM_TOKENIZE, fts.FALLBACK_TOKENIZE])
def tokenizer(request, monkeypatch):
    """Each tokenizer a SQLite version can get (>= 3.45, 3.34-3.44, older)."""
    monkeypatch.setattr(indexer, "fts_tokenizer", lambda: request.param)
    return request.param


@pytest.fixture
def kb(tmp_path, tokenizer):
    """A KB with the Hebrew demo project in one venture and a rival budget in another."""
    project = tmp_path / "systems" / VENTURE / "B-brain" / "project"
    project.mkdir(parents=True)
    for md in DEMO_PROJECT.glob("*.md"):
        shutil.copy(md, project / md.name)
    notes = tmp_path / "systems" / VENTURE / "B-brain" / "notes.md"
    notes.write_text("# הערות\nתקציב השנה אושר.\n", encoding="utf-8")  # noqa: RUF001

    other = tmp_path / "systems" / OTHER / "B-brain"
    other.mkdir(parents=True)
    (other / "secret-budget.md").write_text(
        '# תקציב סודי\nכמה נשאר נטו בתקציב? budget (draft AND plan NEAR "x" it\'s * - : תקציב\n',
        encoding="utf-8",
    )
    db_path = tmp_path / "kb_index.db"
    indexer.index_kb_files(str(tmp_path), db_path=db_path, force=True)
    return tmp_path, db_path


def _search(kb, query, system_key=VENTURE):
    root, db_path = kb
    return indexer.semantic_search(query, system_key=system_key, db_path=db_path, kb_root=str(root))


def test_webinar_question_finds_the_budget(kb):
    results = _search(kb, "כמה נשאר לנו נטו בתקציב?")
    assert results, "the Hebrew budget question must return sources"
    assert any(Path(r["path"]).name == "budget.md" for r in results)


def test_prefixed_word_matches_bare_word(kb):
    """'בתקציב' (in the budget) matches a document that only says 'תקציב'."""
    results = _search(kb, "בתקציב")
    assert any(Path(r["path"]).name == "notes.md" for r in results)


@pytest.mark.parametrize(
    "query",
    [
        '"',
        'תקציב"',
        "-תקציב",
        "title:תקציב",
        "תקציב*",
        "(תקציב",
        "budget (draft",
        "תקציב AND",
        "NEAR(תקציב נטו)",
        "it's",
    ],
)
def test_syntax_characters_never_raise_or_leak(kb, query):
    results = _search(kb, query)
    assert isinstance(results, list)
    assert all(r["system_key"] == VENTURE for r in results), results


def test_like_fallback_is_scoped(kb, monkeypatch):
    """An FTS error falls back to LIKE, which still applies the venture filter."""
    monkeypatch.setattr(indexer, "build_match_query", lambda q: '"unterminated', raising=False)
    results = _search(kb, "תקציב")
    assert results, "LIKE fallback should still find the venture's budget"
    assert all(r["system_key"] == VENTURE for r in results), results


def test_short_tokens_use_scoped_like(kb):
    """Words under three letters can't match trigrams; LIKE covers them, scoped."""
    results = _search(kb, "סה")
    assert results
    assert all(r["system_key"] == VENTURE for r in results)


def test_migrates_v1_unicode61_index(tmp_path):
    """An index built before trigram (user_version 0, unicode61) is rebuilt on open."""
    db_path = tmp_path / "kb_index.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE kb_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE NOT NULL, title TEXT,
            system_key TEXT, content TEXT, embedding BLOB, file_mtime REAL DEFAULT 0, last_indexed TEXT
        );
        CREATE VIRTUAL TABLE kb_fts USING fts5(path, title, content, system_key, content='kb_files', content_rowid='id');
        CREATE TRIGGER kb_ai AFTER INSERT ON kb_files BEGIN
            INSERT INTO kb_fts(rowid, path, title, content, system_key)
            VALUES (new.id, new.path, new.title, new.content, new.system_key);
        END;
        """
    )
    conn.execute(
        "INSERT INTO kb_files (path, title, system_key, content, embedding) VALUES (?, ?, ?, ?, ?)",
        ("systems/tower-b/B-brain/budget.md", "תקציב", VENTURE, "יתרה נטו בתקציב הפרויקט", b"\x00\x00\x80?"),
    )
    conn.commit()
    conn.close()

    results = indexer.semantic_search("כמה נשאר לנו נטו בתקציב?", system_key=VENTURE, db_path=db_path)
    assert [Path(r["path"]).name for r in results] == ["budget.md"]

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == indexer.KB_SCHEMA_VERSION
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'kb_fts'").fetchone()[0]
        assert indexer.fts_tokenizer() in sql
    finally:
        conn.close()


def test_embedding_model_change_clears_old_vectors(tmp_path, monkeypatch):
    """Vectors from another model are dropped so the next index run re-embeds them."""
    db_path = tmp_path / "kb_index.db"
    monkeypatch.setenv("KB_EMBED_MODEL", "model-a")
    indexer._init_index_db(db_path)
    conn = indexer._get_conn(db_path)
    conn.execute("INSERT INTO kb_files (path, system_key, content, embedding) VALUES ('a.md', 's', 'x', X'0000803F')")
    conn.commit()
    conn.close()

    indexer._init_index_db(db_path)  # same model: kept
    conn = indexer._get_conn(db_path)
    assert conn.execute("SELECT embedding FROM kb_files").fetchone()[0] is not None
    conn.close()

    monkeypatch.setenv("KB_EMBED_MODEL", "model-b")
    indexer._init_index_db(db_path)
    conn = indexer._get_conn(db_path)
    assert conn.execute("SELECT embedding FROM kb_files").fetchone()[0] is None
    conn.close()


def test_incremental_index_re_embeds_rows_without_vectors(tmp_path, monkeypatch):
    """Unchanged files whose vector was cleared are embedded again, with the passage prefix."""
    kb_dir = tmp_path / "systems" / VENTURE / "B-brain"
    kb_dir.mkdir(parents=True)
    (kb_dir / "a.md").write_text("# A\nתקציב", encoding="utf-8")  # noqa: RUF001
    db_path = tmp_path / "kb_index.db"
    indexer.index_kb_files(str(tmp_path), db_path=db_path, force=True)

    seen: list[str] = []

    class FakeEmbedder:
        def embed(self, texts):
            seen.extend(texts)
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setenv("KB_EMBED_MODEL", "intfloat/multilingual-e5-small")
    monkeypatch.setattr(indexer, "_get_embedder", lambda: FakeEmbedder())
    assert indexer.index_kb_files(str(tmp_path), db_path=db_path) == 1
    assert seen
    assert seen[0].startswith("passage: ")

    conn = indexer._get_conn(db_path)
    assert conn.execute("SELECT embedding FROM kb_files").fetchone()[0] is not None
    conn.close()


def test_custom_system_dir_gets_its_venture_key(tmp_path):
    """A venture whose folder isn't systems/<key> is indexed under its configured key."""
    venture_dir = tmp_path / "ventures" / "acme-dir" / "B-brain"
    venture_dir.mkdir(parents=True)
    (venture_dir / "plan.md").write_text("# Plan\nquarterly budget", encoding="utf-8")
    db_path = tmp_path / "kb_index.db"
    systems = {"acme": {"system_dir": "ventures/acme-dir"}}
    indexer.index_kb_files(str(tmp_path), db_path=db_path, force=True, systems_config=systems)

    results = indexer.semantic_search("budget", system_key="acme", db_path=db_path)
    assert [Path(r["path"]).name for r in results] == ["plan.md"]


def test_tokenizer_change_rebuilds_the_index(tmp_path, monkeypatch):
    """A SQLite upgrade (different best tokenizer) rebuilds kb_fts on the next open."""
    kb_dir = tmp_path / "systems" / VENTURE / "B-brain"
    kb_dir.mkdir(parents=True)
    shutil.copy(DEMO_PROJECT / "budget.md", kb_dir / "budget.md")
    db_path = tmp_path / "kb_index.db"

    monkeypatch.setattr(indexer, "fts_tokenizer", lambda: fts.FALLBACK_TOKENIZE)
    indexer.index_kb_files(str(tmp_path), db_path=db_path, force=True)
    monkeypatch.setattr(indexer, "fts_tokenizer", lambda: fts.PLAIN_TRIGRAM_TOKENIZE)
    results = indexer.semantic_search("כמה נשאר לנו נטו בתקציב?", system_key=VENTURE, db_path=db_path)

    assert [Path(r["path"]).name for r in results] == ["budget.md"]
    conn = sqlite3.connect(db_path)
    try:
        assert fts.table_tokenizer(conn, "kb_fts") == fts.PLAIN_TRIGRAM_TOKENIZE
        stored = conn.execute("SELECT value FROM kb_meta WHERE key = 'fts_tokenizer'").fetchone()[0]
        assert stored == fts.PLAIN_TRIGRAM_TOKENIZE
    finally:
        conn.close()


def test_incremental_index_moves_file_to_configured_venture_key(tmp_path):
    """An index built before system_dir was honoured gets the right key without a forced reindex."""
    venture_dir = tmp_path / "systems" / "acme-folder" / "B-brain"
    venture_dir.mkdir(parents=True)
    (venture_dir / "plan.md").write_text("# Plan\nquarterly budget", encoding="utf-8")
    db_path = tmp_path / "kb_index.db"
    indexer.index_kb_files(str(tmp_path), db_path=db_path, force=True)
    assert indexer.semantic_search("budget", system_key="acme", db_path=db_path) == []

    systems = {"acme": {"system_dir": "systems/acme-folder"}}
    assert indexer.index_kb_files(str(tmp_path), db_path=db_path, systems_config=systems) == 1

    results = indexer.semantic_search("budget", system_key="acme", db_path=db_path)
    assert [Path(r["path"]).name for r in results] == ["plan.md"]
    assert indexer.semantic_search("budget", system_key="acme-folder", db_path=db_path) == []
    # Nothing changed since: the next incremental run skips it.
    assert indexer.index_kb_files(str(tmp_path), db_path=db_path, systems_config=systems) == 0
