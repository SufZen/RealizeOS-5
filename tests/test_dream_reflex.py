"""Tests for the scheduled Reflex Dreaming job.

Hermetic: no real time waiting. We construct the scheduler and introspect the
registered job's IntervalTrigger, and we invoke the Reflex callback directly
with injected fakes (a fake synapse exposing ``touched_since`` and a fake inbox
capturing ``submit_batch``).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

pytest.importorskip("apscheduler")

from realize_core.dreaming.scheduler import (
    REFLEX_JOB_ID,
    REFLEX_MAX_ENTITIES,
    build_dream_scheduler,
    make_reflex_trigger,
)
from realize_core.fabric.entity import FabricEntity

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


class _FakeInbox:
    """Captures submit_batch calls; mirrors the attributes the builder touches."""

    _policy = None

    def __init__(self):
        self.batches = []

    def submit_batch(self, proposals, policy=None):
        self.batches.append(list(proposals))
        return [getattr(p, "proposal_id", "") for p in proposals]


class _FakeSynapse:
    """Fake synapse exposing ``touched_since`` returning a fixed entity list."""

    def __init__(self, entities):
        self._entities = list(entities)
        self.calls = []

    def touched_since(self, since, scope=None):
        self.calls.append((since, scope))
        return list(self._entities)


def _entity(i: int) -> FabricEntity:
    """A FABRIC entity whose body trips the Reflex tag/ref heuristics."""
    return FabricEntity(
        id=f"dec-{i:03d}",
        type="decision",
        title=f"Decision {i}",
        venture="alpha",
        body="This covers our pricing strategy and budget for the launch.",
        last_modified_at=datetime.now(),
    )


async def _noop():  # pragma: no cover - never invoked
    return None


# ---------------------------------------------------------------------------
# Trigger construction
# ---------------------------------------------------------------------------


class TestReflexTrigger:
    def test_default_interval_is_60_minutes(self):
        trigger = make_reflex_trigger({})
        assert trigger.interval == timedelta(minutes=60)

    def test_custom_interval(self):
        trigger = make_reflex_trigger({"reflex_interval_minutes": 15})
        assert trigger.interval == timedelta(minutes=15)


# ---------------------------------------------------------------------------
# Registration gated on the flag
# ---------------------------------------------------------------------------


class TestReflexRegistration:
    def test_flag_on_registers_reflex_job_with_interval(self):
        config = {
            "features": {"dreaming_reflex": True},
            "dreaming": {"reflex_interval_minutes": 30},
        }
        scheduler = build_dream_scheduler(
            config,
            dream_inbox=_FakeInbox(),
            synapse=object(),
            systems={"alpha": {}},
            reflex_callback=_noop,
        )
        assert scheduler is not None
        jobs = {job.id: job for job in scheduler.get_jobs()}
        assert REFLEX_JOB_ID in jobs
        assert jobs[REFLEX_JOB_ID].trigger.interval == timedelta(minutes=30)

    def test_flag_off_does_not_register_reflex(self):
        config = {"features": {"dreaming_reflex": False}}
        scheduler = build_dream_scheduler(
            config,
            dream_inbox=_FakeInbox(),
            synapse=object(),
            systems={"alpha": {}},
        )
        # No other flags either → nothing registered → None.
        assert scheduler is None

    def test_flag_on_but_no_synapse_skips_reflex(self):
        config = {"features": {"dreaming_reflex": True}}
        scheduler = build_dream_scheduler(
            config,
            dream_inbox=_FakeInbox(),
            synapse=None,
            systems={"alpha": {}},
        )
        assert scheduler is None


# ---------------------------------------------------------------------------
# Callback behavior — built by the production path, exercised with fakes
# ---------------------------------------------------------------------------


def _build_reflex_callback(*, synapse, inbox, systems):
    """Register the real (production) reflex callback and return it."""
    config = {
        "features": {"dreaming_reflex": True},
        "dreaming": {"reflex_interval_minutes": 60},
    }
    scheduler = build_dream_scheduler(
        config,
        dream_inbox=inbox,
        synapse=synapse,
        systems=systems,
    )
    assert scheduler is not None
    job = {j.id: j for j in scheduler.get_jobs()}[REFLEX_JOB_ID]
    return job.func


class TestReflexCallback:
    def test_callback_submits_proposals_for_changed_entities(self):
        synapse = _FakeSynapse([_entity(1), _entity(2)])
        inbox = _FakeInbox()
        callback = _build_reflex_callback(synapse=synapse, inbox=inbox, systems={"alpha": {}})

        asyncio.run(callback())

        # touched_since was used (preferred over the scan fallback).
        assert synapse.calls
        _, scope = synapse.calls[0]
        assert scope == "alpha"
        # Proposals were submitted (both entities trip the tag heuristic).
        assert inbox.batches, "expected at least one submit_batch call"
        flat = [p for batch in inbox.batches for p in batch]
        assert flat, "expected proposals to be submitted"

    def test_callback_caps_entities_per_run(self):
        # More than the cap; each entity yields >=1 proposal.
        many = [_entity(i) for i in range(REFLEX_MAX_ENTITIES + 50)]
        synapse = _FakeSynapse(many)
        inbox = _FakeInbox()
        callback = _build_reflex_callback(synapse=synapse, inbox=inbox, systems={"alpha": {}})

        asyncio.run(callback())

        # The pass analyzes at most REFLEX_MAX_ENTITIES distinct entities, even
        # though each may yield several proposals. Assert on distinct entity ids.
        flat = [p for batch in inbox.batches for p in batch]
        distinct_entities = {p.entity_id for p in flat}
        assert len(distinct_entities) <= REFLEX_MAX_ENTITIES

    def test_callback_never_raises_when_synapse_errors(self):
        class _Boom:
            def touched_since(self, *a, **k):
                raise RuntimeError("boom")

        inbox = _FakeInbox()
        callback = _build_reflex_callback(synapse=_Boom(), inbox=inbox, systems={"alpha": {}})

        # Per-venture guard must swallow the error.
        asyncio.run(callback())
        assert inbox.batches == []
