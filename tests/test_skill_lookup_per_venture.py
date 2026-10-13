"""Skills are looked up for the venture a run is for (review G-1).

Since 5.30 every venture's skills load at startup, and with ``features.packs``
on each venture gets its own copy of a pack skill, with its own ``variables``
(its sheet ids). Two ventures with a skill of the same name are normal: two
developer ventures, or two ventures on one pack. A run for ``beta`` must use
beta's copy (never alpha's, whose sheet it would read and write), and a caller
limited to ``beta`` must be able to run it.
"""

from __future__ import annotations

import json
import textwrap
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

USERS_YAML = textwrap.dedent(
    """
    users:
      - email: owner@realization.co.il
        role: owner
        password_hash: "$2b$12$owner"
      - email: bea@beta.io
        role: operator
        ventures: [beta]
        password_hash: "$2b$12$bea"
    """
)

SKILL = "payment_milestone_check"


def _sheet_ids(venture: str) -> dict[str, str]:
    return {"milestones_sheet_id": f"{venture}-milestones", "payments_sheet_id": f"{venture}-payments"}


@pytest.fixture
def skills(monkeypatch):
    """A fresh skill registry."""
    from realize_core.packs import clear_cache
    from realize_core.skills import detector

    monkeypatch.delenv("REALIZE_PACKS_PATH", raising=False)
    clear_cache()
    monkeypatch.setattr(detector, "_loaded_skills", {})
    monkeypatch.setattr(detector, "_skills_loaded", False)
    yield detector
    clear_cache()


def _project(root, packs: bool) -> None:
    features = "features:\n  packs: true\n" if packs else ""
    (root / "realize-os.yaml").write_text(f"name: test\n{features}systems: []\n", encoding="utf-8")
    (root / "users.yaml").write_text(USERS_YAML, encoding="utf-8")


@pytest.fixture
def pack_ventures(tmp_path, monkeypatch, skills):
    """alpha and beta from the developer template with packs on, each with its own sheet ids."""
    from realize_core.scaffold import scaffold_venture

    monkeypatch.chdir(tmp_path)
    _project(tmp_path, packs=True)
    for key in ("alpha", "beta"):
        scaffold_venture(tmp_path, key, template="real-estate-developer")
        settings_file = tmp_path / "systems" / key / "F-foundations" / "overrides" / "skill-settings.yaml"
        settings = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
        settings[SKILL]["variables"] = _sheet_ids(key)
        settings_file.write_text(yaml.safe_dump(settings, allow_unicode=True), encoding="utf-8")
    skills.reload_skills(kb_path=tmp_path, packs=True)
    return tmp_path


@pytest.fixture
def copied_ventures(tmp_path, monkeypatch, skills):
    """alpha and beta from the developer template with packs off: each has its own copied skill files."""
    from realize_core.scaffold import scaffold_venture

    monkeypatch.chdir(tmp_path)
    _project(tmp_path, packs=False)
    for key in ("alpha", "beta"):
        scaffold_venture(tmp_path, key, template="real-estate-developer")
        skill_file = tmp_path / "systems" / key / "R-routines" / "skills" / "payment-milestone-check.yaml"
        skill = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
        skill["variables"].update(_sheet_ids(key))
        skill_file.write_text(yaml.safe_dump(skill, allow_unicode=True), encoding="utf-8")
    skills.reload_skills(kb_path=tmp_path)
    return tmp_path


def _person(user_id: str, role: str):
    from realize_api.dependencies import CurrentUser

    return CurrentUser(user_id=user_id, role=role, scopes=[])


async def _mcp(state, user, name: str, args: dict) -> dict:
    from realize_core.mcp_server import registry as registry_mod
    from realize_core.mcp_server.auth import bind_user, reset_user
    from realize_core.mcp_server.config import McpConfig
    from realize_core.mcp_server.server import _dispatch

    config = McpConfig(
        enabled=True,
        expose_kb=True,
        expose_ops=True,
        allow_admin=False,
        audit_full_payload=False,
        bearer_token_override="",
    )
    registry_mod.reset_for_tests()
    token = bind_user(user)
    try:
        out = await _dispatch(registry_mod.get_registry(), config, state, name, args)
    finally:
        reset_user(token)
        registry_mod.reset_for_tests()
    return json.loads(out[0].text)


@pytest.fixture
def runs(monkeypatch):
    """Skill runs, recorded instead of executed."""
    from realize_core.skills import executor

    seen: list[dict] = []

    async def fake_execute_skill(**kwargs):
        seen.append(kwargs)
        return "checked"

    monkeypatch.setattr(executor, "execute_skill", fake_execute_skill)
    return seen


def _state(root) -> SimpleNamespace:
    systems = {"alpha": {"name": "Alpha"}, "beta": {"name": "Beta"}}
    return SimpleNamespace(systems=systems, kb_path=root, shared_config={}, config={"features": {}})


@pytest.mark.parametrize("ventures", ["pack_ventures", "copied_ventures"])
def test_each_venture_finds_its_own_copy(ventures, request, skills):
    request.getfixturevalue(ventures)
    for key in ("alpha", "beta"):
        owner, skill = skills.find_skill(SKILL, key)
        assert owner == key
        assert {k: skill["variables"][k] for k in _sheet_ids(key)} == _sheet_ids(key)
    # Without a venture the name is ambiguous: no venture's copy is picked for the caller.
    assert skills.find_skill(SKILL) is None
    assert skills.ventures_with_skill(SKILL) == ["alpha", "beta"]
    # A venture without its own copy never gets another venture's.
    assert skills.find_skill(SKILL, "gamma") is None


@pytest.mark.parametrize("ventures", ["pack_ventures", "copied_ventures"])
async def test_a_run_for_beta_uses_betas_sheet(ventures, request, runs):
    root = request.getfixturevalue(ventures)
    owner = _person("owner@realization.co.il", "owner")
    out = await _mcp(_state(root), owner, "trigger_skill", {"name": SKILL, "input_text": "claim", "system_key": "beta"})
    assert out["system_key"] == "beta"
    assert runs[-1]["system_key"] == "beta"
    assert runs[-1]["skill"]["variables"]["payments_sheet_id"] == "beta-payments"

    # Without a venture the caller is asked to name one, never given the first venture's copy.
    out = await _mcp(_state(root), owner, "run_workflow", {"name": SKILL, "input_text": "claim"})
    assert out["code"] == "MCP_VALIDATION"
    assert "system_key" in out["error"]
    assert len(runs) == 1


@pytest.mark.parametrize("ventures", ["pack_ventures", "copied_ventures"])
async def test_a_beta_limited_caller_can_run_betas_copy(ventures, request, runs):
    from realize_core.mcp_server.venture_guard import check_call

    root = request.getfixturevalue(ventures)
    args = {"name": SKILL, "input_text": "claim", "system_key": "beta"}
    assert check_call("run_workflow", args, frozenset({"beta"})) is None
    bea = _person("bea@beta.io", "operator")
    out = await _mcp(_state(root), bea, "run_workflow", args)
    assert out["system_key"] == "beta"
    assert runs[-1]["skill"]["variables"]["milestones_sheet_id"] == "beta-milestones"
    # Naming alpha is still refused.
    refused = await _mcp(_state(root), bea, "run_workflow", {**args, "system_key": "alpha"})
    assert refused["code"] == "MCP_FORBIDDEN"
    assert len(runs) == 1


def _client(user_id: str | None, role: str = "owner") -> TestClient:
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = {"alpha": {"name": "Alpha", "agents": {}}, "beta": {"name": "Beta", "agents": {}}}
    app.state.config = {"features": {}}
    if user_id is not None:

        @app.middleware("http")
        async def as_principal(request, call_next):
            request.state.user_id = user_id
            request.state.role = role
            request.state.scopes = []
            return await call_next(request)

    return TestClient(app)


def test_rest_detail_is_looked_up_for_the_venture(pack_ventures):
    beta_only = _client("bea@beta.io", "operator")
    detail = beta_only.get(f"/api/workflows/{SKILL}")
    assert detail.status_code == 200
    assert detail.json()["system_key"] == "beta"
    assert beta_only.get(f"/api/workflows/{SKILL}?system_key=beta").json()["system_key"] == "beta"

    owner = _client("owner@realization.co.il")
    assert owner.get(f"/api/workflows/{SKILL}?system_key=beta").json()["system_key"] == "beta"
    assert owner.get(f"/api/workflows/{SKILL}?system_key=alpha").json()["system_key"] == "alpha"
    assert owner.get(f"/api/workflows/{SKILL}?system_key=gamma").status_code == 404


def test_rest_edits_name_the_venture_when_the_name_is_shared(pack_ventures, skills):
    owner = _client("owner@realization.co.il")
    assert owner.put(f"/api/workflows/{SKILL}", json={"enabled": False}).status_code == 409
    assert owner.put(f"/api/workflows/{SKILL}?system_key=beta", json={"enabled": False}).status_code == 200
    assert skills.find_skill(SKILL, "beta")[1]["enabled"] is False
    assert skills.find_skill(SKILL, "alpha")[1].get("enabled", True) is True
    assert owner.delete(f"/api/workflows/{SKILL}").status_code == 409
    assert owner.delete(f"/api/workflows/{SKILL}?system_key=alpha").status_code == 200
    assert skills.ventures_with_skill(SKILL) == ["beta"]
    # A venture can create a skill whose name another venture already uses.
    body = {"name": "site_diary", "system_key": "alpha", "steps": [{"id": "s1", "type": "agent"}]}
    assert owner.post("/api/workflows", json=body).status_code == 201
    assert owner.post("/api/workflows", json={**body, "system_key": "beta"}).status_code == 201
    assert owner.post("/api/workflows", json=body).status_code == 409
    assert skills.ventures_with_skill("site_diary") == ["alpha", "beta"]
    # Even a name only one venture has is changed only when the venture is named.
    assert owner.put("/api/workflows/site_diary?system_key=alpha", json={"enabled": False}).status_code == 200
    assert owner.delete(f"/api/workflows/{SKILL}").status_code == 409


# ---------------------------------------------------------------------------
# No fallback to another venture's copy (security review of G-1)
# ---------------------------------------------------------------------------


def test_without_a_venture_only_shared_skills_are_found(skills, monkeypatch):
    monkeypatch.setattr(
        skills,
        "_loaded_skills",
        {"alpha": [{"name": "site_diary"}], "shared": [{"name": "weekly_summary"}]},
    )
    assert skills.find_skill("site_diary") is None  # even when only one venture has it
    assert skills.get_skill_by_name("site_diary") is None
    assert skills.find_skill("site_diary", "alpha")[0] == "alpha"
    assert skills.find_skill("weekly_summary") == ("shared", {"name": "weekly_summary"})
    assert skills.find_skill("weekly_summary", "beta")[0] == "shared"
    assert skills.find_skill("site_diary", "beta") is None


async def test_a_run_without_a_venture_never_uses_a_ventures_copy(skills, monkeypatch, runs, tmp_path):
    from realize_core.mcp_server.tools.ops_tools import run_workflow

    monkeypatch.setattr(skills, "_loaded_skills", {"alpha": [{"name": "site_diary", "variables": {"sheet": "a"}}]})
    owner = _person("owner@realization.co.il", "owner")
    for venture in ({}, {"system_key": ""}):
        out = await run_workflow({"name": "site_diary", "input_text": "go", **venture}, _state(tmp_path), owner)
        assert out["code"] == "MCP_VALIDATION"
        assert "alpha" not in out["error"]  # which ventures have it is not told
    assert runs == []


async def test_an_unseen_venture_is_refused_before_any_lookup(skills, monkeypatch, runs, tmp_path):
    from realize_core.mcp_server.tools.ops_tools import run_workflow

    monkeypatch.chdir(tmp_path)
    _project(tmp_path, packs=False)

    def no_lookup(*args, **kwargs):
        raise AssertionError("the skill must not be looked up")

    monkeypatch.setattr(skills, "find_skill", no_lookup)
    bea = _person("bea@beta.io", "operator")
    out = await run_workflow({"name": SKILL, "input_text": "go", "system_key": "alpha"}, _state(tmp_path), bea)
    assert out["code"] == "MCP_FORBIDDEN"
    out = await run_workflow({"name": SKILL, "input_text": "go"}, _state(tmp_path), bea)
    assert out["code"] == "MCP_VALIDATION"
    assert runs == []


def test_a_venture_keyed_like_the_shared_skills_does_not_share_its_own(tmp_path, skills, caplog):
    for key, name in (("shared", "secret_payroll"), ("alpha", "site_diary")):
        folder = tmp_path / "systems" / key / "R-routines" / "skills"
        folder.mkdir(parents=True)
        (folder / f"{name}.yaml").write_text(f"name: {name}\ntriggers: [{name}]\n", encoding="utf-8")
    skills.reload_skills(kb_path=tmp_path)
    assert skills.find_skill("secret_payroll", "alpha") is None
    assert "secret_payroll" not in [s["name"] for s in skills.get_skills_for_system("alpha")]
    assert "reserved for shared skills" in caplog.text
    assert skills.find_skill("site_diary", "alpha") is not None
