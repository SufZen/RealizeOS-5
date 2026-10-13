"""Inventory of installed packs and what each venture resolves (portability).

The storage export writes this inventory into the ZIP (``packs-inventory.json``)
next to the verification state and the writable pack folder, so a restore into
a clean installation can be checked against it: the same packs, versions,
content and verification levels, and the same rules and defaults for every
venture. ``python cli.py packs inventory --compare packs-inventory.json``
reports any difference.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from realize_core.packs import loader as _loader
from realize_core.packs import state as _state
from realize_core.packs.models import Pack
from realize_core.packs.resolver import PackResolver

logger = logging.getLogger(__name__)

INVENTORY_FORMAT = 1
#: Pack sub-folders the loader never reads (review sheets and records).
_IGNORED_DIRS = frozenset({"reviews"})


_BOM = b"\xef\xbb\xbf"


def normalised_bytes(data: bytes) -> bytes:
    """A file's bytes as hashed: text loses a UTF-8 byte-order mark and ends lines with ``\\n``.

    The same pack checked out on Windows (CRLF, sometimes a BOM) and in the
    Linux image (LF) then hashes the same. Bytes that aren't UTF-8 text are
    hashed as they are.
    """
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    if data.startswith(_BOM):
        data = data[len(_BOM) :]
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def content_hash(pack_root: Path) -> str:
    """SHA-256 over the pack's files (names and contents), leaving out ``reviews/`` and hidden files.

    Text files are hashed with their line endings and byte-order mark
    normalised (:func:`normalised_bytes`), so a Windows checkout and the
    Linux image of the same pack compare equal. A file that can't be read
    gives ``unreadable: ...`` instead, so one bad file never stops an export;
    the comparison then reports the pack.
    """
    digest = hashlib.sha256()
    root = Path(pack_root)
    try:
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if not path.is_file() or rel.parts[0] in _IGNORED_DIRS or any(p.startswith(".") for p in rel.parts):
                continue
            digest.update(rel.as_posix().encode("utf-8") + b"\0")
            digest.update(normalised_bytes(path.read_bytes()))
            digest.update(b"\0")
    except OSError as exc:
        logger.warning("Pack at %s can't be hashed for the inventory: %s", root, exc)
        return f"unreadable: {exc}"
    return digest.hexdigest()


def _source(pack: Pack) -> str:
    custom = _loader.custom_packs_root()
    if custom is not None and custom in pack.root.resolve().parents:
        return "custom"
    return "shipped"


def installed_packs(packs_root: Path | None = None) -> list[dict[str, Any]]:
    """Every installed pack with its version, origin, content hash and effective levels."""
    out: list[dict[str, Any]] = []
    for (kind, pack_id), pack in sorted(_loader.discover_packs(packs_root).items()):
        out.append(
            {
                "kind": kind,
                "id": pack_id,
                "version": pack.version,
                "source": _source(pack),
                "content_sha256": content_hash(pack.root),
                "verification": pack.verification_level,
                "verification_recorded": pack.verification_state is not None,
                "cards": {
                    card_id: card.effective_level(pack.verification_level)
                    for card_id, card in sorted(pack.rules.items())
                },
            }
        )
    return out


def venture_resolution(venture_dir: Path, packs_root: Path | None = None) -> dict[str, Any]:
    """What a venture resolves through its packs: packs, missing packs, defaults and rules with levels."""
    resolver = PackResolver(venture_dir, enabled=True, packs_root=packs_root)
    return {
        "packs": [
            {"kind": p.kind, "id": p.id, "version": p.version, "verification": p.verification_level}
            for p in resolver.packs
        ],
        "missing": list(resolver.missing),
        "defaults": {
            key: {"value": r.value, "layer": r.layer, "pack": r.pack_id}
            for key, r in sorted(resolver.list("default").items())
        },
        "rules": {
            key: {
                "layer": r.layer,
                "pack": r.pack_id,
                "verification": r.verification,
                "statement": r.value.statement,
                "source": r.value.source,
            }
            for key, r in sorted(resolver.list("rule").items())
        },
    }


def build_inventory(
    kb_path: Path, *, packs_root: Path | None = None, packs_enabled: bool | None = None
) -> dict[str, Any]:
    """The installation's pack inventory: installed packs and every venture's resolution.

    Ventures are the folders under ``<kb_path>/systems`` that have a
    ``packs.yaml``. They are resolved with packs on, whatever the feature
    flag (recorded as ``packs_feature``), so the inventory shows what they use.
    """
    from realize_core import __version__

    ventures: dict[str, Any] = {}
    systems = Path(kb_path) / "systems"
    if systems.is_dir():
        for venture_dir in sorted(p for p in systems.iterdir() if p.is_dir() and (p / "packs.yaml").is_file()):
            ventures[venture_dir.name] = venture_resolution(venture_dir, packs_root)
    custom = _loader.custom_packs_root()
    try:
        recorded = _state.state_path().is_file()
    except OSError:
        recorded = False
    return {
        "format": INVENTORY_FORMAT,
        "generated_at": datetime.now(UTC).isoformat(),
        "realizeos_version": __version__,
        "packs_feature": packs_enabled,
        "pack_roots": [
            {"source": "custom" if custom is not None and root == custom else "shipped", "path": str(root)}
            for root in _loader.pack_roots(packs_root)
        ],
        "verification_state": f"data/{_state.STATE_DIR}/{_state.STATE_FILE}" if recorded else None,
        "packs": installed_packs(packs_root),
        "ventures": ventures,
    }


def compare_inventories(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Differences that matter after a restore: packs, content, levels and each venture's resolution.

    Timestamps, folder paths and the RealizeOS version are ignored; a
    differing version of the same pack shows up through its version and hash.
    """
    problems: list[str] = []
    want = {(p["kind"], p["id"]): p for p in expected.get("packs") or []}
    have = {(p["kind"], p["id"]): p for p in actual.get("packs") or []}
    for key in sorted(want.keys() - have.keys()):
        problems.append(f"pack {key[0]}/{key[1]} is missing")
    for key in sorted(have.keys() - want.keys()):
        problems.append(f"pack {key[0]}/{key[1]} is new")
    for key in sorted(want.keys() & have.keys()):
        for field in ("version", "source", "content_sha256", "verification", "cards"):
            if want[key].get(field) != have[key].get(field):
                problems.append(f"pack {key[0]}/{key[1]}: {field} differs")
    want_v, have_v = expected.get("ventures") or {}, actual.get("ventures") or {}
    for name in sorted(want_v.keys() | have_v.keys()):
        if name not in have_v or name not in want_v:
            problems.append(f"venture {name}: {'missing' if name not in have_v else 'new'}")
            continue
        for field in ("packs", "missing", "defaults", "rules"):
            if want_v[name].get(field) != have_v[name].get(field):
                problems.append(f"venture {name}: resolved {field} differ")
    return problems
