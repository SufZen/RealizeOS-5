"""Shared test fixtures for RealizeOS test suite."""

import pytest


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
