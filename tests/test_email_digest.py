"""Tests for the Email Dream-Inbox Digest channel."""

from __future__ import annotations

from datetime import datetime

import pytest
from realize_core.channels.email import (
    EmailDigestChannel,
    build_dream_digest,
    send_dream_digest,
)
from realize_core.dreaming.inbox import DreamInbox
from realize_core.dreaming.policy import DreamProposal, ProposalStatus


def _proposal(
    proposal_id: str,
    venture: str,
    *,
    action: str = "update_summary",
    cycle_type: str = "curator",
    title: str = "Some proposal",
    confidence: float = 0.9,
) -> DreamProposal:
    return DreamProposal(
        proposal_id=proposal_id,
        cycle_type=cycle_type,
        action=action,
        venture=venture,
        title=title,
        confidence=confidence,
        created_at=datetime(2026, 6, 13, 8, 0, 0),
        status=ProposalStatus.PENDING,
    )


# ===========================================================================
# build_dream_digest — grouping, attention section, links
# ===========================================================================


class TestBuildDreamDigest:
    def test_empty_returns_none(self):
        assert build_dream_digest([]) is None

    def test_groups_by_venture(self):
        proposals = [
            _proposal("dream-a", "alpha", title="Alpha one"),
            _proposal("dream-b", "beta", title="Beta one"),
            _proposal("dream-c", "alpha", title="Alpha two"),
        ]
        text = build_dream_digest(proposals)
        assert text is not None
        # Both ventures appear as headers, sorted.
        assert "## alpha (2)" in text
        assert "## beta (1)" in text
        assert text.index("## alpha") < text.index("## beta")
        # Each item's title appears.
        for t in ("Alpha one", "Alpha two", "Beta one"):
            assert t in text

    def test_includes_cycle_action_confidence_and_date(self):
        proposals = [
            _proposal(
                "dream-x",
                "alpha",
                action="create_insight",
                cycle_type="synthesis",
                confidence=0.83,
            )
        ]
        text = build_dream_digest(proposals)
        assert "[synthesis]" in text
        assert "create_insight" in text
        assert "83%" in text
        assert "2026-06-13" in text

    def test_approve_reject_links(self):
        proposals = [_proposal("dream-link", "alpha")]
        text = build_dream_digest(proposals, base_url="https://app.example.com")
        assert "https://app.example.com/api/dreams/dream-link/approve" in text
        assert "https://app.example.com/api/dreams/dream-link/reject" in text

    def test_low_confidence_in_attention_section(self):
        low = _proposal("dream-low", "alpha", title="Risky", confidence=0.3)
        high = _proposal("dream-high", "alpha", title="Safe", confidence=0.95)
        text = build_dream_digest([high, low])
        assert "NEEDS YOUR ATTENTION" in text
        attention_block = text.split("=== ALL PENDING")[0]
        assert "Risky" in attention_block
        assert "Safe" not in attention_block

    def test_high_impact_action_in_attention_section(self):
        # High confidence but high-impact action must still be flagged.
        impactful = _proposal(
            "dream-del",
            "alpha",
            action="delete_entity",
            title="Delete X",
            confidence=0.99,
        )
        text = build_dream_digest([impactful])
        attention_block = text.split("=== ALL PENDING")[0]
        assert "Delete X" in attention_block

    def test_top_k_cap_with_more_line(self):
        proposals = [_proposal(f"dream-{i}", "alpha", title=f"Item {i}") for i in range(15)]
        text = build_dream_digest(proposals, top_k_per_venture=10)
        assert "+5 more" in text


# ===========================================================================
# send_dream_digest — suppression, send, failure resilience
# ===========================================================================


def _make_inbox(tmp_path, proposals):
    inbox = DreamInbox(inbox_path=tmp_path / "inbox.jsonl")
    for p in proposals:
        # Force PENDING regardless of trust policy so pending() returns them.
        inbox._proposals[p.proposal_id] = p
    return inbox


class _FakeEventLog:
    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)
        return "evt"


class TestSendDreamDigestSuppression:
    @pytest.mark.asyncio
    async def test_suppress_when_empty_returns_false_and_no_send(self, tmp_path, monkeypatch):
        called = {"count": 0}

        async def fake_gmail_send(**kwargs):
            called["count"] += 1
            return {"status": "sent"}

        monkeypatch.setattr(
            "realize_core.tools.google_workspace.gmail_send",
            fake_gmail_send,
        )

        inbox = _make_inbox(tmp_path, [])
        event_log = _FakeEventLog()

        result = await send_dream_digest(inbox, recipient="a@b.com", event_log=event_log)

        assert result is False
        assert called["count"] == 0  # gmail_send NOT called
        assert any(e.action == "dreaming.digest_suppressed" for e in event_log.events)

    @pytest.mark.asyncio
    async def test_sends_when_pending_returns_true(self, tmp_path, monkeypatch):
        sent = {}

        async def fake_gmail_send(*, to, subject, body):
            sent.update(to=to, subject=subject, body=body)
            return {"status": "sent"}

        monkeypatch.setattr(
            "realize_core.tools.google_workspace.gmail_send",
            fake_gmail_send,
        )

        inbox = _make_inbox(tmp_path, [_proposal("dream-1", "alpha", title="Hello")])
        event_log = _FakeEventLog()

        result = await send_dream_digest(inbox, recipient="ops@example.com", event_log=event_log)

        assert result is True
        assert sent["to"] == "ops@example.com"
        assert "Hello" in sent["body"]
        assert any(e.action == "dreaming.digest_sent" for e in event_log.events)


class TestSendDreamDigestResilience:
    @pytest.mark.asyncio
    async def test_send_failure_returns_false_without_raising(self, tmp_path, monkeypatch):
        async def boom_gmail_send(**kwargs):
            raise RuntimeError("Gmail is down")

        monkeypatch.setattr(
            "realize_core.tools.google_workspace.gmail_send",
            boom_gmail_send,
        )

        inbox = _make_inbox(tmp_path, [_proposal("dream-1", "alpha")])
        event_log = _FakeEventLog()

        # Must not raise.
        result = await send_dream_digest(inbox, recipient="ops@example.com", event_log=event_log)

        assert result is False
        assert any(e.action == "dreaming.digest_failed" for e in event_log.events)


# ===========================================================================
# EmailDigestChannel — contract
# ===========================================================================


class TestEmailDigestChannel:
    def test_channel_name_and_init(self):
        ch = EmailDigestChannel(recipient="a@b.com", base_url="https://x.test/")
        assert ch.channel_name == "email"
        assert ch.recipient == "a@b.com"
        assert ch.base_url == "https://x.test"  # trailing slash stripped

    @pytest.mark.asyncio
    async def test_start_stop_are_noops(self):
        ch = EmailDigestChannel(recipient="a@b.com")
        assert await ch.start() is None
        assert await ch.stop() is None

    @pytest.mark.asyncio
    async def test_send_message_uses_metadata_subject(self, monkeypatch):
        from realize_core.channels.base import OutgoingMessage

        captured = {}

        async def fake_gmail_send(*, to, subject, body):
            captured.update(to=to, subject=subject, body=body)
            return {"status": "sent"}

        monkeypatch.setattr(
            "realize_core.tools.google_workspace.gmail_send",
            fake_gmail_send,
        )

        ch = EmailDigestChannel(recipient="a@b.com")
        msg = OutgoingMessage(text="body text", user_id="u1", metadata={"subject": "Custom"})
        await ch.send_message(msg)

        assert captured["subject"] == "Custom"
        assert captured["body"] == "body text"

    @pytest.mark.asyncio
    async def test_send_message_never_raises_on_failure(self, monkeypatch):
        from realize_core.channels.base import OutgoingMessage

        async def boom(**kwargs):
            raise RuntimeError("nope")

        monkeypatch.setattr("realize_core.tools.google_workspace.gmail_send", boom)

        ch = EmailDigestChannel(recipient="a@b.com")
        # Should swallow the exception.
        await ch.send_message(OutgoingMessage(text="x", user_id="u1"))
