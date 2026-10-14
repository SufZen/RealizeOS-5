"""The provider-neutral CI gate (scripts/check_provider_neutral.py).

It passes on the tree and fails on code that names a provider outside the
adapters. It replaces the old client-import grep in test_llm_router_callers.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_provider_neutral", ROOT / "scripts" / "check_provider_neutral.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_the_tree_is_provider_neutral(capsys):
    assert gate.main([]) == 0, capsys.readouterr().out


@pytest.mark.parametrize(
    ("line", "rule"),
    [
        ("text = await call_claude(prompt)", "direct-client-call"),
        ("from realize_core.llm.call import call_gemini_flash", "direct-client-call"),
        ("from realize_core.llm.claude_client import _get_client", "direct-client-import"),
        ("import realize_core.llm.gemini_client as g", "direct-client-import"),
        ("p = registry.get_provider_by_name('claude')", "provider-by-name"),
        ('if provider.name == "claude":', "provider-compare"),
        ('ok = "Gemini" != name', "provider-compare"),
        ('if "gemini" in model:', "provider-in"),
        ('if name in ("openai", "ollama"):', "provider-in-list"),
        ('vision = model.startswith("claude-")', "provider-prefix"),
        ('if model.startswith(("anthropic/", "x")):', "provider-prefix"),
    ],
)
def test_offending_code_fails(tmp_path, capsys, line, rule):
    bad = tmp_path / "feature.py"
    bad.write_text(f"def f(model, name, provider, registry, prompt):\n    {line}\n", encoding="utf-8")

    assert gate.main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert f"feature.py:2: [{rule}]" in out


@pytest.mark.parametrize(
    "line",
    [
        'if name == "claude":  # provider-neutral: ok the alias table names providers',
        'for pkg in ["anthropic", "openai"]:',
        '# if name == "claude": an old comment',
        'models = {"claude": "claude", "gemini": "gemini"}',
        'if provider.supports(Capability.VISION) and name == "fast":',
    ],
)
def test_allowed_code_passes(tmp_path, line):
    (tmp_path / "feature.py").write_text(f"def f(name, provider):\n    {line}\n        pass\n", encoding="utf-8")

    assert gate.scan([tmp_path]) == []


def test_pragma_needs_a_reason(tmp_path):
    (tmp_path / "feature.py").write_text('if name == "claude":  # provider-neutral: ok\n', encoding="utf-8")

    offences = gate.scan([tmp_path])

    assert len(offences) == 1
    assert "[provider-compare]" in offences[0]


def test_allow_list_covers_the_adapters_only():
    assert gate.is_allowed("realize_core/llm/providers/_litellm_adapter.py")
    assert gate.is_allowed("realize_core/llm/claude_client.py")
    assert not gate.is_allowed("realize_core/llm/router.py")
    assert not gate.is_allowed("realize_api/routes/settings_llm.py")
    assert not gate.is_allowed("realize_core/media/__init__.py")


def test_allow_listed_file_is_skipped(tmp_path):
    adapter = tmp_path / "realize_core" / "llm" / "providers" / "x.py"
    adapter.parent.mkdir(parents=True)
    adapter.write_text('if name == "claude":\n    pass\n', encoding="utf-8")

    assert gate.scan([tmp_path], root=tmp_path) == []
