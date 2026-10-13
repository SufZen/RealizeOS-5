"""Developer profession pack and Israel market pack (STORY-43)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from realize_core.fabric.validator import SchemaRegistry, validate_entity
from realize_core.packs import PackResolver, clear_cache, discover_packs

PACKS = Path(__file__).parent.parent / "packs"
HEBREW = re.compile(r"[֐-׿]")


@pytest.fixture(scope="module")
def packs():
    return discover_packs(PACKS)


def test_both_packs_load_cleanly(packs):
    dev = packs[("profession", "developer")]
    il = packs[("market", "il")]
    assert dev.warnings == []
    assert il.warnings == []
    assert (dev.version, il.version) == ("0.1.0", "0.1.0")


def test_israel_pack_has_terms_rules_and_defaults(packs):
    il = packs[("market", "il")]
    assert len(il.terms) >= 10
    assert len(il.rules) >= 5
    for card in il.rules.values():
        assert card.source.startswith("https://")
        assert card.as_of
        assert card.verification == 1
    assert il.defaults["currency"] == "ILS"
    assert il.defaults["work_week"] == ["sun", "mon", "tue", "wed", "thu"]
    assert il.verification_level == 1
    assert il.limits


def test_developer_pack_is_market_neutral():
    dev_root = PACKS / "profession" / "developer"
    for path in dev_root.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert not HEBREW.search(text), path
            for marker in ("ILS", "3210", "Portugal", "Israel", "EUR"):
                assert marker not in text, (path, marker)


def test_glossary_families_are_core_families(packs):
    core = {"project", "contact", "source", "requirement", "money-event", "milestone", "change", "decision", "issue"}
    for pack in packs.values():
        for entry in pack.terms.values():
            assert entry["family"] in core, entry


def test_developer_schemas_extend_core_cleanly(packs):
    registry = SchemaRegistry()
    for name, schema in packs[("profession", "developer")].schemas.items():
        assert registry.register(name, schema) == [], name
    claim = {
        "type": "payment-claim",
        "kind": "payment_claim",
        "amount": 120000,
        "currency": "EUR",
        "milestone": "mil-2026-10-frame-1",
        "counterparty": "contractor-a",
    }
    assert validate_entity(claim, registry=registry).valid


def test_scaffold_writes_packs_yaml(tmp_path):
    from realize_core.scaffold import scaffold_venture

    (tmp_path / "realize-os.yaml").write_text("name: test\nsystems: []\n", encoding="utf-8")
    scaffold_venture(tmp_path, "dev-co", template="real-estate-developer")
    data = yaml.safe_load((tmp_path / "systems" / "dev-co" / "packs.yaml").read_text(encoding="utf-8"))
    # The template is the Israeli developer demo: it links the Israel market pack explicitly.
    assert data == {"profession": ["developer"], "market": ["il"]}


def test_scaffold_without_packs_writes_nothing(tmp_path):
    from realize_core.scaffold import scaffold_venture

    (tmp_path / "realize-os.yaml").write_text("name: test\nsystems: []\n", encoding="utf-8")
    scaffold_venture(tmp_path, "plain")
    assert not (tmp_path / "systems" / "plain" / "packs.yaml").exists()


def test_israeli_developer_venture_resolves_through_both_packs(tmp_path):
    clear_cache()
    venture = tmp_path / "systems" / "il-dev"
    venture.mkdir(parents=True)
    (venture / "packs.yaml").write_text("profession: [developer]\nmarket: [il]\n", encoding="utf-8")
    r = PackResolver(venture, enabled=True, packs_root=PACKS)
    claim = r.resolve("term", "חשבון חלקי")
    assert (claim.value["kind"], claim.layer) == ("payment_claim", "market")
    assert r.resolve("term", "payment claim").layer == "profession"
    assert r.resolve("default", "currency").value == "ILS"
    assert r.resolve("rule", "il.sale-law.buyer-funds-secured").verification == 1
    assert r.resolve("measure", "payment_claims_checked").layer == "profession"


def test_webinar_demo_venture_gets_developer_and_portugal_packs(tmp_path):
    from realize_core.demo_seed import DEMO_KEY, seed_webinar_demo

    clear_cache()
    (tmp_path / "realize-os.yaml").write_text("name: test\nsystems: []\n", encoding="utf-8")
    seed_webinar_demo(tmp_path)
    venture = tmp_path / "systems" / DEMO_KEY
    r = PackResolver(venture, enabled=True, packs_root=PACKS)
    assert [p.id for p in r.packs] == ["pt", "developer"]
    assert r.resolve("term", "auto de medição").pack_id == "pt@0.1.0"
    assert r.resolve("measure", "payment_claims_checked") is not None
    off = PackResolver(venture, enabled=False, packs_root=PACKS)
    assert off.packs == []


# ---------------------------------------------------------------------------
# Thin pointer (STORY-43): with packs on, the template links the developer pack
# ---------------------------------------------------------------------------

TEMPLATE = Path(__file__).parent.parent / "templates" / "real-estate-developer"
TEAM = {"orchestrator", "tenders", "procurement", "site_payments", "finance_investors", "reviewer"}
SKILLS = {"tender_requirements_register", "payment_milestone_check", "investor_report"}


def _project(tmp_path: Path, packs: bool) -> Path:
    features = "features:\n  packs: true\n" if packs else ""
    (tmp_path / "realize-os.yaml").write_text(f"name: test\n{features}systems: []\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def fresh_skills(monkeypatch):
    from realize_core.skills import detector

    clear_cache()
    monkeypatch.setattr(detector, "_loaded_skills", {})
    yield detector
    clear_cache()


def test_developer_pack_carries_the_team_and_the_skills(packs):
    dev = packs[("profession", "developer")]
    assert set(dev.agents) == TEAM
    assert dev.agents_readme is not None
    assert set(dev.skills) == SKILLS


def test_scaffold_with_packs_on_links_instead_of_copying(tmp_path, fresh_skills):
    from realize_core.config import build_systems_dict, load_config
    from realize_core.scaffold import scaffold_venture

    root = _project(tmp_path, packs=True)
    stats = scaffold_venture(root, "dev-co", template="real-estate-developer")
    venture = root / "systems" / "dev-co"
    assert stats["files_linked"] == 10  # six agents, the routing guide and three skills
    assert list((venture / "A-agents").glob("*")) == []
    assert list((venture / "R-routines" / "skills").glob("*")) == []
    assert (venture / "F-foundations" / "venture-identity.md").is_file()  # firm starter files are copied
    assert yaml.safe_load((venture / "packs.yaml").read_text(encoding="utf-8")) == {
        "profession": ["developer"],
        "market": ["il"],
    }
    settings_file = venture / "F-foundations" / "overrides" / "skill-settings.yaml"
    settings = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    assert set(settings) == SKILLS
    assert settings["payment_milestone_check"]["variables"] == {
        "milestones_sheet_id": "REPLACE_WITH_SHEET_ID",
        "payments_sheet_id": "REPLACE_WITH_SHEET_ID",
    }

    # The venture still has its whole team and its skills, from the pack.
    system = build_systems_dict(load_config(root / "realize-os.yaml"), root)["dev-co"]
    assert set(system["agents"]) >= TEAM
    fresh_skills.reload_skills(kb_path=root, packs=True)
    skills = fresh_skills.get_skills_for_system("dev-co")
    assert {s["name"] for s in skills} == SKILLS
    # The Hebrew triggers live in the Israel market pack; the template links it, so they are kept.
    assert "חשבון חלקי" in next(s for s in skills if s["name"] == "payment_milestone_check")["triggers"]


def test_scaffold_with_packs_off_copies_as_before(tmp_path):
    from realize_core.scaffold import scaffold_venture

    root = _project(tmp_path, packs=False)
    stats = scaffold_venture(root, "dev-co", template="real-estate-developer")
    venture = root / "systems" / "dev-co"
    assert "files_linked" not in stats
    copied = {p.relative_to(venture).as_posix() for p in venture.rglob("*") if p.is_file()}
    template = {p.relative_to(TEMPLATE).as_posix() for p in TEMPLATE.rglob("*") if p.is_file()}
    assert copied == template | {"packs.yaml"}
    assert not (venture / "F-foundations" / "overrides").exists()


def test_existing_ventures_keep_their_own_copies_with_packs_on(tmp_path, fresh_skills):
    """A venture created before packs (copied files) works unchanged: its copies win."""
    from realize_core.config import build_systems_dict, load_config
    from realize_core.scaffold import scaffold_venture

    root = _project(tmp_path, packs=False)
    scaffold_venture(root, "old-co", template="real-estate-developer")
    config_file = root / "realize-os.yaml"
    config_file.write_text(config_file.read_text(encoding="utf-8") + "features:\n  packs: true\n", encoding="utf-8")
    system = build_systems_dict(load_config(config_file), root)["old-co"]
    assert system["agent_provenance"] == {}
    assert all(Path(p).parts[:2] == ("systems", "old-co") for p in system["agents"].values())
    fresh_skills.reload_skills(kb_path=root, packs=True)
    skills = fresh_skills.get_skills_for_system("old-co")
    assert {s["name"] for s in skills} == SKILLS
    assert not any("_layer" in s for s in skills)
    assert "חשבון חלקי" in next(s for s in skills if s["name"] == "payment_milestone_check")["triggers"]


def test_template_copies_match_the_pack_plus_the_israel_triggers(packs):
    """The flag-off copies in the template stay the pack's skills, with the Hebrew triggers the Israel pack adds."""
    dev, il = packs[("profession", "developer")], packs[("market", "il")]
    for skill_id, pack_path in dev.skills.items():
        pack_skill = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
        template_path = TEMPLATE / "R-routines" / "skills" / pack_path.name
        template_skill = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        for key in ("name", "description", "agent", "variables", "steps"):
            assert template_skill[key] == pack_skill[key], (skill_id, key)
        assert template_skill["triggers"] == pack_skill["triggers"] + il.skill_settings[skill_id]["triggers"]
    template_agents = {p.stem.replace("-", "_") for p in (TEMPLATE / "A-agents").glob("*.md") if p.stem != "_README"}
    assert template_agents == set(dev.agents)


def test_an_israeli_developer_venture_gets_hebrew_triggers_from_the_israel_pack(tmp_path, fresh_skills):
    venture = tmp_path / "systems" / "il-dev"
    venture.mkdir(parents=True)
    (venture / "packs.yaml").write_text("profession: [developer]\nmarket: [il]\n", encoding="utf-8")
    fresh_skills.reload_skills(kb_path=tmp_path, packs=True)
    claim = fresh_skills.detect_skill("קיבלנו חשבון חלקי מהקבלן", "il-dev")
    assert claim["name"] == "payment_milestone_check"
    assert (claim["_layer"], claim["_pack"]) == ("profession", "developer@0.1.0")
    # Without the Israel pack the developer pack is market-neutral: no Hebrew triggers.
    (venture / "packs.yaml").write_text("profession: [developer]\n", encoding="utf-8")
    clear_cache()
    fresh_skills.reload_skills(kb_path=tmp_path, packs=True)
    assert fresh_skills.detect_skill("קיבלנו חשבון חלקי מהקבלן", "il-dev") is None
