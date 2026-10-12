"""QA D-6 / Codex audit: the running release reports its real version."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_ships_the_version_file():
    assert "COPY VERSION ." in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_mcp_server_reports_the_release_version():
    from types import SimpleNamespace

    from realize_core import __version__
    from realize_core.mcp_server.server import build_mcp_server

    server = build_mcp_server(app_state=SimpleNamespace(), mcp_config=SimpleNamespace())
    assert server.version == __version__
    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
