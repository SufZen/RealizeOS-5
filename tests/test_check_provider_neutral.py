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
        ('key = os.getenv("ANTHROPIC_API_KEY", "")', "provider-key-env"),
        ('key = os.environ.get("GOOGLE_AI_API_KEY")', "provider-key-env"),
        ('key = os.environ["OPENAI_API_KEY"]', "provider-key-env"),
        ('key = getenv("GOOGLE_API_KEY")', "provider-key-env"),
        ('if "OPENAI_API_KEY" in os.environ:', "provider-key-env"),
        ('if "ANTHROPIC_API_KEY" not in environ:', "provider-key-env"),
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
        'key = os.getenv("BRAVE_API_KEY")',
        'key = os.getenv("REALIZE_API_KEY")',
        'key = os.getenv("ANTHROPIC_API_KEY")  # provider-neutral: ok format check of an optional key',
        'KEY_NAME = "OPENAI_API_KEY"',
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


def test_default_roots_include_cli_scripts_and_plugins():
    assert set(gate.DEFAULT_ROOTS) >= {"realize_core", "realize_api", "cli.py", "scripts", "plugins"}
    assert not gate.is_allowed("cli.py")


def test_gate_script_itself_is_not_scanned(tmp_path):
    script = tmp_path / "scripts" / "check_provider_neutral.py"
    script.parent.mkdir()
    script.write_text('x = os.getenv("OPENAI_API_KEY")\n', encoding="utf-8")
    other = tmp_path / "scripts" / "tool.py"
    other.write_text('x = os.getenv("OPENAI_API_KEY")\n', encoding="utf-8")

    offences = gate.scan([tmp_path], root=tmp_path)

    assert offences == ['scripts/tool.py:1: [provider-key-env] x = os.getenv("OPENAI_API_KEY")']


def test_direct_client_rules_apply_to_cli_and_scripts(tmp_path):
    cli = tmp_path / "cli.py"
    cli.write_text("from realize_core.llm.claude_client import _get_client\n", encoding="utf-8")
    script = tmp_path / "scripts" / "smoke.py"
    script.parent.mkdir()
    script.write_text("text = call_gemini(prompt)\n", encoding="utf-8")

    offences = gate.scan([tmp_path], root=tmp_path)

    assert sorted(o.split(":")[0] for o in offences) == ["cli.py", "scripts/smoke.py"]


# --- statements split over several lines (5.31 follow-up #4) ---------------------------

_WRAPPED_KEY_READ = 'def f():\n    key = os.environ.get(\n        "OPENAI_API_KEY", ""\n    )\n    return key\n'


def test_a_wrapped_key_read_is_flagged(tmp_path):
    (tmp_path / "feature.py").write_text(_WRAPPED_KEY_READ, encoding="utf-8")

    offences = gate.scan([tmp_path], root=tmp_path)

    assert len(offences) == 1
    assert offences[0].startswith("feature.py:2: [provider-key-env]")


@pytest.mark.parametrize(
    "source",
    [
        'x = os.getenv(\n    "ANTHROPIC_API_KEY"\n)\n',
        'x = os.environ[\n    "GOOGLE_AI_API_KEY"\n]\n',
        'if (\n    "OPENAI_API_KEY"\n    in os.environ\n):\n    pass\n',
        'if provider.name == (\n    "claude"\n):\n    pass\n',
        'ok = model.startswith(\n    "gemini/"\n)\n',
    ],
    ids=["getenv", "environ-subscript", "key-in-environ", "compare", "prefix"],
)
def test_other_wrapped_forms_are_flagged(tmp_path, source):
    (tmp_path / "feature.py").write_text(source, encoding="utf-8")

    assert len(gate.scan([tmp_path], root=tmp_path)) == 1


@pytest.mark.parametrize("pragma_line", [1, 2, 3], ids=["first-line", "middle-line", "last-line"])
def test_a_pragma_on_any_line_of_the_statement_applies(tmp_path, pragma_line):
    lines = ["key = os.environ.get(", '    "OPENAI_API_KEY", ""', ")"]
    lines[pragma_line - 1] += "  # provider-neutral: ok the DALL-E stub names its key"
    (tmp_path / "feature.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert gate.scan([tmp_path], root=tmp_path) == []


def test_a_pragma_on_the_next_statement_does_not_apply(tmp_path):
    source = 'key = os.environ.get(\n    "OPENAI_API_KEY", ""\n)\nx = 1  # provider-neutral: ok unrelated\n'
    (tmp_path / "feature.py").write_text(source, encoding="utf-8")

    offences = gate.scan([tmp_path], root=tmp_path)

    assert [o.split(":")[1] for o in offences] == ["1"]


def test_a_reasonless_pragma_on_a_wrapped_statement_is_reported(tmp_path):
    source = 'key = os.environ.get(\n    "OPENAI_API_KEY", ""\n)  # provider-neutral: ok\n'
    (tmp_path / "feature.py").write_text(source, encoding="utf-8")

    offences = gate.scan([tmp_path], root=tmp_path)

    assert len(offences) == 1
    assert "[provider-key-env]" in offences[0]


def test_a_file_that_does_not_tokenize_is_still_scanned_line_by_line(tmp_path):
    (tmp_path / "feature.py").write_text('x = (\nkey = os.getenv("OPENAI_API_KEY")\n', encoding="utf-8")

    offences = gate.scan([tmp_path], root=tmp_path)

    assert any("feature.py:2: [provider-key-env]" in o for o in offences)
