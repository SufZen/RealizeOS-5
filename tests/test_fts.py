"""Search-text helpers (``realize_core.utils.fts``): normalisation, tokens and safe FTS5 MATCH queries."""

from __future__ import annotations

import sqlite3

import pytest
from realize_core.utils import fts


class TestNormalize:
    def test_strips_niqqud_and_cantillation_keeps_letters(self):
        assert fts.normalize("תַּקְצִיב") == "תקציב"

    def test_nfkc_and_lowercase(self):
        assert fts.normalize("Ｂudget ＡND") == "budget and"  # noqa: RUF001 - full-width B and A


class TestTokens:
    def test_hebrew_question_drops_stopwords_and_punctuation(self):
        assert fts.tokens("כמה נשאר לנו נטו בתקציב?") == ["נשאר", "נטו", "בתקציב"]

    def test_english_stopwords_and_dedupe(self):
        assert fts.tokens("The budget, the BUDGET and the plan") == ["budget", "plan"]

    def test_short_tokens_split_out(self):
        assert fts.short_tokens("AI budget Q3") == ["ai", "q3"]


class TestBuildMatchQuery:
    def test_hebrew_prefix_letter_adds_stripped_alternate(self):
        query = fts.build_match_query("כמה נשאר לנו נטו בתקציב?")
        assert query == '"נשאר" OR "נטו" OR "בתקציב" OR "תקציב"'

    def test_quotes_are_doubled(self):
        assert fts.build_match_query('budget"plan') == '"budget" OR "plan"'
        assert fts.build_match_query("abc") == '"abc"'

    def test_none_when_nothing_long_enough(self):
        assert fts.build_match_query("a b ?") is None
        assert fts.build_match_query("") is None
        assert fts.build_match_query("של את על") is None

    @pytest.mark.parametrize(
        "query",
        ['"', "-budget", "title:budget", "bud*", "(budget", "budget AND", "NEAR(a b)", "it's", "a OR", "^x", "{a b}"],
    )
    def test_fts5_syntax_is_never_live(self, query):
        """Whatever the user types, the MATCH string parses."""
        conn = sqlite3.connect(":memory:")
        conn.execute(f"CREATE VIRTUAL TABLE t USING fts5(body, tokenize='{fts.fts_tokenizer()}')")
        conn.execute("INSERT INTO t(body) VALUES ('budget plan near title')")
        match = fts.build_match_query(query)
        if match is not None:
            conn.execute("SELECT * FROM t WHERE t MATCH ?", (match,)).fetchall()


class TestTokenizer:
    def test_trigram_with_diacritics_on_new_sqlite(self, monkeypatch):
        monkeypatch.setattr(fts.sqlite3, "sqlite_version_info", (3, 45, 0))
        assert fts.fts_tokenizer() == fts.TRIGRAM_TOKENIZE == "trigram remove_diacritics 1"

    @pytest.mark.parametrize("version", [(3, 34, 0), (3, 40, 1), (3, 44, 2)])
    def test_plain_trigram_on_3_34_to_3_44(self, monkeypatch, version):
        """Debian bookworm (python:3.12-slim) ships 3.40: trigram, without diacritic folding."""
        monkeypatch.setattr(fts.sqlite3, "sqlite_version_info", version)
        assert fts.fts_tokenizer() == fts.PLAIN_TRIGRAM_TOKENIZE == "trigram"

    def test_unicode61_before_trigram_existed(self, monkeypatch):
        monkeypatch.setattr(fts.sqlite3, "sqlite_version_info", (3, 33, 0))
        assert fts.fts_tokenizer() == fts.FALLBACK_TOKENIZE == "unicode61 remove_diacritics 2"

    @pytest.mark.parametrize("tokenize", [fts.TRIGRAM_TOKENIZE, fts.PLAIN_TRIGRAM_TOKENIZE, fts.FALLBACK_TOKENIZE])
    def test_table_tokenizer_reads_the_create_statement(self, tokenize):
        conn = sqlite3.connect(":memory:")
        conn.execute(f"CREATE VIRTUAL TABLE t USING fts5(body, tokenize='{tokenize}')")
        conn.execute("CREATE VIRTUAL TABLE plain USING fts5(body)")
        assert fts.table_tokenizer(conn, "t") == tokenize
        assert fts.table_tokenizer(conn, "plain") == "unicode61"
        assert fts.table_tokenizer(conn, "missing") is None
