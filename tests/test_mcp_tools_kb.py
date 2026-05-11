"""Tests for the MCP knowledge-base tool family (Story 3).

Covers:

* Registry — KB tools appear under the ``kb`` family and are gated by
  ``mcp.expose_kb``.
* Validation — empty queries, oversized queries, path traversal.
* Search — wraps :func:`realize_core.kb.indexer.semantic_search` with
  snippet truncation.
* Document fetch — enforces path containment under ``app.state.kb_path``.
* Ventures listing — uses ``app.state.systems`` directly.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from realize_api.dependencies import CurrentUser

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_registry():
    from realize_core.mcp_server import registry as registry_mod

    registry_mod.reset_for_tests()
    yield registry_mod.get_registry()
    registry_mod.reset_for_tests()


def _user(role: str = "owner") -> CurrentUser:
    return CurrentUser(user_id="test-user", role=role)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestKBRegistry:
    def test_kb_family_registered(self, fresh_registry):
        names = {t.name for t in fresh_registry.all()}
        assert {"kb_search", "venture_kb_search", "kb_get_document", "list_ventures"} <= names

    def test_kb_family_hidden_when_expose_kb_false(self, fresh_registry):
        from realize_core.mcp_server.config import McpConfig

        cfg = McpConfig(
            enabled=True,
            expose_kb=False,
            expose_ops=False,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        visible_names = {t.name for t in fresh_registry.visible_tools(cfg)}
        assert "kb_search" not in visible_names
        assert "realize_chat" in visible_names  # chat family is always on

    def test_kb_family_visible_when_expose_kb_true(self, fresh_registry):
        from realize_core.mcp_server.config import McpConfig

        cfg = McpConfig(
            enabled=True,
            expose_kb=True,
            expose_ops=False,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        visible_names = {t.name for t in fresh_registry.visible_tools(cfg)}
        assert "kb_search" in visible_names
        assert "kb_get_document" in visible_names


# ---------------------------------------------------------------------------
# kb_search
# ---------------------------------------------------------------------------


class TestKBSearch:
    @pytest.mark.asyncio
    async def test_empty_query_rejected(self):
        from realize_core.mcp_server.tools.kb_tools import kb_search

        result = await kb_search({"query": "   "}, SimpleNamespace(), _user())
        assert result["code"] == "MCP_VALIDATION"

    @pytest.mark.asyncio
    async def test_oversized_query_rejected(self):
        from realize_core.mcp_server.tools.kb_tools import MAX_QUERY_CHARS, kb_search

        result = await kb_search({"query": "x" * (MAX_QUERY_CHARS + 1)}, SimpleNamespace(), _user())
        assert result["code"] == "MCP_VALIDATION"

    @pytest.mark.asyncio
    async def test_search_calls_semantic_search_and_truncates(self):
        from realize_core.mcp_server.tools.kb_tools import MAX_SNIPPET_CHARS, kb_search

        long_snippet = "X" * (MAX_SNIPPET_CHARS + 100)
        fake_results = [
            {
                "path": "shared/identity.md",
                "title": "Identity",
                "system_key": "realization-il",
                "snippet": long_snippet,
                "score": 0.91,
            }
        ]
        with patch(
            "realize_core.kb.indexer.semantic_search",
            return_value=fake_results,
        ) as mock:
            result = await kb_search(
                {"query": "identity", "top_k": 5, "system_key": "realization-il"},
                SimpleNamespace(),
                _user(),
            )

        mock.assert_called_once()
        kwargs = mock.call_args.kwargs
        assert kwargs["query"] == "identity"
        assert kwargs["system_key"] == "realization-il"
        assert kwargs["top_k"] == 5
        assert result["results"][0]["snippet"].endswith("…")
        assert len(result["results"][0]["snippet"]) <= MAX_SNIPPET_CHARS + 1

    @pytest.mark.asyncio
    async def test_top_k_clamped(self):
        from realize_core.mcp_server.tools.kb_tools import MAX_TOP_K, kb_search

        with patch("realize_core.kb.indexer.semantic_search", return_value=[]) as mock:
            await kb_search({"query": "x", "top_k": 9999}, SimpleNamespace(), _user())
        assert mock.call_args.kwargs["top_k"] == MAX_TOP_K

    @pytest.mark.asyncio
    async def test_search_internal_error_is_structured(self):
        from realize_core.mcp_server.tools.kb_tools import kb_search

        with patch(
            "realize_core.kb.indexer.semantic_search",
            side_effect=RuntimeError("index corrupt"),
        ):
            result = await kb_search({"query": "x"}, SimpleNamespace(), _user())
        assert result["code"] == "MCP_INTERNAL"
        assert "index corrupt" in result["error"]


# ---------------------------------------------------------------------------
# venture_kb_search
# ---------------------------------------------------------------------------


class TestVentureKBSearch:
    @pytest.mark.asyncio
    async def test_unknown_venture_returns_not_found_with_available(self):
        from realize_core.mcp_server.tools.kb_tools import venture_kb_search

        state = SimpleNamespace(systems={"arena": {}, "realization-il": {}})
        result = await venture_kb_search({"venture_key": "no-such", "query": "x"}, state, _user())
        assert result["code"] == "MCP_NOT_FOUND"
        assert set(result["available"]) == {"arena", "realization-il"}

    @pytest.mark.asyncio
    async def test_scopes_to_venture(self):
        from realize_core.mcp_server.tools.kb_tools import venture_kb_search

        state = SimpleNamespace(systems={"arena": {}})
        with patch("realize_core.kb.indexer.semantic_search", return_value=[]) as mock:
            await venture_kb_search({"venture_key": "arena", "query": "pipeline"}, state, _user())
        assert mock.call_args.kwargs["system_key"] == "arena"


# ---------------------------------------------------------------------------
# kb_get_document
# ---------------------------------------------------------------------------


class TestKBGetDocument:
    @pytest.mark.asyncio
    async def test_reads_existing_file(self, tmp_path):
        from realize_core.mcp_server.tools.kb_tools import kb_get_document

        target = tmp_path / "shared" / "identity.md"
        target.parent.mkdir(parents=True)
        target.write_text("hello world", encoding="utf-8")
        state = SimpleNamespace(kb_path=tmp_path)

        result = await kb_get_document({"path": "shared/identity.md"}, state, _user())
        assert result["content"] == "hello world"
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_path_traversal_rejected(self, tmp_path):
        from realize_core.mcp_server.tools.kb_tools import kb_get_document

        state = SimpleNamespace(kb_path=tmp_path)
        result = await kb_get_document({"path": "../etc/passwd"}, state, _user())
        assert result["code"] == "MCP_VALIDATION"

    @pytest.mark.asyncio
    async def test_resolved_outside_kb_rejected(self, tmp_path):
        from realize_core.mcp_server.tools.kb_tools import kb_get_document

        # Symlink-ish escape via absolute path
        state = SimpleNamespace(kb_path=tmp_path)
        outside = tmp_path.parent / "outside.md"
        outside.write_text("secret", encoding="utf-8")

        result = await kb_get_document({"path": str(outside)}, state, _user())
        # An absolute path with "../" or that resolves outside the KB
        # must be blocked. Our validator catches the absolute path via
        # the resolve-relative-to check.
        assert result["code"] in {"MCP_FORBIDDEN", "MCP_VALIDATION", "MCP_NOT_FOUND"}

    @pytest.mark.asyncio
    async def test_missing_file_returns_not_found(self, tmp_path):
        from realize_core.mcp_server.tools.kb_tools import kb_get_document

        state = SimpleNamespace(kb_path=tmp_path)
        result = await kb_get_document({"path": "missing.md"}, state, _user())
        assert result["code"] == "MCP_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_max_chars_truncates(self, tmp_path):
        from realize_core.mcp_server.tools.kb_tools import kb_get_document

        target = tmp_path / "big.md"
        target.write_text("A" * 1000, encoding="utf-8")
        state = SimpleNamespace(kb_path=tmp_path)

        result = await kb_get_document({"path": "big.md", "max_chars": 100}, state, _user())
        assert result["truncated"] is True
        assert len(result["content"]) == 100


# ---------------------------------------------------------------------------
# list_ventures
# ---------------------------------------------------------------------------


class TestListVentures:
    @pytest.mark.asyncio
    async def test_returns_venture_inventory(self, tmp_path):
        from realize_core.mcp_server.tools.kb_tools import list_ventures

        state = SimpleNamespace(
            systems={
                "arena": {"name": "Arena", "description": "VC fund", "agents": {"writer": "writer.md"}},
                "realization-il": {"name": "Realization IL", "agents": {}},
            },
            kb_path=tmp_path,
        )
        result = await list_ventures({}, state, _user())
        keys = {v["key"] for v in result["ventures"]}
        assert keys == {"arena", "realization-il"}
        arena = next(v for v in result["ventures"] if v["key"] == "arena")
        assert arena["agent_count"] == 1
        assert arena["name"] == "Arena"

    @pytest.mark.asyncio
    async def test_empty_systems_returns_empty_list(self):
        from realize_core.mcp_server.tools.kb_tools import list_ventures

        state = SimpleNamespace(systems={}, kb_path=None)
        result = await list_ventures({}, state, _user())
        assert result == {"ventures": []}


# ---------------------------------------------------------------------------
# Integration via dispatcher
# ---------------------------------------------------------------------------


class TestDispatchKB:
    @pytest.mark.asyncio
    async def test_list_ventures_via_dispatcher(self, fresh_registry):
        from realize_core.mcp_server.config import McpConfig
        from realize_core.mcp_server.server import _dispatch

        cfg = McpConfig(
            enabled=True,
            expose_kb=True,
            expose_ops=False,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        state = SimpleNamespace(systems={"arena": {"name": "Arena", "agents": {}}})
        out = await _dispatch(fresh_registry, cfg, state, "list_ventures", {})
        body = json.loads(out[0].text)
        assert body["ventures"][0]["key"] == "arena"

    @pytest.mark.asyncio
    async def test_kb_search_blocked_when_family_disabled(self, fresh_registry):
        from realize_core.mcp_server.config import McpConfig
        from realize_core.mcp_server.server import _dispatch

        cfg = McpConfig(
            enabled=True,
            expose_kb=False,
            expose_ops=False,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        out = await _dispatch(fresh_registry, cfg, SimpleNamespace(), "kb_search", {"query": "x"})
        body = json.loads(out[0].text)
        assert body["code"] == "MCP_TOOL_DISABLED"
