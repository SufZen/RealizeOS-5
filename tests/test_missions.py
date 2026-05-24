"""
Tests for Event Log, SOUL, and Mission Engine.
"""

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from realize_core.fabric.event_log import EventLog
from realize_core.fabric.event_types import (
    Event,
    EventCategory,
    dream_event,
    knowledge_event,
    message_event,
    mission_event,
    runtime_event,
)
from realize_core.fabric.soul import AgentSoul, UserSoul
from realize_core.missions.state import Mission, MissionState, MissionStep, StepStatus
from realize_core.missions.engine import MissionEngine
from realize_core.runtimes.registry import RuntimeRegistry


# ─── Event Types ──────────────────────────────────────────────────────────────

class TestEventTypes:
    def test_basic_event(self):
        event = Event(category="message", action="message.inbound", actor="user-asaf")
        assert event.event_id  # Auto-generated
        assert event.timestamp  # Auto-generated
        assert event.category == "message"

    def test_event_serialization(self):
        event = Event(
            category="mission",
            action="mission.created",
            actor="system",
            venture="test-biz",
            payload={"title": "Test Mission"},
        )
        d = event.to_dict()
        assert d["category"] == "mission"
        assert d["payload"]["title"] == "Test Mission"

        # Round-trip
        event2 = Event.from_dict(d)
        assert event2.category == event.category
        assert event2.payload == event.payload

    def test_message_event(self):
        event = message_event(
            actor="user-asaf",
            venture="test-biz",
            text="Hello agent!",
            agent="maria",
        )
        assert event.category == EventCategory.MESSAGE
        assert event.payload["text"] == "Hello agent!"

    def test_mission_event(self):
        event = mission_event(
            mission_id="m-2026-05-20-test-001",
            action="created",
            venture="test-biz",
        )
        assert event.category == EventCategory.MISSION
        assert event.mission_id == "m-2026-05-20-test-001"

    def test_knowledge_event(self):
        event = knowledge_event(
            entity_id="dec-2026-05-pricing-001",
            action="created",
            actor="user-asaf",
        )
        assert event.category == EventCategory.KNOWLEDGE

    def test_dream_event(self):
        event = dream_event(action="proposal", cycle_type="curator")
        assert event.category == EventCategory.DREAMING

    def test_runtime_event(self):
        event = runtime_event(runtime_id="claude-code-cli", action="registered")
        assert event.category == EventCategory.RUNTIME


# ─── Event Log ────────────────────────────────────────────────────────────────

class TestEventLog:
    def test_append_and_query(self, tmp_path):
        log = EventLog(tmp_path / "events.jsonl")

        log.append(message_event(actor="user-asaf", text="Hello"))
        log.append(message_event(actor="agent-maria", text="Hi!", direction="outbound"))
        log.append(mission_event(mission_id="m-001", action="created", venture="biz"))

        events = log.query()
        assert len(events) == 3

    def test_query_by_category(self, tmp_path):
        log = EventLog(tmp_path / "events.jsonl")
        log.append(message_event(actor="user-asaf", text="Hello"))
        log.append(mission_event(mission_id="m-001", action="created"))

        messages = log.query(category="message")
        assert len(messages) == 1
        assert messages[0].category == "message"

    def test_query_by_venture(self, tmp_path):
        log = EventLog(tmp_path / "events.jsonl")
        log.append(message_event(actor="user-asaf", venture="biz-a", text="Hello"))
        log.append(message_event(actor="user-asaf", venture="biz-b", text="World"))

        results = log.query(venture="biz-a")
        assert len(results) == 1

    def test_tail(self, tmp_path):
        log = EventLog(tmp_path / "events.jsonl")
        for i in range(25):
            log.append(message_event(actor="user", text=f"msg-{i}"))

        tail = log.tail(n=5)
        assert len(tail) == 5

    def test_count(self, tmp_path):
        log = EventLog(tmp_path / "events.jsonl")
        log.append(message_event(actor="user", text="a"))
        log.append(message_event(actor="user", text="b"))
        log.append(mission_event(mission_id="m-1", action="x"))

        assert log.count() == 3
        assert log.count(category="message") == 2

    def test_empty_log(self, tmp_path):
        log = EventLog(tmp_path / "events.jsonl")
        assert log.query() == []
        assert log.tail() == []
        assert log.count() == 0


# ─── SOUL ─────────────────────────────────────────────────────────────────────

class TestUserSoul:
    def test_load_save_roundtrip(self, tmp_path):
        path = tmp_path / "user-soul.yaml"

        soul = UserSoul(
            locale="pt-PT",
            languages=["he", "en", "pt"],
            working_hours="09:00-19:00 Europe/Lisbon",
            timezone="Europe/Lisbon",
            voice="formal-but-warm",
            default_runtime_preferences={"code": "claude-code-cli"},
            constraints=["Never auto-send messages without approval"],
        )
        soul.save(path)

        loaded = UserSoul.load(path)
        assert loaded.locale == "pt-PT"
        assert loaded.languages == ["he", "en", "pt"]
        assert loaded.voice == "formal-but-warm"
        assert loaded.constraints[0] == "Never auto-send messages without approval"

    def test_missing_file_defaults(self, tmp_path):
        soul = UserSoul.load(tmp_path / "nonexistent.yaml")
        assert soul.locale == "en"

    def test_to_context(self):
        soul = UserSoul(locale="pt-PT", languages=["en", "pt"])
        ctx = soul.to_context()
        assert ctx["locale"] == "pt-PT"
        assert "languages" in ctx


class TestAgentSoul:
    def test_from_config(self):
        config = {
            "name": "Maria",
            "role": "Sales Agent",
            "personality": "Friendly and professional",
            "expertise": ["real-estate", "negotiation"],
            "home_runtime": "internal",
            "capabilities": ["writing.business"],
        }
        soul = AgentSoul.from_config(config)
        assert soul.name == "Maria"
        assert soul.role == "Sales Agent"
        assert "real-estate" in soul.expertise

    def test_load_from_yaml(self, tmp_path):
        import yaml
        path = tmp_path / "agent.yaml"
        path.write_text(yaml.dump({
            "name": "Antonio",
            "role": "Tech Lead",
            "home_runtime": "claude-code-cli",
        }))

        soul = AgentSoul.load(path)
        assert soul.name == "Antonio"
        assert soul.home_runtime == "claude-code-cli"


# ─── Mission State ────────────────────────────────────────────────────────────

class TestMissionState:
    def test_valid_transitions(self):
        mission = Mission(mission_id="m-001", title="Test", goal="Do something")
        assert mission.state == MissionState.PROPOSED

        assert mission.transition(MissionState.PLANNED) is True
        assert mission.state == MissionState.PLANNED

        assert mission.transition(MissionState.IN_PROGRESS) is True
        assert mission.started_at is not None

        assert mission.transition(MissionState.COMPLETED) is True
        assert mission.completed_at is not None

    def test_invalid_transition(self):
        mission = Mission(mission_id="m-001", title="Test", goal="Do something")
        # Can't go directly from PROPOSED to IN_PROGRESS
        assert mission.transition(MissionState.IN_PROGRESS) is False

    def test_terminal_states(self):
        mission = Mission(mission_id="m-001", title="Test", goal="Do something")
        mission.transition(MissionState.PLANNED)
        mission.transition(MissionState.IN_PROGRESS)
        mission.transition(MissionState.COMPLETED)

        # Can't transition from COMPLETED
        assert mission.transition(MissionState.IN_PROGRESS) is False

    def test_progress_tracking(self):
        mission = Mission(
            mission_id="m-001",
            title="Test",
            goal="Do something",
            plan=[
                MissionStep(step_id="s1", description="Step 1", status=StepStatus.SUCCEEDED),
                MissionStep(step_id="s2", description="Step 2", status=StepStatus.PENDING),
            ],
        )
        assert mission.progress == 0.5

    def test_next_step(self):
        mission = Mission(
            mission_id="m-001",
            title="Test",
            goal="Do something",
            plan=[
                MissionStep(step_id="s1", description="Step 1", status=StepStatus.SUCCEEDED),
                MissionStep(step_id="s2", description="Step 2", status=StepStatus.PENDING),
                MissionStep(step_id="s3", description="Step 3", status=StepStatus.PENDING, inputs_from=["s2"]),
            ],
        )
        # s2 is next (no unresolved deps); s3 depends on s2
        assert mission.next_step.step_id == "s2"

    def test_budget_check(self):
        mission = Mission(
            mission_id="m-001",
            title="Test",
            goal="Do something",
            budget_eur=5.0,
            cost_consumed_eur=6.0,
        )
        assert mission.is_over_budget

    def test_serialization(self):
        mission = Mission(
            mission_id="m-001",
            title="Test",
            goal="Do something",
            venture="test-biz",
        )
        d = mission.to_dict()
        assert d["mission_id"] == "m-001"
        assert d["state"] == "proposed"
        assert d["progress"] == 0.0


# ─── Mission Engine ──────────────────────────────────────────────────────────

class TestMissionEngine:
    @pytest.fixture
    def engine(self, tmp_path):
        registry = RuntimeRegistry()
        event_log = EventLog(tmp_path / "events.jsonl")
        return MissionEngine(registry=registry, event_log=event_log)

    def test_create_mission(self, engine):
        mission = engine.create_mission(
            title="Find Properties",
            goal="Find 3 distressed properties in Setúbal",
            venture="burtucala",
            owner="user-asaf",
            budget_eur=5.0,
        )
        assert mission.mission_id.startswith("m-")
        assert mission.state == MissionState.PROPOSED
        assert mission.budget_eur == 5.0

    def test_plan_mission(self, engine):
        mission = engine.create_mission(
            title="Test Mission",
            goal="Do a multi-step task",
        )

        planned = engine.plan_mission(
            mission.mission_id,
            steps=[
                {"description": "Search for data", "runtime": "internal"},
                {"description": "Analyze results", "runtime": "internal", "inputs_from": ["s1"]},
                {"description": "Write report", "runtime": "internal", "inputs_from": ["s2"]},
            ],
        )

        assert planned.state == MissionState.PLANNED
        assert len(planned.plan) == 3
        assert planned.plan[1].inputs_from == ["s1"]

    def test_list_missions(self, engine):
        engine.create_mission(title="M1", goal="Goal 1", venture="biz-a")
        engine.create_mission(title="M2", goal="Goal 2", venture="biz-b")
        engine.create_mission(title="M3", goal="Goal 3", venture="biz-a")

        all_missions = engine.list_missions()
        assert len(all_missions) == 3

        biz_a = engine.list_missions(venture="biz-a")
        assert len(biz_a) == 2

    def test_cancel_mission(self, engine):
        mission = engine.create_mission(title="Cancel Me", goal="To be cancelled")
        cancelled = engine.cancel_mission(mission.mission_id)
        assert cancelled.state == MissionState.CANCELLED

    def test_event_log_integration(self, engine, tmp_path):
        engine.create_mission(title="Logged Mission", goal="With events")

        log = EventLog(tmp_path / "events.jsonl")
        events = log.query(category="mission")
        # The engine's event log is separate from this log instance
        # But the engine's own log should have the events
        assert engine._event_log.count(category="mission") >= 1
