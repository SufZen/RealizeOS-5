"""``realize-os index`` — rebuild the KB search index."""

from __future__ import annotations


def index() -> None:
    """Rebuild the knowledge-base search index."""
    import argparse

    from cli import cmd_index

    ns = argparse.Namespace()
    cmd_index(ns)
