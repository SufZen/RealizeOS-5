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
    from realize_core.skills.executor import StepFailedError, _execute_tool_step

    ctx = _ctx()
    ctx.step_results["rows"] = "I could not find any rows."
    with pytest.raises(StepFailedError, match="not valid JSON"):
        await _execute_tool_step(
            {"tool": "record_rows", "params": {"values": "{rows}"}, "json_params": ["values"]}, ctx
        )
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


# ---------------------------------------------------------------------------
# Independent review (Codex) F10/F11: failures stop the workflow; tool steps leave a trail
# ---------------------------------------------------------------------------


class RowsTool(BaseTool):
    """Like sheets_append: `values` must be rows (a list of lists)."""

    name = "rows"
    description = "rows"
    category = ToolCategory.PRODUCTIVITY

    def __init__(self):
        self.calls: list[dict] = []

    def get_schemas(self):
        schema = {
            "type": "object",
            "properties": {"values": {"type": "array", "items": {"type": "array", "items": {}}}},
        }
        return [ToolSchema("append_rows", "append rows", schema)]

    def is_available(self):
        return True

    async def execute(self, action, params):
        self.calls.append(params)
        return ToolResult.ok(output=f"appended {len(params['values'])}")


@pytest.fixture
def rows_tool(monkeypatch):
    import realize_core.tools.tool_registry as tr

    monkeypatch.setattr(tr, "_registry", None)
    tool = RowsTool()
    tr.get_tool_registry().register(tool)
    return tool


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ['{"not": "rows"}', '["a", "b"]', "[]"], ids=["object", "flat-list", "empty"])
async def test_wrong_shape_is_refused(rows_tool, value):
    from realize_core.skills.executor import StepFailedError, _execute_tool_step

    ctx = _ctx()
    ctx.step_results["rows"] = value
    with pytest.raises(StepFailedError, match="expected shape"):
        await _execute_tool_step(
            {"tool": "append_rows", "params": {"values": "{rows}"}, "json_params": ["values"]}, ctx
        )
    assert rows_tool.calls == []


@pytest.mark.asyncio
async def test_a_failed_step_stops_the_workflow(rows_tool, monkeypatch):
    from realize_core.skills import executor

    later: list[str] = []

    async def llm(system_prompt, messages, system_key, **_):
        later.append(messages[-1]["content"])
        return "FINAL REPORT"

    monkeypatch.setattr(executor, "_call_llm", llm)
    skill = {
        "name": "demo",
        "steps": [
            {
                "id": "rows",
                "type": "tool",
                "tool": "append_rows",
                "params": {"values": "no rows here"},
                "json_params": ["values"],
            },
            {"id": "report", "type": "agent", "agent": "orchestrator", "prompt": "Summarise"},
        ],
    }
    out = await executor._execute_v2_steps(skill, "go", "acme", "u1", None, {}, {}, "api")

    assert "stopped at step 'rows'" in out
    assert "FINAL REPORT" not in out
    assert later == []  # nothing after the failed step ran
    assert rows_tool.calls == []


@pytest.mark.asyncio
async def test_tool_steps_emit_the_trail(rows_tool):
    from realize_core.skills.executor import _execute_v2_steps

    events: list[dict] = []
    skill = {
        "name": "demo",
        "steps": [
            {
                "id": "write",
                "type": "tool",
                "tool": "append_rows",
                "params": {"values": '[["a", 1]]'},
                "json_params": ["values"],
            }
        ],
    }
    await _execute_v2_steps(skill, "go", "acme", "u1", None, {}, {}, "api", emit=events.append)

    assert [e["type"] for e in events] == ["tool_call", "tool_result"]
    assert events[0]["input"] == {"values": [["a", 1]]}
    assert events[1]["success"] is True
