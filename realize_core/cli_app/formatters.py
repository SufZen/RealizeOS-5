"""Output formatters for CLI commands: table, json, yaml.

Every list/get command supports ``--format table|json|yaml`` (default ``table``).
These helpers keep formatting logic out of command modules.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table

_console = Console()


def to_table(
    rows: Sequence[dict[str, Any]],
    *,
    columns: Sequence[str] | None = None,
    title: str | None = None,
) -> None:
    """Print *rows* as a rich table to stdout.

    If *columns* is ``None``, columns are derived from the keys of the first row.
    """
    if not rows:
        _console.print("[dim]No results.[/dim]")
        return

    if columns is None:
        columns = list(rows[0].keys())

    table = Table(title=title, show_lines=False)
    for col in columns:
        table.add_column(col.replace("_", " ").title(), overflow="fold")

    for row in rows:
        table.add_row(*(str(row.get(c, "")) for c in columns))

    _console.print(table)


def to_json(data: Any) -> None:
    """Dump *data* as indented JSON to stdout."""
    json.dump(data, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def to_yaml(data: Any) -> None:
    """Dump *data* as YAML to stdout."""
    yaml.dump(data, sys.stdout, default_flow_style=False, sort_keys=False)


def emit(
    data: Any,
    *,
    output_format: str = "table",
    columns: Sequence[str] | None = None,
    title: str | None = None,
) -> None:
    """Route *data* to the right formatter.

    *data* should be a list of dicts for ``table`` format, or any
    JSON-serialisable value for ``json`` / ``yaml``.
    """
    fmt = output_format.lower().strip()
    if fmt == "json":
        to_json(data)
    elif fmt == "yaml":
        to_yaml(data)
    elif isinstance(data, list):
        to_table(data, columns=columns, title=title)
    else:
        # Single object — wrap in a list
        to_table([data] if isinstance(data, dict) else [{"value": data}], columns=columns, title=title)
