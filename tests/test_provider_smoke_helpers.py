"""Pure helpers of scripts/provider_smoke.py. The live smoke itself never runs in tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("provider_smoke", ROOT / "scripts" / "provider_smoke.py")
smoke = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = smoke  # dataclasses look their module up
_spec.loader.exec_module(smoke)


@pytest.mark.parametrize(
    ("path", "protected"),
    [
        ("D:/realization-demo", True),
        ("D:/realization-demo/RealizeOS-5", True),
        ("d:\\Realization-Demo\\RealizeOS-5\\data", True),
        ("D:/realization-demo/../elsewhere", False),
        ("D:/realization-demo-copy", False),
        ("D:/SufZen Gits/RealizeOS-5", False),
    ],
)
def test_the_live_demo_folder_is_refused(path, protected):
    assert smoke.is_protected(path) is protected


def test_a_real_payment_row_passes():
    row = [["2026-10-14", "קבלן הדגמה", "4", 360000, 342000, "PARTIAL", "אישור מפקח חתום"]]
    assert smoke.row_problems(row) == []


@pytest.mark.parametrize(
    "rows",
    [
        [["2026-10-14", "contractor", "milestone", 0, 0, "verdict", "missing evidence"]],
        [["{today}", "Demo Builders", "4", 1, 1, "PARTIAL", "ok"]],
        [["2026-10-14", "Demo Builders", "{check}", 1, 1, "PARTIAL", "ok"]],
        "not rows",
        [],
    ],
)
def test_template_rows_and_placeholders_fail(rows):
    assert smoke.row_problems(rows)


class _Provider:
    def __init__(self, name, model):
        self.name = name
        self._model = model

    def default_model_id(self):
        return self._model

    async def complete(self, system_prompt, messages, model=None, **kwargs):
        from realize_core.llm.base_provider import LLMResponse

        return LLMResponse(text="ok", provider=self.name, model=model or "")

    async def complete_with_tools(self, system_prompt, messages, tools, model=None, **kwargs):
        from realize_core.llm.base_provider import LLMResponse

        return LLMResponse(text="ok", provider=self.name, model="")


class _Registry:
    def __init__(self, *providers):
        self._p = {p.name: p for p in providers}

    def list_all(self):
        return dict.fromkeys(self._p, True)

    def get_provider_by_name(self, name):
        return self._p.get(name)


async def test_call_recorder_names_provider_and_model_per_check():
    gemini, ollama = _Provider("gemini", "gemini/gemini-2.5-flash"), _Provider("ollama", "ollama_chat/qwen3:8b")
    recorder = smoke.CallRecorder()
    recorder.install(_Registry(gemini, ollama))

    mark = recorder.mark()
    await gemini.complete("s", [], model="gemini/gemini-2.5-pro")
    await gemini.complete("s", [], model="gemini/gemini-2.5-pro")
    await ollama.complete_with_tools("s", [], [])  # no model in the reply: the provider default
    assert recorder.since(mark) == "gemini:gemini/gemini-2.5-pro, ollama:ollama_chat/qwen3:8b"
    assert recorder.since(recorder.mark()) == "-"


def test_table_prints_the_route_per_row(capsys):
    results = [
        smoke.Result("Budget answer cites [S1]", "PASS", "answer", route="gemini:gemini/gemini-2.5-pro"),
        smoke.Result("KB finds the budget", "PASS", "budget.md"),
    ]
    smoke._print_table("gemini", results)
    out = capsys.readouterr().out
    assert "gemini:gemini/gemini-2.5-pro" in out
    lines = [line for line in out.splitlines() if "KB finds the budget" in line]
    assert len(lines) == 1
    assert " - " in lines[0]
