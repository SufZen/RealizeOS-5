"""Text from outside shown on a terminal without letting it drive the terminal.

Values that came from outside RealizeOS (a pilot user's contact, a
reviewer's spreadsheet, a name inside an archive) may hold escape
sequences or other control characters. Echoed raw, ``\\x1b[...`` can rewrite
what the operator sees, move the cursor or set the window title.
:func:`escape_nonprintable` shows them as visible escapes instead.
"""

from __future__ import annotations


def _escape(ch: str) -> str:
    code = ord(ch)
    if code < 0x100:
        return f"\\x{code:02x}"
    return f"\\u{code:04x}" if code < 0x10000 else f"\\U{code:08x}"


def escape_nonprintable(value: object) -> str:
    """``str(value)`` with every non-printable character shown as ``\\xNN``, ``\\uNNNN`` or ``\\UNNNNNNNN``.

    Printable text, non-Latin scripts included, is unchanged. Line breaks and
    tabs are escaped too, so one value stays on one line; use
    :func:`escape_lines` to keep a multi-line text's layout.
    """
    return "".join(ch if ch.isprintable() else _escape(ch) for ch in str(value))


def escape_lines(text: str) -> str:
    """:func:`escape_nonprintable` on each line of ``text``, keeping its line breaks."""
    return "\n".join(escape_nonprintable(line) for line in str(text).split("\n"))
