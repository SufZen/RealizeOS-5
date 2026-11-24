"""scripts/compare_models.py with a fake router: no real LLM call."""

import importlib.util
from pathlib import Path

from realize_core.llm.base_provider import LLMResponse

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "compare_models.py"


def _load():
    spec = importlib.util.spec_from_file_location("compare_models", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_writes_side_by_side_table(tmp_path, monkeypatch):
    calls = []

    async def fake_route(system_prompt, messages, *, model=None, max_retries=3, **kw):
        calls.append((model, max_retries))
        if model == "b/model":
            return LLMResponse(text="", error="boom")
        return LLMResponse(text=f"answer | from {model}", cost_usd=0.01, model=model)

    monkeypatch.setattr("realize_core.llm.router.route_completion", fake_route)
    questions = tmp_path / "q.txt"
    questions.write_text("# comment\nWhat is X?\n\nWhat is Y?\n", encoding="utf-8")
    out = tmp_path / "out.md"

    status = _load().main([str(questions), "--before", "a/model", "--after", "b/model", "--out", str(out)])

    report = out.read_text(encoding="utf-8")
    assert status == 1  # one model failed
    assert calls == [("a/model", 0), ("b/model", 0)] * 2
    assert "answer \\| from a/model" in report
    assert "ERROR: boom" in report
    assert "| a/model | 0.0200 |" in report


def test_empty_file_is_a_setup_error(tmp_path):
    questions = tmp_path / "q.txt"
    questions.write_text("# only comments\n", encoding="utf-8")
    assert _load().main([str(questions), "--before", "a", "--after", "b"]) == 2


def test_refuses_to_overwrite_the_questions_file(tmp_path):
    questions = tmp_path / "q.txt"
    questions.write_text("What?\n", encoding="utf-8")
    assert _load().main([str(questions), "--before", "a", "--after", "b", "--out", str(questions)]) == 2
    assert questions.read_text(encoding="utf-8") == "What?\n"
