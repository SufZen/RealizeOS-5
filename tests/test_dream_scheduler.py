"""Tests for the unified wall-clock Dream scheduler.

Hermetic: no real time waiting. We construct the scheduler and introspect the
registered jobs' CronTrigger fields (hour, day_of_week, timezone) rather than
letting any job fire.
"""

from __future__ import annotations

import pytest

pytest.importorskip("apscheduler")

from realize_core.dreaming.scheduler import (
    CURATOR_JOB_ID,
    DIGEST_JOB_ID,
    build_dream_scheduler,
    make_curator_trigger,
    make_digest_trigger,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeInbox:
    """Minimal stand-in for DreamInbox — only attributes the builder touches."""

    _policy = None

    def submit_batch(self, _proposals):  # pragma: no cover - never invoked here
        return None


def _field_expr(trigger, name: str) -> str:
    """Return the string form of a CronTrigger field (e.g. '8', 'mon-fri')."""
    for field in trigger.fields:
        if field.name == name:
            return str(field)
    raise AssertionError(f"field {name!r} not found on trigger")


async def _noop():  # pragma: no cover - never invoked
    return None


# ---------------------------------------------------------------------------
# Trigger field construction
# ---------------------------------------------------------------------------


class TestTriggers:
    def test_digest_trigger_defaults(self):
        trigger = make_digest_trigger({})
        assert _field_expr(trigger, "hour") == "8"
        assert _field_expr(trigger, "minute") == "0"
        assert "mon-fri" in _field_expr(trigger, "day_of_week")
        assert str(trigger.timezone) == "Europe/Lisbon"

    def test_digest_trigger_every_day_when_workdays_false(self):
        trigger = make_digest_trigger({"workdays_only": False, "hour": 9})
        assert _field_expr(trigger, "hour") == "9"
        # mon-sun == every day; APScheduler may normalize to '*' or '0-6'
        dow = _field_expr(trigger, "day_of_week")
        assert dow in ("*", "0-6", "mon-sun")

    def test_curator_trigger_defaults(self):
        trigger = make_curator_trigger({})
        assert _field_expr(trigger, "hour") == "3"
        assert str(trigger.timezone) == "Europe/Lisbon"


# ---------------------------------------------------------------------------
# build_dream_scheduler — registration gated on flags
# ---------------------------------------------------------------------------


class TestBuildScheduler:
    def test_both_flags_on_registers_two_jobs(self):
        config = {
            "features": {"email_digest": True, "dreaming_curator": True},
            "email_digest": {"recipient": "info@realization.co.il", "hour": 8},
            "dreaming": {"hour": 3},
        }
        scheduler = build_dream_scheduler(
            config,
            dream_inbox=_FakeInbox(),
            synapse=object(),
            systems={"alpha": {}, "beta": {}},
            digest_callback=_noop,
            curator_callback=_noop,
        )
        assert scheduler is not None
        jobs = {job.id: job for job in scheduler.get_jobs()}
        assert set(jobs) == {DIGEST_JOB_ID, CURATOR_JOB_ID}

        digest = jobs[DIGEST_JOB_ID].trigger
        assert _field_expr(digest, "hour") == "8"
        assert "mon-fri" in _field_expr(digest, "day_of_week")
        assert str(digest.timezone) == "Europe/Lisbon"

        curator = jobs[CURATOR_JOB_ID].trigger
        assert _field_expr(curator, "hour") == "3"
        assert str(curator.timezone) == "Europe/Lisbon"

    def test_all_flags_off_returns_none(self):
        config = {"features": {"email_digest": False, "dreaming_curator": False}}
        scheduler = build_dream_scheduler(
            config,
            dream_inbox=_FakeInbox(),
            synapse=object(),
            systems={},
        )
        assert scheduler is None

    def test_digest_only(self):
        config = {
            "features": {"email_digest": True, "dreaming_curator": False},
            "email_digest": {"recipient": "x@example.com"},
        }
        scheduler = build_dream_scheduler(
            config,
            dream_inbox=_FakeInbox(),
            synapse=object(),
            systems={},
            digest_callback=_noop,
        )
        assert scheduler is not None
        assert [job.id for job in scheduler.get_jobs()] == [DIGEST_JOB_ID]

    def test_digest_without_recipient_not_registered(self):
        config = {
            "features": {"email_digest": True, "dreaming_curator": False},
            "email_digest": {"recipient": "  "},
        }
        scheduler = build_dream_scheduler(
            config,
            dream_inbox=_FakeInbox(),
            synapse=object(),
            systems={},
            digest_callback=_noop,
        )
        # No recipient → no digest job → nothing registered → None.
        assert scheduler is None

    def test_curator_only(self):
        config = {
            "features": {"email_digest": False, "dreaming_curator": True},
            "dreaming": {"hour": 5, "timezone": "UTC"},
        }
        scheduler = build_dream_scheduler(
            config,
            dream_inbox=_FakeInbox(),
            synapse=object(),
            systems={"alpha": {}},
            curator_callback=_noop,
        )
        assert scheduler is not None
        jobs = [job.id for job in scheduler.get_jobs()]
        assert jobs == [CURATOR_JOB_ID]
        trigger = scheduler.get_jobs()[0].trigger
        assert _field_expr(trigger, "hour") == "5"
        assert str(trigger.timezone) == "UTC"
