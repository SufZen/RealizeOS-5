"""MCP get_history returns each answer's trail, like REST history (#48 provenance included)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from realize_api.dependencies import CurrentUser


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    from realize_core.memory.conversation import clear_all
    from realize_core.memory.store import init_db

    monkeypatch.setattr("realize_core.memory.store.DB_PATH", tmp_path / "memory.db")
    init_db()
    clear_all()
    yield
    clear_all()


RULE_SOURCE = {
    "id": "R1",
    "title": "Price revision",
    "path": "packs/market/pt/rules/price-revision.md",
    "layer": "market",
    "pack": "pt@0.1.0",
    "verification": 1,
    "as_of": "2026-10-13",
    "review_by": "2027-04-13",
}


@pytest.mark.asyncio
async def test_get_history_returns_each_answers_trail_with_provenance(memory_db):
    from realize_core.mcp_server.tools.chat_tools import get_history
    from realize_core.memory.conversation import add_message, save_trail

    add_message("acme", "dana@acme.io", "user", "Is price revision allowed?")
    answer = add_message("acme", "dana@acme.io", "assistant", "Yes [R1].")
    save_trail(
        answer,
        {
            "sources": [RULE_SOURCE, {"id": "S1", "title": "Contract", "path": "B-brain/contract.md"}],
            "steps": [
                {"type": "tool_call", "name": "sheets_read", "input": {"spreadsheet_id": "secret-sheet"}},
                {"type": "tool_result", "name": "sheets_read", "success": True, "output": "salary rows"},
                {"type": "approval_requested", "name": "sheets_append", "request_id": "apr-1"},
            ],
        },
    )
    dana = CurrentUser(user_id="dana@acme.io", role="operator")

    out = await get_history({"system_key": "acme", "user_id": "dana@acme.io"}, app_state=None, user=dana)

    question, reply = out["messages"]
    assert "trail" not in question
    trail = reply["trail"]
    assert trail["sources"][0] == RULE_SOURCE  # the #48 provenance fields come back
    assert trail["sources"][1] == {"id": "S1", "title": "Contract", "path": "B-brain/contract.md"}
    assert trail["steps"] == [
        {"type": "tool_call", "name": "sheets_read"},
        {"type": "tool_result", "name": "sheets_read", "success": True, "held": None},
        {"type": "approval_requested", "name": "sheets_append", "request_id": "apr-1"},
    ]
    # Tool inputs and outputs are not echoed to MCP clients, as in realize_chat.
    assert "secret-sheet" not in json.dumps(out)
    assert "salary rows" not in json.dumps(out)


@pytest.mark.asyncio
async def test_get_history_stays_scoped_to_the_caller(memory_db):
    from realize_core.mcp_server.tools.chat_tools import get_history
    from realize_core.memory.conversation import add_message, save_trail

    answer = add_message("acme", "boss@acme.io", "assistant", "Payroll is 80k [R1]")
    save_trail(answer, {"sources": [RULE_SOURCE], "steps": []})
    dana = CurrentUser(user_id="dana@acme.io", role="operator")

    out = await get_history({"system_key": "acme", "user_id": "boss@acme.io"}, app_state=None, user=dana)

    assert out["code"] == "MCP_FORBIDDEN"
    assert "Payroll" not in json.dumps(out)
    assert "pt@0.1.0" not in json.dumps(out)


@pytest.mark.asyncio
async def test_get_history_matches_rest_history_for_sources(memory_db):
    """REST and MCP return the same sources; MCP leaves out tool inputs/outputs only."""
    from realize_api.routes.chat import get_conversations
    from realize_core.mcp_server.tools.chat_tools import get_history
    from realize_core.memory.conversation import add_message, save_trail

    answer = add_message("acme", "dana@acme.io", "assistant", "Yes [R1].")
    save_trail(answer, {"sources": [RULE_SOURCE], "steps": [{"type": "tool_call", "name": "kb_search"}]})
    request = SimpleNamespace(state=SimpleNamespace(user_id="dana@acme.io", role="operator", scopes=[]))

    rest = await get_conversations("acme", "dana@acme.io", request)
    mcp = await get_history(
        {"system_key": "acme", "user_id": "dana@acme.io"},
        app_state=None,
        user=CurrentUser(user_id="dana@acme.io", role="operator"),
    )

    assert mcp["messages"][0]["trail"]["sources"] == rest["messages"][0]["trail"]["sources"]
    assert mcp["messages"][0]["trail"]["steps"] == rest["messages"][0]["trail"]["steps"]
