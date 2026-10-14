"""Search text for SQLite FTS5: normalisation, tokens and safe MATCH queries.

User questions ("כמה נשאר לנו נטו בתקציב?") must never reach ``MATCH`` raw:
FTS5 reads ``"``, ``-``, ``:``, ``*``, ``(``, ``AND``/``OR``/``NOT``/``NEAR``
as syntax, so a question either fails to parse or means something else.
:func:`build_match_query` turns any text into quoted terms joined with
``OR`` (bm25 ranks documents matching more of them first).

The index side uses the ``trigram`` tokenizer (:func:`fts_tokenizer`): it
matches substrings in any script, where ``unicode61`` needs whole words.
Hebrew attaches prefixes (ו ה ב ל מ ש כ) to words, so the query side also
adds each such word without its prefix: "בתקציב" (in the budget) finds
"תקציב" (budget).

Shared by the KB indexer, memory store and synapse search.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata

#: Tokenizer for FTS5 tables: trigram with diacritic folding (SQLite >= 3.45).
TRIGRAM_TOKENIZE = "trigram remove_diacritics 1"
#: Fallback for older SQLite, where trigram can't fold diacritics.
FALLBACK_TOKENIZE = "unicode61 remove_diacritics 2"

#: Shortest term trigram can match.
MIN_TERM_LEN = 3
#: Most terms put in one query (bounds the SQL for very long messages).
MAX_TERMS = 64

#: Hebrew one-letter prefixes: and, the, in, to, from, that, as.
HEBREW_PREFIXES = frozenset("והבלמשכ")
#: How many stacked prefixes are stripped ("ובתקציב" -> "בתקציב" -> "תקציב").
MAX_PREFIX_STRIP = 2

HEBREW_STOPWORDS = frozenset(
    [
        "של",
        "את",
        "על",
        "עם",
        "זה",
        "זו",
        "הוא",
        "היא",
        "אנחנו",
        "לנו",
        "כמה",
        "מה",
        "מי",
        "איך",
        "האם",
        "יש",
        "אין",
        "גם",
        "או",
        "אבל",
        "כי",
        "אם",
        "לא",
        "כן",
    ]
)
ENGLISH_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "so",
        "that",
        "the",
        "their",
        "them",
        "there",
        "these",
        "they",
        "this",
        "to",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    ]
)
STOPWORDS = HEBREW_STOPWORDS | ENGLISH_STOPWORDS

# Niqqud and cantillation marks (U+0591-U+05C7) that aren't letters or punctuation.
# Hebrew letters (U+05D0-U+05EA) are outside this range.
_HEBREW_MARKS = re.compile("[֑-ׇֽֿׁׂׅׄ]")
# Runs of letters and digits in any script (``\w`` minus the underscore).
_WORD = re.compile(r"[^\W_]+")


def _is_hebrew(token: str) -> bool:
    return "א" <= token[0] <= "ת"


def normalize(text: str) -> str:
    """NFKC, Hebrew niqqud and cantillation removed, lower-cased."""
    return _HEBREW_MARKS.sub("", unicodedata.normalize("NFKC", text or "")).lower()


def tokens(text: str) -> list[str]:
    """Words of ``text`` (any script), stopwords dropped, first occurrence kept."""
    seen: dict[str, None] = {}
    for word in _WORD.findall(normalize(text)):
        if word not in STOPWORDS:
            seen.setdefault(word, None)
    return list(seen)


def short_tokens(text: str) -> list[str]:
    """Words too short for a trigram match, for an optional ``LIKE`` clause."""
    return [t for t in tokens(text) if len(t) < MIN_TERM_LEN]


def _prefix_alternates(token: str) -> list[str]:
    """``token`` with leading Hebrew prefix letters stripped, one at a time."""
    found = []
    for _ in range(MAX_PREFIX_STRIP):
        if len(token) < 4 or not _is_hebrew(token) or token[0] not in HEBREW_PREFIXES:
            break
        token = token[1:]
        found.append(token)
    return found


def match_terms(text: str) -> list[str]:
    """Terms of at least :data:`MIN_TERM_LEN` letters, with Hebrew prefix-stripped alternates."""
    terms: dict[str, None] = {}
    for token in tokens(text):
        if len(token) < MIN_TERM_LEN:
            continue
        terms.setdefault(token, None)
        for alt in _prefix_alternates(token):
            terms.setdefault(alt, None)
    return list(terms)[:MAX_TERMS]


def build_match_query(text: str) -> str | None:
    """An FTS5 ``MATCH`` string for ``text``: every term quoted, joined with ``OR``.

    Returns None when no term is long enough (the caller skips FTS then).
    """
    terms = match_terms(text)
    if not terms:
        return None
    return " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)


def fts_tokenizer() -> str:
    """The ``tokenize=`` value for new FTS5 tables on this SQLite."""
    if sqlite3.sqlite_version_info >= (3, 45, 0):
        return TRIGRAM_TOKENIZE
    return FALLBACK_TOKENIZE
