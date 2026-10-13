"""Spreadsheet cells written as data, never as formulas (CSV / formula injection).

Rows that RealizeOS writes into a spreadsheet often carry text a model took
from an untrusted document (a tender, an email, a contractor's claim). A cell
that starts with ``=``, ``+``, ``-``, ``@``, a tab or a line break is read as a
formula by Google Sheets (with ``USER_ENTERED``) and by Excel or LibreOffice
when the sheet is exported, which lets a document smuggle in
``=IMPORTXML(...)`` or ``=HYPERLINK(...)`` and send data elsewhere.

:func:`neutralize_cell` prefixes such text with an apostrophe, the
spreadsheet convention for "this is text". Numbers and other non-text values
are left alone.
"""

from __future__ import annotations

from typing import Any

#: First characters that make a spreadsheet read a cell as a formula (OWASP),
#: with the full-width forms some spreadsheet locales also accept.
FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r", "\n", "\uff1d", "\uff0b", "\uff0d", "\uff20")


def neutralize_cell(value: Any) -> Any:
    """``value``, with an apostrophe in front when it is text a spreadsheet would read as a formula."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def neutralize_rows(rows: Any) -> Any:
    """Every cell of a 2-D list through :func:`neutralize_cell` (anything else is returned unchanged)."""
    if not isinstance(rows, list):
        return rows
    return [[neutralize_cell(cell) for cell in row] if isinstance(row, list) else neutralize_cell(row) for row in rows]
