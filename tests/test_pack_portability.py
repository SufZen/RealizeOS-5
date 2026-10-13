"""Portability (audit 2026-10-13): an export restores the same packs, levels and rules.

The export used to leave out the reviewed levels and any modified or custom
pack. It now carries the verification state, the writable pack folder
(``REALIZE_PACKS_PATH``) and a resolved-pack inventory; restoring into a clean
installation gives the same resolver output.
"""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest
from realize_core.governance.gates import Decider, decide_approval
from realize_core.packs import clear_cache, loader, state
from realize_core.packs.inventory import build_inventory, compare_inventories, venture_resolution
from realize_core.packs.verify import request_verification

PACKS = Path(__file__).parent.parent / "packs"
OWNER = Decider(user_id="owner@x", role="owner", allowed_ventures=None)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def install(tmp_path, monkeypatch):
    """An installation: shipped pt pack, a custom zz pack, a venture using both, approvals recorded."""
    from realize_core.db.schema import init_schema, set_db_path

    shipped = tmp_path / "shipped"
    shutil.copytree(PACKS / "market" / "pt", shipped / "market" / "pt", ignore=shutil.ignore_patterns("reviews"))
    monkeypatch.setattr(loader, "default_packs_root", lambda: shipped)

    kb = tmp_path / "kb"
    data = tmp_path / "data"
    custom = tmp_path / "custom-packs"
    zz = custom / "market" / "zz"
    _write(
        zz / "pack.yaml",
        "id: zz\nkind: market\nversion: 2.1.0\ntitle: Zed\ndefaults: {currency: ZED}\nverification: {level: 1}\n",
    )
    _write(
        zz / "rules" / "tax.md",
        "---\nid: zz.tax\nstatement: Works carry a 9% tax.\nsource: https://zz.example/tax\n"
        "as_of: '2026-10-13'\nreview_by: '2099-01-01'\nverification: 1\n---\nBody.\n",
    )
    _write(zz / ".git" / "config", "[core]\n")  # hidden: never exported
    _write(kb / "systems" / "acme" / "packs.yaml", "market: [zz, pt]\n")
    _write(kb / "systems" / "acme" / "F-foundations" / "overrides" / "defaults.yaml", "units: imperial\n")
    _write(kb / "realize-os.yaml", "features:\n  packs: true\nsystems: []\n")
    _write(kb / ".env", "ANTHROPIC_API_KEY=sk-secret\n")

    monkeypatch.setenv("DATA_PATH", str(data))
    monkeypatch.setenv(loader.PACKS_PATH_ENV, str(custom))
    monkeypatch.setattr(state, "state_path", lambda: state.state_path_in(data))
    monkeypatch.setattr("realize_core.memory.store.DB_PATH", data / "memory.db")
    data.mkdir()
    ops = data / "realize_data.db"
    set_db_path(ops)
    init_schema(ops)
    clear_cache()

    whole = request_verification("acme", kind="market", pack_id="pt", level=2, reviewer="Ana Silva, advogada")
    cards = request_verification("acme", kind="market", pack_id="zz", level=2, reviewer="Z. Reviewer", cards=["zz.tax"])
    for approval_id in (whole, cards):
        assert asyncio.run(decide_approval(approval_id, True, decider=OWNER))["execution"]["success"] is True
    yield {"kb": kb, "data": data, "custom": custom, "shipped": shipped, "tmp": tmp_path}
    set_db_path(None)
    clear_cache()


def _export(kb: Path) -> zipfile.ZipFile:
    from realize_api.routes.storage_settings import _build_export

    target = kb.parent / "export.zip"
    _build_export(kb, target)
    return zipfile.ZipFile(io.BytesIO(target.read_bytes()))


def test_export_carries_state_custom_packs_and_inventory(install):
    archive = _export(install["kb"])
    names = set(archive.namelist())
    assert "data/packs/verification.json" in names
    assert "custom-packs/market/zz/pack.yaml" in names
    assert "custom-packs/market/zz/rules/tax.md" in names
    assert "packs-inventory.json" in names
    assert not any(".git" in n or n.startswith(".env") for n in names)
    assert not any(n.startswith("custom-packs/market/pt") or n.startswith("shipped") for n in names)

    inventory = json.loads(archive.read("packs-inventory.json"))
    assert inventory["packs_feature"] is True
    assert inventory["verification_state"] == "data/packs/verification.json"
    packs = {(p["kind"], p["id"]): p for p in inventory["packs"]}
    assert packs[("market", "pt")]["source"] == "shipped"
    assert packs[("market", "pt")]["verification"] == 2
    assert packs[("market", "zz")]["source"] == "custom"
    assert packs[("market", "zz")]["cards"] == {"zz.tax": 1}  # card at 2, pack itself still at its own level
    acme = inventory["ventures"]["acme"]
    assert [p["id"] for p in acme["packs"]] == ["zz", "pt"]
    assert acme["rules"]["pt.vat.rates"]["verification"] == 2
    assert acme["defaults"]["units"] == {"value": "imperial", "layer": "firm", "pack": None}
    assert "sk-secret" not in archive.read("packs-inventory.json").decode("utf-8")


def test_restore_into_a_clean_installation_resolves_the_same(install, monkeypatch):
    original = venture_resolution(install["kb"] / "systems" / "acme")
    archive = _export(install["kb"])
    exported_inventory = json.loads(archive.read("packs-inventory.json"))

    # A clean installation: nothing from the old one but the release's shipped packs.
    clean = install["tmp"] / "clean"
    restore_kb, restore_data, restore_custom = clean / "kb", clean / "data", clean / "custom-packs"
    for name in archive.namelist():
        if name.startswith("data/"):
            target = restore_data / name[len("data/") :]
        elif name.startswith("custom-packs/"):
            target = restore_custom / name[len("custom-packs/") :]
        else:
            target = restore_kb / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))
    monkeypatch.setenv("DATA_PATH", str(restore_data))
    monkeypatch.setenv(loader.PACKS_PATH_ENV, str(restore_custom))
    monkeypatch.setattr(state, "state_path", lambda: state.state_path_in(restore_data))
    clear_cache()

    restored = venture_resolution(restore_kb / "systems" / "acme")

    assert restored == original
    assert restored["rules"]["zz.tax"]["verification"] == 1  # min(card 2, pack 1)
    assert restored["rules"]["pt.vat.rates"]["verification"] == 2
    assert compare_inventories(exported_inventory, build_inventory(restore_kb)) == []
    # The approvals themselves came along in the database snapshot.
    with sqlite3.connect(restore_data / "realize_data.db") as conn:
        statuses = {r[0] for r in conn.execute("SELECT execution_status FROM approval_queue")}
    assert statuses == {"succeeded"}


def test_restore_without_the_state_is_reported(install, monkeypatch):
    from realize_core.cli_app import app
    from typer.testing import CliRunner

    archive = _export(install["kb"])
    exported = install["tmp"] / "packs-inventory.json"
    exported.write_bytes(archive.read("packs-inventory.json"))
    runner = CliRunner()

    same = runner.invoke(app, ["packs", "inventory", "--kb", str(install["kb"]), "--compare", str(exported)])
    assert same.exit_code == 0, same.output
    assert "Same packs" in same.output

    monkeypatch.setattr(state, "state_path", lambda: install["tmp"] / "nowhere" / "verification.json")
    clear_cache()
    differs = runner.invoke(app, ["packs", "inventory", "--kb", str(install["kb"]), "--compare", str(exported)])
    assert differs.exit_code == 1
    assert "pack market/pt: verification differs" in differs.output
    assert "venture acme: resolved rules differ" in differs.output
