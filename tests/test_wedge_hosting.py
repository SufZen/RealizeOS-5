"""Hosting the self-serve pilot (STORY-46): tool allowlist, invites, retention job, CLI."""

from __future__ import annotations

import asyncio
import os
import stat
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from realize_core.mcp_server.config import McpConfig, mcp_config_from_env
from realize_core.mcp_server.registry import get_registry
from realize_core.wedge import pilot
from realize_core.wedge import store as wedge_store
from typer.testing import CliRunner

PILOT_TOOLS = ("tender_register_method", "tender_register_submit", "request_audit_call")
PILOT_CONFIG = {"features": {"wedge": True}, "mcp": {"tools": list(PILOT_TOOLS) + ["realize_health"]}}


def _cfg(**overrides) -> McpConfig:
    base = {
        "enabled": True,
        "expose_kb": True,
        "expose_ops": True,
        "allow_admin": False,
        "audit_full_payload": False,
        "bearer_token_override": "",
    }
    base.update(overrides)
    return McpConfig(**base)


# ---------------------------------------------------------------- mcp.tools allowlist


def test_tools_allowlist_from_yaml_and_env(monkeypatch):
    monkeypatch.delenv("MCP_TOOLS", raising=False)
    assert mcp_config_from_env({}).tools is None
    assert mcp_config_from_env({"mcp": {"tools": []}}).tools is None
    assert mcp_config_from_env({"mcp": {"tools": ["a", " b ", "a", ""]}}).tools == ("a", "b")
    assert mcp_config_from_env({"mcp": {"tools": "a,b"}}).tools == ("a", "b")
    monkeypatch.setenv("MCP_TOOLS", "x, y")
    assert mcp_config_from_env({"mcp": {"tools": ["a"]}}).tools == ("x", "y")
    monkeypatch.setenv("MCP_TOOLS", "")  # an empty env var (as in .env.example) means unset
    assert mcp_config_from_env({"mcp": {"tools": ["a"]}}).tools == ("a",)


@pytest.mark.parametrize("bad", [{"tender_register_submit": True}, 42, ["tender_register_submit", 7], True])
def test_malformed_allowlist_serves_nothing(monkeypatch, bad):
    monkeypatch.delenv("MCP_TOOLS", raising=False)
    cfg = mcp_config_from_env({"mcp": {"enabled": True, "tools": bad}})
    assert cfg.tools == ()
    assert get_registry().visible_tools(cfg) == []


def test_allowlist_limits_listing_and_calls():
    registry = get_registry()
    everything = {t.name for t in registry.visible_tools(_cfg())}
    assert set(PILOT_TOOLS) <= everything
    assert "realize_chat" in everything

    hosted = _cfg(tools=PILOT_TOOLS + ("realize_health",))
    assert {t.name for t in registry.visible_tools(hosted)} == set(PILOT_TOOLS) | {"realize_health"}
    assert not registry.is_visible(registry.get("realize_chat"), hosted)
    assert registry.is_visible(registry.get("tender_register_submit"), hosted)


def test_allowlist_cannot_widen_families():
    registry = get_registry()
    cfg = _cfg(allow_admin=False, tools=("create_venture",))
    assert not registry.is_visible(registry.get("create_venture"), cfg)
    assert registry.visible_tools(cfg) == []


def test_unknown_allowlist_names_are_reported():
    assert get_registry().unknown_names(_cfg(tools=("tender_register_submit", "tender_regster"))) == ["tender_regster"]


def test_disabled_tool_call_is_refused_by_dispatcher():
    from types import SimpleNamespace

    from realize_core.mcp_server.server import MCPErrorCode, _dispatch

    out = asyncio.run(
        _dispatch(get_registry(), _cfg(tools=PILOT_TOOLS), SimpleNamespace(), "realize_chat", {"message": "hi"})
    )
    assert MCPErrorCode.DISABLED in out[0].text


# ---------------------------------------------------------------- invites


@pytest.fixture
def users_file(tmp_path):
    path = tmp_path / "users.yaml"
    path.write_text(
        "# owner\nusers:\n  - email: owner@example.com\n    role: owner\n    password_hash: '$2b$12$abc'\n",
        encoding="utf-8",
    )
    return path


def test_invite_adds_a_sandboxed_viewer(users_file, monkeypatch):
    monkeypatch.setattr(pilot, "hash_password", lambda pw: f"hashed:{len(pw)}")
    result = pilot.invite(" Pilot@Example.com ", config=PILOT_CONFIG, users_file=users_file)

    assert result.written
    assert result.email == "pilot@example.com"
    assert result.venture == pilot.sandbox_venture("pilot@example.com")
    assert result.venture.startswith("pilot-")
    assert len(result.password) >= 20
    data = yaml.safe_load(users_file.read_text(encoding="utf-8"))
    added = data["users"][-1]
    assert added == {
        "email": "pilot@example.com",
        "role": "viewer",
        "ventures": [result.venture],
        "password_hash": f"hashed:{len(result.password)}",
    }
    assert result.password not in users_file.read_text(encoding="utf-8")
    assert data["users"][0]["email"] == "owner@example.com"
    assert result.backup
    assert "owner@example.com" in result.backup.read_text(encoding="utf-8")


def test_invited_user_loads_and_sees_only_the_sandbox(users_file, monkeypatch):
    from realize_core.security import users as users_mod

    monkeypatch.setattr(pilot, "hash_password", lambda pw: "$2b$12$" + "x" * 53)
    result = pilot.invite("pilot@example.com", config=PILOT_CONFIG, users_file=users_file)
    loaded = users_mod._load_yaml_users(users_file)
    user = next(u for u in loaded if u.email == "pilot@example.com")
    assert user.role == "viewer"
    assert user.ventures == (result.venture,)


@pytest.mark.parametrize("email", ["", "not-an-email", "a@b", "with space@x.io"])
def test_invite_rejects_bad_emails(users_file, email):
    with pytest.raises(pilot.PilotInviteError):
        pilot.invite(email, config=PILOT_CONFIG, users_file=users_file)


@pytest.mark.parametrize(
    ("config", "reason"),
    [
        ({"mcp": {"tools": ["tender_register_submit"]}}, "features.wedge is off"),
        ({"features": {"wedge": True}}, "mcp.tools is not set"),
        ({"features": {"wedge": True}, "mcp": {"tools": ["tender_register_submit", "kb_search"]}}, "kb_search"),
        ({"features": {"wedge": True}, "mcp": {"tools": {"bad": 1}}}, None),
    ],
)
def test_invite_only_on_a_pilot_host(users_file, monkeypatch, config, reason):
    monkeypatch.delenv("MCP_TOOLS", raising=False)
    before = users_file.read_text(encoding="utf-8")
    problems = pilot.pilot_profile_problems(config)
    if reason:
        assert any(reason in p for p in problems)
        with pytest.raises(pilot.PilotInviteError, match="pilot host"):
            pilot.invite("pilot@example.com", config=config, users_file=users_file)
    else:  # a malformed allowlist serves nothing, which is still a pilot-safe host
        assert problems == []
    assert users_file.read_text(encoding="utf-8") == before


def test_invite_refuses_when_sandbox_venture_exists(users_file):
    config = dict(PILOT_CONFIG, systems=[{"key": pilot.sandbox_venture("pilot@example.com")}])
    with pytest.raises(pilot.PilotInviteError, match="must be empty"):
        pilot.invite("pilot@example.com", config=config, users_file=users_file)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_invite_keeps_users_file_mode(users_file, monkeypatch):
    monkeypatch.setattr(pilot, "hash_password", lambda pw: "hashed")
    users_file.chmod(0o600)
    pilot.invite("pilot@example.com", config=PILOT_CONFIG, users_file=users_file)
    assert stat.S_IMODE(users_file.stat().st_mode) == 0o600


def test_invite_rejects_existing_user(users_file):
    with pytest.raises(pilot.PilotInviteError, match="already a user"):
        pilot.invite("OWNER@example.com", config=PILOT_CONFIG, users_file=users_file)


def test_invite_refuses_without_users_file(tmp_path):
    with pytest.raises(pilot.PilotInviteError, match="REALIZE_ADMIN_USER"):
        pilot.invite("pilot@example.com", config=PILOT_CONFIG, users_file=tmp_path / "users.yaml")


def test_invite_refuses_malformed_file(tmp_path):
    path = tmp_path / "users.yaml"
    path.write_text("users: {not: a list}\n", encoding="utf-8")
    with pytest.raises(pilot.PilotInviteError, match="not a list"):
        pilot.invite("pilot@example.com", config=PILOT_CONFIG, users_file=path)


def test_invite_writes_without_backup_on_read_only_directory(users_file, monkeypatch):
    monkeypatch.setattr(pilot, "hash_password", lambda pw: "hashed")

    def no_backup(*_a, **_k):
        raise PermissionError("read-only file system")

    monkeypatch.setattr(pilot.shutil, "copy2", no_backup)
    result = pilot.invite("pilot@example.com", config=PILOT_CONFIG, users_file=users_file)
    assert result.written
    assert result.backup is None
    assert "pilot@example.com" in users_file.read_text(encoding="utf-8")


def test_invite_returns_entry_when_file_is_read_only(users_file, monkeypatch):
    monkeypatch.setattr(pilot, "hash_password", lambda pw: "hashed")

    def fail(*_a, **_k):
        raise PermissionError("read-only mount")

    monkeypatch.setattr(pilot, "_write_text", fail)
    before = users_file.read_text(encoding="utf-8")
    result = pilot.invite("pilot@example.com", config=PILOT_CONFIG, users_file=users_file)
    assert not result.written
    assert "pilot@example.com" in result.entry_yaml
    assert "hashed" in result.entry_yaml
    assert result.password not in result.entry_yaml
    assert users_file.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------- retention job


@pytest.fixture
def db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


def test_purge_loop_deletes_expired_runs_then_waits(db, monkeypatch):
    old = datetime.now(UTC) - timedelta(days=40)
    monkeypatch.setattr(wedge_store, "_now", lambda: old)
    wedge_store.record_run("u1", market="pt", verification=1, items=3, without_locator=0)
    monkeypatch.setattr(wedge_store, "_now", lambda: datetime.now(UTC))
    wedge_store.record_run("u2", market="pt", verification=1, items=3, without_locator=0)

    async def run() -> None:
        task = asyncio.create_task(pilot.purge_loop(interval_seconds=3600))
        for _ in range(50):
            await asyncio.sleep(0.02)
            if len(wedge_store.funnel(days=365)) and wedge_store.funnel(days=365)[0]["runs"] == 1:
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert wedge_store.funnel(days=365)[0]["runs"] == 1


def test_purge_loop_survives_a_failed_purge(monkeypatch):
    import sqlite3

    calls = []

    async def run() -> None:
        second_try = asyncio.Event()
        loop = asyncio.get_running_loop()

        def boom(*_a, **_k):
            calls.append(1)
            if len(calls) >= 2:
                loop.call_soon_threadsafe(second_try.set)
            raise sqlite3.OperationalError("locked")

        monkeypatch.setattr(pilot, "purge_expired", boom)
        task = asyncio.create_task(pilot.purge_loop(interval_seconds=0.01))
        await asyncio.wait_for(second_try.wait(), timeout=5)
        task.cancel()

    asyncio.run(run())
    assert len(calls) >= 2


# ---------------------------------------------------------------- CLI

runner = CliRunner()


def _app():
    from realize_core.cli_app import app

    return app


def test_cli_invite_prints_password_once(users_file, monkeypatch):
    import realize_core.config as config_mod

    monkeypatch.chdir(users_file.parent)
    monkeypatch.delenv("MCP_TOOLS", raising=False)
    monkeypatch.setattr(config_mod, "load_config", lambda *a, **k: PILOT_CONFIG)
    monkeypatch.setattr(pilot, "hash_password", lambda pw: "hashed")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://pilot.example.com/")
    result = runner.invoke(_app(), ["wedge", "invite", "pilot@example.com"])
    assert result.exit_code == 0, result.output
    assert "Password (shown once" in result.output
    assert "https://pilot.example.com/mcp" in result.output


def test_cli_invite_error_exits_nonzero(tmp_path, monkeypatch):
    import realize_core.config as config_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_mod, "load_config", lambda *a, **k: PILOT_CONFIG)
    result = runner.invoke(_app(), ["wedge", "invite", "pilot@example.com"])
    assert result.exit_code == 1


def test_cli_invite_refused_off_a_pilot_host(users_file, monkeypatch):
    import realize_core.config as config_mod

    monkeypatch.chdir(users_file.parent)
    monkeypatch.setattr(config_mod, "load_config", lambda *a, **k: {"features": {"wedge": False}})
    result = runner.invoke(_app(), ["wedge", "invite", "pilot@example.com"])
    assert result.exit_code == 1
    assert "pilot@example.com" not in users_file.read_text(encoding="utf-8")


def test_cli_funnel_and_purge(db):
    wedge_store.record_run("u1", market="pt", verification=1, items=3, without_locator=0)
    result = runner.invoke(_app(), ["wedge", "funnel"])
    assert result.exit_code == 0
    assert "pt" in result.output
    as_json = runner.invoke(_app(), ["wedge", "funnel", "--format", "json"])
    assert as_json.exit_code == 0
    assert '"market": "pt"' in as_json.output
    purged = runner.invoke(_app(), ["wedge", "purge"])
    assert purged.exit_code == 0
    assert "Deleted 0" in purged.output
