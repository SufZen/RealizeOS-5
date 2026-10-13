"""Outside text shown on a terminal (``realize_core.utils.text``), shared by the wedge, packs and storage CLIs."""

from __future__ import annotations

import pytest
from realize_core.utils.text import escape_lines, escape_nonprintable


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("plain text", "plain text"),
        ("חשבון חלקי · λογαριασμός · ção", "חשבון חלקי · λογαριασμός · ção"),  # other scripts stay as they are
        ("\x1b]0;owned\x07", "\\x1b]0;owned\\x07"),
        ("a\nb\tc\rd", "a\\x0ab\\x09c\\x0dd"),
        ("rtl\u202eoverride", "rtl\\u202eoverride"),
        ("tag\U000e0041", "tag\\U000e0041"),
        (None, "None"),
        (42, "42"),
    ],
)
def test_escape_nonprintable(value, shown):
    assert escape_nonprintable(value) == shown


def test_escaping_twice_changes_nothing():
    once = escape_nonprintable("\x1b[2J")
    assert escape_nonprintable(once) == once


def test_escape_lines_keeps_the_line_breaks():
    assert escape_lines("first\x1b[31m\nsecond\r\n") == "first\\x1b[31m\nsecond\\x0d\n"


def test_wedge_uses_the_shared_helper():
    from realize_core.cli_app.commands import wedge

    assert wedge._safe is escape_nonprintable
