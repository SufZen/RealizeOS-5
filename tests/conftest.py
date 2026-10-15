"""Shared test fixtures for RealizeOS test suite."""

import os
import sys

# KB embeddings off for the whole run, subprocesses included: fastembed is a core
# dependency and would otherwise download its model. Tests that need vectors fake them.
os.environ["KB_EMBED_MODEL"] = "none"
# Before anything imports litellm: PRODUCTION stops litellm's load_dotenv(), which
# finds the developer's .env (with real provider keys) by walking up from the venv;
# the local cost map keeps litellm from downloading prices.
os.environ["LITELLM_MODE"] = "PRODUCTION"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

import ipaddress
import socket

import pytest
from realize_core.memory import conversation as _conversation

#: The real conversation helpers, taken before any test can patch them.
_REAL_CONVERSATION_HELPERS = {
    name: getattr(_conversation, name) for name in ("add_message", "get_history", "to_llm_messages")
}


@pytest.fixture(scope="session")
def _session_ops_db(tmp_path_factory):
    """One fully migrated operational DB for the whole run, in a temp folder."""
    from realize_core.db.migrations import run_migrations
    from realize_core.db.schema import init_schema
    from realize_core.migration.engine import MigrationEngine

    path = tmp_path_factory.mktemp("ops") / "realize_data.db"
    init_schema(path)
    run_migrations(path)
    MigrationEngine(db_path=path).migrate_up()
    return path


@pytest.fixture(autouse=True)
def _isolated_ops_db(_session_ops_db):
    """Default every test to the temp operational DB.

    Without this, a test that doesn't set its own DB falls back to
    ``<cwd>/realize_data.db``: the developer's real database locally, and an
    empty file in CI, so results differed between the two. Tests that call
    ``set_db_path`` themselves still override it.
    """
    from realize_core.db import schema

    schema.set_db_path(_session_ops_db)
    yield
    schema.set_db_path(None)


@pytest.fixture(scope="session")
def _pack_state_root(tmp_path_factory):
    return tmp_path_factory.mktemp("pack-state")


@pytest.fixture(autouse=True)
def _isolated_pack_state(_pack_state_root, monkeypatch):
    """Give every test its own pack verification state file.

    The state normally lives in ``DATA_PATH/packs/verification.json``; without
    this, a developer's local approvals would change the levels tests see.
    The folder is only created if the test records a verification.
    """
    import uuid

    from realize_core.packs import state

    path = _pack_state_root / uuid.uuid4().hex / state.STATE_FILE
    monkeypatch.setattr(state, "state_path", lambda: path)
    state.clear_cache()
    yield
    state.clear_cache()


@pytest.fixture(autouse=True)
def _isolated_skill_cascade(monkeypatch):
    """Start every test with the pack skill cascade off, as a fresh process is.

    An app started with ``features.packs`` on turns it on for later skill
    loads (``configure_pack_cascade``); it must not carry into other tests.
    """
    from realize_core.skills import detector

    monkeypatch.setattr(detector, "_pack_cascade", False)
    monkeypatch.setattr(detector, "_venture_dirs", None)
    # Workflows created or changed through the API are kept across reloads until restart.
    monkeypatch.setattr(detector, "_runtime_skills", {})
    monkeypatch.setattr(detector, "_runtime_edits", {})
    monkeypatch.setattr(detector, "_runtime_removed", set())


@pytest.fixture(autouse=True)
def _real_conversation_helpers():
    """Start every test with ``base_handler`` using the real conversation helpers.

    ``realize_core.base_handler`` binds ``add_message``, ``get_history`` and
    ``to_llm_messages`` by name when it is first imported. When that first
    import happens inside a test that has stubbed them on
    ``realize_core.memory.conversation`` (the approval tests capture posted
    messages that way), the stub outlived the test: later tests that go
    through ``process_message`` stored no history, and the webinar API test
    failed or passed depending on which test imported ``base_handler`` first.
    """
    base_handler = sys.modules.get("realize_core.base_handler")
    if base_handler is not None:
        for name, helper in _REAL_CONVERSATION_HELPERS.items():
            setattr(base_handler, name, helper)


@pytest.fixture(params=["anthropic", "openai", "gemini", "ollama"])
def fake_llm(request, monkeypatch):
    """The only LLM is one real provider adapter over a scripted, mocked transport.

    Parametrised over the four wire shapes (``tests.fakes.llm.SHAPES``); see
    ``tests/fakes/llm.py``. The registry, environment and transports are
    restored after the test.
    """
    from tests.fakes.llm import install_fake_llm

    return install_fake_llm(monkeypatch, request.param)


@pytest.fixture
def kb_root(tmp_path):
    """Create a minimal KB directory structure for testing.

    Returns:
        Path to the root KB directory with:
        - shared/identity.md
        - shared/user-preferences.md
        - systems/test/F-foundations/venture-identity.md
        - systems/test/F-foundations/venture-voice.md
        - systems/test/A-agents/_README.md
        - systems/test/A-agents/orchestrator.md
        - systems/test/A-agents/writer.md
        - systems/test/I-insights/learning-log.md
    """
    # Shared identity files
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "identity.md").write_text(encoding="utf-8", data="# Identity\nI am a test user named Alex.")
    (shared / "user-preferences.md").write_text(encoding="utf-8", data="# Preferences\nBe concise. Use bullet points.")

    # System directory structure
    system_dir = tmp_path / "systems" / "test"
    system_dir.mkdir(parents=True)

    # Foundations
    foundations = system_dir / "F-foundations"
    foundations.mkdir()
    (foundations / "venture-identity.md").write_text(
        encoding="utf-8", data="# Venture Identity\nTest Brand Inc — AI-powered solutions for everyone."
    )
    (foundations / "venture-voice.md").write_text(
        encoding="utf-8", data="# Venture Voice\nProfessional, direct, and friendly."
    )

    # Agents
    agents = system_dir / "A-agents"
    agents.mkdir()
    (agents / "_README.md").write_text(
        encoding="utf-8",
        data="# Agent Routing\n"
        "- Orchestrator: general queries, coordination\n"
        "- Writer: content creation, blog posts, copy\n",
    )
    (agents / "orchestrator.md").write_text(
        encoding="utf-8", data="# Orchestrator\nYou coordinate the team and handle general queries."
    )
    (agents / "writer.md").write_text(
        encoding="utf-8", data="# Writer\nYou create compelling content and persuasive copy."
    )

    # Insights / memory
    insights = system_dir / "I-insights"
    insights.mkdir()
    (insights / "learning-log.md").write_text(
        encoding="utf-8", data="# Learning Log\n- User prefers short paragraphs\n- Always include CTA in posts"
    )

    return tmp_path


@pytest.fixture
def system_config():
    """Standard test system configuration dict."""
    return {
        "name": "Test System",
        "brand_identity": "systems/test/F-foundations/venture-identity.md",
        "brand_voice": "systems/test/F-foundations/venture-voice.md",
        "agents_readme": "systems/test/A-agents/_README.md",
        "memory_dir": "systems/test/I-insights",
        "insights_dir": "systems/test/I-insights",
        "agents": {
            "orchestrator": "systems/test/A-agents/orchestrator.md",
            "writer": "systems/test/A-agents/writer.md",
        },
    }


@pytest.fixture
def shared_config():
    """Standard test shared configuration dict."""
    return {
        "identity": "shared/identity.md",
        "preferences": "shared/user-preferences.md",
    }


@pytest.fixture
def empty_system_config():
    """System config with no files configured."""
    return {
        "name": "Empty System",
        "agents": {},
    }


@pytest.fixture
def minimal_yaml_config():
    """Return a minimal YAML config string for testing."""
    return """
name: "Test Business"
systems:
  - key: test
    name: "Test System"
    directory: systems/test
shared:
  identity: shared/identity.md
  preferences: shared/user-preferences.md
features:
  review_pipeline: true
  auto_memory: true
"""


# ---------------------------------------------------------------------------
# Provider environment and the network guard
# ---------------------------------------------------------------------------

#: Provider keys cleared for every test (a test may set them again).
_PROVIDER_KEYS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_WORKSPACE_ID",
    "GOOGLE_AI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_BASE_URL",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
    "TOGETHER_API_KEY",
    "COHERE_API_KEY",
    "XAI_API_KEY",
)
_PROVIDER_PREFIXES = ("LLM_", "OLLAMA_", "LITELLM_")
_KEPT = {"LITELLM_MODE", "LITELLM_LOCAL_MODEL_COST_MAP"}
#: Where Ollama probes go in tests: a TEST-NET-1 address the network guard refuses at once.
TEST_OLLAMA_BASE_URL = "http://192.0.2.1:11434"
_TEST_OLLAMA_HOST = "192.0.2.1"


@pytest.fixture(autouse=True)
def _clean_provider_env(monkeypatch):
    """Start every test with no provider configured and Ollama pointed nowhere.

    Clears provider API keys and ``LLM_*`` / ``OLLAMA_*`` / ``LITELLM_*``
    settings (keeping the litellm mode flags above), points Ollama at an
    address the network guard refuses, and drops the provider registry
    singleton so it is rebuilt from this clean environment. Tests that need a
    provider set its variables themselves.
    """
    import realize_core.llm.registry as llm_registry

    for name in list(os.environ):
        if _is_provider_env(name):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", TEST_OLLAMA_BASE_URL)
    monkeypatch.setattr(llm_registry, "_registry", None)


def _is_provider_env(name: str) -> bool:
    return name in _PROVIDER_KEYS or (name.startswith(_PROVIDER_PREFIXES) and name not in _KEPT)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    item._provider_env = {k: v for k, v in os.environ.items() if _is_provider_env(k)}
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    """After every fixture (monkeypatch included) is undone, put provider settings back.

    Code under test may write ``os.environ`` directly (the settings routes do);
    a value monkeypatch never saw would otherwise leak into later tests.
    """
    yield
    before = getattr(item, "_provider_env", None)
    if before is None:
        return
    for name in [k for k in os.environ if _is_provider_env(k) and k not in before]:
        del os.environ[name]
    os.environ.update(before)


#: Non-loopback connection attempts refused during the run: (test id, target).
BLOCKED_CONNECTIONS: list[tuple[str, str]] = []
_current_test = {"id": ""}


class NetworkBlockedError(ConnectionRefusedError):
    """A test tried to reach a non-loopback address."""


def _is_loopback(host) -> bool:
    if host is None:
        return True
    host = host.decode() if isinstance(host, bytes) else str(host)
    host = host.strip("[]").split("%")[0]
    if host in ("", "localhost", "localhost.localdomain", "testserver") or host.endswith(".localhost"):
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if getattr(addr, "ipv4_mapped", None):
        addr = addr.ipv4_mapped
    return addr.is_loopback or addr.is_unspecified


def _record(target: str) -> None:
    if _TEST_OLLAMA_HOST not in target:  # the expected Ollama probe
        BLOCKED_CONNECTIONS.append((_current_test["id"], target))


def _check_target(address) -> None:
    if isinstance(address, tuple) and address and not _is_loopback(address[0]):
        _record(f"{address[0]}:{address[1] if len(address) > 1 else ''}")
        raise NetworkBlockedError(f"network access blocked in tests: {address[0]}")


def _install_network_guard() -> None:
    """Refuse every non-loopback connection (sync sockets, DNS and the Windows proactor)."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def connect(self, address):
        _check_target(address)
        return real_connect(self, address)

    def connect_ex(self, address):
        _check_target(address)
        return real_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        if not _is_loopback(host):
            _record(f"dns:{host}")
            raise socket.gaierror(socket.EAI_NONAME, f"network access blocked in tests: {host}")
        return real_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo
    if sys.platform == "win32":
        from asyncio import windows_events

        real_proactor_connect = windows_events.IocpProactor.connect

        def proactor_connect(self, conn, address):
            _check_target(address)
            return real_proactor_connect(self, conn, address)

        windows_events.IocpProactor.connect = proactor_connect


_install_network_guard()


@pytest.fixture(autouse=True)
def _network_guard_test_id(request):
    _current_test["id"] = request.node.nodeid
    yield
    _current_test["id"] = ""


def pytest_terminal_summary(terminalreporter):
    if BLOCKED_CONNECTIONS:
        terminalreporter.section("network guard")
        seen = sorted(set(BLOCKED_CONNECTIONS))
        terminalreporter.write_line(f"{len(seen)} non-loopback connection attempt(s) refused:")
        for test_id, target in seen[:200]:
            terminalreporter.write_line(f"  {test_id or '<collection>'} -> {target}")
