"""Audit N06: a malformed pack can't stop a venture that doesn't use it.

The loader checks every file's shape before reading a field, a pack that
still fails is skipped with a warning naming its folder, and a resolver loads
only the packs its venture names.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest
import yaml
from realize_core.packs import PackResolver, build_pack_context, clear_cache, discover_packs, load_pack, loader

PACKS = Path(__file__).parent.parent / "packs"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rule(rid: str, **extra) -> str:
    meta = {"id": rid, "statement": f"Statement {rid}.", "source": "https://example.org", "as_of": "2026-10-13"}
    meta.update(extra)
    return "---\n" + yaml.safe_dump(meta, allow_unicode=True) + "---\nBody.\n"


@pytest.fixture
def root(tmp_path, monkeypatch) -> Path:
    """A valid market pack ``test`` and a broken profession pack ``unrelated`` nobody uses."""
    root = tmp_path / "packs"
    good = root / "market" / "test"
    _write(good / "pack.yaml", "id: test\nkind: market\nversion: 1.0.0\ntitle: Test\ndefaults: {currency: TST}\n")
    _write(good / "glossary" / "en.yaml", "- {term: interim claim, family: money-event, kind: payment_claim}\n")
    _write(good / "rules" / "r1.md", _rule("test.r1", applies_to={"family": "money-event", "kinds": ["payment_claim"]}))
    bad = root / "profession" / "unrelated"
    _write(bad / "pack.yaml", "id: unrelated\nkind: profession\nversion: 0.1.0\n")
    _write(bad / "R-routines" / "skills" / "broken.yaml", "- unexpected\n- list\n")
    monkeypatch.setattr(loader, "default_packs_root", lambda: root)
    clear_cache()
    yield root
    clear_cache()


@pytest.fixture
def venture(tmp_path) -> Path:
    v = tmp_path / "systems" / "acme"
    _write(v / "packs.yaml", "market: [test]\n")
    return v


def test_the_audit_reproduction_no_longer_raises(root, venture):
    """A skill YAML that is a list used to raise AttributeError for every venture."""
    resolver = PackResolver(venture, enabled=True)
    assert [p.id for p in resolver.packs] == ["test"]
    assert resolver.resolve("default", "currency").value == "TST"
    unrelated = load_pack(root / "profession" / "unrelated")
    assert unrelated is not None
    assert unrelated.skills == {}
    assert any("broken.yaml: a skill must be a mapping" in w for w in unrelated.warnings)


def test_resolver_loads_only_the_packs_its_venture_names(root, venture, monkeypatch):
    loaded: list[str] = []
    real = loader.load_pack

    def spy(path, **kwargs):
        loaded.append(Path(path).name)
        return real(path, **kwargs)

    monkeypatch.setattr(loader, "load_pack", spy)
    PackResolver(venture, enabled=True)
    assert loaded == ["test"]


def test_a_pack_that_still_fails_is_skipped_with_its_path(root, venture, monkeypatch, caplog):
    real = loader._load_content

    def explode(pack, pack_root):
        if pack.id == "unrelated":
            raise AttributeError("'list' object has no attribute 'get'")
        return real(pack, pack_root)

    monkeypatch.setattr(loader, "_load_content", explode)
    with caplog.at_level(logging.WARNING, logger="realize_core.packs.loader"):
        found = discover_packs()
    assert ("market", "test") in found
    assert ("profession", "unrelated") not in found
    messages = [r.getMessage() for r in caplog.records]
    assert any(str(root / "profession" / "unrelated") in m and "skipped" in m for m in messages)
    assert PackResolver(venture, enabled=True).packs[0].id == "test"


def test_warnings_are_logged_once(root, caplog, monkeypatch):
    monkeypatch.setattr(loader, "_warned", set())
    with caplog.at_level(logging.DEBUG, logger="realize_core.packs.loader"):
        discover_packs()
        discover_packs()
    about = [r for r in caplog.records if "broken.yaml" in r.getMessage()]
    assert [r.levelno for r in about] == [logging.WARNING, logging.DEBUG]
    assert str(root / "profession" / "unrelated") in about[0].getMessage()


@pytest.mark.parametrize(
    ("relpath", "content", "warning"),
    [
        ("pack.yaml", "id: x\nkind: market\nversion: 1\ndefaults: [a, b]\n", "defaults must be a mapping"),
        ("pack.yaml", "id: x\nkind: market\nversion: 1\nlanguages: 7\n", "languages must be a list"),
        ("pack.yaml", "id: x\nkind: market\nversion: 1\nverification: {level: high}\n", "not a whole number"),
        ("glossary/en.yaml", "{term: a, family: b}\n", "glossary must be a list"),
        ("glossary/en.yaml", "- {term: a, family: b, kind: [x]}\n", "has a kind that isn't text"),
        ("rules/r.md", _rule("x.r", applies_to=["money-event"]), "applies_to must be a mapping"),
        ("rules/r.md", _rule("x.r", applies_to={"kinds": 5}), "applies_to.kinds must be a list"),
        ("trust.yaml", "- approve\n", "trust.yaml: must be a mapping"),
        ("measures.yaml", "{id: m}\n", "measures.yaml: must be a list"),
        ("schemas/s.json", "[1, 2]", "a schema must be a JSON object"),
    ],
)
def test_wrong_shapes_become_warnings(tmp_path, relpath, content, warning):
    pack_dir = tmp_path / "market" / "x"
    if relpath != "pack.yaml":
        _write(pack_dir / "pack.yaml", "id: x\nkind: market\nversion: 1\n")
    _write(pack_dir / relpath, content)
    pack = load_pack(pack_dir)
    assert pack is not None
    assert any(warning in w for w in pack.warnings), pack.warnings
    resolver = PackResolver(tmp_path / "v", enabled=True, available={("market", "x"): pack})
    build_pack_context(resolver, "a message about a")  # never raises


def test_undecodable_and_binary_files_are_warnings(tmp_path):
    pack_dir = tmp_path / "market" / "x"
    _write(pack_dir / "pack.yaml", "id: x\nkind: market\nversion: 1\n")
    (pack_dir / "rules").mkdir()
    (pack_dir / "rules" / "bin.md").write_bytes(b"---\n\xff\xfe\x00 not text\n---\n")
    (pack_dir / "glossary").mkdir()
    (pack_dir / "glossary" / "en.yaml").write_bytes(b"\xff\xfe\x00")
    pack = load_pack(pack_dir)
    assert pack is not None
    assert pack.rules == {}
    assert len(pack.warnings) == 2


def test_manifest_that_is_not_a_mapping_skips_only_that_pack(root):
    _write(root / "market" / "list" / "pack.yaml", "- id\n- kind\n")
    _write(root / "market" / "noid" / "pack.yaml", "id: [1]\nkind: market\nversion: 1\n")
    found = discover_packs()
    assert ("market", "test") in found
    assert len([k for k in found if k[0] == "market"]) == 1


def test_packs_yaml_with_a_single_id_or_bad_entries(tmp_path):
    v = tmp_path / "v"
    _write(v / "packs.yaml", "market: il\nprofession: {id: developer}\n")
    assert loader.read_venture_packs(v) == {
        "market": [{"id": "il", "version": ""}],
        "profession": [{"id": "developer", "version": ""}],
    }
    _write(v / "packs.yaml", "market: [[nested], {version: 1}, pt]\nprofession: 5\n")
    assert loader.read_venture_packs(v) == {"market": [{"id": "pt", "version": ""}], "profession": []}
    _write(v / "packs.yaml", "- market\n")
    assert loader.read_venture_packs(v) == {"market": [], "profession": []}


def test_a_pack_id_cannot_step_outside_the_pack_folder(root, tmp_path):
    _write(tmp_path / "outside" / "pack.yaml", "id: ../outside\nkind: market\nversion: 1\n")
    assert loader.find_pack("market", "../outside") is None
    assert loader.find_pack("market", "../../outside") is None
    assert not loader.is_safe_id("../x")
    assert loader.is_safe_id("pt")


def test_broken_firm_overrides_keep_the_other_layers(root, venture):
    _write(venture / "F-foundations" / "overrides" / "defaults.yaml", "- not a mapping\n")
    _write(venture / "F-foundations" / "overrides" / "disable.yaml", "{a: b}\n")
    resolver = PackResolver(venture, enabled=True)
    assert resolver.resolve("default", "currency").value == "TST"
    assert any("defaults.yaml" in w for w in resolver.firm.warnings)


def test_chat_prompt_context_survives_an_unrelated_broken_pack(root, venture, tmp_path):
    from realize_core.prompt import builder

    sources: list[dict] = []
    prompt = builder.build_system_prompt(
        tmp_path,
        {"system_dir": "systems/acme", "name": "Acme"},
        "acme",
        user_message="Check this interim claim",
        features={"packs": True},
        sources_out=sources,
    )
    assert "Local context (profession and market packs)" in prompt
    assert "interim claim → money-event/payment_claim" in prompt
    assert sources[0]["id"] == "R1"


def test_wedge_market_lookup_survives_an_unrelated_broken_pack(root):
    from realize_core.wedge.register import get_method

    shutil.copytree(PACKS / "market" / "pt", root / "market" / "pt", ignore=shutil.ignore_patterns("reviews"))
    _write(root / "market" / "zz" / "pack.yaml", "- broken\n")
    method = get_method("PT")
    assert method["market"]["market"] == "pt"
    assert method["market"]["verification"] == 1
    assert method["market"]["rules"]
    assert get_method("zz")["market"]["verification"] == 0  # broken pack: treated as no pack
