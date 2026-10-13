"""Audit N07: the resolver cache notices every change, not only a newer newest file.

The cache used to compare the newest modification time among all pack files.
Editing a file that isn't the newest (for example when another file is dated
in the future) kept the old rules. It now compares every file's path, size,
modification time and file id, plus the recorded verification state.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import yaml
from realize_core.packs import clear_cache, get_resolver, state


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _manifest(currency: str) -> str:
    return yaml.safe_dump(
        {"id": "m", "kind": "market", "version": "1.0.0", "title": "M", "defaults": {"currency": currency}}
    )


def _rule(rid: str, statement: str) -> str:
    meta = {"id": rid, "statement": statement, "source": "https://example.org", "as_of": "2026-10-13"}
    return "---\n" + yaml.safe_dump(meta) + "---\n"


def _set_mtime(path: Path, seconds_from_now: float) -> None:
    when = time.time() + seconds_from_now
    os.utime(path, (when, when))


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / "packs"
    _write(root / "market" / "m" / "pack.yaml", _manifest("OLD"))
    _write(root / "market" / "m" / "rules" / "a.md", _rule("m.a", "Rule A."))
    _write(root / "market" / "other" / "pack.yaml", "id: other\nkind: market\nversion: 1\n")
    venture = tmp_path / "systems" / "v"
    _write(venture / "packs.yaml", "market: [m]\n")
    clear_cache()
    yield root, venture
    clear_cache()


def _resolver(layout):
    root, venture = layout
    return get_resolver(venture, enabled=True, packs_root=root)


def test_unchanged_files_reuse_the_cached_resolver(layout):
    assert _resolver(layout) is _resolver(layout)


def test_the_audit_reproduction_future_dated_unrelated_file(layout):
    root, _ = layout
    _set_mtime(root / "market" / "other" / "pack.yaml", 3600)  # an unrelated file dated an hour ahead
    first = _resolver(layout)
    assert first.resolve("default", "currency").value == "OLD"
    manifest = root / "market" / "m" / "pack.yaml"
    manifest.write_text(_manifest("NEW"), encoding="utf-8")  # same size as before
    _set_mtime(manifest, 5)  # still older than the future-dated file

    second = _resolver(layout)

    assert second is not first
    assert second.resolve("default", "currency").value == "NEW"


def test_editing_a_file_that_is_not_the_newest(layout):
    root, _ = layout
    first = _resolver(layout)
    _write(root / "market" / "m" / "rules" / "z.md", _rule("m.z", "Newest file."))
    _set_mtime(root / "market" / "m" / "rules" / "z.md", 600)
    assert _resolver(layout) is not first
    second = _resolver(layout)
    card = root / "market" / "m" / "rules" / "a.md"
    stamp = card.stat().st_mtime
    card.write_text(_rule("m.a", "Rule A, revised."), encoding="utf-8")
    os.utime(card, (stamp, stamp + 1))
    third = _resolver(layout)
    assert third is not second
    assert third.resolve("rule", "m.a").value.statement == "Rule A, revised."


def test_deleting_a_file(layout):
    root, _ = layout
    first = _resolver(layout)
    assert first.resolve("rule", "m.a") is not None
    (root / "market" / "m" / "rules" / "a.md").unlink()
    second = _resolver(layout)
    assert second is not first
    assert second.resolve("rule", "m.a") is None


def test_adding_a_file_with_an_old_timestamp(layout):
    root, _ = layout
    first = _resolver(layout)
    added = root / "market" / "m" / "rules" / "b.md"
    _write(added, _rule("m.b", "Rule B."))
    _set_mtime(added, -86400)  # e.g. copied in with its original date
    second = _resolver(layout)
    assert second is not first
    assert second.resolve("rule", "m.b") is not None


def test_firm_override_and_packs_yaml_changes(layout):
    root, venture = layout
    first = _resolver(layout)
    _write(venture / "F-foundations" / "overrides" / "defaults.yaml", "currency: FIRM\n")
    _set_mtime(venture / "F-foundations" / "overrides" / "defaults.yaml", -86400)
    second = _resolver(layout)
    assert second is not first
    assert second.resolve("default", "currency").value == "FIRM"
    (venture / "packs.yaml").write_text("market: [other]\n", encoding="utf-8")
    assert [p.id for p in _resolver(layout).packs] == ["other"]


def test_recorded_verification_invalidates(layout):
    root, _ = layout
    first = _resolver(layout)
    assert first.resolve("rule", "m.a").verification == 1
    state.record_verification(
        "market",
        "m",
        version="1.0.0",
        level=2,
        reviewer="R",
        approved_by="owner",
        approval_id="a1",
        cards=["m.a"],
        whole_pack=True,
        today="2026-10-13",
    )
    second = _resolver(layout)
    assert second is not first
    assert second.resolve("rule", "m.a").verification == 2
