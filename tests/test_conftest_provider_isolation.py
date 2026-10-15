"""No fixture scope ever sees the developer's real provider keys (5.31 follow-up #6).

tests/conftest.py clears provider/LLM settings at import, before any fixture runs.
Per-test cleaning used to be the only guard, and the teardown hook restored a
snapshot that still held the shell's keys, so class- and module-scoped fixtures
(set up before the function-scoped clean) saw real keys.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_PROBED = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PRIMARY", "LITELLM_MODEL")


@pytest.fixture(scope="module")
def module_scoped_env():
    return {k: os.environ.get(k) for k in _PROBED}


@pytest.fixture(scope="class")
def class_scoped_env():
    return {k: os.environ.get(k) for k in _PROBED}


class TestScopes:
    def test_module_and_class_fixtures_see_no_provider_settings(self, module_scoped_env, class_scoped_env):
        assert module_scoped_env == dict.fromkeys(_PROBED)
        assert class_scoped_env == dict.fromkeys(_PROBED)


def test_keys_set_in_the_outer_environment_never_reach_a_fixture():
    """Run the scope test in a child pytest whose parent shell has provider keys set."""
    env = {k: v for k, v in os.environ.items() if k != "REALIZE_API_KEY"}
    env.update(
        {
            "OPENAI_API_KEY": "sk-shell-key-must-not-leak",
            "ANTHROPIC_API_KEY": "sk-ant-shell-key-must-not-leak",
            "LLM_PRIMARY": "openai",
            "LITELLM_MODEL": "openai/gpt-4o",
        }
    )
    node = f"{Path(__file__).relative_to(ROOT).as_posix()}::TestScopes"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "-p", "no:cacheprovider", "-p", "no:randomly"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    assert "1 passed" in result.stdout
