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


# ─── Codex audit N05: configured directories, durable writes, visible outcome ──


@pytest.fixture
def configured(tmp_path, monkeypatch) -> Path:
    """realize-os.yaml maps venture key ``acme`` to ``systems/acme-office`` (and ``rogue`` outside systems/)."""
    config = tmp_path / "realize-os.yaml"
    config.write_text(
        "systems:\n"
        "  - key: acme\n    name: Acme\n    directory: systems/acme-office\n"
        "  - key: rogue\n    name: Rogue\n    directory: shared\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REALIZE_CONFIG", str(config))
    return tmp_path


def _approval(venture: str, note: str = "ok") -> str:
    from realize_core.governance.gates import create_approval_request

    return create_approval_request(
        venture, "site_payments", "tool_call", {"summary": note}, params={"basis": [{"source": "a.pdf"}]}
    )


def _decide(approval_id: str, approve: bool = True, note: str | None = None) -> dict:
    from realize_core.governance.gates import decide_approval

    return asyncio.run(decide_approval(approval_id, approve, note, decided_by="asaf", channel="dashboard"))


def _intent(db, approval_id: str) -> dict:
    conn = decision_log._connect(db)
    try:
        row = conn.execute("SELECT * FROM decision_writes WHERE approval_id = ?", (approval_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def _decision_files(venture_dir: Path) -> list[Path]:
    folder = venture_dir / "B-brain" / "decisions"
    return sorted(folder.iterdir()) if folder.is_dir() else []


def test_configured_directory_that_differs_from_the_key(db, kb, configured):
    from realize_core.scheduler.reports import generate_weekly_review

    office = kb / "systems" / "acme-office"
    office.mkdir(parents=True)
    approval_id = _approval("acme")

    out = _decide(approval_id, True, "pay it")

    assert out["decision_log"]["logged"] is True
    assert out["decision_log"]["error"] is None
    [d] = list_decisions(office)
    assert d["approval_id"] == approval_id
    assert d["id"] == out["decision_log"]["decision_id"]
    assert not (kb / "systems" / "acme").exists()
    assert _intent(db, approval_id)["status"] == "done"
    # The weekly review reads the same configured folder.
    text = asyncio.run(generate_weekly_review({"acme": {}}, kb))
    assert "**acme**: 1 decisions recorded" in text


def test_configured_directory_outside_systems_is_refused(db, kb, configured):
    (kb / "shared").mkdir()

    out = _decide(_approval("rogue"))

    assert out["approval"]["status"] == "approved"
    assert out["decision_log"]["logged"] is False
    assert "outside systems/ or ventures/" in out["decision_log"]["error"]
    assert not (kb / "shared" / "B-brain").exists()
    assert record_approval_decision(out["approval"], True) is None


def test_unavailable_disk_queues_the_write_and_a_retry_writes_it_once(db, kb, monkeypatch):
    from realize_core.governance.decision_log import retry_pending_decisions

    real_replace = decision_log.os.replace

    def disk_full(src, dst):
        raise OSError(28, "No space left on device", str(dst))

    monkeypatch.setattr(decision_log.os, "replace", disk_full)
    approval_id = _approval("tower-b", "Pay claim 3")

    out = _decide(approval_id, False, "Line 4 is not in the contract")

    # The decision itself stands; the log write is queued and the result says so.
    assert out["approval"]["status"] == "rejected"
    assert out["decision_log"] == {
        "logged": False,
        "pending": True,
        "error": "No space left on device",
        "decision_id": None,
    }
    assert _decision_files(_venture(kb)) == []  # no partial entry, no temp file left behind
    intent = _intent(db, approval_id)
    assert (intent["status"], intent["attempts"]) == ("pending", 1)
    assert "No space left on device" in intent["last_error"]

    monkeypatch.setattr(decision_log.os, "replace", real_replace)  # the disk is back
    assert retry_pending_decisions() == {"logged": 1, "pending": 0}
    assert retry_pending_decisions() == {"logged": 0, "pending": 0}

    [d] = list_decisions(_venture(kb))
    assert d["approval_id"] == approval_id
    assert d["outcome"] == "rejected"
    assert "Line 4 is not in the contract" in d["_body"]
    assert d["date"] == out["approval"]["decided_at"][:10]  # dated when it was decided, not when retried
    assert len(_decision_files(_venture(kb))) == 1
    assert _intent(db, approval_id)["status"] == "done"


class _Crash(BaseException):
    """The process stops (not an error anything catches)."""


def _row_status(approval_id: str) -> str:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        return conn.execute("SELECT status FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()["status"]
    finally:
        conn.close()


def test_crash_between_decision_and_intent_still_logs_once(db, kb, monkeypatch):
    """The decision commits, then the process dies before the log write is queued (review G-4)."""
    from realize_core.governance.decision_log import retry_pending_decisions

    def crash(*args, **kwargs):
        raise _Crash

    real_queue = decision_log._queue
    monkeypatch.setattr(decision_log, "_queue", crash)
    approval_id = _approval("tower-b", "Pay claim 4")
    with pytest.raises(_Crash):
        _decide(approval_id, True, "pay it")
    assert _decision_files(_venture(kb)) == []

    # Restart: the decision stands, its intent was stored with it, and the retry writes it once.
    monkeypatch.setattr(decision_log, "_queue", real_queue)
    assert _row_status(approval_id) == "approved"
    assert _intent(db, approval_id)["status"] == "pending"
    assert retry_pending_decisions()["logged"] == 1
    assert retry_pending_decisions()["logged"] == 0
    [d] = list_decisions(_venture(kb))
    assert (d["approval_id"], d["outcome"]) == (approval_id, "approved")
    assert len(_decision_files(_venture(kb))) == 1


def test_next_decision_retries_a_pending_write(db, kb, monkeypatch):
    real_replace = decision_log.os.replace

    def read_only(src, dst):
        raise PermissionError(13, "Permission denied", str(dst))

    monkeypatch.setattr(decision_log.os, "replace", read_only)
    first = _approval("tower-b", "first")
    assert _decide(first)["decision_log"]["pending"] is True

    monkeypatch.setattr(decision_log.os, "replace", real_replace)
    second = _approval("tower-b", "second")
    assert _decide(second)["decision_log"]["logged"] is True

    assert sorted(d["approval_id"] for d in list_decisions(_venture(kb))) == sorted([first, second])
    assert _intent(db, first)["status"] == "done"


def test_missing_venture_folder_is_retried_once_it_exists(db, kb):
    from realize_core.governance.decision_log import retry_pending_decisions

    out = _decide(_approval("new-site"))
    assert out["decision_log"]["pending"] is True
    assert "no folder" in out["decision_log"]["error"]

    (kb / "systems" / "new-site").mkdir()
    assert retry_pending_decisions()["logged"] == 1
    assert len(list_decisions(kb / "systems" / "new-site")) == 1


def test_automatic_retries_stop_after_repeated_failures(db, kb):
    from realize_core.governance.decision_log import MAX_AUTO_ATTEMPTS, pending_decisions, retry_pending_decisions

    approval_id = _approval("gone")
    _decide(approval_id)
    for _ in range(MAX_AUTO_ATTEMPTS + 2):
        retry_pending_decisions()
    assert _intent(db, approval_id)["attempts"] == MAX_AUTO_ATTEMPTS
    # Still pending, and still tried when the owner asks.
    assert [i["approval_id"] for i in pending_decisions()] == [approval_id]
    retry_pending_decisions(max_attempts=None)
    assert _intent(db, approval_id)["attempts"] == MAX_AUTO_ATTEMPTS + 1


def test_inputs_are_not_queued(db, kb):
    from realize_core.governance.decision_log import log_decision

    out = log_decision({"id": "q-1", "venture_key": "tower-b", "action_type": "skill_input"}, True)
    assert out == {"logged": False, "pending": False, "error": None, "decision_id": None}
    assert _intent(db, "q-1") == {}


def test_rest_and_mcp_report_the_decision_log_outcome(db, kb):
    from realize_api.routes.approvals import _flatten
    from realize_core.mcp_server.tools.ops_tools import _decision_summary

    out = _decide(_approval("tower-b"))

    flat = _flatten(out)
    assert flat["status"] == "approved"  # the historical shape is kept
    assert flat["decision_log"]["logged"] is True
    summary = _decision_summary(out)
    assert (summary["decision_logged"], summary["decision_log_pending"]) == (True, False)


def test_cli_retry_reports_what_is_still_waiting(db, kb):
    from realize_core.cli_app import app
    from typer.testing import CliRunner

    approval_id = _approval("later-site")
    _decide(approval_id)

    runner = CliRunner()
    waiting = runner.invoke(app, ["decisions", "retry"])
    assert waiting.exit_code == 1
    assert "Recorded 0 decision(s); 1 still waiting" in waiting.output
    assert approval_id in waiting.output

    (kb / "systems" / "later-site").mkdir()
    done = runner.invoke(app, ["decisions", "retry"])
    assert done.exit_code == 0
    assert "Recorded 1 decision(s); 0 still waiting" in done.output


def test_migration_013_creates_the_write_queue(tmp_path):
    import sqlite3

    from realize_core.db.migrations import run_migrations
    from realize_core.db.schema import init_schema
    from realize_core.migration.engine import MigrationEngine

    path = tmp_path / "fresh.db"
    init_schema(path)
    run_migrations(path)
    MigrationEngine(db_path=path).migrate_up()

    conn = sqlite3.connect(path)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'index')")}
    finally:
        conn.close()
    assert {"decision_writes", "idx_decision_writes_status"} <= names
