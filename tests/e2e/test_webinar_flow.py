"""STORY-20 — the webinar storyline end to end, with a mocked LLM and Google tools.

Seed the Hebrew demo venture → Hebrew requests trigger the right skills →
the tender becomes a requirements register, the contractor's payment request
is checked against the milestones, and each sheet write waits for approval and
runs exactly once when approved → the investor report is a reviewed draft.

Every storyline test runs twice (STORY-43): with packs off, the venture is
created from the template and has its own copies of the agents and skills;
with ``features.packs`` on, it links the developer pack and gets them from it.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
import yaml
from realize_core.memory.conversation import add_message as _real_add_message
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

DEMO = "tower-b-demo"

TENDER_TEXT = "תנאי המכרז, סעיף 6.1: על המציע להיות רשום ב-IMPIC. חוזה, סעיף 18: ערבות ביצוע 5%."
MILESTONES = [["4", "שלד — קומות 4-6 וגג", "10%", "360000", "אישור מפקח, תמונות מתוארכות, דוח מדידה"]]
BUDGET = [['סה"כ', "6000000", "5640000", "2926000"]]


class FakeGoogle(BaseTool):
    """Drive and Sheets for the demo: reads return fixtures, appends are recorded."""

    name = "google_demo"
    description = "Demo Drive and Sheets"
    category = ToolCategory.PRODUCTIVITY

    def __init__(self):
        self.appended: list[tuple[str, str, list]] = []
        self.reads: list[dict] = []

    def get_schemas(self):
        obj = {"type": "object", "properties": {}}
        return [
            ToolSchema("drive_read_content", "read a Drive file", obj),
            ToolSchema("sheets_read", "read a sheet range", obj),
            ToolSchema("sheets_append", "append rows", obj, is_destructive=True),
        ]

    def is_available(self):
        return True

    async def execute(self, action, params):
        if action == "drive_read_content":
            return ToolResult.ok(output=TENDER_TEXT)
        if action == "sheets_read":
            self.reads.append(params)
            rows = MILESTONES if params.get("range") == "Milestones" else BUDGET
            return ToolResult.ok(output=json.dumps(rows, ensure_ascii=False))
        if action == "sheets_append":
            self.appended.append((params["spreadsheet_id"], params["range"], params["values"]))
            return ToolResult.ok(output=f"appended {len(params['values'])} rows")
        return ToolResult.fail(f"unknown action {action}")


@pytest.fixture(params=["template", "packs"])
def project(request, tmp_path):
    from realize_core.demo_seed import seed_webinar_demo
    from realize_core.packs import clear_cache

    clear_cache()
    root = tmp_path / "project"
    root.mkdir()
    if request.param == "packs":
        (root / "realize-os.yaml").write_text("features:\n  packs: true\nsystems: []\n", encoding="utf-8")
    seed_webinar_demo(root)
    return root


def _packs_on(root) -> bool:
    config = yaml.safe_load((root / "realize-os.yaml").read_text(encoding="utf-8")) or {}
    return bool((config.get("features") or {}).get("packs"))


def _reload(root) -> None:
    """Load the project's skills the way the app does: with the packs' skills when packs are on."""
    from realize_core.skills.detector import reload_skills

    reload_skills(kb_path=root, packs=_packs_on(root))


def _set_ids(root, skill: str, **ids) -> None:
    """Set a skill's Google ids where the venture keeps them (its skill file, or skill-settings.yaml)."""
    own = list((root / "systems" / DEMO / "R-routines" / "skills").glob("*.yaml"))
    if own:
        for path in own:
            text = path.read_text(encoding="utf-8")
            for name, value in ids.items():
                text = text.replace(f'{name}: "REPLACE_WITH_SHEET_ID"', f'{name}: "{value}"')
            path.write_text(text, encoding="utf-8")
        return
    path = root / "systems" / DEMO / "F-foundations" / "overrides" / "skill-settings.yaml"
    settings = yaml.safe_load(path.read_text(encoding="utf-8"))
    settings[skill]["variables"].update(ids)
    path.write_text(yaml.safe_dump(settings, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def ops_db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


@pytest.fixture
def google(monkeypatch, ops_db):
    """The registry with the demo Google tool behind the approval gate."""
    import realize_core.tools.tool_registry as tr
    from realize_core.governance.tool_gate import ToolGate

    monkeypatch.setattr(tr, "_registry", None)
    registry = tr.get_tool_registry()
    tool = FakeGoogle()
    registry.register(tool)
    registry.set_gate(ToolGate(config={}))
    return tool


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """Fresh skill registry and no writes into real conversations."""
    import realize_core.memory.conversation as conv
    from realize_core.llm import router
    from realize_core.skills import detector

    monkeypatch.setattr(detector, "_loaded_skills", {})
    monkeypatch.setattr(detector, "_skills_loaded", False)
    monkeypatch.setattr(conv, "add_message", lambda *a, **k: None)
    monkeypatch.setattr(router, "_check_rate_limit", lambda: True)
    monkeypatch.setattr(router, "_check_cost_limit", lambda: True)


@pytest.fixture
def llm(monkeypatch):
    """Scripted model: JSON when a step asks for rows, a labelled answer otherwise."""
    from realize_core.skills import executor

    calls: list[dict] = []

    async def scripted(system_prompt, messages, system_key):
        prompt = messages[-1]["content"]
        agent = (
            system_prompt.split("## Active Agent: ", 1)[1].split("\n", 1)[0]
            if "## Active Agent: " in system_prompt
            else "?"
        )
        calls.append({"agent": agent, "prompt": prompt, "system_key": system_key})
        if "Return ONLY a JSON array of rows" in prompt:
            return '```json\n[["מנהלי", "רישום ב-IMPIC", "yes", "דנה", "", "תנאי המכרז 6.1"]]\n```'
        if "Return ONLY a JSON array with one row" in prompt:
            return 'Here it is: [["2026-10-11", "קבלן הדגמה", "4", "360000", "342000", "PARTIAL", "אישור מפקח חתום"]]'
        if "Produce the final report" in prompt:
            return "דוח רבעוני — טיוטה (Sheet: Summary)\n\nDraft for the developer — not sent to investors."
        return f"[{agent}] ok"

    monkeypatch.setattr(executor, "_call_llm", scripted)
    return calls


def _systems(root):
    from realize_core.config import build_systems_dict

    config = yaml.safe_load((root / "realize-os.yaml").read_text(encoding="utf-8"))
    return build_systems_dict(config, kb_path=root)


def _load_skill(root, name: str, **variables) -> dict:
    from realize_core.skills.detector import find_skill

    _reload(root)
    owner, skill = find_skill(name, DEMO)
    assert owner == DEMO
    return {**skill, "variables": {**skill.get("variables", {}), **variables}}


async def _run(root, skill, message):
    from realize_core.skills.executor import execute_skill

    return await execute_skill(
        skill=skill,
        user_message=message,
        system_key=DEMO,
        user_id="dana",
        kb_path=root,
        system_config=_systems(root)[DEMO],
        shared_config={},
        channel="api",
    )


def _pending(db) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM approval_queue WHERE status = 'pending'")]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The storyline
# ---------------------------------------------------------------------------


def test_seed_creates_the_hebrew_demo_venture(project):
    venture = project / "systems" / DEMO
    team = {"orchestrator", "tenders", "procurement", "site_payments", "finance_investors", "reviewer"}
    agents = {p.stem for p in (venture / "A-agents").glob("*.md")}
    if _packs_on(project):
        # Linked, not copied: the team comes from the developer pack.
        assert agents == set()
        provenance = _systems(project)[DEMO]["agent_provenance"].values()
        assert {(p["layer"], p["pack"]) for p in provenance} == {("profession", "developer@0.1.0")}
    else:
        assert {"orchestrator", "tenders", "procurement", "site-payments", "finance-investors", "reviewer"} <= agents
    assert team <= set(_systems(project)[DEMO]["agents"])
    assert len(list((venture / "B-brain" / "project").glob("*.md"))) == 6
    assert "נתוני הדגמה" in (venture / "B-brain" / "project" / "budget.md").read_text(encoding="utf-8")

    system = _systems(project)[DEMO]
    assert system["locale"] == "he"
    assert "דרישת תשלום" in system["agent_routing"]["site_payments"]


def test_hebrew_requests_trigger_the_demo_skills(project):
    from realize_core.skills.detector import detect_skill

    _reload(project)
    assert detect_skill("קיבלנו דרישת תשלום 4 מהקבלן", DEMO)["name"] == "payment_milestone_check"
    assert detect_skill("תבנה רשימת דרישות מתיק המכרז", DEMO)["name"] == "tender_requirements_register"
    assert detect_skill("תכין דוח רבעוני למשקיעים", DEMO)["name"] == "investor_report"


@pytest.mark.asyncio
async def test_tender_becomes_a_register_after_approval(project, google, llm, ops_db):
    from realize_core.governance.gates import decide_approval

    skill = _load_skill(project, "tender_requirements_register", tender_doc_id="doc-1", register_sheet_id="sheet-r")
    await _run(project, skill, "תבנה רשימת דרישות מתיק המכרז")

    # The tender agent read the document; the register write waits for the developer.
    assert TENDER_TEXT in next(c["prompt"] for c in llm if c["agent"] == "tenders")
    assert google.appended == []
    [held] = _pending(ops_db)
    assert held["action_name"] == "sheets_append"
    assert json.loads(held["params_json"])["values"][0][1] == "רישום ב-IMPIC"  # parsed from the fenced JSON

    await decide_approval(held["id"], approve=True)
    assert google.appended == [
        ("sheet-r", "Requirements", [["מנהלי", "רישום ב-IMPIC", "yes", "דנה", "", "תנאי המכרז 6.1"]])
    ]


@pytest.mark.asyncio
async def test_payment_request_is_checked_and_runs_once_when_approved(project, google, llm, ops_db):
    from realize_core.governance.gates import decide_approval

    skill = _load_skill(project, "payment_milestone_check", milestones_sheet_id="sheet-m", payments_sheet_id="sheet-p")
    await _run(project, skill, "קיבלנו דרישת תשלום 4: 360,000 € על סיום השלד")

    check = next(c for c in llm if "Compare it with the milestone schedule" in c["prompt"])
    assert check["agent"] == "site_payments"
    assert "שלד — קומות 4-6 וגג" in check["prompt"]  # the milestone sheet reached the agent
    assert google.appended == []  # nothing written, nothing paid

    [held] = _pending(ops_db)
    assert held["venture_key"] == DEMO
    await decide_approval(held["id"], approve=True)
    assert await decide_approval(held["id"], approve=True) is None  # a second approval runs nothing
    assert len(google.appended) == 1
    sheet, tab, rows = google.appended[0]
    assert (sheet, tab) == ("sheet-p", "Payments")
    assert rows[0][5] == "PARTIAL"


@pytest.mark.asyncio
async def test_investor_report_is_a_reviewed_draft(project, google, llm, ops_db):
    skill = _load_skill(project, "investor_report", budget_sheet_id="sheet-b")
    report = await _run(project, skill, "תכין דוח רבעוני למשקיעים")

    assert google.reads == [{"spreadsheet_id": "sheet-b", "range": "Summary"}]
    assert [c["agent"] for c in llm] == ["finance_investors", "reviewer", "finance_investors"]
    assert "Draft for the developer — not sent to investors." in report
    assert _pending(ops_db) == []  # reading and drafting need no approval


def test_every_agent_the_template_names_exists(project):
    """Routing and skill steps must use discovered agent keys (file stem, '-' → '_')."""
    from realize_core.skills.detector import get_skills_for_system

    system = _systems(project)[DEMO]
    agents = set(system["agents"])
    named = set(system["agent_routing"]) | {a for chain in system["routing"].values() for a in chain}
    _reload(project)
    skills = get_skills_for_system(DEMO)
    assert {s["name"] for s in skills} == {"tender_requirements_register", "payment_milestone_check", "investor_report"}
    for skill in skills:
        named |= {skill["agent"]} | {s["agent"] for s in skill["steps"] if s.get("type") == "agent"}
    assert named <= agents, f"unknown agents: {sorted(named - agents)}"


def test_cli_creates_a_venture_from_the_template(tmp_path):
    """`realize-os venture create --template real-estate-developer` uses the developer team."""
    import argparse

    from cli import cmd_venture

    cmd_venture(
        argparse.Namespace(
            venture_action="create",
            key="acme-dev",
            name=None,
            description=None,
            directory=str(tmp_path),
            confirm=None,
            template="real-estate-developer",
        )
    )
    agents = {p.stem for p in (tmp_path / "systems" / "acme-dev" / "A-agents").glob("*.md")}
    assert {"tenders", "site-payments", "finance-investors"} <= agents


# ---------------------------------------------------------------------------
# The payment case through the real API (review F11): permission, held write,
# approval outcome and the stored trail, as a scoped operator
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    from realize_core.memory.conversation import clear_all
    from realize_core.memory.store import init_db

    monkeypatch.setattr("realize_core.memory.store.DB_PATH", tmp_path / "memory.db")
    init_db()
    clear_all()
    yield
    clear_all()


def _api(project, user_id, scopes):
    from fastapi.testclient import TestClient
    from realize_api.main import create_app

    _reload(project)
    app = create_app()
    app.state.systems = _systems(project)
    app.state.kb_path = project
    app.state.config = {"features": {"packs": True} if _packs_on(project) else {}}

    @app.middleware("http")
    async def as_principal(request, call_next):
        request.state.user_id = user_id
        request.state.role = "operator"
        request.state.scopes = list(scopes)
        return await call_next(request)

    return TestClient(app)


def test_payment_case_through_the_api(project, google, llm, ops_db, memory_db, monkeypatch):
    import realize_core.memory.conversation as conv

    # The autouse fixture stubs add_message; this test stores real history.
    monkeypatch.setattr(conv, "add_message", _real_add_message)

    _set_ids(project, "payment_milestone_check", milestones_sheet_id="sheet-m", payments_sheet_id="sheet-p")

    dana = _api(project, "dana@demo", [f"venture:{DEMO}"])
    body = dana.post(
        "/api/chat", json={"message": "קיבלנו דרישת תשלום 4: 360,000 € על סיום השלד", "system_key": DEMO}
    ).json()

    # The skill's tool steps are in the answer's trail: the sheet it read and the held write.
    steps = body["trail"]["steps"]
    read = next(s for s in steps if s["type"] == "tool_call" and s["name"] == "sheets_read")
    assert read["input"] == {"spreadsheet_id": "sheet-m", "range": "Milestones"}
    held = next(s for s in steps if s["type"] == "approval_requested")
    assert google.appended == []

    # The trail is stored with the answer.
    history = dana.get(f"/api/conversations/{DEMO}/dana@demo").json()["messages"]
    assert history[-1]["trail"]["steps"]

    # Someone limited to another venture can't see or decide it.
    other = _api(project, "eve@other", ["venture:other"])
    assert other.post(f"/api/approvals/{held['request_id']}/approve", json={}).status_code in (403, 404)
    assert google.appended == []

    # The operator approves: the write runs once, and the decider is on the row.
    assert dana.post(f"/api/approvals/{held['request_id']}/approve", json={}).status_code == 200
    assert len(google.appended) == 1
    assert dana.post(f"/api/approvals/{held['request_id']}/approve", json={}).status_code == 409
    conn = sqlite3.connect(ops_db)
    decided_by, status = conn.execute(
        "SELECT decided_by, execution_status FROM approval_queue WHERE id = ?", (held["request_id"],)
    ).fetchone()
    conn.close()
    assert (decided_by, status) == ("dana@demo", "succeeded")
