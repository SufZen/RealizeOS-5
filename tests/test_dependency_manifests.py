"""Guard against drift between the two runtime dependency manifests.

Docker and the installers install from ``requirements.txt`` while
``pip install realize-os`` uses ``pyproject.toml``. The two drifted apart
once (Gemini SDK, mcp, litellm missing from pyproject), so they are
checked here line by line.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _normalize(spec: str) -> str:
    """Lower-case and strip whitespace, comments and extras from a requirement."""
    spec = spec.split("#", 1)[0].strip().lower().replace(" ", "")
    return re.sub(r"\[[^\]]*\]", "", spec)


def _requirements_txt() -> set[str]:
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return {_normalize(line) for line in lines if _normalize(line)}


def _pyproject() -> set[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {_normalize(dep) for dep in data["project"]["dependencies"]}


def test_runtime_manifests_match():
    req, proj = _requirements_txt(), _pyproject()
    assert req == proj, f"only in requirements.txt: {sorted(req - proj)}; only in pyproject.toml: {sorted(proj - req)}"


def test_mcp_capped_below_v2():
    """mcp 2.x removed the decorator server API used by realize_core.mcp_server."""
    assert any(dep.startswith("mcp") and "<2" in dep for dep in _pyproject())


def test_version_single_source():
    """``__version__``, ``VERSION`` and pyproject must agree (health + CLI report it)."""
    from realize_core import __version__

    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == expected == data["project"]["version"]
