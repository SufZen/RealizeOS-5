"""
Codex audit F14: a provider key saved in Setup must apply without a restart.

Setup wrote .env and os.environ, but the Anthropic/Gemini keys were captured
in module constants at import and the API clients were cached forever. A
server started without a key reported "configured" yet Claude stayed
unavailable; rotating a key kept using the old one.
"""

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def setup_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REALIZE_ROOT", str(tmp_path))
    config_path = tmp_path / "realize-os.yaml"
    config_path.write_text(yaml.safe_dump({"systems": [], "features": {}}), encoding="utf-8")
    monkeypatch.setenv("REALIZE_CONFIG", str(config_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Some test modules leave a stub claude_client in sys.modules; load the real one.
    import importlib
    import sys

    monkeypatch.delitem(sys.modules, "realize_core.llm.claude_client", raising=False)
    cc = importlib.import_module("realize_core.llm.claude_client")

    from realize_api.routes import setup

    app = FastAPI()
    app.include_router(setup.router, prefix="/api")
    app.state.kb_path = tmp_path
    return TestClient(app), cc


def _save_key(client, value):
    res = client.put("/api/setup/connection", json={"id": "anthropic", "value": value})
    assert res.status_code == 200, res.text


def test_key_saved_in_setup_makes_claude_available(setup_app):
    from realize_core.llm.providers.claude_provider import ClaudeProvider

    client, _ = setup_app
    assert not ClaudeProvider().is_available()

    _save_key(client, "sk-ant-synthetic-1")

    assert ClaudeProvider().is_available()


def test_rotated_key_rebuilds_the_client(setup_app):
    client, cc = setup_app

    _save_key(client, "sk-ant-synthetic-1")
    first = cc._get_client()
    assert first.api_key == "sk-ant-synthetic-1"
    assert cc._get_client() is first  # unchanged key: same client

    _save_key(client, "sk-ant-synthetic-2")
    assert cc._get_client().api_key == "sk-ant-synthetic-2"


def test_removed_key_stops_the_client(setup_app):
    client, cc = setup_app
    _save_key(client, "sk-ant-synthetic-1")
    cc._get_client()

    _save_key(client, "")

    with pytest.raises(RuntimeError, match="not configured"):
        cc._get_client()
