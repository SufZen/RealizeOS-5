"""Decision log v0 (STORY-44): approvals become decision entities; agents propose, people confirm."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from realize_core.governance import decision_log
from realize_core.governance.decision_log import (
    DECISION_LOG_ACTION,
    export_markdown,
    list_decisions,
    propose_decision,
    record_approval_decision,
    weekly_counts,
)


@pytest.fixture
def db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


@pytest.fixture
def kb(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "kb"
    (root / "systems" / "tower-b").mkdir(parents=True)
    monkeypatch.setattr(decision_log, "_kb_path", lambda kb_path=None: Path(kb_path) if kb_path else root)
    return root


def _venture(kb: Path) -> Path:
    return kb / "systems" / "tower-b"


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text[3 : text.find("\n---", 3)])


def test_approved_action_becomes_one_decision(db, kb):
    from realize_core.governance.gates import create_approval_request, decide_approval

    approval_id = create_approval_request(
        "tower-b",
        "site_payments",
        "tool_call",
        {"summary": "Pay claim 3"},
        action_name="sheets_append",
        params={"basis": [{"source": "claim-3.pdf", "locator": "p.2"}], "project": "tower-b", "kind": "payment"},
    )
    asyncio.run(
        decide_approval(approval_id, False, "Line 4 is not in the contract", decided_by="asaf", channel="dashboard")
    )
    decisions = list_decisions(_venture(kb))
    assert len(decisions) == 1
    d = decisions[0]
    assert d["approval_id"] == approval_id
    assert d["outcome"] == "rejected"
    assert d["decided_by"] == "asaf"
    assert d["channel"] == "dashboard"
    assert d["verified"] is True
    assert d["basis"] == [{"source": "claim-3.pdf", "locator": "p.2"}]
    assert "Line 4 is not in the contract" in d["_body"]


def test_recording_is_idempotent(db, kb):
    record = {
        "id": "abc-123",
        "venture_key": "tower-b",
        "action_type": "tool_call",
        "action_name": "gmail_send",
        "decided_by": "asaf",
    }
    first = record_approval_decision(record, True)
    second = record_approval_decision(record, True)
    assert first == second
    assert len(list_decisions(_venture(kb))) == 1


def test_inputs_and_credentials_are_not_decisions(db, kb):
    for action_type in ("skill_input", "agent_credential", "agent_input"):
        record = {"id": f"x-{action_type}", "venture_key": "tower-b", "action_type": action_type}
        assert record_approval_decision(record, True) is None
    assert list_decisions(_venture(kb)) == []


def test_unknown_venture_is_skipped(db, kb):
    assert record_approval_decision({"id": "1", "venture_key": "nope", "action_type": "tool_call"}, True) is None


def test_proposed_decision_is_recorded_only_after_approval(db, kb):
    from realize_core.governance.gates import decide_approval, get_pending_approvals

    approval_id = propose_decision(
        "tower-b",
        title="Switch façade supplier",
        statement="Agreed in the site meeting to move to supplier B for the façade.",
        basis=[{"source": "whatsapp:site-group", "locator": "2026-10-12 17:42"}],
        project="tower-b",
        requested_by="agent-claude",
    )
    pending = get_pending_approvals("tower-b")
    assert any(p["id"] == approval_id and p["action_type"] == DECISION_LOG_ACTION for p in pending)
    assert list_decisions(_venture(kb)) == []

    asyncio.run(decide_approval(approval_id, True, decided_by="asaf"))
    decisions = list_decisions(_venture(kb))
    assert len(decisions) == 1
    assert decisions[0]["title"] == "Switch façade supplier"
    assert decisions[0]["created_by"] == "agent-claude"
    assert decisions[0]["verified"] is True


def test_rejected_proposal_records_nothing(db, kb):
    from realize_core.governance.gates import decide_approval

    approval_id = propose_decision("tower-b", title="t", statement="s", requested_by="agent")
    asyncio.run(decide_approval(approval_id, False, decided_by="asaf"))
    assert list_decisions(_venture(kb)) == []


def test_decision_without_located_source_is_flagged(db, kb):
    from realize_core.governance.gates import decide_approval

    approval_id = propose_decision(
        "tower-b", title="Verbal OK", statement="Told on the phone", basis=[{"source": "phone call"}]
    )
    asyncio.run(decide_approval(approval_id, True, decided_by="asaf"))
    d = list_decisions(_venture(kb))[0]
    assert d["verified"] is False
    assert weekly_counts(_venture(kb)) == {"recorded": 1, "without_source": 1}


def test_export_in_three_languages(db, kb):
    record_approval_decision(
        {
            "id": "e1",
            "venture_key": "tower-b",
            "action_type": "tool_call",
            "action_name": "drive_upload",
            "decided_by": "asaf",
        },
        True,
    )
    assert export_markdown(_venture(kb), language="he").startswith("# יומן החלטות")
    assert export_markdown(_venture(kb), language="pt").startswith("# Registo de decisões")
    en = export_markdown(_venture(kb))
    assert "Approved: drive_upload" in en
    assert "No source" in en


def test_weekly_review_has_a_decisions_line(db, kb):
    from realize_core.scheduler.reports import generate_weekly_review

    record_approval_decision(
        {"id": "w1", "venture_key": "tower-b", "action_type": "tool_call", "decided_by": "asaf"}, True
    )
    text = asyncio.run(generate_weekly_review({"tower-b": {}}, kb))
    assert "## Decisions" in text
    assert "1 decisions recorded, 1 without a source" in text


def test_mcp_log_decision_queues_for_approval(db, kb):
    from realize_core.governance.gates import get_pending_approvals
    from realize_core.mcp_server.tools.decision_tools import log_decision

    state = SimpleNamespace(systems={"tower-b": {}})
    user = SimpleNamespace(user_id="partner")
    out = asyncio.run(
        log_decision({"venture_key": "tower-b", "title": "Hold retention", "statement": "Keep 5%"}, state, user)
    )
    assert out["status"] == "pending_approval"
    assert out["unverified"] is True
    assert any(p["id"] == out["approval_id"] for p in get_pending_approvals("tower-b"))
    missing = asyncio.run(log_decision({"venture_key": "x", "title": "t", "statement": "s"}, state, user))
    assert missing["code"] == "MCP_NOT_FOUND"


def test_log_decision_is_registered_and_guarded():
    from realize_core.mcp_server import registry, venture_guard

    registry.reset_for_tests()
    tool = registry.get_registry().get("log_decision")
    assert (tool.family, tool.scope) == ("ops", "editor")
    assert "log_decision" in venture_guard.NEEDS_VENTURE
    assert venture_guard.TOOL_PERMISSIONS["log_decision"] == "agents:execute"
