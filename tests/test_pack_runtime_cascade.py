"""The run-time pack cascade: skills, agents, schemas and trust defaults from packs (spec 010, STORY-42/43).

A fixture KB with two ventures and two packs:

- ``acme-co`` links the profession pack ``acme`` and the market pack ``zz``,
  has its own ``local_wins`` skill and ``reviewer`` agent, and firm overrides
  (skill ids, a disable list) in ``F-foundations/overrides/``;
- ``plain`` links no pack.

Everything runs behind ``features.packs``; with it off the results must be
what they were before packs (checked against snapshots).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

VENTURE = "acme-co"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yaml(path: Path, data) -> None:
    _write(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


QUOTE_CHECK = {
    "name": "quote_check",
    # A pack can't pick the venture a skill runs for, nor the loader's own markers.
    "system_key": "plain",
    "_format": "skill_md",
    "_layer": "firm",
    "description": "Check a supplier quote and record it for approval",
    "agent": "estimator",
    "triggers": ["check the quote"],
    "variables": {"ledger_id": "REPLACE_WITH_SHEET_ID"},
    "steps": [
        {"id": "check", "type": "agent", "agent": "estimator", "prompt": "Check: {user_message}"},
        {"id": "record", "type": "tool", "tool": "ledger_append", "params": {"sheet": "{ledger_id}", "row": "{check}"}},
        {"id": "summary", "type": "agent", "agent": "reviewer", "inject_context": ["check", "record"]},
    ],
}

NOTE_TAKER = {
    "name": "note_taker",
    "triggers": ["take a note"],
    "steps": [{"id": "note", "type": "tool", "tool": "ledger_note", "params": {"text": "{user_message}"}}],
}


@pytest.fixture
def packs_root(tmp_path: Path) -> Path:
    root = tmp_path / "packs"
    acme = root / "profession" / "acme"
    _yaml(acme / "pack.yaml", {"id": "acme", "kind": "profession", "version": "0.1.0", "title": "Acme"})
    _write(acme / "A-agents" / "estimator.md", "# Estimator\n\nChecks quotes line by line.\n")
    _write(acme / "A-agents" / "reviewer.md", "# Pack reviewer\n")
    _write(acme / "A-agents" / "_README.md", "# Acme routing guide\n")
    _write(acme / "A-agents" / "_notes.md", "# Not an agent\n")
    _yaml(acme / "R-routines" / "skills" / "quote-check.yaml", QUOTE_CHECK)
    _yaml(acme / "R-routines" / "skills" / "note-taker.yaml", NOTE_TAKER)
    _yaml(acme / "R-routines" / "skills" / "local-wins.yaml", {"name": "local_wins", "triggers": ["pack version"]})
    _write(
        acme / "schemas" / "quote.json",
        json.dumps(
            {
                "$id": "pack://acme/quote.json",
                "allOf": [{"$ref": "https://realizeos.ai/schemas/v0.1/money-event.json"}],
                "properties": {"kind": {"const": "quote"}, "discount_percent": {"type": "number"}},
                "required": ["counterparty"],
            }
        ),
    )
    _yaml(acme / "trust.yaml", {"ledger_append": "approve", "gmail_send": "auto"})
    zz = root / "market" / "zz"
    _yaml(zz / "pack.yaml", {"id": "zz", "kind": "market", "version": "0.2.0", "verification": {"level": 1}})
    _yaml(
        zz / "skill-settings.yaml",
        {"quote_check": {"triggers": ["בדיקת הצעה"], "variables": {"ledger_id": "someone-elses-sheet"}}},
    )
    _yaml(zz / "trust.yaml", {"ledger_read": "block"})
    return root


@pytest.fixture
def kb(tmp_path: Path, packs_root: Path, monkeypatch) -> Path:
    from realize_core.packs import clear_cache, loader

    monkeypatch.delenv("REALIZE_PACKS_PATH", raising=False)
    monkeypatch.setattr(loader, "default_packs_root", lambda: packs_root)
    monkeypatch.setattr(loader, "_warned", set())  # every test sees its own warnings
    clear_cache()
    root = tmp_path / "kb"
    acme = root / "systems" / VENTURE
    _yaml(acme / "packs.yaml", {"profession": ["acme"], "market": ["zz"]})
    _yaml(acme / "R-routines" / "skills" / "local-wins.yaml", {"name": "local_wins", "triggers": ["venture version"]})
    _write(acme / "A-agents" / "reviewer.md", "# Venture reviewer\n")
    _yaml(
        acme / "F-foundations" / "overrides" / "skill-settings.yaml",
        {"quote_check": {"variables": {"ledger_id": "sheet-acme"}}},
    )
    plain = root / "systems" / "plain"
    _yaml(plain / "R-routines" / "skills" / "hello.yaml", {"name": "hello", "triggers": ["hello"]})
    _write(plain / "A-agents" / "writer.md", "# Writer\n")
    yield root
    clear_cache()


def _config(packs: bool, **extra) -> dict:
    config = {
        "systems": [
            {"key": VENTURE, "directory": f"systems/{VENTURE}", "routing": {"quotes": ["estimator", "reviewer"]}},
            {"key": "plain", "directory": "systems/plain"},
        ],
        **extra,
    }
    if packs:
        config["features"] = {"packs": True}
    return config


@pytest.fixture
def skills(monkeypatch):
    """A fresh skill registry for the test."""
    from realize_core.skills import detector

    monkeypatch.setattr(detector, "_loaded_skills", {})
    monkeypatch.setattr(detector, "_skills_loaded", False)
    return detector


def _names(detector, key: str) -> list[str]:
    return [s["name"] for s in detector.get_skills_for_system(key)]


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


def test_pack_skills_join_the_ventures_own(kb, skills):
    skills.reload_skills(kb_path=kb, packs=True)
    assert sorted(_names(skills, VENTURE)) == ["local_wins", "note_taker", "quote_check"]
    quote = next(s for s in skills.get_skills_for_system(VENTURE) if s["name"] == "quote_check")
    assert (quote["_layer"], quote["_pack"], quote["_skill_id"]) == ("profession", "acme@0.1.0", "quote_check")
    assert quote["_version"] == 2
    assert _names(skills, "plain") == ["hello"]


def test_find_skill_resolves_a_custom_pack_skill(kb, skills):
    skills.reload_skills(kb_path=kb, packs=True)
    owner, skill = skills.find_skill("quote_check")
    assert owner == VENTURE
    assert skill["steps"][1]["tool"] == "ledger_append"
    assert "system_key" not in skill
    assert "_format" not in skill
    assert skill["_layer"] == "profession"
    listed = [s for s in skills.get_all_skills() if s["name"] == "quote_check"]
    assert [s["system_key"] for s in listed] == [VENTURE]


def test_the_ventures_own_skill_wins_and_is_listed_once(kb, skills):
    skills.reload_skills(kb_path=kb, packs=True)
    local = [s for s in skills.get_skills_for_system(VENTURE) if s["name"] == "local_wins"]
    assert len(local) == 1
    assert local[0]["triggers"] == ["venture version"]
    assert "_layer" not in local[0]
    assert skills.detect_skill("the pack version please", VENTURE) is None


def test_skill_settings_add_triggers_and_only_the_firm_sets_ids(kb, skills, caplog):
    caplog.set_level(logging.WARNING)
    skills.reload_skills(kb_path=kb, packs=True)
    quote = skills.detect_skill("בדיקת הצעה מהספק", VENTURE)
    assert quote["name"] == "quote_check"
    assert quote["triggers"] == ["check the quote", "בדיקת הצעה"]
    assert quote["variables"] == {"ledger_id": "sheet-acme"}
    assert "sets variables for skill 'quote_check'; ignored" in caplog.text


def test_the_firm_can_switch_a_pack_skill_off(kb, skills):
    _yaml(kb / "systems" / VENTURE / "F-foundations" / "overrides" / "disable.yaml", ["quote_check"])
    skills.reload_skills(kb_path=kb, packs=True)
    assert "quote_check" not in _names(skills, VENTURE)


def test_flag_off_loads_exactly_the_ventures_own_skills(kb, skills):
    snapshot = {VENTURE: ["local_wins"], "plain": ["hello"]}
    skills.reload_skills(kb_path=kb)
    assert {k: [s["name"] for s in v] for k, v in skills._loaded_skills.items()} == snapshot
    skills.reload_skills(kb_path=kb, packs=False)
    assert {k: [s["name"] for s in v] for k, v in skills._loaded_skills.items()} == snapshot
    assert skills.find_skill("quote_check") is None


def test_the_app_loads_the_cascade_only_with_the_flag(kb, skills):
    from realize_core.config_runtime import sync_skill_cascade

    state = SimpleNamespace(kb_path=kb)
    sync_skill_cascade(state, _config(packs=False))
    # Flag off: the ventures' own skills load (they didn't before 5.30), pack skills don't.
    assert "local_wins" in _names(skills, VENTURE)
    assert "quote_check" not in _names(skills, VENTURE)
    sync_skill_cascade(state, _config(packs=True))
    assert "quote_check" in _names(skills, VENTURE)
    skills.reload_skills(kb_path=kb)  # e.g. installing a skill: keeps the cascade
    assert "quote_check" in _names(skills, VENTURE)
    sync_skill_cascade(state, _config(packs=False))
    assert "quote_check" not in _names(skills, VENTURE)
    assert "local_wins" in _names(skills, VENTURE)


def test_malformed_pack_skills_are_skipped_and_the_rest_load(kb, packs_root, skills, caplog):
    caplog.set_level(logging.WARNING)
    acme_skills = packs_root / "profession" / "acme" / "R-routines" / "skills"
    _yaml(acme_skills / "bad-triggers.yaml", {"name": "bad_triggers", "triggers": {"not": "a list"}})
    _yaml(acme_skills / "bad-steps.yaml", {"name": "bad_steps", "steps": "run everything"})
    _write(acme_skills / "broken.yaml", "name: [unclosed\n")
    broken = packs_root / "market" / "broken"
    _write(broken / "pack.yaml", "id: broken\nkind: market\nversion: [\n")
    _yaml(kb / "systems" / VENTURE / "packs.yaml", {"profession": ["acme"], "market": ["zz", "broken"]})
    skills.reload_skills(kb_path=kb, packs=True)
    assert sorted(_names(skills, VENTURE)) == ["local_wins", "note_taker", "quote_check"]
    assert "bad-triggers.yaml skipped: triggers must be a list" in caplog.text
    assert "bad-steps.yaml skipped: steps must be a list of mappings" in caplog.text


# ---------------------------------------------------------------------------
# Pack skills run through the same executor, gate, approvals and trail
# ---------------------------------------------------------------------------


class Ledger(BaseTool):
    """A write (``ledger_append``, ``ledger_note``) and a read (``ledger_read``) that record their calls."""

    name = "ledger"
    description = "ledger"
    category = ToolCategory.PRODUCTIVITY

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_schemas(self):
        obj = {"type": "object", "properties": {}}
        return [
            ToolSchema("ledger_append", "append a row", obj, is_destructive=True),
            ToolSchema("ledger_note", "write a note", obj, is_destructive=True),
            ToolSchema("ledger_read", "read rows", obj, is_destructive=False),
        ]

    def is_available(self):
        return True

    async def execute(self, action, params):
        self.calls.append((action, dict(params)))
        return ToolResult.ok(output="done")


@pytest.fixture
def ops_db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


def _gated_ledger(monkeypatch, kb: Path, config: dict) -> Ledger:
    import realize_core.tools.tool_registry as tr
    from realize_core.governance.tool_gate import ToolGate

    monkeypatch.setattr(tr, "_registry", None)
    registry = tr.get_tool_registry()
    tool = Ledger()
    registry.register(tool)
    registry.set_gate(ToolGate(config=config, kb_path=kb))
    return tool


@pytest.fixture
def llm(monkeypatch):
    from realize_core.skills import executor

    calls: list[dict] = []

    async def scripted(system_prompt, messages, system_key):
        agent = (
            system_prompt.split("## Active Agent: ", 1)[1].split("\n", 1)[0]
            if "## Active Agent: " in system_prompt
            else "?"
        )
        calls.append({"agent": agent, "prompt": messages[-1]["content"], "system_prompt": system_prompt})
        return f"[{agent}] quote looks fine"

    monkeypatch.setattr(executor, "_call_llm", scripted)
    return calls


def _pending(db: Path) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM approval_queue WHERE status = 'pending'")]
    finally:
        conn.close()


async def _run(kb: Path, config: dict, skill: dict, message: str, events: list | None = None) -> str:
    from realize_core.config import build_systems_dict
    from realize_core.skills.executor import execute_skill

    async def emit(event):
        if events is not None:
            events.append(event)

    return await execute_skill(
        skill=skill,
        user_message=message,
        system_key=VENTURE,
        user_id="dana",
        kb_path=kb,
        system_config=build_systems_dict(config, kb)[VENTURE],
        shared_config={},
        channel="api",
        emit=emit,
    )


@pytest.mark.asyncio
async def test_a_pack_skill_runs_through_the_executor_gate_and_approval(kb, skills, llm, ops_db, monkeypatch):
    from realize_core.governance.gates import decide_approval

    config = _config(packs=True, trust={"level": 5})  # level 5: data writes would run on their own
    ledger = _gated_ledger(monkeypatch, kb, config)
    skills.reload_skills(kb_path=kb, packs=True)
    skill = skills.detect_skill("please check the quote from the supplier", VENTURE)
    events: list[dict] = []
    out = await _run(kb, config, skill, "please check the quote from the supplier", events)

    # The pack agent answered with its own definition, and the write waits: the pack's
    # trust default (ledger_append: approve) is stricter than trust level 5.
    assert llm[0]["agent"] == "estimator"
    assert "Checks quotes line by line." in llm[0]["system_prompt"]
    assert "waiting for operator approval" in out
    assert ledger.calls == []
    assert [e["type"] for e in events] == ["source", "tool_call", "approval_requested", "tool_result"]
    # The trail says where the workflow came from, like a rule card (no server path).
    assert events[0] == {
        "type": "source",
        "id": "W1",
        "title": "Workflow: quote_check",
        "path": "quote-check.yaml",
        "layer": "profession",
        "pack": "acme@0.1.0",
    }
    [held] = _pending(ops_db)
    assert (held["action_name"], held["venture_key"]) == ("ledger_append", VENTURE)
    assert json.loads(held["params_json"])["sheet"] == "sheet-acme"  # the firm's id, not the market pack's

    await decide_approval(held["id"], approve=True)
    assert ledger.calls == [("ledger_append", {"sheet": "sheet-acme", "row": "[estimator] quote looks fine"})]
    assert await decide_approval(held["id"], approve=True) is None  # runs once


@pytest.mark.asyncio
async def test_outside_agents_writes_from_pack_skills_are_held(kb, skills, llm, ops_db, monkeypatch):
    from realize_core.security.agent_access import acting_for_outside_agent

    config = _config(packs=True, trust={"level": 5})
    ledger = _gated_ledger(monkeypatch, kb, config)
    skills.reload_skills(kb_path=kb, packs=True)
    _owner, note = skills.find_skill("note_taker")

    # A person at trust level 5: the note (no pack default) runs on its own.
    await _run(kb, config, note, "take a note: call the supplier")
    assert ledger.calls == [("ledger_note", {"text": "take a note: call the supplier"})]

    # An outside agent never gets automatic writes, from a pack skill either (STORY-37).
    with acting_for_outside_agent("agent:0123456789ab"):
        out = await _run(kb, config, note, "take a note: pay the supplier")
    assert "waiting for operator approval" in out
    assert len(ledger.calls) == 1
    assert [r["action_name"] for r in _pending(ops_db)] == ["ledger_note"]


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


def test_pack_agents_join_the_venture_and_its_own_win(kb):
    from realize_core.config import build_systems_dict

    system = build_systems_dict(_config(packs=True), kb)[VENTURE]
    assert set(system["agents"]) == {"estimator", "reviewer"}
    assert Path(system["agents"]["reviewer"]).parts[-3:] == (VENTURE, "A-agents", "reviewer.md")
    assert (kb / system["agents"]["estimator"]).read_text(encoding="utf-8").startswith("# Estimator")
    assert system["agent_provenance"] == {"estimator": {"layer": "profession", "pack": "acme@0.1.0"}}
    assert (kb / system["agents_readme"]).read_text(encoding="utf-8") == "# Acme routing guide\n"


def test_a_ventures_own_routing_guide_wins(kb):
    from realize_core.config import build_systems_dict

    _write(kb / "systems" / VENTURE / "A-agents" / "_README.md", "# Our guide\n")
    system = build_systems_dict(_config(packs=True), kb)[VENTURE]
    assert system["agents_readme"] == f"systems/{VENTURE}/A-agents/_README.md"


def test_flag_off_agents_are_exactly_the_ventures_own(kb):
    from realize_core.config import build_systems_dict

    off = build_systems_dict(_config(packs=False), kb)
    assert off == build_systems_dict({**_config(packs=False), "features": {"packs": False}}, kb)
    assert {k: sorted(v["agents"]) for k, v in off.items()} == {VENTURE: ["reviewer"], "plain": ["writer"]}
    assert all("agent_provenance" not in v for v in off.values())
    assert off[VENTURE]["agents_readme"] == f"systems/{VENTURE}/A-agents/_README.md"


def test_routing_to_a_pack_agent_validates_with_packs_on(kb):
    from realize_core.config import validate_systems

    def unknown(packs: bool) -> list[str]:
        return [w for w in validate_systems(_config(packs=packs), kb) if "estimator" in w]

    assert unknown(packs=False)
    assert unknown(packs=True) == []


def test_a_pack_agent_prompt_uses_its_definition_and_shows_in_the_trail(kb):
    from realize_core.agents.trail import trail_source
    from realize_core.config import build_systems_dict
    from realize_core.prompt import builder

    builder.clear_cache()
    system = build_systems_dict(_config(packs=True), kb)[VENTURE]
    sources: list[dict] = []
    prompt = builder.build_system_prompt(
        kb, system, VENTURE, agent_key="estimator", features={"packs": True}, sources_out=sources
    )
    assert "## Active Agent: estimator\n# Estimator" in prompt
    assert "# Acme routing guide" in prompt
    agent = next(s for s in sources if s["id"] == "A1")
    assert trail_source(agent) == {
        "id": "A1",
        "title": "Agent: estimator",
        "path": "estimator.md",
        "layer": "profession",
        "pack": "acme@0.1.0",
    }
    # The venture's own agent adds no trail row.
    own: list[dict] = []
    builder.build_system_prompt(kb, system, VENTURE, agent_key="reviewer", features={"packs": True}, sources_out=own)
    assert not any(s["id"] == "A1" for s in own)


def test_pack_agents_get_no_extra_tools(kb, monkeypatch):
    """A pack agent is offered exactly the tools a venture agent without a persona gets."""
    import realize_core.tools.tool_registry as tr
    from realize_core.base_handler import agent_tool_schemas
    from realize_core.config import build_systems_dict

    _write(kb / "systems" / VENTURE / "A-agents" / "writer.md", "# Writer\n")
    _write(kb / "systems" / VENTURE / "A-agents" / "writer.persona.yaml", "name: writer\ntools_allowlist: [ledger]\n")
    _yaml(
        kb.parent / "packs" / "profession" / "acme" / "A-agents" / "estimator.persona.yaml",
        {"name": "estimator", "tools_allowlist": ["ledger", "everything"]},
    )
    monkeypatch.setattr(tr, "_registry", None)
    tr.get_tool_registry().register(Ledger())
    system = build_systems_dict(_config(packs=True), kb)[VENTURE]

    def names(agent: str) -> set[str]:
        return {s["name"] for s in agent_tool_schemas(agent, kb, system)}

    # No gate installed: only reads are offered, to every agent alike.
    assert names("estimator") == names("reviewer") == {"ledger_read"}


def test_pack_files_that_point_outside_the_pack_are_skipped(kb, packs_root, tmp_path):
    from realize_core.packs import clear_cache, load_pack

    secret = tmp_path / "secret.md"
    secret.write_text("# Not pack content\n", encoding="utf-8")
    link = packs_root / "profession" / "acme" / "A-agents" / "leak.md"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    clear_cache()
    pack = load_pack(packs_root / "profession" / "acme")
    assert "leak" not in pack.agents
    assert any("leak.md: points outside the pack folder" in w for w in pack.warnings)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


def test_pack_schema_extensions_validate_the_ventures_entities(kb):
    from realize_core.fabric.validator import SchemaRegistry, validate_entity
    from realize_core.packs.schemas import schema_registry_for

    registry = schema_registry_for(kb / "systems" / VENTURE, enabled=True)
    quote = {"type": "quote", "kind": "quote", "amount": 1200, "currency": "EUR", "counterparty": "supplier-a"}
    assert validate_entity(quote, registry=registry).valid
    missing = validate_entity({k: v for k, v in quote.items() if k != "counterparty"}, registry=registry)
    assert [w.field for w in missing.warnings] == ["counterparty"]
    assert registry.get_schema("money-event") == SchemaRegistry().get_schema("money-event")

    # Another venture, without the pack, doesn't know the type; packs off gives the core only.
    assert schema_registry_for(kb / "systems" / "plain", enabled=True).get_schema("quote") is None
    off = schema_registry_for(kb / "systems" / VENTURE, enabled=False)
    assert off.known_types == SchemaRegistry().known_types


def test_a_pack_schema_cannot_replace_or_fork_a_core_schema(kb, packs_root, caplog):
    from realize_core.fabric.validator import SchemaRegistry, validate_entity
    from realize_core.packs import clear_cache
    from realize_core.packs.schemas import schema_registry_for

    caplog.set_level(logging.WARNING)
    schemas = packs_root / "profession" / "acme" / "schemas"
    core = SchemaRegistry()
    _write(schemas / "money-event.json", json.dumps({"properties": {"amount": {"type": "string"}}}))
    _write(schemas / "sneaky.json", json.dumps({"$id": core.get_schema("money-event")["$id"], "properties": {}}))
    _write(schemas / "forked.json", json.dumps({"properties": {"anything": {"type": "string"}}}))
    _write(
        schemas / "retyped.json",
        json.dumps({"allOf": [{"$ref": "money-event.json"}], "properties": {"amount": {"type": "string"}}}),
    )
    _write(schemas / "garbage.json", json.dumps({"allOf": "money-event", "properties": []}))
    clear_cache()

    registry = schema_registry_for(kb / "systems" / VENTURE, enabled=True)
    assert registry.get_schema("money-event") == core.get_schema("money-event")
    assert registry.get_schema("sneaky") is None
    assert registry.get_schema("forked") is None
    assert registry.get_schema("garbage") is None
    assert registry.get_schema("retyped")["properties"]["amount"]["type"] == "number"  # the core type holds
    bad = validate_entity({"type": "retyped", "amount": "a lot"}, registry=registry)
    assert any(w.field == "amount" for w in bad.warnings)
    assert "money-event from profession pack acme@0.1.0 skipped" in caplog.text
    assert "retypes core type 'number' as 'string'" in caplog.text


def test_cli_lint_uses_each_ventures_pack_schemas(kb, monkeypatch):
    from realize_core.cli_app import app
    from typer.testing import CliRunner

    _write(
        kb / "systems" / VENTURE / "B-brain" / "quote-1.md",
        "---\nid: quote-1\ntype: quote\nkind: quote\namount: 10\ncurrency: EUR\n---\nA quote.\n",
    )
    monkeypatch.chdir(kb)
    monkeypatch.delenv("REALIZE_CONFIG", raising=False)
    runner = CliRunner()
    _yaml(kb / "realize-os.yaml", _config(packs=True))
    on = runner.invoke(app, ["fabric", "lint", "--venture", VENTURE])
    assert "Missing required field: counterparty" in on.output
    _yaml(kb / "realize-os.yaml", _config(packs=False))
    off = runner.invoke(app, ["fabric", "lint", "--venture", VENTURE])
    assert "counterparty" not in off.output


# ---------------------------------------------------------------------------
# Trust defaults: tighten, never loosen
# ---------------------------------------------------------------------------


def _decide(kb: Path, config: dict, action: str, *, venture: str = VENTURE, destructive: bool = True):
    from realize_core.governance.context import tool_call_context
    from realize_core.governance.tool_gate import ToolGate

    gate = ToolGate(config=config, kb_path=kb)
    with tool_call_context(system_key=venture, agent_key="estimator", user_id="dana"):
        return gate.decide(action, {"row": "x"}, is_destructive=destructive).outcome.value


def test_pack_trust_tightens(kb, ops_db):
    level5 = _config(packs=True, trust={"level": 5})
    assert _decide(kb, level5, "ledger_append") == "needs_approval"  # profession: auto → approve
    assert _decide(kb, level5, "ledger_read", destructive=False) == "block"  # market: auto → block
    # Another venture, packs off, or a call for no venture: the ladder alone decides.
    assert _decide(kb, level5, "ledger_append", venture="plain") == "allow"
    assert _decide(kb, _config(packs=False, trust={"level": 5}), "ledger_append") == "allow"
    assert _decide(kb, level5, "ledger_append", venture="") == "allow"


def test_pack_trust_never_loosens(kb, ops_db, caplog):
    caplog.set_level(logging.WARNING)
    level3 = _config(packs=True, trust={"level": 3})
    # gmail_send is send_email: approve at level 3. The pack's "auto" is ignored and logged.
    assert _decide(kb, level3, "gmail_send") == "needs_approval"
    assert "would loosen gmail_send from approve to auto; ignored" in caplog.text
    # A ladder decision that already blocks stays blocked whatever the packs say.
    level1 = _config(packs=True, trust={"level": 1})
    assert _decide(kb, level1, "ledger_append") == "block"


def test_firm_overrides_tighten_further_and_can_switch_a_pack_default_off(kb, ops_db):
    overrides = kb / "systems" / VENTURE / "F-foundations" / "overrides"
    level5 = _config(packs=True, trust={"level": 5})
    _yaml(overrides / "trust.yaml", {"data_write": "block", "unknown_write": "block", "ledger_note": "auto"})
    assert _decide(kb, level5, "sheets_append") == "block"  # the firm blocks data writes (sheets_append)
    assert _decide(kb, level5, "ledger_append") == "block"  # and writes the ladder has no rule for
    assert _decide(kb, level5, "ledger_read", destructive=False) == "block"  # the market pack's block stays
    _yaml(overrides / "trust.yaml", {})
    _yaml(overrides / "disable.yaml", ["ledger_append"])
    assert _decide(kb, level5, "ledger_append") == "allow"  # back to the ladder, never below it
    assert _decide(kb, _config(packs=True, trust={"level": 3}), "ledger_append") == "needs_approval"


def test_unusable_trust_values_are_ignored(kb, packs_root, ops_db, caplog):
    from realize_core.packs import clear_cache

    caplog.set_level(logging.WARNING)
    _yaml(packs_root / "profession" / "acme" / "trust.yaml", {"ledger_append": "sometimes"})
    clear_cache()
    assert _decide(kb, _config(packs=True, trust={"level": 5}), "ledger_append") == "allow"
    assert "sets trust 'sometimes' for ledger_append" in caplog.text


def test_startup_loads_venture_skills_by_configured_key(tmp_path, skills):
    """A venture whose folder differs from its key finds its skills, flag off (fixed in 5.30)."""
    from realize_core.config_runtime import sync_skill_cascade

    folder = tmp_path / "systems" / "acme-office" / "R-routines" / "skills"
    folder.mkdir(parents=True)
    (folder / "site-visit.yaml").write_text(
        "name: site_visit_report\ntriggers: [site visit report]\nsteps: []\n", encoding="utf-8"
    )
    state = SimpleNamespace(
        kb_path=tmp_path,
        systems={"acme": {"system_dir": "systems/acme-office"}},
    )
    sync_skill_cascade(state, {"features": {}})

    assert [s["name"] for s in skills.get_skills_for_system("acme")][:1] == ["site_visit_report"]
    assert skills.detect_skill("please write the site visit report", "acme")["name"] == "site_visit_report"
    assert "acme-office" not in skills._loaded_skills
    skills.reload_skills(kb_path=tmp_path)  # e.g. after a library install: same mapping
    assert skills.find_skill("site_visit_report") is not None
    assert "acme" in skills._loaded_skills
