"""``realize-os storage`` — restore a storage export on a new server.

Commands:
  restore  — unpack an export ZIP into a new, empty folder (never overwrites)

``python cli.py storage restore ...`` works the same. The export itself is
made in the dashboard (Settings → Storage & Backup) or with
``POST /api/storage/export``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

storage_app = typer.Typer(no_args_is_help=True)


@storage_app.command("restore")
def storage_restore(
    archive: Annotated[Path, typer.Argument(help="The export ZIP (realizeos-export-*.zip).")],
    directory: Annotated[
        Path,
        typer.Option("--directory", "-d", help="New or empty folder to restore into. Nothing is overwritten."),
    ],
) -> None:
    """Restore a storage export into a new, empty folder.

    The archive is checked before anything is written: an entry outside an
    export's layout refuses the whole restore. ``.env``, ``users.yaml`` and
    ``.credentials/`` are not in an export; copy them from the old server.
    """
    from realize_core.storage.restore import RestoreError, restore_export

    try:
        result = restore_export(archive, directory)
    except RestoreError as exc:
        typer.echo(f"Error: {exc}. Nothing was written.", err=True)
        raise typer.Exit(1) from exc
    except OSError as exc:
        typer.echo(f"Error: could not write the restore: {exc}. {directory} was left as it was.", err=True)
        raise typer.Exit(1) from exc

    target = result.target
    typer.echo(f"Restored {len(result.files)} file(s) into {target}.")
    typer.echo("Next:")
    typer.echo("  1. Copy .env, users.yaml and .credentials/ from the old server (they are not in an export).")
    env = f"DATA_PATH={result.data_path}"
    if result.packs_path is not None:
        env += f" REALIZE_PACKS_PATH={result.packs_path}"
    typer.echo(f"  2. Run RealizeOS from {target} with {env}.")
    if result.inventory is not None:
        typer.echo(
            f"  3. Check the packs: python cli.py packs inventory --kb {target} --compare {result.inventory}"
            " (with the same variables set)."
        )
