"""``realize-os bot`` — start the Telegram bot."""

from __future__ import annotations

import argparse


def bot() -> None:
    """Start the Telegram bot."""
    from cli import cmd_bot

    ns = argparse.Namespace()
    cmd_bot(ns)
