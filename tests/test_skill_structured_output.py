"""Skills: model/tier pinning, unresolved placeholders, and JSON steps on any provider.

The payment-row scenario is the webinar bug: on Gemini the JSON step echoed the
prompt's template row ("contractor", "milestone", "verdict") instead of values.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import litellm  # noqa: F401  (imported before any test clears provider keys)
import pytest
import yaml
from realize_core.llm.base_provider import BaseLLMProvider, LLMResponse, ModelInfo
from realize_core.llm.registry import ProviderRegistry
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

ROOT = Path(__file__).resolve().parents[1]
PAYMENT_YAMLS = [
    ROOT / "packs" / "profession" / "developer" / "R-routines" / "skills" / "payment-milestone-check.yaml",
    ROOT / "templates" / "real-estate-developer" / "R-routines" / "skills" / "payment-milestone-check.yaml",
]
TENDER_YAMLS = [
    ROOT / "packs" / "profession" / "developer" / "R-routines" / "skills" / "tender-requirements-register.yaml",
    ROOT / "templates" / "real-estate-developer" / "R-routines" / "skills" / "tender-requirements-register.yaml",
]

ROWS_SCHEMA = {"type": "array", "items": {"type": "array", "items": {}}}


@pytest.fixture(autouse=True)
def _plain_system_prompt(monkeypatch):
    monkeypatch.setattr("realize_core.prompt.builder.build_system_prompt", lambda **kw: "system")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeGemini(BaseLLMProvider):
    """The only registered provider (no Claude anywhere); replies through ``script``."""

    tier_models: ClassVar[dict[str, str]] = {"fast": "gemini_flash", "standard": "gemini_pro", "deep": "gemini_pro"}

    def __init__(self):
        self.calls: list[dict] = []
        self.script = lambda prompt, n: "ok"

    @property
    def name(self):
        return "gemini"

    async def complete(self, system_prompt, messages, model=None, **kwargs):
        prompt = messages[-1]["content"]
        self.calls.append({"prompt": prompt, "model": model, **kwargs})
        return LLMResponse(text=self.script(prompt, len(self.calls)), model=model or "", provider="gemini")

    def list_models(self):
        return [
            ModelInfo(model_id="gemini/gemini-2.5-flash"),
            ModelInfo(model_id="gemini/gemini-2.5-pro"),
        ]


@pytest.fixture
def gemini(monkeypatch):
    for tier in ("FAST", "STANDARD", "DEEP"):
        monkeypatch.delenv(f"LLM_MODEL_{tier}", raising=False)
    provider = _FakeGemini()
    reg = ProviderRegistry()
    reg.register(provider, {"gemini_flash": "gemini/gemini-2.5-flash", "gemini_pro": "gemini/gemini-2.5-pro"})
    reg.set_fallback_chain(["gemini"])
    with (
        patch("realize_core.llm.registry.get_registry", return_value=reg),
        patch("realize_core.llm.router._check_rate_limit", return_value=True),
        patch("realize_core.llm.router._check_cost_limit", return_value=True),
    ):
        yield provider


class FakeSheets(BaseTool):
    """sheets_read returns the milestone schedule; sheets_append records rows."""

    name = "fake_sheets"
    description = "sheets"
    category = ToolCategory.PRODUCTIVITY

    def __init__(self):
        self.appended: list[dict] = []

    def get_schemas(self):
        read = {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "range": {"type": "string"}}}
        append = {
            "type": "object",
            "properties": {"spreadsheet_id": {"type": "string"}, "range": {"type": "string"}, "values": ROWS_SCHEMA},
        }
        return [ToolSchema("sheets_read", "read", read), ToolSchema("sheets_append", "append", append)]

    def is_available(self):
        return True

    async def execute(self, action, params):
        if action == "sheets_read":
            return ToolResult.ok(output="Milestone 4 | Frame works | 30% | 360000\nContractor | Demo Builders Ltd")
        self.appended.append(params)
        return ToolResult.ok(output="appended 1 row")


@pytest.fixture
def sheets(monkeypatch):
    import realize_core.tools.tool_registry as tr

    monkeypatch.setattr(tr, "_registry", None)
    tool = FakeSheets()
    tr.get_tool_registry().register(tool)
    return tool


def _skill(path: Path) -> dict:
    skill = yaml.safe_load(path.read_text(encoding="utf-8"))
    skill["variables"] = {**skill.get("variables", {}), "milestones_sheet_id": "m1", "payments_sheet_id": "p1"}
    return {**skill, "_version": 2}


TODAY = date.today().isoformat()
TEMPLATE_ROW = json.dumps([[TODAY, "contractor", "milestone", 0, 0, "verdict", "missing evidence"]])
REAL_ROW = json.dumps([[TODAY, "Demo Builders Ltd", "Milestone 4", 360000, 342000, "PARTIAL", "supervisor sign-off"]])


def _payment_script(json_replies: list[str]):
    replies = iter(json_replies)

    def script(prompt, n):
        if "Return ONLY a JSON array with one row" in prompt:
            return next(replies)
        if "Compare it with the milestone schedule" in prompt:
            return "Verdict: PARTIAL\nMilestone 4 — Frame works, 30%\nContractor: Demo Builders Ltd"
        return "Short report for the developer"

    return script


# ---------------------------------------------------------------------------
# Unresolved placeholders
# ---------------------------------------------------------------------------


def _ctx():
    from realize_core.skills.executor import SkillContext

    ctx = SkillContext("go", "acme", "u1")
    ctx.variables["sheet_id"] = "s-1"
    ctx.known_steps = {"check", "rows"}
    ctx.current_step = "rows"
    return ctx


def test_inject_fills_known_values():
    ctx = _ctx()
    ctx.step_results["check"] = "PARTIAL"
    assert ctx.inject("{check} {sheet_id} {user_message} {today}") == f"PARTIAL s-1 go {TODAY}"


def test_inject_refuses_a_step_reference_without_a_result():
    from realize_core.skills.executor import StepFailedError

    with pytest.raises(StepFailedError, match=r"unresolved placeholder \{check\} in step rows"):
        _ctx().inject("Use {check}")


def test_inject_leaves_unknown_names_and_json_braces_alone():
    text = 'Return {"a": 1} and {not_a_step} and {x}'
    assert _ctx().inject(text) == text


# ---------------------------------------------------------------------------
# Tier / model precedence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("step", "skill", "expected"),
    [
        (
            {"model": "gemini/gemini-2.5-pro", "tier": "fast"},
            {"model": "x", "tier": "deep"},
            {"model": "gemini/gemini-2.5-pro"},
        ),
        ({"tier": "deep"}, {"model": "anthropic/claude-opus-5-5"}, {"tier": "deep"}),
        ({}, {"model": "gpt4o", "tier": "fast", "task_type": "content"}, {"model": "gpt4o"}),
        ({}, {"tier": "standard", "task_type": "complex"}, {"tier": "standard"}),
        ({}, {"task_type": "complex"}, {"task_type": "complex"}),
    ],
    ids=["step-model", "step-tier", "skill-model", "skill-tier", "skill-task-type"],
)
async def test_routing_precedence_reaches_route_completion(monkeypatch, step, skill, expected):
    from realize_core.llm import router
    from realize_core.skills import executor

    seen: list[dict] = []

    async def fake_route(system_prompt, messages, **kwargs):
        seen.append(kwargs)
        return LLMResponse(text="done")

    monkeypatch.setattr(router, "route_completion", fake_route)
    skill_def = {"name": "demo", **skill, "steps": [{"id": "a", "type": "agent", "prompt": "Do it", **step}]}

    assert await executor._execute_v2_steps(skill_def, "write a post", "acme", "u1", None, {}, {}, "api") == "done"
    routing = {k: v for k, v in seen[0].items() if k in ("model", "tier", "task_type") and v is not None}
    assert routing == expected


async def test_unpinned_steps_classify_the_user_message_only(monkeypatch):
    from realize_core.llm import router
    from realize_core.skills import executor

    classified: list[str] = []
    seen: list[dict] = []

    def fake_classify(message, system_key=None):
        classified.append(message)
        return "financial"

    async def fake_route(system_prompt, messages, **kwargs):
        seen.append(kwargs)
        return LLMResponse(text="done")

    monkeypatch.setattr(router, "classify_task", fake_classify)
    monkeypatch.setattr(router, "route_completion", fake_route)
    skill = {"name": "demo", "steps": [{"id": "a", "type": "agent", "prompt": "Write the code for {user_message}"}]}

    await executor._execute_v2_steps(skill, "check the payment", "acme", "u1", None, {}, {}, "api")

    assert classified == ["check the payment"]
    assert seen[0]["task_type"] == "financial"


async def test_skill_md_and_v1_honour_the_skill_tier(monkeypatch):
    from realize_core.llm import router
    from realize_core.skills import executor

    seen: list[dict] = []

    async def fake_route(system_prompt, messages, **kwargs):
        seen.append(kwargs)
        return LLMResponse(text="done")

    monkeypatch.setattr(router, "route_completion", fake_route)
    await executor.execute_skill(
        {"name": "md", "_format": "skill_md", "tier": "deep", "_instructions": "x"}, "hi", "acme", "u1"
    )
    await executor.execute_skill(
        {"name": "v1", "_version": 1, "pipeline": ["writer"], "model": "gpt4o"}, "hi", "acme", "u1"
    )

    assert seen[0]["tier"] == "deep"
    assert seen[1]["model"] == "gpt4o"


async def test_delegate_step_keeps_its_tier(monkeypatch):
    from realize_core.llm import router
    from realize_core.skills import executor

    seen: list[dict] = []

    async def fake_route(system_prompt, messages, **kwargs):
        seen.append(kwargs)
        return LLMResponse(text="done")

    monkeypatch.setattr(router, "route_completion", fake_route)
    skill = {"name": "demo", "steps": [{"id": "d", "type": "delegate", "agent": "writer", "tier": "deep"}]}

    await executor._execute_v2_steps(skill, "go", "acme", "u1", None, {}, {}, "api")

    assert seen[0]["tier"] == "deep"


async def test_unknown_tier_stops_the_workflow(monkeypatch):
    from realize_core.skills import executor

    skill = {"name": "demo", "steps": [{"id": "a", "type": "agent", "prompt": "x", "tier": "turbo"}]}
    out = await executor._execute_v2_steps(skill, "go", "acme", "u1", None, {}, {}, "api")
    assert "stopped at step 'a'" in out
    assert "turbo" in out


# ---------------------------------------------------------------------------
# Placeholder-echo guard
# ---------------------------------------------------------------------------

PROMPT = 'Return ONLY a JSON array with one row:\n[["2026-10-14", "contractor", "milestone", 0, 0, "verdict", "missing evidence"]]'
CONTEXT = "### check\nVerdict: PARTIAL\nContractor: Demo Builders Ltd"


@pytest.mark.parametrize(
    "value",
    [
        [["2026-10-14", "contractor", "milestone", 0, 0, "verdict", "missing evidence"]],
        [["{contractor}", "Demo Builders Ltd"]],
        {"name": "{contractor}"},
    ],
    ids=["template-labels", "bare-placeholder", "placeholder-in-object"],
)
def test_echo_guard_rejects(value):
    from realize_core.skills.executor import _reject_placeholder_echo

    with pytest.raises(ValueError):
        _reject_placeholder_echo(value, PROMPT, CONTEXT)


@pytest.mark.parametrize(
    ("value", "context"),
    [
        ([["2026-10-14", "Demo Builders Ltd", "Milestone 4", 1, 1, "PARTIAL", "photos"]], CONTEXT),
        # Every leaf is a label, but the data really says so: accepted.
        ([["2026-10-14", "contractor", "milestone", 0, 0, "verdict", "missing evidence"]], "Name: contractor"),
        ([[1, 2]], CONTEXT),
        ([["{not json braces", "a"]], CONTEXT),
    ],
    ids=["real-values", "label-in-context", "numbers-only", "brace-text"],
)
def test_echo_guard_accepts(value, context):
    from realize_core.skills.executor import _reject_placeholder_echo

    _reject_placeholder_echo(value, PROMPT, context)


# ---------------------------------------------------------------------------
# The payment row on a non-Claude provider
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", PAYMENT_YAMLS, ids=["pack", "template"])
async def test_template_row_is_retried_then_real_row_reaches_the_sheet(gemini, sheets, path):
    from realize_core.skills.executor import _execute_v2_steps

    gemini.script = _payment_script([TEMPLATE_ROW, REAL_ROW])

    out = await _execute_v2_steps(
        _skill(path), "Demo Builders asks 360000 for milestone 4", "acme", "u1", None, {}, {}, "api"
    )

    assert out == "Short report for the developer"
    assert [p["values"] for p in sheets.appended] == [json.loads(REAL_ROW)]
    json_calls = [c for c in gemini.calls if "Return ONLY a JSON array with one row" in c["prompt"]]
    assert len(json_calls) == 2
    assert "rejected" in json_calls[1]["prompt"]
    assert "rejected" not in json_calls[0]["prompt"]
    # tier: standard on the JSON step → the provider's standard model
    assert {c["model"] for c in json_calls} == {"gemini/gemini-2.5-pro"}
    # The schema is the sheet's `values` schema, wrapped in an object every provider accepts.
    schema = json_calls[0]["response_schema"]
    assert schema["type"] == "object"
    assert schema["properties"]["value"]["type"] == "array"
    assert schema["properties"]["value"]["items"]["type"] == "array"
    assert schema["properties"]["value"]["items"]["items"] != {}  # cells are scalars, not objects
    # Steps that feed no tool get no schema.
    assert all("response_schema" not in c for c in gemini.calls if c not in json_calls)


async def test_object_wrapped_reply_is_unwrapped(gemini, sheets):
    from realize_core.skills.executor import _execute_v2_steps

    gemini.script = _payment_script([json.dumps({"value": json.loads(REAL_ROW)})])

    await _execute_v2_steps(_skill(PAYMENT_YAMLS[0]), "pay", "acme", "u1", None, {}, {}, "api")

    assert [p["values"] for p in sheets.appended] == [json.loads(REAL_ROW)]


async def test_template_row_twice_stops_before_the_sheet(gemini, sheets):
    from realize_core.skills.executor import _execute_v2_steps

    gemini.script = _payment_script([TEMPLATE_ROW, TEMPLATE_ROW])

    out = await _execute_v2_steps(_skill(PAYMENT_YAMLS[0]), "pay", "acme", "u1", None, {}, {}, "api")

    assert "stopped at step 'payment_row'" in out
    assert sheets.appended == []
    assert not any("Write a short message" in c["prompt"] for c in gemini.calls)


async def test_direct_executor_function_raises_after_two_bad_answers(gemini, sheets):
    from realize_core.skills.executor import SkillContext, StepFailedError, _execute_agent_step

    gemini.script = lambda prompt, n: "not json at all"
    ctx = SkillContext("pay", "acme", "u1")

    with pytest.raises(StepFailedError, match="JSON"):
        await _execute_agent_step(
            {"id": "rows", "prompt": "Return rows"}, ctx, None, {}, {}, "api", json_schema=ROWS_SCHEMA
        )
    assert len(gemini.calls) == 2


@pytest.mark.parametrize("path", PAYMENT_YAMLS + TENDER_YAMLS, ids=["pay-pack", "pay-tpl", "tender-pack", "tender-tpl"])
def test_json_steps_in_the_yamls_are_pinned_to_standard(path):
    skill = yaml.safe_load(path.read_text(encoding="utf-8"))
    consumers = {
        later["params"]["values"].strip("{}") for later in skill["steps"] if later.get("json_params") == ["values"]
    }
    pinned = {s["id"]: s.get("tier") for s in skill["steps"] if s["id"] in consumers}
    assert pinned
    assert set(pinned.values()) == {"standard"}
