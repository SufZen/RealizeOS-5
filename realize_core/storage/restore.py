"""Restore a storage export into a new, empty folder (``realize-os storage restore``).

The export (``POST /api/storage/export``, Settings → Storage & Backup) is a
ZIP with a fixed layout:

- ``realize-os.yaml``, ``systems/`` and ``shared/``: the ventures' brain and config;
- ``data/``: database snapshots, the Synapse index and Dream Inbox, and the
  pack verification state (``data/packs/verification.json``);
- ``custom-packs/``: the writable pack folder (``REALIZE_PACKS_PATH``);
- ``packs-inventory.json``: what the old installation resolved, to check the restore.

A restore unpacks that layout as it is into one folder, so the new
installation runs from it with ``DATA_PATH=<folder>/data`` and, when the
export had custom packs, ``REALIZE_PACKS_PATH=<folder>/custom-packs``. It
only writes into a folder that is missing or empty and never overwrites
anything; an archive entry outside the layout (an absolute path, ``..``, a
link, an unknown top-level name) refuses the whole restore before anything
is written. ``.env``, ``users.yaml`` and ``.credentials/`` are not in an
export; they are copied by hand.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)

#: Top-level names an export contains (``realize_api.routes.storage_settings``).
EXPORT_FILES = frozenset({"realize-os.yaml", "packs-inventory.json"})
EXPORT_TREES = frozenset({"systems", "shared", "data", "custom-packs"})

#: Where the restored install keeps its data and its writable packs.
DATA_DIR = "data"
CUSTOM_PACKS_DIR = "custom-packs"
INVENTORY_FILE = "packs-inventory.json"

_CHUNK = 1024 * 1024


class RestoreError(ValueError):
    """The archive can't be restored here; nothing was written."""


@dataclass
class RestoreResult:
    """What a restore wrote.

    Attributes:
        target: The folder the export was restored into.
        files: Archive names written, in archive order.
        data_path: ``<target>/data`` (use as ``DATA_PATH``).
        packs_path: ``<target>/custom-packs`` when the export had custom packs, else None.
        inventory: ``<target>/packs-inventory.json`` when the export had one, else None.
    """

    target: Path
    files: list[str] = field(default_factory=list)
    data_path: Path | None = None
    packs_path: Path | None = None
    inventory: Path | None = None


def _is_link(info: zipfile.ZipInfo) -> bool:
    """True for an entry stored as a symbolic link (Unix mode in the external attributes)."""
    return stat.S_ISLNK(info.external_attr >> 16)


def check_member(info: zipfile.ZipInfo) -> PurePosixPath | None:
    """The entry's relative path inside the export layout, or None for a directory entry.

    Raises:
        RestoreError: The entry is absolute, climbs out with ``..``, is a link,
            or isn't part of an export's layout.
    """
    name = info.filename
    if "\\" in name or "\x00" in name:
        raise RestoreError(f"'{name}' is not a valid archive path")
    path = PurePosixPath(name)
    if path.is_absolute() or (path.parts and ":" in path.parts[0]):
        raise RestoreError(f"'{name}' is an absolute path")
    if any(part in ("..", "") for part in path.parts) or not path.parts:
        raise RestoreError(f"'{name}' leaves the restore folder")
    if _is_link(info):
        raise RestoreError(f"'{name}' is a link; an export never contains links")
    top = path.parts[0]
    if info.is_dir():
        if top not in EXPORT_TREES:
            raise RestoreError(f"'{name}' is not part of a RealizeOS export")
        return None
    if len(path.parts) == 1 and top in EXPORT_FILES:
        return path
    if len(path.parts) > 1 and top in EXPORT_TREES:
        return path
    raise RestoreError(f"'{name}' is not part of a RealizeOS export")


def _require_empty(target: Path) -> None:
    if target.exists() and not target.is_dir():
        raise RestoreError(f"{target} exists and is not a folder")
    if target.is_dir() and any(target.iterdir()):
        raise RestoreError(f"{target} is not empty; restore only into a new or empty folder")


def restore_export(archive: Path | str, target: Path | str) -> RestoreResult:
    """Unpack a storage export into ``target``, which must be missing or empty.

    The archive is checked completely before anything is written. Files are
    unpacked into a temporary folder next to ``target`` and moved into place
    at the end, so a failure leaves ``target`` as it was.

    Args:
        archive: The export ZIP.
        target: The folder to restore into (created when missing).

    Returns:
        What was written and where the new installation's data and packs are.

    Raises:
        RestoreError: Not a readable ZIP, not an export, an unsafe entry, or
            ``target`` isn't empty. Nothing is written.
        OSError: Writing failed; ``target`` is left as it was.
    """
    archive, target = Path(archive), Path(target).absolute()
    _require_empty(target)
    try:
        zf = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RestoreError(f"{archive} is not a readable ZIP: {exc}") from exc
    with zf:
        members = [(info, check_member(info)) for info in zf.infolist()]
        files = [(info, path) for info, path in members if path is not None]
        if not files:
            raise RestoreError(f"{archive} contains no files")
        if len({str(path) for _, path in files}) != len(files):
            raise RestoreError(f"{archive} lists the same file twice")
        if not any(path.parts[0] in ("systems", "realize-os.yaml") for _, path in files):
            raise RestoreError(f"{archive} has no realize-os.yaml or systems/: not a RealizeOS export")

        target.parent.mkdir(parents=True, exist_ok=True)
        needed = sum(info.file_size for info, _ in files)
        free = shutil.disk_usage(target.parent).free
        if needed > free:
            raise RestoreError(f"The export needs {needed} bytes unpacked; only {free} are free in {target.parent}")
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.restore-", dir=target.parent))
        moved = False
        try:
            for info, path in files:
                dest = staging.joinpath(*path.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with zf.open(info) as src, open(dest, "xb") as out:
                        shutil.copyfileobj(src, out, _CHUNK)
                except zipfile.BadZipFile as exc:
                    raise RestoreError(f"'{info.filename}' in {archive} is damaged: {exc}") from exc
            _require_empty(target)  # still empty: nobody wrote there meanwhile
            if target.is_dir():
                target.rmdir()
            os.replace(staging, target)
            moved = True
        finally:
            if not moved:
                shutil.rmtree(staging, ignore_errors=True)

    names = [str(path) for _, path in files]
    tops = {path.parts[0] for _, path in files}
    result = RestoreResult(
        target=target,
        files=names,
        data_path=target / DATA_DIR,
        packs_path=target / CUSTOM_PACKS_DIR if CUSTOM_PACKS_DIR in tops else None,
        inventory=target / INVENTORY_FILE if INVENTORY_FILE in tops else None,
    )
    logger.info("Restored %d file(s) from %s into %s", len(names), archive, target)
    return result
