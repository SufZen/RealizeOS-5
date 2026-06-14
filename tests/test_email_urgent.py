"""
Tests for immediate "urgent" email alerts (spec 003 US2).

Two surfaces are covered:

1. :func:`realize_core.channels.email.send_urgent_alert` — sends immediately via
   the lazily-imported ``gmail_send``, returns ``True`` on success, ``False`` on
   an empty recipient (no send) or a Gmail failure (no raise).

2. :func:`realize_core.dreaming.apply.apply_approved` — when ``urgent_recipient``
   is set, a ``blocked`` outcome (a hard-denied action that was nonetheless
   marked approved) triggers exactly one urgent alert; with ``urgent_recipient``
   empty, no alert is sent.

Hermetic: gmail is always monkeypatched; the apply tests reuse the temp-git
venture pattern from ``tests/test_dream_apply.py``.
"""

from __future__ import annotations

import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest
from realize_core.dreaming.apply import apply_approved
from realize_core.dreaming.inbox import DreamInbox
from realize_core.dreaming.policy import DreamProposal, ProposalStatus, TrustPolicy

# ── Git venture helpers (mirrors tests/test_dream_apply.py) ───────────────────


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), capture_output=True, check=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def _write_entity(repo: Path, layer: str, slug: str, entity_id: str, entity_type: str = "insight") -> Path:
    layer_dir = repo / layer
    layer_dir.mkdir(parents=True, exist_ok=True)
    path = layer_dir / f"{slug}.md"
    fm = [
        "---",
        f"id: {entity_id}",
        f"type: {entity_type}",
        f"title: {slug.replace('-', ' ').title()}",
        f"slug: {slug}",
        "---",
    ]
    path.write_text("\n".join(fm) + "\n\nBody.\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", f"seed {entity_id}")
    return path


def _make_inbox(tmp_path: Path) -> DreamInbox:
    return DreamInbox(inbox_path=tmp_path / "inbox.jsonl", policy=TrustPolicy())


def _seed_approved(inbox: DreamInbox, proposal: DreamProposal) -> DreamProposal:
    """Inject an already-APPROVED proposal directly into the inbox."""
    proposal.status = ProposalStatus.APPROVED
    proposal.reviewed_at = datetime.now()
    proposal.reviewed_by = "test"
    inbox._proposals[proposal.proposal_id] = proposal
    inbox._save()
    return proposal


def _install_fake_gmail(monkeypatch: pytest.MonkeyPatch, calls: list, *, raises: bool = False) -> None:
    """Install a fake ``realize_core.tools.google_workspace`` module with gmail_send."""

    async def fake_gmail_send(to: str, subject: str, body: str) -> None:
        calls.append({"to": to, "subject": subject, "body": body})
        if raises:
            raise RuntimeError("gmail boom")

    mod = types.ModuleType("realize_core.tools.google_workspace")
    mod.gmail_send = fake_gmail_send  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "realize_core.tools.google_workspace", mod)


# ── send_urgent_alert ─────────────────────────────────────────────────────────


def test_send_urgent_alert_sends_and_returns_true(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from realize_core.channels.email import send_urgent_alert

    calls: list = []
    _install_fake_gmail(monkeypatch, calls)

    ok = asyncio.run(send_urgent_alert(recipient="ops@example.com", subject="SUBJ", body="BODY"))

    assert ok is True
    assert len(calls) == 1
    assert calls[0] == {"to": "ops@example.com", "subject": "SUBJ", "body": "BODY"}


def test_send_urgent_alert_empty_recipient_no_send(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from realize_core.channels.email import send_urgent_alert

    calls: list = []
    _install_fake_gmail(monkeypatch, calls)

    ok = asyncio.run(send_urgent_alert(recipient="", subject="SUBJ", body="BODY"))

    assert ok is False
    assert calls == []  # no send attempted


def test_send_urgent_alert_gmail_failure_returns_false_no_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from realize_core.channels.email import send_urgent_alert

    calls: list = []
    _install_fake_gmail(monkeypatch, calls, raises=True)

    # Must not raise.
    ok = asyncio.run(send_urgent_alert(recipient="ops@example.com", subject="S", body="B"))

    assert ok is False
    assert len(calls) == 1  # send was attempted, but failed


# ── apply_approved → urgent alert on blocked ──────────────────────────────────


def _seed_blocked_proposal(inbox: DreamInbox) -> DreamProposal:
    """An approved proposal whose action is hard-denied → blocked at apply time."""
    return _seed_approved(
        inbox,
        DreamProposal(
            cycle_type="curator",
            action="delete_entity",  # on HARD_DENY_ACTIONS
            entity_id="ins-099",
            entity_type="insight",
            venture="venture-a",
            title="Forbidden delete",
            diff={"add_tags": ["x"]},
        ),
    )


def test_blocked_triggers_exactly_one_urgent_alert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "venture-a"
    _init_repo(repo)
    _write_entity(repo, "I-insights", "thing", "ins-099")

    inbox = _make_inbox(tmp_path)
    _seed_blocked_proposal(inbox)

    # Monkeypatch send_urgent_alert at its definition site so the lazy import in
    # apply._send_block_alert picks up the patched callable.
    sent: list = []

    async def fake_send_urgent_alert(recipient, subject, body, event_log=None):
        sent.append({"recipient": recipient, "subject": subject, "body": body})
        return True

    import realize_core.channels.email as email_mod

    monkeypatch.setattr(email_mod, "send_urgent_alert", fake_send_urgent_alert)

    results = apply_approved(inbox, {"venture-a": repo}, urgent_recipient="ops@example.com")

    assert len(results) == 1
    assert results[0].outcome == "blocked"
    assert len(sent) == 1  # exactly one urgent alert
    assert sent[0]["recipient"] == "ops@example.com"
    assert "delete_entity" in sent[0]["subject"]
    assert results[0].proposal_id in sent[0]["body"]


def test_blocked_no_alert_when_recipient_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "venture-a"
    _init_repo(repo)
    _write_entity(repo, "I-insights", "thing", "ins-099")

    inbox = _make_inbox(tmp_path)
    _seed_blocked_proposal(inbox)

    sent: list = []

    async def fake_send_urgent_alert(recipient, subject, body, event_log=None):
        sent.append(recipient)
        return True

    import realize_core.channels.email as email_mod

    monkeypatch.setattr(email_mod, "send_urgent_alert", fake_send_urgent_alert)

    # Default urgent_recipient="" → no alert.
    results = apply_approved(inbox, {"venture-a": repo})

    assert results[0].outcome == "blocked"
    assert sent == []  # no alert sent when recipient empty


def test_blocked_dry_run_does_not_alert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "venture-a"
    _init_repo(repo)
    _write_entity(repo, "I-insights", "thing", "ins-099")

    inbox = _make_inbox(tmp_path)
    _seed_blocked_proposal(inbox)

    sent: list = []

    async def fake_send_urgent_alert(recipient, subject, body, event_log=None):
        sent.append(recipient)
        return True

    import realize_core.channels.email as email_mod

    monkeypatch.setattr(email_mod, "send_urgent_alert", fake_send_urgent_alert)

    results = apply_approved(inbox, {"venture-a": repo}, dry_run=True, urgent_recipient="ops@example.com")

    assert results[0].outcome == "blocked"
    assert sent == []  # dry-run never alerts
