"""
Tests for Event Log, SOUL, and Mission Engine.
"""

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
from realize_core.missions.engine import MissionEngine
from realize_core.missions.state import Mission, MissionState, MissionStep, StepStatus
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
        path.write_text(
            yaml.dump(
                {
                    "name": "Antonio",
                    "role": "Tech Lead",
                    "home_runtime": "claude-code-cli",
                }
            )
        )

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
        log.query(category="mission")
        # The engine's event log is separate from this log instance
        # But the engine's own log should have the events
        assert engine._event_log.count(category="mission") >= 1


# ─── Codex audit F11: approval events hold the mission ──────────────────────


class _HoldingRuntime:
    """A contract-conforming runtime: step s1 requests an approval, then ends 'success'."""

    runtime_id = "fake"

    def __init__(self):
        self.invocations: list[str] = []

    async def invoke(self, step, context):
        from realize_core.runtimes.events import ApprovalRequestEvent, FinalResultEvent

        self.invocations.append(step.step_id)
        if step.step_id == "s1":
            yield ApprovalRequestEvent(run_id="r", category="tool", proposed_action={"request_id": "apv-1"})
        yield FinalResultEvent(run_id="r", output={"text": f"{step.step_id} done"}, status="success")


class TestMissionApprovalHold:
    @pytest.fixture
    def setup(self, tmp_path):
        from types import SimpleNamespace

        registry = RuntimeRegistry()
        runtime = _HoldingRuntime()
        registry._runtimes["fake"] = SimpleNamespace(
            runtime=runtime, status="ready", invocation_count=0, last_used=None, total_cost_eur=0.0
        )
        engine = MissionEngine(registry=registry, event_log=EventLog(tmp_path / "events.jsonl"))
        mission = engine.create_mission(title="Pay and report", goal="g", venture="acme")
        engine.plan_mission(
            mission.mission_id,
            steps=[
                {"description": "Pay the contractor", "runtime": "fake"},
                {"description": "Report the payment", "runtime": "fake", "inputs_from": ["s1"]},
            ],
        )
        return engine, runtime, mission.mission_id

    @pytest.mark.asyncio
    async def test_held_step_holds_the_mission_and_its_dependants(self, setup):
        engine, runtime, mission_id = setup

        mission = await engine.execute_mission(mission_id)

        assert mission.state == MissionState.AWAITING_APPROVAL
        assert mission.plan[0].status == StepStatus.AWAITING_APPROVAL
        assert mission.plan[1].status == StepStatus.PENDING
        assert runtime.invocations == ["s1"]

    @pytest.mark.asyncio
    async def test_approval_continues_from_the_actual_outcome(self, setup):
        import asyncio

        from realize_core.missions import engine as engine_mod

        engine, runtime, mission_id = setup
        await engine.execute_mission(mission_id)

        assert await engine_mod.on_approval_decided("apv-1", True, {"success": True, "output": "paid"})
        await asyncio.gather(*engine_mod._continuations)

        mission = engine._get_mission(mission_id)
        assert mission.state == MissionState.COMPLETED
        assert mission.plan[0].output["approved_output"] == "paid"
        assert runtime.invocations == ["s1", "s2"]

    @pytest.mark.asyncio
    async def test_rejection_fails_the_step_and_blocks_dependants(self, setup):
        from realize_core.missions import engine as engine_mod

        engine, runtime, mission_id = setup
        await engine.execute_mission(mission_id)

        import asyncio

        await engine_mod.on_approval_decided("apv-1", False)
        await asyncio.gather(*engine_mod._continuations)

        mission = engine._get_mission(mission_id)
        assert mission.state == MissionState.FAILED
        assert "blocked" in mission.outcome_summary
        assert mission.plan[0].status == StepStatus.FAILED
        assert mission.plan[1].status == StepStatus.PENDING
        assert runtime.invocations == ["s1"]


# ─── Codex audit F16: plans are validated before anything is stored ─────────


class TestPlanValidation:
    @pytest.mark.parametrize(
        ("steps", "message"),
        [
            ([], "at least one step"),
            ([{"runtime": "internal"}], "needs a description"),
            ([{"description": "a", "step_id": "x"}, {"description": "b", "step_id": "x"}], "used twice"),
            ([{"description": "a", "inputs_from": ["nope"]}], "unknown step"),
            (
                [
                    {"description": "a", "step_id": "a", "inputs_from": ["b"]},
                    {"description": "b", "step_id": "b", "inputs_from": ["a"]},
                ],
                "cycle",
            ),
            ([{"description": "a", "inputs_from": ["s1"]}], "cycle"),
        ],
    )
    def test_bad_plans_are_refused(self, steps, message):
        from realize_core.missions.engine import validate_plan

        with pytest.raises(ValueError, match=message):
            validate_plan(steps)

    def test_oversized_plans_are_refused_quickly(self):
        """Security review: a huge plan can't make validation slow."""
        import time

        from realize_core.missions.engine import MAX_PLAN_STEPS, validate_plan

        huge = [{"description": "x"} for _ in range(50_000)]
        started = time.perf_counter()
        with pytest.raises(ValueError, match="at most"):
            validate_plan(huge)
        with pytest.raises(ValueError, match="at most"):
            validate_plan([{"description": "x", "inputs_from": ["s1"] * 10_000}])
        assert time.perf_counter() - started < 1.0

        # A long chain at the limit is fine and checked in linear time.
        chain = [{"description": "x"}] + [
            {"description": "x", "inputs_from": [f"s{i}"]} for i in range(1, MAX_PLAN_STEPS)
        ]
        assert validate_plan(chain) is chain

    def test_valid_plan_passes(self):
        from realize_core.missions.engine import validate_plan

        steps = [{"description": "a"}, {"description": "b", "inputs_from": ["s1"]}]
        assert validate_plan(steps) is steps

    def test_failed_plan_leaves_the_mission_unchanged(self, tmp_path):
        engine = MissionEngine(registry=RuntimeRegistry(), event_log=EventLog(tmp_path / "e.jsonl"))
        mission = engine.create_mission(title="T", goal="g")

        with pytest.raises(ValueError):
            engine.plan_mission(mission.mission_id, [{"runtime": "internal"}])

        assert mission.state == MissionState.PROPOSED
        assert mission.plan == []

    def test_rest_create_with_a_bad_plan_is_400_and_creates_nothing(self, tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from realize_api.routes import missions

        app = FastAPI()
        app.include_router(missions.router, prefix="/api")
        app.state.mission_engine = MissionEngine(
            registry=RuntimeRegistry(), event_log=EventLog(tmp_path / "events.jsonl")
        )
        client = TestClient(app)

        res = client.post("/api/missions", json={"title": "T", "goal": "g", "steps": [{"runtime": "internal"}]})

        assert res.status_code == 400
        assert client.get("/api/missions").json()["count"] == 0
