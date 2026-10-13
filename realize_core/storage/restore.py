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
anything. An archive entry outside the layout (an absolute or drive path,
``..``, a backslash, a link or device file, an unknown top-level name, a
destination that resolves outside the folder) refuses the whole restore
before anything is written, and so does an archive with more than
``MAX_MEMBERS`` entries or more than ``MAX_TOTAL_BYTES`` unpacked. So does a
name Windows would rewrite or reserve, on every platform: a segment ending
in a space or a dot (Windows drops them, so ``.. `` would become ``..``) or a
device name such as ``CON``, ``NUL`` or ``COM1``. Members are copied one by
one; ``extractall`` is never used. ``.env``, ``users.yaml`` and
``.credentials/`` are not in an export; they are copied by hand.

A colon is part of a legal file name on Linux and macOS (``standup 10:30.md``),
so such files restore there. Windows can't store one (it would open an
alternate data stream), so on Windows those files are skipped with a warning
and listed in :attr:`RestoreResult.skipped`. A drive name (``C:``) is refused
everywhere.
"""

from __future__ import annotations

import logging
import os
import posixpath
import re
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

#: Limits that stop a hostile or broken archive (a "zip bomb") from filling the disk.
MAX_MEMBERS = 200_000
MAX_TOTAL_BYTES = 20 * 1024**3

_CHUNK = 1024 * 1024

#: Device names Windows reserves, as a whole name or before an extension (``nul.txt``).
_WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul", "conin$", "conout$"}
    | {f"{port}{n}" for port in ("com", "lpt") for n in "0123456789\u00b9\u00b2\u00b3"}
)
#: A drive name at the start of a segment (``C:``, ``c:x``).
_DRIVE = re.compile(r"[A-Za-z]:")
#: Prefix of a Windows extended-length path, which keeps every name as it is.
_EXTENDED = "\\\\?\\"


class RestoreError(ValueError):
    """The archive can't be restored here; nothing was written."""


@dataclass
class RestoreResult:
    """What a restore wrote.

    Attributes:
        target: The folder the export was restored into.
        files: Archive names written, in archive order.
        skipped: Archive names not written because this system can't store
            them (a colon in a name on Windows), in archive order.
        data_path: ``<target>/data`` (use as ``DATA_PATH``).
        packs_path: ``<target>/custom-packs`` when the export had custom packs, else None.
        inventory: ``<target>/packs-inventory.json`` when the export had one, else None.
    """

    target: Path
    files: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    data_path: Path | None = None
    packs_path: Path | None = None
    inventory: Path | None = None


def _file_type(info: zipfile.ZipInfo) -> int:
    """The Unix file type the entry was stored with (0 when the archive didn't record one)."""
    return stat.S_IFMT(info.external_attr >> 16)


def _names_may_hold_colons() -> bool:
    """True where a file name may contain ``:`` (everywhere but Windows)."""
    return os.name != "nt"


def _check_segment(name: str, part: str) -> None:
    """Refuse a path segment that names a drive, or that Windows would rewrite or reserve."""
    if _DRIVE.match(part):
        raise RestoreError(f"{name!r} names a drive")
    if part.endswith((" ", ".")):
        # Windows drops a trailing space or dot, so ".. " would be written as "..".
        raise RestoreError(f"{name!r} has a name ending in a space or a dot ({part!r})")
    if part.split(".", 1)[0].rstrip(" ").casefold() in _WINDOWS_DEVICE_NAMES:
        raise RestoreError(f"{name!r} uses a name Windows reserves for a device ({part!r})")


def check_member(info: zipfile.ZipInfo, target: Path | None = None) -> PurePosixPath | None:
    """The entry's relative path inside the export layout, or None for a directory entry.

    The name must already be in canonical form: relative, ``/``-separated,
    no ``.`` or ``..`` segments, no empty segments, no drive letter or UNC
    prefix, no backslash or control character. No segment may name a drive
    (``C:``), end in a space or a dot, or be a Windows device name (``CON``,
    ``NUL``, ``COM1``, ``nul.txt``, ...), on any platform. A colon elsewhere
    in a name is accepted here (:func:`restore_export` skips such files on
    Windows). Only regular files and folders are accepted. With ``target``,
    the resolved destination must also lie inside ``target`` (a check on real
    paths, not on strings).

    Raises:
        RestoreError: The entry is unsafe or isn't part of an export's layout.
    """
    name = info.filename
    if not name or any(ord(ch) < 32 for ch in name) or "\\" in name:
        raise RestoreError(f"{name!r} is not a valid archive path")
    if name.startswith("/"):
        raise RestoreError(f"{name!r} is an absolute path")
    bare = name.rstrip("/") if info.is_dir() else name
    if posixpath.normpath(bare) != bare or bare in (".", ".."):
        raise RestoreError(f"{name!r} is not a plain relative path")
    path = PurePosixPath(bare)
    if ".." in path.parts:
        raise RestoreError(f"{name!r} leaves the restore folder")
    for part in path.parts:
        _check_segment(name, part)
    kind = _file_type(info)
    if stat.S_ISLNK(kind):
        raise RestoreError(f"{name!r} is a link; an export never contains links")
    if kind and not (stat.S_ISREG(kind) or stat.S_ISDIR(kind)):
        raise RestoreError(f"{name!r} is a device or special file; an export has only files and folders")
    if target is not None:
        root = Path(target).resolve()
        if not root.joinpath(*path.parts).resolve().is_relative_to(root):
            raise RestoreError(f"{name!r} resolves outside {root}")
    top = path.parts[0]
    if info.is_dir():
        if top not in EXPORT_TREES:
            raise RestoreError(f"{name!r} is not part of a RealizeOS export")
        return None
    if len(path.parts) == 1 and top in EXPORT_FILES:
        return path
    if len(path.parts) > 1 and top in EXPORT_TREES:
        return path
    raise RestoreError(f"{name!r} is not part of a RealizeOS export")


def _remove_staging(staging: Path) -> None:
    """Delete the staging folder and everything in it; a folder that's already gone is fine.

    On Windows the usual file APIs drop a trailing space or dot from every
    name, so a folder such as ``acme.`` can't be removed through them; the
    extended-length form (``\\\\?\\C:\\...``) passes names through unchanged.
    A failure is logged, never raised: the restore's own error matters more.
    """
    path = str(staging)
    if os.name == "nt" and not path.startswith(_EXTENDED):
        path = _EXTENDED + ("UNC\\" + path[2:] if path.startswith("\\\\") else path)
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return
    except OSError:
        logger.warning("Could not remove the restore staging folder %s; delete it by hand", staging, exc_info=True)


def _checked_members(
    infos: list[zipfile.ZipInfo], target: Path
) -> tuple[list[tuple[zipfile.ZipInfo, PurePosixPath | None]], list[str]]:
    """Every entry through :func:`check_member`, and the files this system must skip.

    Where a file name can't hold a colon (Windows), an entry with one is
    checked like any other, except that it isn't resolved under ``target``
    (that would name an alternate data stream), and then left out with a
    warning.
    """
    members: list[tuple[zipfile.ZipInfo, PurePosixPath | None]] = []
    skipped: list[str] = []
    colons_ok = _names_may_hold_colons()
    for info in infos:
        if colons_ok or ":" not in info.filename:
            members.append((info, check_member(info, target)))
            continue
        path = check_member(info)
        if path is not None:
            skipped.append(str(path))
    if skipped:
        logger.warning(
            "Skipping %d file(s) whose names hold a colon, which this system can't store: %s",
            len(skipped),
            ", ".join(skipped),
        )
    return members, skipped


def _require_empty(target: Path) -> None:
    if target.exists() and not target.is_dir():
        raise RestoreError(f"{target} exists and is not a folder")
    if target.is_dir() and any(target.iterdir()):
        raise RestoreError(f"{target} is not empty; restore only into a new or empty folder")


def _copy_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, dest: Path, budget: int, archive: Path) -> int:
    """Write one member to ``dest`` (which must not exist); returns the bytes written.

    Never more than the size the archive declares for the member, nor more
    than ``budget``: a member that inflates beyond either is refused.
    """
    written = 0
    try:
        with zf.open(info) as src, open(dest, "xb") as out:
            while chunk := src.read(_CHUNK):
                written += len(chunk)
                if written > info.file_size or written > budget:
                    raise RestoreError(f"{info.filename!r} in {archive} unpacks to more than it declares")
                out.write(chunk)
    except zipfile.BadZipFile as exc:
        raise RestoreError(f"{info.filename!r} in {archive} is damaged: {exc}") from exc
    return written


def restore_export(
    archive: Path | str,
    target: Path | str,
    *,
    max_total_bytes: int = MAX_TOTAL_BYTES,
    max_members: int = MAX_MEMBERS,
) -> RestoreResult:
    """Unpack a storage export into ``target``, which must be missing or empty.

    The archive is checked completely before anything is written: every
    entry's name (:func:`check_member`, including where it resolves under
    ``target``), the number of entries and their total unpacked size. Files
    are then copied one by one (never ``extractall``) into a temporary
    folder next to ``target``, each destination checked again on the real
    filesystem, and moved into place at the end, so a failure leaves
    ``target`` as it was and the temporary folder is removed.

    On Windows a file whose name holds a colon (legal on Linux, where the
    export may have been made) can't be written: it is checked like every
    other entry, then skipped with a warning and listed in ``skipped``.

    Args:
        archive: The export ZIP.
        target: The folder to restore into (created when missing).
        max_total_bytes: Refuse an archive that unpacks to more than this.
        max_members: Refuse an archive with more entries than this.

    Returns:
        What was written and where the new installation's data and packs are.

    Raises:
        RestoreError: Not a readable ZIP, not an export, an unsafe entry, too
            large, or ``target`` isn't empty. Nothing is left in ``target``.
        OSError: Writing failed; ``target`` is left as it was.
    """
    archive, target = Path(archive), Path(target).absolute()
    _require_empty(target)
    try:
        zf = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RestoreError(f"{archive} is not a readable ZIP: {exc}") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > max_members:
            raise RestoreError(f"{archive} has {len(infos)} entries; a restore takes at most {max_members}")
        members, skipped = _checked_members(infos, target)
        files = [(info, path) for info, path in members if path is not None]
        if not files:
            raise RestoreError(f"{archive} contains no files")
        if len({str(path) for _, path in files}) != len(files):
            raise RestoreError(f"{archive} lists the same file twice")
        if not any(path.parts[0] in ("systems", "realize-os.yaml") for _, path in files):
            raise RestoreError(f"{archive} has no realize-os.yaml or systems/: not a RealizeOS export")
        needed = sum(info.file_size for info, _ in files)
        if needed > max_total_bytes:
            raise RestoreError(f"{archive} unpacks to {needed} bytes; a restore takes at most {max_total_bytes} bytes")

        target.parent.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(target.parent).free
        if needed > free:
            raise RestoreError(f"The export needs {needed} bytes unpacked; only {free} are free in {target.parent}")
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.restore-", dir=target.parent)).resolve()
        moved = False
        try:
            budget = min(needed, max_total_bytes)
            for info, path in files:
                dest = staging.joinpath(*path.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.resolve().is_relative_to(staging):
                    raise RestoreError(f"{info.filename!r} resolves outside the restore folder")
                budget -= _copy_member(zf, info, dest, budget, archive)
            _require_empty(target)  # still empty: nobody wrote there meanwhile
            if target.is_dir():
                target.rmdir()
            os.replace(staging, target)
            moved = True
        finally:
            if not moved:
                _remove_staging(staging)

    names = [str(path) for _, path in files]
    tops = {path.parts[0] for _, path in files}
    result = RestoreResult(
        target=target,
        files=names,
        skipped=skipped,
        data_path=target / DATA_DIR,
        packs_path=target / CUSTOM_PACKS_DIR if CUSTOM_PACKS_DIR in tops else None,
        inventory=target / INVENTORY_FILE if INVENTORY_FILE in tops else None,
    )
    logger.info("Restored %d file(s) from %s into %s", len(names), archive, target)
    return result
