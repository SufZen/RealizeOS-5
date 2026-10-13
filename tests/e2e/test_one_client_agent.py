"""One real client agent, end to end, against a real server process (STORY-37 acceptance).

Starts the real app with uvicorn in a subprocess on a free port, against a
temporary knowledge base and data folder, and drives it the way an outside
agent does: the MCP Python SDK client over Streamable HTTP (``/mcp``) with an
agent token in ``Authorization: Bearer``. It proves, against a real process:

- **scoped reads**: the agent lists and searches its own venture and is
  refused the other one;
- **held writes**: ``run_workflow`` comes back ``pending_approval`` and nothing runs;
- **people decide**: the agent is refused ``approve_request`` (MCP and REST);
  the owner approves over REST and the workflow runs once;
- **restart**: the server is killed while an approved run is in flight (the
  approval is claimed, the model call hasn't answered), restarted, and the
  agent sees ``unknown_outcome``; nothing re-runs at startup or on a second
  approval;
- **export**: the owner's export carries the approvals, their decisions and the
  agent's trail, and no agent token secret.

The model is a local fixture speaking the Ollama API on 127.0.0.1 (the
provider-boundary stub; no real model key is ever set), so the run can be held
open deterministically. The test skips, with the reason, when the server
process can't be spawned or no local port can be bound.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import anyio
import httpx
import pytest

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_REPLY = "Fixture summary: the tower crane is booked for Tuesday."
STARTUP_TIMEOUT = 45.0

CONFIG_YAML = """\
name: "One client agent (e2e)"
systems:
  - key: alpha
    name: "Alpha Towers"
    directory: systems/alpha
  - key: beta
    name: "Beta Bridges"
    directory: systems/beta
features:
  # Loads every venture's own skills at startup (docs/skill-authoring.md).
  packs: true
  agent_tokens: true
mcp:
  enabled: true
"""

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

SKILL_YAML = """\
name: site_summary
description: Summarise the site for the client
triggers: ["site summary"]
pipeline: [orchestrator]
"""


# ---------------------------------------------------------------------------
# Fixture model: the Ollama API on 127.0.0.1, optionally holding its answer
# ---------------------------------------------------------------------------


class FixtureLLM:
    """A local stand-in for a model provider (Ollama's ``/api/tags`` and ``/api/chat``).

    ``chat_calls`` counts completions asked for. While ``hold`` is set, a
    completion waits until ``release`` is set (or 60 s), which keeps an
    approved run in flight for as long as the test needs.
    """

    def __init__(self) -> None:
        self.chat_calls = 0
        self.hold = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        """Base URL to put in ``OLLAMA_HOST``."""
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> None:
        """Serve in a background thread."""
        self._thread.start()

    def stop(self) -> None:
        """Let held requests go and stop serving."""
        self.release.set()
        self._server.shutdown()
        self._server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode("utf-8")
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError:  # the server under test was killed mid-call
                    logger.debug("Fixture LLM client went away")

            def do_GET(self) -> None:
                if self.path.startswith("/api/tags"):
                    self._reply({"models": [{"name": "fixture"}]})
                else:
                    self.send_error(404)

            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if not self.path.startswith("/api/chat"):
                    self.send_error(404)
                    return
                with fixture._lock:
                    fixture.chat_calls += 1
                if fixture.hold.is_set():
                    fixture.release.wait(timeout=60)
                self._reply(
                    {
                        "model": "fixture",
                        "message": {"role": "assistant", "content": FIXTURE_REPLY},
                        "prompt_eval_count": 1,
                        "eval_count": 1,
                        "done": True,
                    }
                )

            def log_message(self, format: str, *args: Any) -> None:
                logger.debug("fixture llm: " + format, *args)

        return Handler


# ---------------------------------------------------------------------------
# The real server, in a subprocess
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _server_env(kb: Path, *, api_key: str, llm_url: str, audit_dir: Path) -> dict[str, str]:
    """The test's environment, minus RealizeOS settings and every key, plus this install's."""
    drop = ("REALIZE_", "MCP_", "KB_PATH", "DATA_PATH", "OLLAMA_")
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(drop) and not k.endswith(("_API_KEY", "_SECRET", "_TOKEN"))
    }
    env.update(
        {
            "PYTHONPATH": str(REPO_ROOT),
            "PYTHONIOENCODING": "utf-8",
            "PYTHON_DOTENV_DISABLED": "1",
            "KB_PATH": str(kb),
            "DATA_PATH": str(kb / "data"),
            "REALIZE_CONFIG": str(kb / "realize-os.yaml"),
            "REALIZE_API_KEY": api_key,
            "REALIZE_AUDIT_LOG_DIR": str(audit_dir),
            "MCP_ENABLED": "true",
            "OLLAMA_HOST": llm_url,
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
            "NO_PROXY": "127.0.0.1,localhost",
            # Never a real model: every hosted provider stays unavailable.
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_AI_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "GEMINI_API_KEY": "",
            "OPENAI_API_KEY": "",
        }
    )
    return env


class Server:
    """``uvicorn realize_api.main:app`` on a free local port; restartable on the same data."""

    def __init__(self, kb: Path, env: dict[str, str], log_dir: Path) -> None:
        self.kb, self.env, self.log_dir = kb, env, log_dir
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.starts = 0

    @property
    def base(self) -> str:
        """Base URL of the running server."""
        return f"http://127.0.0.1:{self.port}"

    @property
    def log_path(self) -> Path:
        """This start's combined stdout/stderr."""
        return self.log_dir / f"server-{self.starts}.log"

    def log_tail(self, chars: int = 4000) -> str:
        """The end of this start's log, for failure messages."""
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace")[-chars:]
        except OSError:
            return ""

    def start(self) -> None:
        """Start and wait for ``/api/health``; skip when no process or port is available."""
        for _ in range(3):
            self.starts += 1
            try:
                self.port = _free_port()
            except OSError as exc:
                pytest.skip(f"No local port can be bound for the server: {exc}")
            command = [
                sys.executable,
                "-m",
                "uvicorn",
                "realize_api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ]
            with self.log_path.open("wb") as log:
                try:
                    self.proc = subprocess.Popen(
                        command, cwd=str(self.kb), env=self.env, stdout=log, stderr=subprocess.STDOUT
                    )
                except OSError as exc:
                    pytest.skip(f"The server process can't be started: {exc}")
            if self._wait_healthy():
                return
            tail = self.log_tail()
            if "address already in use" in tail.lower() or "error while attempting to bind" in tail.lower():
                continue  # another process took the port between choosing and binding it
            self.kill()
            pytest.fail(f"The server did not become healthy in {STARTUP_TIMEOUT:.0f}s:\n{tail}")
        pytest.skip("No free local port could be bound by the server after 3 attempts")

    def _wait_healthy(self) -> bool:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        with httpx.Client(trust_env=False, timeout=2.0) as client:
            while time.monotonic() < deadline:
                if self.proc is None or self.proc.poll() is not None:
                    return False
                try:
                    if client.get(f"{self.base}/api/health").status_code == 200:
                        return True
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
        return False

    def kill(self) -> None:
        """Stop the process at once, as a crash or a power cut would."""
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=15)

    def stop(self) -> None:
        """Ask the process to stop; kill it if it doesn't."""
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.kill()


# ---------------------------------------------------------------------------
# MCP client (the SDK's Streamable HTTP transport)
# ---------------------------------------------------------------------------


def _streamable_client(url: str, http_client: httpx.AsyncClient):
    """The SDK's Streamable HTTP client: the current API, else the one older SDKs in range have."""
    from mcp.client import streamable_http

    if hasattr(streamable_http, "streamable_http_client"):
        return streamable_http.streamable_http_client(url, http_client=http_client)
    return streamable_http.streamablehttp_client(url, headers=dict(http_client.headers))  # mcp < 1.24


def mcp_calls(base: str, token: str, calls: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    """Open one MCP session as the agent and run ``calls`` in order.

    ``("tools/list", {})`` returns the sorted tool names; every other entry is
    a tool call and returns its JSON result.
    """
    from mcp import ClientSession

    async def run() -> list[Any]:
        results: list[Any] = []
        headers = {"Authorization": f"Bearer {token}"}
        timeout = httpx.Timeout(30.0, read=60.0)
        with anyio.fail_after(90):
            async with httpx.AsyncClient(headers=headers, timeout=timeout, trust_env=False) as http_client:
                async with _streamable_client(f"{base}/mcp", http_client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        init = await session.initialize()
                        assert init.serverInfo.name == "realize-os"
                        for name, arguments in calls:
                            if name == "tools/list":
                                results.append(sorted(t.name for t in (await session.list_tools()).tools))
                            else:
                                result = await session.call_tool(name, arguments)
                                results.append(json.loads(result.content[0].text))
        return results

    return anyio.run(run)


def _outcome(approvals: dict[str, Any], approval_id: str) -> dict[str, Any]:
    rows = [row for row in approvals["approvals"] if row["id"] == approval_id]
    assert len(rows) == 1, approvals
    return rows[0]


def _wait_for(predicate, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"Timed out after {timeout}s waiting for {what}")


# ---------------------------------------------------------------------------
# The journey
# ---------------------------------------------------------------------------


@pytest.fixture
def install(tmp_path):
    """A RealizeOS folder with two ventures, users and one workflow in alpha."""
    kb = tmp_path / "kb"
    for key, text in (
        ("alpha", "Alpha builds towers in Lisbon. The site code word is pelican."),
        ("beta", "Beta builds bridges. The site code word is walrus."),
    ):
        (kb / "systems" / key / "F-foundations").mkdir(parents=True)
        (kb / "systems" / key / "A-agents").mkdir(parents=True)
        (kb / "systems" / key / "F-foundations" / "venture-identity.md").write_text(
            f"# {key.title()} identity\n{text}\n", encoding="utf-8"
        )
    skills = kb / "systems" / "alpha" / "R-routines" / "skills"
    skills.mkdir(parents=True)
    (skills / "site-summary.yaml").write_text(SKILL_YAML, encoding="utf-8")
    (kb / "realize-os.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    (kb / "users.yaml").write_text(USERS_YAML, encoding="utf-8")
    return kb


@pytest.fixture
def llm():
    """The fixture model, stopped (and any held answer released) after the test."""
    fixture = FixtureLLM()
    fixture.start()
    yield fixture
    fixture.stop()


def test_one_agent_scoped_reads_held_writes_approval_restart_export(install, llm, tmp_path):
    started = time.monotonic()
    api_key = secrets.token_urlsafe(32)
    owner = {"X-API-Key": api_key}
    env = _server_env(install, api_key=api_key, llm_url=llm.url, audit_dir=tmp_path / "audit")
    server = Server(install, env, tmp_path)
    rest = httpx.Client(trust_env=False, timeout=60.0)
    approver: threading.Thread | None = None
    try:
        server.start()

        # The owner issues an agent token for one venture.
        created = rest.post(
            f"{server.base}/api/agent-tokens",
            headers=owner,
            json={"name": "e2e-claude", "user": "dana@example.com", "ventures": ["alpha"]},
        )
        assert created.status_code == 201, created.text
        token = created.json()["token"]
        agent = created.json()["agent_token"]["principal"]
        assert agent.startswith("agent:")
        run = {"name": "site_summary", "input_text": "Summarise the site for the client", "system_key": "alpha"}

        # Scoped reads, a held write, and a refused decision — as the agent, over MCP.
        tools, ventures, found, other, other_kb, held, refused = mcp_calls(
            server.base,
            token,
            [
                ("tools/list", {}),
                ("list_ventures", {}),
                ("venture_kb_search", {"venture_key": "alpha", "query": "pelican"}),
                ("get_system", {"system_key": "beta"}),
                ("venture_kb_search", {"venture_key": "beta", "query": "walrus"}),
                ("run_workflow", run),
                ("approve_request", {"approval_id": "placeholder"}),
            ],
        )
        assert {"list_ventures", "venture_kb_search", "run_workflow", "list_approvals"} <= set(tools)
        # tools/list doesn't offer an agent the decisions it can't make; calling one is still refused.
        assert not {"approve_request", "reject_request", "delete_venture"} & set(tools)
        assert [v["key"] for v in ventures["ventures"]] == ["alpha"]
        assert found["results"], found
        assert all("alpha" in r["path"] for r in found["results"]), found
        assert other["code"] == "MCP_FORBIDDEN"
        assert other_kb["code"] == "MCP_FORBIDDEN"
        assert held["status"] == "pending_approval", held
        first = held["approval_id"]
        assert refused["code"] == "MCP_AGENT_CANNOT_DECIDE"
        assert llm.chat_calls == 0  # nothing ran

        (refused_own,) = mcp_calls(server.base, token, [("approve_request", {"approval_id": first})])
        assert refused_own["code"] == "MCP_AGENT_CANNOT_DECIDE"
        as_agent = rest.post(
            f"{server.base}/api/approvals/{first}/approve", headers={"Authorization": f"Bearer {token}"}
        )
        assert as_agent.status_code == 403

        # A person approves over REST: the workflow runs once, as the agent.
        approved = rest.post(f"{server.base}/api/approvals/{first}/approve", headers=owner, json={})
        assert approved.status_code == 200, approved.text
        assert approved.json()["execution_status"] == "succeeded", approved.json()
        assert llm.chat_calls == 1
        (listed,) = mcp_calls(server.base, token, [("list_approvals", {"venture_key": "alpha", "approval_id": first})])
        done = _outcome(listed, first)
        assert (done["outcome"], done["requested_by"]) == ("succeeded", agent)
        assert FIXTURE_REPLY in done["result"]

        # A second held write; the server dies while its approved run waits on the model.
        (second_held,) = mcp_calls(server.base, token, [("run_workflow", run)])
        second = second_held["approval_id"]
        llm.hold.set()

        def approve_second() -> None:
            try:
                rest.post(f"{server.base}/api/approvals/{second}/approve", headers=owner, json={}, timeout=60)
            except httpx.HTTPError:
                pass  # the server is killed under this request

        approver = threading.Thread(target=approve_second, daemon=True)
        approver.start()
        _wait_for(lambda: llm.chat_calls == 2, 30, "the approved run to reach the model")
        server.kill()
        approver.join(timeout=30)
        llm.hold.clear()
        llm.release.set()

        # Restart on the same data: the status is truthful and nothing re-runs.
        server.start()
        assert rest.get(f"{server.base}/api/health").json()["status"] == "ok"
        after_first, after_second = mcp_calls(
            server.base,
            token,
            [
                ("list_approvals", {"venture_key": "alpha", "approval_id": first}),
                ("list_approvals", {"venture_key": "alpha", "approval_id": second}),
            ],
        )
        assert _outcome(after_first, first)["outcome"] == "succeeded"
        assert _outcome(after_second, second)["outcome"] == "unknown_outcome"
        again = rest.post(f"{server.base}/api/approvals/{second}/approve", headers=owner, json={})
        assert again.status_code == 409, again.text
        time.sleep(1.0)  # give anything that would wrongly resume a claimed run the time to do it
        assert llm.chat_calls == 2

        # The owner's export carries the trail and the decisions, never the token.
        exported = rest.post(f"{server.base}/api/storage/export", headers=owner)
        assert exported.status_code == 200, exported.text
        archive = zipfile.ZipFile(io.BytesIO(exported.content))
        decisions = [
            archive.read(n).decode("utf-8")
            for n in archive.namelist()
            if n.startswith("systems/alpha/B-brain/decisions/")
        ]
        assert any(first in text for text in decisions)
        assert any(second in text for text in decisions)
        snapshot = tmp_path / "exported-ops.db"
        snapshot.write_bytes(archive.read("data/realize_data.db"))
        with sqlite3.connect(snapshot) as conn:
            rows = {
                row[0]: row[1:]
                for row in conn.execute(
                    "SELECT id, status, execution_status, requested_by, action_name FROM approval_queue"
                )
            }
            trail = {row[0] for row in conn.execute("SELECT action FROM activity_events WHERE venture_key = 'alpha'")}
            stored_hash = conn.execute("SELECT token_hash FROM agent_tokens").fetchone()[0]
        assert rows[first] == ("approved", "succeeded", agent, "mcp:run_workflow")
        assert rows[second] == ("approved", "claimed", agent, "mcp:run_workflow")
        assert {"mcp_write_held", "approval_executed"} <= trail
        assert stored_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token.encode() not in b"".join(archive.read(n) for n in archive.namelist())

        # Everything the agent did is on the audit record, refusals included.
        events = [
            json.loads(line)
            for line in (tmp_path / "audit" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        mine = {(e["action"], e["outcome"]) for e in events if e.get("user_id") == agent}
        assert ("mcp.get_system", "denied") in mine
        assert any(action == "mcp.approve_request" and outcome != "success" for action, outcome in mine)
        assert time.monotonic() - started < 120
    except BaseException:
        logger.error("Server log (start %d):\n%s", server.starts, server.log_tail())
        raise
    finally:
        llm.release.set()
        server.stop()
        rest.close()
        if approver is not None:
            approver.join(timeout=5)
