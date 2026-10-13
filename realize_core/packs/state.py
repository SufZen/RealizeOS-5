"""Verification state of profession and market packs, kept as operational data (audit N04).

Raising a pack's verification is an approval (``pack_verify``, see
:mod:`realize_core.packs.verify`). It used to rewrite ``pack.yaml`` and the
rule cards inside the installed pack. Shipped packs live in the application
folder, which the production image mounts read-only, so the approval could
not be applied there, and a failure halfway through left some cards changed
and others not.

Now pack files stay as shipped. What an approval decides (level, reviewer,
review date, approver and approval id, for some cards or for the whole pack)
goes into one JSON file under ``DATA_PATH``::

    DATA_PATH/packs/verification.json

Each approval rewrites that file once and atomically (a temporary file next
to it, flushed to disk, then renamed over it), so a failure leaves the old
state or the new one, never part of it. The loader lays the state over every
pack it loads (:func:`apply_state`), so the resolver, chat context, MCP tools
and the wedge all see the effective levels. The location is fixed relative to
``DATA_PATH``: no setting points it anywhere else.

File format::

    {"format": 1,
     "packs": {"market/pt": {
        "version": "0.1.0",                     # pack version when approved
        "pack": {"level": 2, "reviewed_by": ..., "reviewed_at": ...,
                 "approved_by": ..., "approval_id": ...},   # whole-pack approvals only
        "cards": {"pt.vat.rates": {"verification": 2, "verified_by": ...,
                  "reviewed_at": ..., "approved_by": ..., "approval_id": ...}},
        "updated_at": "..."}}}
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from realize_core.packs.models import Pack

logger = logging.getLogger(__name__)

STATE_FORMAT = 1
STATE_DIR = "packs"
STATE_FILE = "verification.json"

#: How long a writer waits for another writer (seconds).
LOCK_TIMEOUT = 20.0
#: A lock file older than this is left over from a process that died (seconds).
#: A write takes milliseconds; shorter than the wait, so a stale lock is cleared
#: by the next writer instead of failing it.
STALE_LOCK_SECONDS = 15.0
#: Windows refuses to rename over a file another thread is reading at that
#: instant; the rename is retried this many times.
_REPLACE_ATTEMPTS = 5

#: Pack-level fields an approval records (merged over the manifest's ``verification``).
_PACK_FIELDS = ("level", "reviewed_by", "reviewed_at", "approved_by", "approval_id", "partner_agreement", "corrections")


class VerificationStateError(OSError):
    """The verification state can't be located, read for an update, or written."""


_cache_lock = threading.Lock()
_cached: tuple[tuple, dict[str, Any]] | None = None
_write_thread_lock = threading.Lock()
#: Bumped on every write by this process, so the resolver cache sees it even
#: when the file's size and timestamp happen to repeat.
_generation = 0


def state_key(kind: str, pack_id: str) -> str:
    """The key a pack has in the state file: ``<kind>/<id>``."""
    return f"{kind}/{pack_id}"


def state_path_in(base: Path) -> Path:
    """``<base>/packs/verification.json``, refusing a path that leaves ``base``.

    Raises:
        VerificationStateError: The path resolves outside ``base`` (for
            example through a symlinked ``packs`` folder).
    """
    base = Path(base).resolve()
    path = base / STATE_DIR / STATE_FILE
    if base not in path.resolve().parents:
        raise VerificationStateError(f"{path} resolves outside DATA_PATH ({base}); the pack state isn't used")
    return path


def state_path() -> Path:
    """``DATA_PATH/packs/verification.json``; the state is never read or written anywhere else.

    Raises:
        VerificationStateError: The path resolves outside ``DATA_PATH``.
    """
    from realize_core.config import data_dir

    return state_path_in(data_dir())


def _empty() -> dict[str, Any]:
    return {"format": STATE_FORMAT, "packs": {}}


def _stat_key(path: Path) -> tuple | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (str(path), st.st_size, st.st_mtime_ns, st.st_ino)


def fingerprint() -> tuple:
    """What the resolver cache compares to notice a change in the state (audit N07)."""
    try:
        path = state_path()
    except VerificationStateError as exc:
        return (_generation, "unusable", str(exc))
    try:
        key = _stat_key(path)
    except OSError as exc:
        return (_generation, str(path), "unreadable", str(exc))
    return (_generation, key or (str(path), None))


def _parse(path: Path) -> dict[str, Any]:
    """Read and check the state file. Raises :class:`VerificationStateError` when it can't be used."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VerificationStateError(f"cannot read {path} ({exc})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("packs"), dict):
        raise VerificationStateError(f"{path} is not a pack verification state file")
    return data


def load_state() -> dict[str, Any]:
    """The recorded verification state; empty when nothing has been approved yet.

    An unusable file is reported once and treated as empty, so packs fall back
    to the levels in their own files, never to a higher level.
    """
    global _cached
    from realize_core.packs.loader import warn_once

    try:
        path = state_path()
        key = _stat_key(path)
    except OSError as exc:
        warn_once("Pack verification state unavailable: %s", exc)
        return _empty()
    if key is None:
        return _empty()
    with _cache_lock:
        if _cached is not None and _cached[0] == key:
            return _cached[1]
    try:
        data = _parse(path)
    except VerificationStateError as exc:
        warn_once("Pack verification state ignored, levels come from the pack files: %s", exc)
        return _empty()
    with _cache_lock:
        _cached = (key, data)
    return data


def _valid_level(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4:
        return None
    return value


def apply_state(pack: Pack) -> None:
    """Lay the recorded verification state over a loaded pack.

    Sets the pack's level (whole-pack approvals) and each recorded card's
    level, reviewer and review date. The usual rules still apply on top: a
    card's effective level is the lower of its own and the pack's, and a card
    past its ``review_by`` date drops to level 1.
    """
    entry = load_state()["packs"].get(state_key(pack.kind, pack.id))
    if not isinstance(entry, dict):
        return
    applied: dict[str, Any] = {}
    whole = entry.get("pack")
    if isinstance(whole, dict) and _valid_level(whole.get("level")) is not None:
        pack.verification_level = whole["level"]
        pack.verification = {**pack.verification, **{k: whole[k] for k in _PACK_FIELDS if k in whole}}
        applied["pack"] = dict(whole)
    cards = entry.get("cards") if isinstance(entry.get("cards"), dict) else {}
    applied_cards: dict[str, Any] = {}
    for card_id, record in cards.items():
        card = pack.rules.get(card_id)
        level = _valid_level(record.get("verification")) if isinstance(record, dict) else None
        if card is None or level is None:
            continue
        card.verification = level
        if record.get("verified_by"):
            card.verified_by = str(record["verified_by"])
        if record.get("reviewed_at"):
            card.reviewed_at = str(record["reviewed_at"])
        applied_cards[card_id] = dict(record)
    if applied_cards:
        applied["cards"] = applied_cards
    if not applied:
        return
    version = entry.get("version")
    applied["version"] = version
    pack.verification_state = applied
    if version and str(version) != pack.version:
        pack.warnings.append(
            f"verification was approved for version {version}; version {pack.version} is installed. "
            "Review the changed cards again."
        )


def _acquire(lock: Path) -> int:
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > STALE_LOCK_SECONDS:
                    logger.warning("Removing a stale pack verification lock %s", lock)
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise VerificationStateError(f"another approval is writing {lock.parent}; try again") from None
            time.sleep(0.05)


@contextlib.contextmanager
def _write_lock(path: Path) -> Iterator[None]:
    """One writer at a time: a thread lock here, and a lock file for other processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    with _write_thread_lock:
        fd = _acquire(lock)
        try:
            yield
        finally:
            os.close(fd)
            with contextlib.suppress(FileNotFoundError):
                lock.unlink()


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Replace ``path`` with ``data`` in one step: write a temp file, flush it, rename it over."""
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == _REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(0.05)
        replaced = True
    finally:
        if not replaced:
            with contextlib.suppress(OSError):
                tmp.unlink()


def record_verification(
    kind: str,
    pack_id: str,
    *,
    version: str,
    level: int,
    reviewer: str,
    approved_by: str,
    approval_id: str | None,
    cards: list[str],
    whole_pack: bool,
    partner_agreement: str | None = None,
    corrections: dict[str, Any] | None = None,
    today: str,
) -> dict[str, Any]:
    """Record one approved verification in a single atomic write. Returns the pack's new entry.

    Args:
        kind: ``market`` or ``profession``.
        pack_id: The pack's id.
        version: The pack's version now (kept to flag a later version change).
        level: The level granted (2 or 3; checked by the caller).
        reviewer: The named professional who reviewed.
        approved_by: The person who approved the request.
        approval_id: The ``pack_verify`` approval.
        cards: Rule card ids raised to ``level``.
        whole_pack: The pack's own level is raised too.
        partner_agreement: The maintenance agreement (level 3).
        corrections: Facts corrected per card, from the review.
        today: The review date to record (ISO date).

    Raises:
        VerificationStateError: The state file can't be read for the update
            (it is never overwritten then) or can't be written.
    """
    global _generation
    path = state_path()
    key = state_key(kind, pack_id)
    with _write_lock(path):
        data = _parse(path) if path.exists() else _empty()
        entry = dict(data["packs"].get(key) or {})
        stamp = {"verified_by": reviewer, "reviewed_at": today, "approved_by": approved_by, "approval_id": approval_id}
        card_state = dict(entry.get("cards") or {})
        for card_id in cards:
            card_state[card_id] = {"verification": level, **stamp}
        entry["cards"] = card_state
        entry["version"] = version
        if whole_pack:
            pack_entry = dict(entry.get("pack") or {})
            pack_entry.update(
                {
                    "level": level,
                    "reviewed_by": reviewer,
                    "reviewed_at": today,
                    "approved_by": approved_by,
                    "approval_id": approval_id,
                }
            )
            if level == 3:
                pack_entry["partner_agreement"] = partner_agreement
            if corrections:
                pack_entry["corrections"] = dict(corrections)
            entry["pack"] = pack_entry
        entry["updated_at"] = datetime.now(UTC).isoformat()
        data["packs"][key] = entry
        data["format"] = STATE_FORMAT
        _atomic_write(path, data)
        _generation += 1
    logger.info("Pack %s verification %s recorded in %s (approval %s)", key, level, path, approval_id)
    return entry


def clear_cache() -> None:
    """Forget the cached state (tests and config reloads)."""
    global _cached
    with _cache_lock:
        _cached = None
