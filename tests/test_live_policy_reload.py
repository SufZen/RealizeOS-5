"""
Codex audit F05: a policy change in Settings must reach the live tool gate.

Startup gave ToolGate one config object; the trust/settings handlers replaced
app.state.config but never the gate's copy. Lowering trust 5 → 1 showed "1"
in Settings while gmail_send was still allowed, and toggling enforce_gates
changed the file without installing or removing the gate.
"""

from types import SimpleNamespace

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """A config file with enforcement on at trust level 5, a fresh registry, and an app."""
    import realize_core.tools.tool_registry as tr
    from realize_core.config_runtime import reload_app_config

    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "realize-os.yaml"
    config_path.write_text(
        yaml.safe_dump({"systems": [], "features": {"enforce_gates": True}, "trust": {"level": 5}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("REALIZE_CONFIG", str(config_path))
    monkeypatch.setattr(tr, "_registry", None)

    from realize_api.routes import settings, settings_trust

    app = FastAPI()
    app.include_router(settings_trust.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.state.kb_path = tmp_path
    app.state.approval_store = SimpleNamespace()  # never written: no action is held here
    reload_app_config(app.state)
    return app, tr.get_tool_registry()


def _decide(registry, action):
    return registry._gate.decide(action, {}, is_destructive=True).outcome.value


def test_trust_change_applies_to_the_live_gate(setup):
    app, registry = setup
    assert _decide(registry, "gmail_send") == "allow"

    res = TestClient(app).put("/api/trust/level", json={"level": 1})

    assert res.status_code == 200
    assert app.state.config["trust"]["level"] == 1
    assert registry._gate is app.state.tool_gate
    assert _decide(registry, "gmail_send") != "allow"


def test_turning_enforcement_off_and_on_installs_and_removes_the_gate(setup):
    app, registry = setup
    client = TestClient(app)

    assert client.put("/api/settings/features", json={"features": {"enforce_gates": False}}).status_code == 200
    assert not registry.has_gate
    assert app.state.tool_gate is None

    assert client.put("/api/settings/features", json={"features": {"enforce_gates": True}}).status_code == 200
    assert registry.has_gate
    assert registry._gate is app.state.tool_gate


def test_gate_that_cannot_be_built_fails_closed(setup, monkeypatch):
    """Security review: a failed gate build must not leave enforcement silently off."""
    app, registry = setup
    import realize_core.governance.tool_gate as tg
    from realize_core.config_runtime import FailClosedGate, sync_tool_gate

    app.state.tool_gate = None
    registry.set_gate(None)

    real_gate = tg.ToolGate

    def broken(*args, **kwargs):
        raise RuntimeError("policy file unreadable")

    monkeypatch.setattr(tg, "ToolGate", broken)
    sync_tool_gate(app.state, {"features": {"enforce_gates": True}})

    assert isinstance(registry._gate, FailClosedGate)
    assert _decide(registry, "gmail_send") == "block"
    assert registry._gate.decide("sheets_read", {}, is_destructive=False).outcome.value == "allow"

    # A later successful sync replaces the stand-in with the real gate.
    monkeypatch.setattr(tg, "ToolGate", real_gate)
    sync_tool_gate(app.state, {"features": {"enforce_gates": True}, "trust": {"level": 5}})
    assert not isinstance(registry._gate, FailClosedGate)
