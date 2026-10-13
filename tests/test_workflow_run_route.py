"""POST /api/workflows/{name}/run: the REST twin of MCP run_workflow, per venture (5.30)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner


@pytest.fixture
def world(monkeypatch):
    from realize_core.skills import detector, executor

    monkeypatch.setattr(
        detector,
        "_loaded_skills",
        {
            "alpha": [{"name": "report", "steps": [], "variables": {"sheet": "ALPHA"}}],
            "beta": [{"name": "report", "steps": [], "variables": {"sheet": "BETA"}}],
        },
    )
    runs: list[dict] = []

    async def fake_execute_skill(**kwargs):
        runs.append({"sheet": kwargs["skill"]["variables"]["sheet"], "system_key": kwargs["system_key"]})
        return "done"

    monkeypatch.setattr(executor, "execute_skill", fake_execute_skill)
    return runs


def _client(user_id: str | None = None, role: str = "owner", scopes: list[str] | None = None) -> TestClient:
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = {"alpha": {"name": "Alpha", "agents": {}}, "beta": {"name": "Beta", "agents": {}}}
    app.state.config = {"features": {}}
    if user_id is not None:

        @app.middleware("http")
        async def as_principal(request, call_next):
            request.state.user_id = user_id
            request.state.role = role
            request.state.scopes = scopes or []
            return await call_next(request)

    return TestClient(app)


def test_runs_the_named_ventures_own_copy(world):
    r = _client().post("/api/workflows/report/run", json={"system_key": "beta", "input_text": "Q3"})
    assert r.status_code == 200, r.text
    assert r.json()["output"] == "done"
    assert world == [{"sheet": "BETA", "system_key": "beta"}]


def test_venture_is_required_and_fields_are_strict(world):
    client = _client()
    assert client.post("/api/workflows/report/run", json={"input_text": "Q3"}).status_code == 422
    assert (
        client.post("/api/workflows/report/run", json={"system_key": "beta", "input_text": "Q3", "x": 1}).status_code
        == 422
    )
    assert client.post("/api/workflows/nope/run", json={"system_key": "beta", "input_text": "Q3"}).status_code == 404
    assert world == []


def test_viewers_cant_run(world, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "users.yaml").write_text(
        "users:\n  - email: vic@x.io\n    role: viewer\n    password_hash: '$2b$12$v'\n", encoding="utf-8"
    )
    r = _client("vic@x.io", role="viewer").post(
        "/api/workflows/report/run", json={"system_key": "beta", "input_text": "Q3"}
    )
    assert r.status_code == 403
    assert world == []


def test_cli_run_uses_the_route(monkeypatch):
    from realize_core.cli_app import app
    from realize_core.cli_app.commands import workflow

    calls = []
    monkeypatch.setattr(
        workflow, "api_post", lambda path, **kw: calls.append((path, kw["json_body"])) or {"output": "ok"}
    )
    result = CliRunner().invoke(app, ["workflow", "run", "report", "--venture", "beta", "--message", "Q3 numbers"])
    assert result.exit_code == 0, result.output
    assert calls == [("/api/workflows/report/run", {"system_key": "beta", "input_text": "Q3 numbers"})]
    missing = CliRunner().invoke(app, ["workflow", "run", "report"])
    assert missing.exit_code != 0  # --venture is required
