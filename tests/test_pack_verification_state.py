"""Audit N04: pack verification is applied as operational data, and its outcome is stored.

- The approval's outcome has the same shape as a tool action's and is stored
  on the row (``execution_status``, ``result_json``, ``error``).
- Pack files are never written: shipped packs can be read-only, as in the
  production image. The state goes to ``DATA_PATH/packs/verification.json``
  in one atomic write, so a failure leaves no partial multi-card state.
- ``REALIZE_PACKS_PATH`` adds a writable folder for the firm's own packs.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import threading
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from realize_core.governance.gates import Decider, decide_approval
from realize_core.packs import PackResolver, clear_cache, load_pack, loader, state
from realize_core.packs.verify import apply_verification, request_verification

PACKS = Path(__file__).parent.parent / "packs"
OWNER = Decider(user_id="owner@x", role="owner", allowed_ventures=None)


@pytest.fixture
def db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


@pytest.fixture
def shipped(tmp_path, monkeypatch) -> Path:
    """A copy of the Portugal pack as the shipped packs folder."""
    root = tmp_path / "shipped"
    shutil.copytree(PACKS / "market" / "pt", root / "market" / "pt", ignore=shutil.ignore_patterns("reviews"))
    monkeypatch.setattr(loader, "default_packs_root", lambda: root)
    clear_cache()
    yield root
    clear_cache()


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()
    }


def _row(approval_id: str) -> dict:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        return dict(conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone())
    finally:
        conn.close()


def _approve(approval_id: str) -> dict:
    return asyncio.run(decide_approval(approval_id, True, decider=OWNER))


# ---------------------------------------------------------------------------
# Outcome shape and persistence
# ---------------------------------------------------------------------------


def test_failure_is_returned_in_the_tool_shape_and_stored(db, shipped):
    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="R")
    shutil.rmtree(shipped / "market" / "pt")  # uninstalled before the decision

    out = _approve(approval_id)

    execution = out["execution"]
    assert execution == {
        "executed": True,
        "success": False,
        "output": "",
        "error": "Verification not applied: Pack market/pt is not installed",
    }
    row = _row(approval_id)
    assert row["status"] == "approved"
    assert row["execution_status"] == "failed"
    assert row["error"] == execution["error"]
    assert json.loads(row["result_json"]) == {"output": ""}
    assert row["executed_at"]
    assert out["approval"]["execution_status"] == "failed"  # the response shows it too


def test_success_is_stored_like_a_tool_execution(db, shipped):
    approval_id = request_verification(
        "ops", kind="market", pack_id="pt", level=2, reviewer="Ana", cards=["pt.vat.rates"]
    )
    execution = _approve(approval_id)["execution"]
    assert execution["success"] is True
    assert execution["output"].startswith(
        "1 rule card(s) of market/pt raised to verification 2 (reviewed): pt.vat.rates"
    )
    row = _row(approval_id)
    assert row["execution_status"] == "succeeded"
    assert json.loads(row["result_json"]) == {"output": execution["output"]}


def test_an_applied_verification_is_not_applied_twice(db, shipped):
    from realize_core.governance.gates import _apply_pack_verification

    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="R")
    assert _approve(approval_id)["execution"]["success"] is True
    assert asyncio.run(decide_approval(approval_id, True, decider=OWNER)) is None  # no longer pending
    again = asyncio.run(_apply_pack_verification(approval_id))
    assert again == {"executed": False, "success": False, "output": "", "error": None}


def test_level_three_still_needs_a_partner_agreement_when_applied(db, shipped):
    """Parameters edited after the request are checked again when applied."""
    from realize_core.db.schema import get_connection

    approval_id = request_verification(
        "ops", kind="market", pack_id="pt", level=3, reviewer="R", partner_agreement="PA-1"
    )
    conn = get_connection()
    params = json.loads(conn.execute("SELECT params_json FROM approval_queue WHERE id=?", (approval_id,)).fetchone()[0])
    params["partner_agreement"] = ""
    conn.execute("UPDATE approval_queue SET params_json = ? WHERE id = ?", (json.dumps(params), approval_id))
    conn.commit()
    conn.close()

    execution = _approve(approval_id)["execution"]
    assert execution["success"] is False
    assert "partner maintenance agreement" in execution["error"]
    assert not state.state_path().exists()


def test_level_three_records_the_agreement(db, shipped):
    approval_id = request_verification(
        "ops", kind="market", pack_id="pt", level=3, reviewer="R", partner_agreement="PA-2026-01"
    )
    assert _approve(approval_id)["execution"]["success"] is True
    pack = load_pack(shipped / "market" / "pt")
    assert pack.verification_level == 3
    assert pack.verification["partner_agreement"] == "PA-2026-01"


def test_an_expired_review_date_still_drops_a_card_to_level_one(db, shipped):
    """A card past its file's ``review_by`` that no approval covers stays at level 1."""
    card = shipped / "market" / "pt" / "rules" / "vat-rates.md"
    past = (date.today() - timedelta(days=1)).isoformat()
    text = card.read_text(encoding="utf-8")
    card.write_text(text.replace("review_by: '2027-04-13'", f"review_by: '{past}'"), encoding="utf-8")
    assert f"review_by: '{past}'" in card.read_text(encoding="utf-8")

    approval_id = request_verification(
        "ops", kind="market", pack_id="pt", level=2, reviewer="R", cards=["pt.contracts.price-revision"]
    )
    assert _approve(approval_id)["execution"]["success"] is True
    manifest = shipped / "market" / "pt" / "pack.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("level: 1", "level: 2", 1), encoding="utf-8"
    )  # the pack's own level, so the approved card shows 2

    venture = shipped.parent / "systems" / "pt-dev"
    venture.mkdir(parents=True)
    (venture / "packs.yaml").write_text("market: [pt]\n", encoding="utf-8")
    resolver = PackResolver(venture, enabled=True)
    assert resolver.resolve("rule", "pt.vat.rates").verification == 1
    assert resolver.resolve("rule", "pt.contracts.price-revision").verification == 2


def test_a_recorded_review_date_that_passed_drops_a_card_to_level_one(db, shipped):
    """The next review date an approval recorded expires the card like a file date does."""
    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="R")
    assert _approve(approval_id)["execution"]["success"] is True
    path = state.state_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    past = (date.today() - timedelta(days=1)).isoformat()
    data["packs"]["market/pt"]["cards"]["pt.vat.rates"]["review_by"] = past
    path.write_text(json.dumps(data), encoding="utf-8")
    clear_cache()

    pack = load_pack(shipped / "market" / "pt")
    assert pack.rules["pt.vat.rates"].review_by == past
    assert pack.rules["pt.vat.rates"].effective_level(pack.verification_level) == 1
    assert pack.rules["pt.contracts.price-revision"].effective_level(pack.verification_level) == 2


# ---------------------------------------------------------------------------
# Read-only shipped packs, writable data
# ---------------------------------------------------------------------------


def _deny_writes_under(root: Path, monkeypatch) -> list[str]:
    """Make every write API refuse paths under ``root``, as a read-only mount would."""
    attempts: list[str] = []
    root = root.resolve()

    def guarded(path) -> bool:
        try:
            inside = root in Path(path).resolve().parents or Path(path).resolve() == root
        except (OSError, TypeError):
            return False
        if inside:
            attempts.append(str(path))
        return inside

    real_open, real_replace, real_mkstemp = open, os.replace, __import__("tempfile").mkstemp
    real_write_text, real_write_bytes, real_mkdir = Path.write_text, Path.write_bytes, Path.mkdir

    def fake_open(file, mode="r", *args, **kwargs):
        if any(m in mode for m in "wax+") and not isinstance(file, int) and guarded(file):
            raise PermissionError(f"read-only file system: {file}")
        return real_open(file, mode, *args, **kwargs)

    def fake_replace(src, dst, *args, **kwargs):
        if guarded(dst) or guarded(src):
            raise PermissionError(f"read-only file system: {dst}")
        return real_replace(src, dst, *args, **kwargs)

    def fake_mkstemp(*args, dir=None, **kwargs):
        if dir is not None and guarded(dir):
            raise PermissionError(f"read-only file system: {dir}")
        return real_mkstemp(*args, dir=dir, **kwargs)

    def fake_write_text(self, *args, **kwargs):
        if guarded(self):
            raise PermissionError(f"read-only file system: {self}")
        return real_write_text(self, *args, **kwargs)

    def fake_write_bytes(self, *args, **kwargs):
        if guarded(self):
            raise PermissionError(f"read-only file system: {self}")
        return real_write_bytes(self, *args, **kwargs)

    def fake_mkdir(self, *args, **kwargs):
        if guarded(self) and not self.exists():
            raise PermissionError(f"read-only file system: {self}")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    monkeypatch.setattr(os, "replace", fake_replace)
    monkeypatch.setattr("tempfile.mkstemp", fake_mkstemp)
    monkeypatch.setattr(Path, "write_text", fake_write_text)
    monkeypatch.setattr(Path, "write_bytes", fake_write_bytes)
    monkeypatch.setattr(Path, "mkdir", fake_mkdir)
    return attempts


def test_read_only_shipped_packs_with_a_writable_data_dir(db, shipped, tmp_path, monkeypatch):
    """The production layout: /app/packs read-only, DATA_PATH writable (simulated on every OS)."""
    monkeypatch.setattr(state, "state_path", lambda: tmp_path / "data" / "packs" / "verification.json")
    before = _snapshot(shipped)
    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="Ana Silva")
    attempts = _deny_writes_under(shipped, monkeypatch)

    out = _approve(approval_id)

    assert out["execution"]["success"] is True, out["execution"]
    assert attempts == []  # nothing even tried to write into the packs folder
    assert _snapshot(shipped) == before
    assert (tmp_path / "data" / "packs" / "verification.json").is_file()
    pack = load_pack(shipped / "market" / "pt")
    assert pack.verification_level == 2
    assert {c.verification for c in pack.rules.values()} == {2}


@pytest.mark.skipif(sys.platform == "win32", reason="Windows ignores the read-only attribute on folders")
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores POSIX permission bits")
def test_read_only_shipped_packs_posix_permissions(db, shipped, tmp_path, monkeypatch):
    """The same with real permission bits: the packs tree is read-only for this process."""
    import stat

    monkeypatch.setattr(state, "state_path", lambda: tmp_path / "data" / "packs" / "verification.json")
    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="Ana Silva")
    before = _snapshot(shipped)
    paths = sorted(shipped.rglob("*"), reverse=True) + [shipped]
    for path in paths:
        mode = path.stat().st_mode
        path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    try:
        with pytest.raises(PermissionError):
            (shipped / "market" / "pt" / "probe").write_text("x", encoding="utf-8")
        out = _approve(approval_id)
    finally:
        for path in reversed(paths):
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
    assert out["execution"]["success"] is True, out["execution"]
    assert _snapshot(shipped) == before
    assert load_pack(shipped / "market" / "pt").verification_level == 2


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


def _leftovers(path: Path) -> list[str]:
    return sorted(p.name for p in path.parent.iterdir() if p.name != path.name) if path.parent.is_dir() else []


def test_failed_rename_leaves_no_partial_state(db, shipped, monkeypatch):
    first = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="R", cards=["pt.vat.rates"])
    assert _approve(first)["execution"]["success"] is True
    path = state.state_path()
    before = path.read_bytes()

    second = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="R2")  # whole pack

    def fail(*args, **kwargs):
        raise OSError("disk went away")

    with monkeypatch.context() as patched:
        patched.setattr(os, "replace", fail)
        execution = _approve(second)["execution"]

    assert execution["success"] is False
    assert "disk went away" in execution["error"]
    assert _row(second)["execution_status"] == "failed"
    assert path.read_bytes() == before  # all or nothing: still only the first approval
    assert _leftovers(path) == []
    clear_cache()
    pack = load_pack(shipped / "market" / "pt")
    assert pack.verification_level == 1
    assert pack.rules["pt.vat.rates"].verification == 2
    assert pack.rules["pt.contracts.price-revision"].verification == 1


def test_failure_during_the_write_leaves_no_partial_state(db, shipped, monkeypatch):
    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="R")
    calls = []

    def fail_fsync(fd):
        calls.append(fd)
        raise OSError("I/O error while flushing")

    with monkeypatch.context() as patched:
        patched.setattr(os, "fsync", fail_fsync)
        execution = _approve(approval_id)["execution"]

    assert calls  # the temporary file had been written when it failed
    assert execution["success"] is False
    path = state.state_path()
    assert not path.exists()
    assert _leftovers(path) == []
    assert load_pack(shipped / "market" / "pt").verification_level == 1


def test_an_unreadable_state_file_is_never_overwritten(db, shipped, caplog):
    path = state.state_path()
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="R")

    execution = _approve(approval_id)["execution"]

    assert execution["success"] is False
    assert "cannot read" in execution["error"]
    assert path.read_text(encoding="utf-8") == "{not json"
    # Reading falls back to the pack files' own levels, with a warning.
    with caplog.at_level("WARNING"):
        assert load_pack(shipped / "market" / "pt").verification_level == 1


def test_concurrent_approvals_both_land(shipped):
    pack = load_pack(shipped / "market" / "pt")
    ids = sorted(pack.rules)[:6]
    errors: list[BaseException] = []

    def record(card_id: str) -> None:
        try:
            apply_verification(
                {"kind": "market", "pack_id": "pt", "level": 2, "reviewer": "R", "cards": [card_id]}, "owner"
            )
        except (OSError, ValueError) as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=record, args=(card_id,)) for card_id in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    recorded = json.loads(state.state_path().read_text(encoding="utf-8"))["packs"]["market/pt"]["cards"]
    assert sorted(recorded) == ids


def test_state_lives_under_data_path(tmp_path, monkeypatch):
    monkeypatch.undo()  # the real state_path, not the per-test one from conftest
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "data"))
    assert state.state_path() == (tmp_path / "data").resolve() / "packs" / "verification.json"
    assert state.state_path_in(tmp_path / "x") == (tmp_path / "x").resolve() / "packs" / "verification.json"


def test_state_path_cannot_leave_the_data_dir(tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    base = tmp_path / "data2"
    base.mkdir()
    try:
        (base / "packs").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need extra rights on this Windows account")
    with pytest.raises(state.VerificationStateError, match="outside DATA_PATH"):
        state.state_path_in(base)


def test_version_change_after_approval_is_flagged(db, shipped):
    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="R")
    assert _approve(approval_id)["execution"]["success"] is True
    manifest = shipped / "market" / "pt" / "pack.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["version"] = "0.2.0"
    manifest.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    pack = load_pack(shipped / "market" / "pt")
    assert pack.verification_level == 2
    assert any("approved for version 0.1.0" in w for w in pack.warnings)


# ---------------------------------------------------------------------------
# Writable pack folder (REALIZE_PACKS_PATH)
# ---------------------------------------------------------------------------


def test_custom_pack_folder_adds_and_replaces_packs(shipped, tmp_path, monkeypatch):
    custom = tmp_path / "custom"
    shutil.copytree(shipped / "market" / "pt", custom / "market" / "pt")
    manifest = custom / "market" / "pt" / "pack.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["title"] = "Portugal (firm edition)"
    manifest.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    zz = custom / "market" / "zz"
    zz.mkdir(parents=True)
    (zz / "pack.yaml").write_text("id: zz\nkind: market\nversion: 1.0.0\ntitle: Zed\n", encoding="utf-8")
    monkeypatch.setenv(loader.PACKS_PATH_ENV, str(custom))

    assert loader.pack_roots() == [custom.resolve(), shipped]
    found = loader.discover_packs()
    assert found[("market", "pt")].title == "Portugal (firm edition)"
    assert ("market", "zz") in found
    venture = tmp_path / "systems" / "firm"
    venture.mkdir(parents=True)
    (venture / "packs.yaml").write_text("market: [zz, pt]\n", encoding="utf-8")
    resolver = PackResolver(venture, enabled=True)
    assert [p.title for p in resolver.packs] == ["Zed", "Portugal (firm edition)"]
    assert resolver.missing == []


def test_custom_pack_folder_that_does_not_exist_is_ignored(shipped, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(loader.PACKS_PATH_ENV, str(tmp_path / "missing"))
    with caplog.at_level("WARNING"):
        assert loader.pack_roots() == [shipped]
    assert ("market", "pt") in loader.discover_packs()
