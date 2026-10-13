"""MCP stdio transport (STORY-37).

``realize-os mcp stdio`` / ``python cli.py mcp stdio`` serves the same tools
as ``/mcp`` over stdin/stdout for a local agent. These tests cover:

- identity: a ``users.yaml`` user is required, there is no anonymous owner,
  ``--venture`` only narrows;
- refusals before any state is built (MCP off, production admin without JWT);
- a real subprocess round-trip with the MCP SDK client: initialize →
  tools/list → a read tool → a venture-scope refusal;
- stdout carrying JSON-RPC only, including through the ``--directory``
  relaunch, while logs, ``print()`` and child processes go to stderr.

Subprocesses use the temp operational DB from ``tests/conftest.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import anyio
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = str(REPO_ROOT / "cli.py")

USERS_YAML = """\
users:
  - email: owner@example.com
    role: owner
    password_hash: "not-a-real-hash"
  - email: dana@example.com
    role: operator
    ventures: [alpha]
    password_hash: "not-a-real-hash"
"""

CONFIG_YAML = """\
name: "Stdio Test"
systems:
  - key: alpha
    name: "Alpha Ventures"
    directory: systems/alpha
  - key: beta
    name: "Beta Ventures"
    directory: systems/beta
"""


@pytest.fixture
def users_dir(tmp_path, monkeypatch):
    """A working directory with ``users.yaml`` (users are read from the cwd)."""
    (tmp_path / "users.yaml").write_text(USERS_YAML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def stdio_project(tmp_path, _session_ops_db):
    """A RealizeOS project folder plus the environment to run ``mcp stdio`` in it."""
    project = tmp_path / "project"
    for key, text in (
        ("alpha", "Alpha builds towers. The site code word is pelican."),
        ("beta", "Beta builds bridges."),
    ):
        (project / "systems" / key / "F-foundations").mkdir(parents=True)
        (project / "systems" / key / "A-agents").mkdir(parents=True)
        (project / "systems" / key / "F-foundations" / "venture-identity.md").write_text(
            f"# {key.title()} identity\n{text}\n", encoding="utf-8"
        )
    (project / "realize-os.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    (project / "users.yaml").write_text(USERS_YAML, encoding="utf-8")

    env = {k: v for k, v in os.environ.items() if not k.startswith(("REALIZE_", "MCP_", "KB_PATH", "DATA_PATH"))}
    env.update(
        {
            "MCP_ENABLED": "true",
            "REALIZE_DB_PATH": str(_session_ops_db),
            "DATA_PATH": str(tmp_path / "data"),
            "REALIZE_AUDIT_LOG_DIR": str(tmp_path / "audit"),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return project, env


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class TestResolveStdioUser:
    @pytest.mark.parametrize("user_id", [None, "", "   "])
    def test_no_identity_is_refused(self, users_dir, user_id):
        from realize_core.mcp_server.stdio import StdioStartupError, resolve_stdio_user

        with pytest.raises(StdioStartupError, match="anonymous owner"):
            resolve_stdio_user(user_id)

    def test_unknown_user_is_refused(self, users_dir):
        from realize_core.mcp_server.stdio import StdioStartupError, resolve_stdio_user

        with pytest.raises(StdioStartupError, match="not a configured user"):
            resolve_stdio_user("mallory@example.com")

    def test_role_comes_from_users_yaml(self, users_dir):
        from realize_core.mcp_server.stdio import resolve_stdio_user

        user = resolve_stdio_user("Dana@Example.com")
        assert (user.user_id, user.role, user.scopes) == ("dana@example.com", "operator", [])

    def test_venture_limited_user_keeps_their_limit(self, users_dir):
        from realize_core.mcp_server.stdio import resolve_stdio_user
        from realize_core.mcp_server.venture_guard import caller_ventures

        assert caller_ventures(resolve_stdio_user("dana@example.com")) == frozenset({"alpha"})

    def test_venture_outside_the_users_ventures_is_refused(self, users_dir):
        from realize_core.mcp_server.stdio import StdioStartupError, resolve_stdio_user

        with pytest.raises(StdioStartupError, match="no access to venture"):
            resolve_stdio_user("dana@example.com", ["beta"])

    def test_venture_narrows_an_owner(self, users_dir):
        from realize_core.mcp_server.stdio import resolve_stdio_user
        from realize_core.mcp_server.venture_guard import caller_ventures

        user = resolve_stdio_user("owner@example.com", ["beta", "beta", " "])
        assert user.role == "owner"
        assert user.scopes == ["venture:beta"]
        assert caller_ventures(user) == frozenset({"beta"})


# ---------------------------------------------------------------------------
# Refusals before any state is built
# ---------------------------------------------------------------------------


class TestPrepareRefusals:
    def test_mcp_off_is_refused(self, users_dir, monkeypatch):
        from realize_core.mcp_server.stdio import StdioStartupError, prepare_stdio

        monkeypatch.delenv("MCP_ENABLED", raising=False)
        with pytest.raises(StdioStartupError, match="MCP is off"):
            prepare_stdio("owner@example.com", config={"mcp": {"enabled": False}})

    def test_production_without_identity_is_refused(self, users_dir, monkeypatch):
        from realize_core.mcp_server.stdio import StdioStartupError, prepare_stdio

        monkeypatch.setenv("REALIZE_ENV", "production")
        monkeypatch.setenv("MCP_ENABLED", "true")
        with pytest.raises(StdioStartupError, match="No identity"):
            prepare_stdio(None, config={})

    def test_production_admin_without_jwt_is_refused(self, users_dir, monkeypatch):
        from realize_core.mcp_server.auth import MCPProductionAuthError
        from realize_core.mcp_server.stdio import prepare_stdio

        monkeypatch.setenv("REALIZE_ENV", "production")
        monkeypatch.setenv("MCP_ENABLED", "true")
        monkeypatch.setenv("MCP_ALLOW_ADMIN", "true")
        monkeypatch.delenv("REALIZE_JWT_ENABLED", raising=False)
        with pytest.raises(MCPProductionAuthError):
            prepare_stdio("owner@example.com", config={})


# ---------------------------------------------------------------------------
# Subprocess round-trips
# ---------------------------------------------------------------------------


def _tool_json(result) -> dict:
    return json.loads(result.content[0].text)


async def test_sdk_client_round_trip(stdio_project, tmp_path):
    """initialize → tools/list → read tool → venture refusal, over a real stdio pipe."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    project, env = stdio_project
    params = StdioServerParameters(
        command=sys.executable,
        args=[CLI, "mcp", "stdio", "--user", "dana@example.com"],
        env=env,
        cwd=str(project),
    )
    with (tmp_path / "server-stderr.log").open("w", encoding="utf-8") as errlog:
        with anyio.fail_after(90):
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    init = await session.initialize()
                    assert init.serverInfo.name == "realize-os"

                    names = {t.name for t in (await session.list_tools()).tools}
                    assert {"realize_health", "list_ventures", "kb_search", "get_system"} <= names
                    assert "delete_venture" not in names  # admin family stays off

                    ventures = _tool_json(await session.call_tool("list_ventures", {}))
                    assert [v["key"] for v in ventures["ventures"]] == ["alpha"]

                    found = _tool_json(
                        await session.call_tool("kb_search", {"query": "pelican", "system_key": "alpha"})
                    )
                    assert any("alpha" in r["path"] for r in found["results"])

                    refused = _tool_json(await session.call_tool("get_system", {"system_key": "beta"}))
                    assert refused["code"] == "MCP_FORBIDDEN"

    log = (tmp_path / "server-stderr.log").read_text(encoding="utf-8")
    assert "MCP stdio server ready" in log
    assert "user=dana@example.com role=operator ventures=alpha" in log

    # Same audit trail as the HTTP transports, under the stdio caller's identity.
    events = [
        json.loads(line) for line in (tmp_path / "audit" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    seen = {(e["user_id"], e["action"], e["outcome"]) for e in events}
    assert ("dana@example.com", "mcp.stdio.session_start", "success") in seen
    assert ("dana@example.com", "mcp.get_system", "denied") in seen


def _exchange(proc: subprocess.Popen, message: dict) -> bytes | None:
    """Send one JSON-RPC line; read the reply line for requests."""
    proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
    proc.stdin.flush()
    return proc.stdout.readline() if "id" in message else None


def test_stdout_is_json_rpc_only_through_directory_relaunch(stdio_project, tmp_path):
    """Run from another folder with --directory; every stdout line is JSON-RPC."""
    project, env = stdio_project
    stderr_path = tmp_path / "stderr.log"
    with stderr_path.open("wb") as stderr:
        proc = subprocess.Popen(
            [sys.executable, CLI, "mcp", "stdio", "--directory", str(project), "--user", "owner@example.com"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            cwd=str(tmp_path),
            env=env,
        )
        watchdog = threading.Timer(90, proc.kill)
        watchdog.start()
        try:
            lines = [
                _exchange(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "0"},
                        },
                    },
                )
            ]
            _exchange(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            lines.append(_exchange(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
            lines.append(
                _exchange(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "list_ventures", "arguments": {}},
                    },
                )
            )
            proc.stdin.close()
            lines.append(proc.stdout.read())
            assert proc.wait() == 0
        finally:
            watchdog.cancel()

    stdout = b"".join(lines).decode("utf-8")
    replies = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    assert [r["id"] for r in replies] == [1, 2, 3]
    assert all(r["jsonrpc"] == "2.0" and "result" in r for r in replies)
    assert "\r" not in stdout
    ventures = json.loads(replies[2]["result"]["content"][0]["text"])["ventures"]
    assert sorted(v["key"] for v in ventures) == ["alpha", "beta"]  # owner, no --venture

    log = stderr_path.read_text(encoding="utf-8", errors="replace")
    assert "MCP stdio server ready" in log
    assert "user=owner@example.com role=owner ventures=all" in log


def test_missing_identity_exits_without_writing_stdout(stdio_project):
    project, env = stdio_project
    proc = subprocess.run(
        [sys.executable, CLI, "mcp", "stdio"],
        input=b"",
        capture_output=True,
        cwd=str(project),
        env=env,
        timeout=90,
    )
    assert proc.returncode == 2
    assert proc.stdout == b""
    assert b"No identity" in proc.stderr


def test_claim_stdout_sends_stray_output_to_stderr(tmp_path):
    """print(), raw fd writes and child processes can't reach the JSON-RPC stream."""
    script = (
        "import os, subprocess, sys, anyio\n"
        "from realize_core.mcp_server.stdio import claim_stdout\n"
        "out = claim_stdout()\n"
        "print('noise-print')\n"
        "os.write(1, b'noise-fd\\n')\n"
        "subprocess.run([sys.executable, '-c', 'print(\"noise-child\")'], check=True)\n"
        "async def main():\n"
        '    await out.write(\'{"jsonrpc": "2.0"}\\n\')\n'
        "    await out.flush()\n"
        "anyio.run(main)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == b'{"jsonrpc": "2.0"}\n'
    for noise in (b"noise-print", b"noise-fd", b"noise-child"):
        assert noise in proc.stderr
