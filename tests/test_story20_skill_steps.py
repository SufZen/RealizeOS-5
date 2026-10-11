"""STORY-20 — skill variables and JSON tool params (used by the demo pack skills)."""

from __future__ import annotations

import pytest
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema


class Recorder(BaseTool):
    name = "recorder"
    description = "records params"
    category = ToolCategory.PRODUCTIVITY

    def __init__(self):
        self.calls: list[dict] = []

    def get_schemas(self):
        return [ToolSchema("record_rows", "record", {"type": "object", "properties": {}})]

    def is_available(self):
        return True

    async def execute(self, action, params):
        self.calls.append(params)
        return ToolResult.ok(output="recorded")


@pytest.fixture
def recorder(monkeypatch):
    import realize_core.tools.tool_registry as tr

    monkeypatch.setattr(tr, "_registry", None)
    tool = Recorder()
    tr.get_tool_registry().register(tool)
    return tool


def _ctx():
    from realize_core.skills.executor import SkillContext

    return SkillContext("go", "acme", "u1")


@pytest.mark.parametrize(
    "text",
    [
        '[["a", 1]]',
        '```json\n[["a", 1]]\n```',
        'Here are the rows: [["a", 1]] — done.',
    ],
    ids=["plain", "fenced", "prose"],
)
def test_parse_json_text(text):
    from realize_core.skills.executor import _parse_json_text

    assert _parse_json_text(text) == [["a", 1]]


def test_parse_json_text_rejects_non_json():
    from realize_core.skills.executor import _parse_json_text

    with pytest.raises(ValueError):
        _parse_json_text("no rows here")


@pytest.mark.asyncio
async def test_json_params_reach_the_tool_as_data(recorder):
    from realize_core.skills.executor import _execute_tool_step

    ctx = _ctx()
    ctx.step_results["rows"] = '```json\n[["2026-10-11", "120000"]]\n```'
    step = {"tool": "record_rows", "params": {"values": "{rows}", "sheet": "{rows}"}, "json_params": ["values"]}

    assert await _execute_tool_step(step, ctx) == "recorded"
    assert recorder.calls[0]["values"] == [["2026-10-11", "120000"]]
    assert isinstance(recorder.calls[0]["sheet"], str)  # only listed params are parsed


@pytest.mark.asyncio
async def test_invalid_json_param_stops_the_step(recorder):
    from realize_core.skills.executor import _execute_tool_step

    ctx = _ctx()
    ctx.step_results["rows"] = "I could not find any rows."
    out = await _execute_tool_step(
        {"tool": "record_rows", "params": {"values": "{rows}"}, "json_params": ["values"]}, ctx
    )

    assert out == "Error: 'values' for record_rows is not valid JSON"
    assert recorder.calls == []


@pytest.mark.asyncio
async def test_skill_variables_fill_placeholders(recorder, monkeypatch):
    from realize_core.skills.executor import _execute_v2_steps

    skill = {
        "name": "demo",
        "variables": {"sheet_id": "sheet-42"},
        "steps": [{"id": "write", "type": "tool", "tool": "record_rows", "params": {"spreadsheet_id": "{sheet_id}"}}],
    }
    await _execute_v2_steps(skill, "go", "acme", "u1", None, {}, {}, "api")

    assert recorder.calls == [{"spreadsheet_id": "sheet-42"}]
