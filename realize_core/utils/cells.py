"""Spreadsheet cells written as data, never as formulas (CSV / formula injection).

Rows that RealizeOS writes into a spreadsheet often carry text a model took
from an untrusted document (a tender, an email, a contractor's claim). A cell
that starts with ``=``, ``+``, ``-``, ``@``, a tab or a line break is read as a
formula by Google Sheets (with ``USER_ENTERED``) and by Excel or LibreOffice
when the sheet is exported, which lets a document smuggle in
``=IMPORTXML(...)`` or ``=HYPERLINK(...)`` and send data elsewhere.

:func:`neutralize_cell` prefixes such text with an apostrophe, the
spreadsheet convention for "this is text". Numbers, plain signed numbers
written as text (``-1200``, ``+5``, ``-1,200.50``) and other non-text values
are left alone: they can't be formulas, and amounts must stay summable.
"""

from __future__ import annotations

import re
from typing import Any

#: A plain signed number written as text: never a formula, so it stays a number.
_SIGNED_NUMBER = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")

#: First characters that make a spreadsheet read a cell as a formula (OWASP),
#: with the full-width forms some spreadsheet locales also accept.
FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r", "\n", "\uff1d", "\uff0b", "\uff0d", "\uff20")


def neutralize_cell(value: Any) -> Any:
    """``value``, with an apostrophe in front when it is text a spreadsheet would read as a formula.

    Leading spaces are looked through (`` =IMPORTXML(...)``), since some
    spreadsheets ignore them when deciding what a cell is.
    """
    if not isinstance(value, str):
        return value
    head = value.lstrip(" \u00a0\u3000")
    if head.startswith(FORMULA_PREFIXES) and not _SIGNED_NUMBER.fullmatch(head):
        return "'" + value
    return value


def neutralize_rows(rows: Any) -> Any:
    """Every cell of a 2-D list through :func:`neutralize_cell` (anything else is returned unchanged).

    Text is never turned into numbers here: ``"6.10"`` may be a clause, not 6.1.
    A skill that writes amounts sends them as JSON numbers.
    """
    if not isinstance(rows, list):
        return rows
    return [[neutralize_cell(cell) for cell in row] if isinstance(row, list) else neutralize_cell(row) for row in rows]
