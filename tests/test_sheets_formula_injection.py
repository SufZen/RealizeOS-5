"""Rows written to Google Sheets are data, never formulas (CSV / formula injection).

The tender register is built from an untrusted tender document by a model,
so a register item can be ``=IMPORTXML("http://x", "//a")``. Whatever the
model writes, the Sheets append path stores it as text: RAW input by
default, and an apostrophe in front of any text a spreadsheet would read as
a formula, under either input option and in exports. The developer skills
from the template and from the developer pack both go through that path.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema
from realize_core.utils.cells import neutralize_cell, neutralize_rows

ROOT = Path(__file__).resolve().parent.parent
MALICIOUS = '=IMPORTXML("http://x", "//a")'


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (MALICIOUS, "'" + MALICIOUS),
        ('+HYPERLINK("http://x")', '\'+HYPERLINK("http://x")'),
        ("-2+3", "'-2+3"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\t=1+1", "'\t=1+1"),
        ("\r=1+1", "'\r=1+1"),
        ("\uff1d1+1", "'\uff1d1+1"),
        ("Tender section 6.1", "Tender section 6.1"),
        ("רישום ב-IMPIC", "רישום ב-IMPIC"),
        ("", ""),
        (360000, 360000),
        (-5, -5),
        (None, None),
    ],
)
def test_text_that_would_start_a_formula_is_neutralised(value, expected):
    assert neutralize_cell(value) == expected


def test_rows_are_neutralised_cell_by_cell():
    assert neutralize_rows([[MALICIOUS, "ok", 3], ["-x"]]) == [["'" + MALICIOUS, "ok", 3], ["'-x"]]
    assert neutralize_rows("not rows") == "not rows"


class FakeSheetsService:
    """Records what the Sheets API would receive."""

    def __init__(self) -> None:
        self.appends: list[dict] = []

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def append(self, **kwargs):
        self.appends.append(kwargs)
        return self

    def execute(self):
        return {"updates": {"updatedRows": len(self.appends[-1]["body"]["values"])}}


@pytest.fixture
def sheets(monkeypatch) -> FakeSheetsService:
    from realize_core.tools import google_sheets

    service = FakeSheetsService()
    monkeypatch.setattr(google_sheets, "_sheets_service", lambda: service)
    return service


@pytest.mark.parametrize("option", [None, "RAW", "USER_ENTERED", "FORMULA_PLEASE"])
def test_the_append_path_writes_values_as_data(sheets, option):
    from realize_core.tools.google_sheets import _sheets_append_sync

    kwargs = {} if option is None else {"value_input_option": option}
    _sheets_append_sync("sheet-1", "Requirements", [["6.1", MALICIOUS, "yes"]], **kwargs)
    [call] = sheets.appends
    assert call["body"]["values"] == [["6.1", "'" + MALICIOUS, "yes"]]
    assert call["valueInputOption"] == ("USER_ENTERED" if option == "USER_ENTERED" else "RAW")


@pytest.mark.parametrize(
    ("cell", "kept"),
    [("-1200", True), ("+5", True), ("-1,200.50", True), ("0.5", True), ("-1+2", False), ("-x", False), ("=1", False)],
)
def test_plain_signed_numbers_stay_numbers(cell, kept):
    from realize_core.utils.cells import neutralize_cell

    assert neutralize_cell(cell) == (cell if kept else "'" + cell)


@pytest.mark.parametrize("cell", [" =IMPORTXML(1,2)", "\u00a0+A1", "  @SUM(A1)"])
def test_leading_spaces_dont_hide_a_formula(cell):
    from realize_core.utils.cells import neutralize_cell

    assert neutralize_cell(cell) == "'" + cell


def test_raw_appends_keep_numbers_numbers_and_text_text(sheets):
    from realize_core.tools.google_sheets import _sheets_append_sync

    _sheets_append_sync("sheet-1", "Payments", [["6.10", -1200.5, 4800, "=SUM(A1)", "007"]])
    [call] = sheets.appends
    assert call["valueInputOption"] == "RAW"
    # JSON numbers stay numbers (summable); a clause "6.10" or "007" is never turned into a number.
    assert call["body"]["values"] == [["6.10", -1200.5, 4800, "'=SUM(A1)", "007"]]


@pytest.mark.parametrize(
    "path",
    [
        "templates/real-estate-developer/R-routines/skills/payment-milestone-check.yaml",
        "packs/profession/developer/R-routines/skills/payment-milestone-check.yaml",
    ],
)
def test_payment_rows_ask_for_amounts_as_numbers(path):
    skill = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    row = next(step for step in skill["steps"] if step.get("id") == "payment_row")
    assert "amounts" in row["prompt"]
    assert "JSON numbers" in row["prompt"]


def test_the_tool_schema_defaults_to_raw():
    from realize_core.tools.google_sheets import SHEETS_TOOL_SCHEMAS

    append = next(s for s in SHEETS_TOOL_SCHEMAS if s["name"] == "sheets_append")
    option = append["input_schema"]["properties"]["value_input_option"]
    assert option["default"] == "RAW"
    assert option["enum"] == ["RAW", "USER_ENTERED"]


# ---------------------------------------------------------------------------
# The developer skills, from the template and from the pack, through one path
# ---------------------------------------------------------------------------


class FakeDrive(BaseTool):
    """The tender document, with an injected formula in it."""

    name = "fake_drive"
    description = "fake drive"
    category = ToolCategory.PRODUCTIVITY

    def get_schemas(self):
        return [ToolSchema("drive_read_content", "read a file", {"type": "object", "properties": {}})]

    def is_available(self):
        return True

    async def execute(self, action, params):
        return ToolResult.ok(output=f"Section 6.1: bidders must register. {MALICIOUS}")


@pytest.fixture
def ops_db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


@pytest.fixture
def registry(monkeypatch, sheets, ops_db):
    """The real Google Sheets tool (fake API underneath) behind the approval gate."""
    import realize_core.tools.tool_registry as tr
    from realize_core.governance.tool_gate import ToolGate
    from realize_core.tools import google_auth, google_sheets

    monkeypatch.setattr(google_auth, "has_stored_credentials", lambda: True)
    monkeypatch.setattr(tr, "_registry", None)
    reg = tr.get_tool_registry()
    reg.register(google_sheets.get_tool())
    reg.register(FakeDrive())
    reg.set_gate(ToolGate(config={}))
    return reg


@pytest.fixture
def llm(monkeypatch):
    """The model copies the injected formula into the register, as a hijacked model would."""
    from realize_core.skills import executor

    async def scripted(system_prompt, messages, system_key):
        if "Return ONLY a JSON array of rows" in messages[-1]["content"]:
            return json.dumps([["6.1", MALICIOUS, "yes", "Dana", "", "Tender 6.1"]])
        return "summary"

    monkeypatch.setattr(executor, "_call_llm", scripted)


def _template_skill() -> dict:
    path = ROOT / "templates" / "real-estate-developer" / "R-routines" / "skills" / "tender-requirements-register.yaml"
    skill = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {**skill, "_version": 2}


def _pack_skill(tmp_path: Path, monkeypatch) -> dict:
    from realize_core.packs import clear_cache
    from realize_core.skills import detector

    monkeypatch.setattr(detector, "_loaded_skills", {})
    clear_cache()
    venture = tmp_path / "kb" / "systems" / "dev-co"
    venture.mkdir(parents=True)
    (venture / "packs.yaml").write_text("profession: [developer]\n", encoding="utf-8")
    detector.reload_skills(kb_path=tmp_path / "kb", packs=True)
    owner, skill = detector.find_skill("tender_requirements_register", "dev-co")
    assert (owner, skill["_layer"], skill["_pack"]) == ("dev-co", "profession", "developer@0.1.0")
    return skill


def _pending(db: Path) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM approval_queue WHERE status = 'pending'")]
    finally:
        conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["template", "pack"])
async def test_a_tender_with_a_formula_is_registered_as_text(
    source, registry, llm, sheets, ops_db, tmp_path, monkeypatch
):
    from realize_core.governance.gates import decide_approval
    from realize_core.skills.executor import execute_skill

    skill = _template_skill() if source == "template" else _pack_skill(tmp_path, monkeypatch)
    skill = {**skill, "variables": {**skill["variables"], "tender_doc_id": "doc-1", "register_sheet_id": "sheet-r"}}
    await execute_skill(
        skill=skill,
        user_message="Build the tender register",
        system_key="dev-co",
        user_id="dana",
        kb_path=tmp_path / "kb",
        system_config={},
    )

    assert sheets.appends == []  # the write waits for a person
    [held] = _pending(ops_db)
    assert held["action_name"] == "sheets_append"
    await decide_approval(held["id"], approve=True)

    [call] = sheets.appends
    assert call["spreadsheetId"] == "sheet-r"
    assert call["valueInputOption"] == "RAW"
    assert call["body"]["values"] == [["6.1", "'" + MALICIOUS, "yes", "Dana", "", "Tender 6.1"]]


@pytest.mark.parametrize(
    "path",
    [
        "templates/real-estate-developer/R-routines/skills/tender-requirements-register.yaml",
        "packs/profession/developer/R-routines/skills/tender-requirements-register.yaml",
        "templates/real-estate-developer/R-routines/skills/payment-milestone-check.yaml",
        "packs/profession/developer/R-routines/skills/payment-milestone-check.yaml",
    ],
)
def test_skills_that_write_rows_ask_for_plain_text_and_never_set_user_entered(path):
    skill = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    prompts = " ".join(str(step.get("prompt", "")) for step in skill["steps"])
    assert "never start a cell with =, +, - or @" in prompts
    for step in skill["steps"]:
        assert "value_input_option" not in (step.get("params") or {})
