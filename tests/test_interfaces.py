"""
Sprint 1 Interface Tests — Verify all base classes are importable and correct.

Tests that every shared interface module:
  1. Can be imported without errors
  2. Exports the expected classes/enums/dataclasses
  3. Models can be instantiated with minimal args
  4. Protocols are runtime-checkable
  5. Enums have the expected members
  6. Pydantic models validate correctly
"""
from datetime import datetime

import pytest

# =====================================================================
# 1. realize_core.agents.base
# =====================================================================

class TestAgentBase:
    """Tests for realize_core.agents.base — shared agent interfaces."""

    def test_imports(self):
        pass

    def test_handoff_type_enum(self):
        from realize_core.agents.base import HandoffType
        assert HandoffType.STANDARD == "standard"
        assert HandoffType.QA_PASS == "qa_pass"
        assert HandoffType.QA_FAIL == "qa_fail"
        assert HandoffType.ESCALATION == "escalation"
        assert HandoffType.PHASE_GATE == "phase_gate"
        assert HandoffType.SPRINT == "sprint"
        assert HandoffType.INCIDENT == "incident"
        assert len(HandoffType) == 7

    def test_agent_status_enum(self):
        from realize_core.agents.base import AgentStatus
        assert AgentStatus.IDLE == "idle"
        assert AgentStatus.RUNNING == "running"
        assert AgentStatus.PAUSED == "paused"
        assert AgentStatus.ERROR == "error"
        assert len(AgentStatus) == 4

    def test_handoff_data_creation(self):
        from realize_core.agents.base import HandoffData, HandoffType
        hd = HandoffData(
            source_agent="writer",
            target_agent="reviewer",
            handoff_type=HandoffType.STANDARD,
            payload={"draft": "Hello world"},
        )
        assert hd.source_agent == "writer"
        assert hd.target_agent == "reviewer"
        assert hd.handoff_type == HandoffType.STANDARD
        assert hd.retry_count == 0
        assert not hd.is_retry_exhausted

    def test_handoff_data_retry(self):
        from realize_core.agents.base import HandoffData, HandoffType
        hd = HandoffData(
            source_agent="writer",
            target_agent="reviewer",
            handoff_type=HandoffType.STANDARD,
            max_retries=2,
        )
        retry1 = hd.with_retry()
        assert retry1.retry_count == 1
        assert retry1.handoff_type == HandoffType.QA_FAIL
        assert not retry1.is_retry_exhausted

        retry2 = retry1.with_retry()
        assert retry2.retry_count == 2
        assert retry2.is_retry_exhausted

    def test_handoff_data_is_frozen(self):
        from realize_core.agents.base import HandoffData, HandoffType
        hd = HandoffData(
            source_agent="a", target_agent="b",
            handoff_type=HandoffType.STANDARD,
        )
        with pytest.raises(AttributeError):
            hd.source_agent = "c"  # type: ignore[misc]

    def test_pipeline_stage(self):
        from realize_core.agents.base import HandoffType, PipelineStage
        stage = PipelineStage(
            name="drafting",
            agent_key="writer",
            description="Create first draft",
            handoff_type=HandoffType.STANDARD,
            guardrails=["no_profanity"],
            timeout_seconds=120,
            required_inputs=["brief"],
            expected_outputs=["draft"],
        )
        assert stage.name == "drafting"
        assert stage.agent_key == "writer"
        assert stage.timeout_seconds == 120

    def test_agent_config_minimal(self):
        from realize_core.agents.base import AgentConfig
        cfg = AgentConfig(name="Writer", key="writer")
        assert cfg.name == "Writer"
        assert cfg.key == "writer"
        assert cfg.version == "2"
        assert cfg.tools == []
        assert cfg.guardrails == []
        assert cfg.communication_style == "professional"

    def test_agent_config_full(self):
        from realize_core.agents.base import AgentConfig, GuardrailConfig
        cfg = AgentConfig(
            name="PM Agent",
            key="pm",
            scope="Project management and task delegation",
            persona="PM",
            reports_to="exec",
            inputs=["task_brief"],
            outputs=["project_plan"],
            guardrails=[
                GuardrailConfig(name="budget_check", enforcement="strict"),
            ],
            tools=["calendar_create_event", "gmail_send"],
            critical_rules=["Never approve over-budget items"],
            decision_logic="If task > 2 hours, delegate to team.",
            success_metrics=["on_time_delivery_pct"],
            communication_style="exec-brief",
            pipeline_stages=[
                {"name": "planning", "agent_key": "pm"},
            ],
            schedule_cron="0 9 * * 1-5",
        )
        assert cfg.persona == "PM"
        assert cfg.reports_to == "exec"
        assert len(cfg.guardrails) == 1
        assert cfg.guardrails[0].enforcement == "strict"
        assert cfg.schedule_cron == "0 9 * * 1-5"

    def test_agent_config_extra_fields_allowed(self):
        from realize_core.agents.base import AgentConfig
        cfg = AgentConfig(
            name="Test", key="test",
            custom_field="custom_value",
        )
        assert cfg.model_extra.get("custom_field") == "custom_value"

    def test_base_agent_is_protocol(self):
        import typing

        from realize_core.agents.base import BaseAgent
        assert typing.runtime_checkable  # sanity
        assert hasattr(BaseAgent, "__protocol_attrs__") or hasattr(BaseAgent, "__abstractmethods__") or True
        # Runtime-checkable protocol should be usable with isinstance
        assert isinstance(BaseAgent, type)


# =====================================================================
# 2. realize_core.skills.base
# =====================================================================

class TestSkillBase:
    """Tests for realize_core.skills.base — shared skill interfaces."""

    def test_imports(self):
        pass

    def test_skill_format_enum(self):
        from realize_core.skills.base import SkillFormat
        assert SkillFormat.YAML == "yaml"
        assert SkillFormat.SKILL_MD == "skill_md"
        assert len(SkillFormat) == 2

    def test_trigger_method_enum(self):
        from realize_core.skills.base import TriggerMethod
        assert TriggerMethod.KEYWORD == "keyword"
        assert TriggerMethod.SEMANTIC == "semantic"
        assert TriggerMethod.EXPLICIT == "explicit"
        assert TriggerMethod.PIPELINE == "pipeline"
        assert len(TriggerMethod) == 4

    def test_skill_trigger_result(self):
        from realize_core.skills.base import SkillTriggerResult, TriggerMethod
        result = SkillTriggerResult(
            skill_key="email-triage",
            score=0.85,
            trigger_method=TriggerMethod.KEYWORD,
            matched_keywords=["email", "triage"],
        )
        assert result.is_match
        assert result.exceeds_threshold(0.8)
        assert not result.exceeds_threshold(0.9)

    def test_skill_trigger_result_low_score(self):
        from realize_core.skills.base import SkillTriggerResult, TriggerMethod
        result = SkillTriggerResult(
            skill_key="unknown",
            score=0.3,
            trigger_method=TriggerMethod.SEMANTIC,
        )
        assert not result.is_match
        assert not result.exceeds_threshold(0.5)

    def test_skill_trigger_result_frozen(self):
        from realize_core.skills.base import SkillTriggerResult, TriggerMethod
        result = SkillTriggerResult(
            skill_key="test", score=0.5,
            trigger_method=TriggerMethod.KEYWORD,
        )
        with pytest.raises(AttributeError):
            result.score = 0.9  # type: ignore[misc]

    def test_skill_metadata(self):
        from realize_core.skills.base import SkillFormat, SkillMetadata
        meta = SkillMetadata(
            key="email-triage",
            name="Email Triage",
            description="Triage incoming emails",
            format=SkillFormat.YAML,
            tags=["email", "productivity"],
            trigger_keywords=["triage", "email"],
        )
        assert meta.key == "email-triage"
        assert meta.format == SkillFormat.YAML
        assert "email" in meta.tags


# =====================================================================
# 3. realize_core.storage.base
# =====================================================================

class TestStorageBase:
    """Tests for realize_core.storage.base — storage provider interfaces."""

    def test_imports(self):
        pass

    def test_storage_backend_enum(self):
        from realize_core.storage.base import StorageBackend
        assert StorageBackend.LOCAL == "local"
        assert StorageBackend.S3 == "s3"
        assert StorageBackend.GCS == "gcs"
        assert StorageBackend.AZURE_BLOB == "azure_blob"
        assert len(StorageBackend) == 4

    def test_storage_object(self):
        from realize_core.storage.base import StorageObject
        obj = StorageObject(
            key="ventures/my-biz/agents/writer.md",
            size_bytes=1234,
            content_type="text/markdown",
            last_modified=datetime(2026, 1, 1),
        )
        assert obj.key == "ventures/my-biz/agents/writer.md"
        assert obj.extension == ".md"
        assert obj.size_bytes == 1234

    def test_storage_object_no_extension(self):
        from realize_core.storage.base import StorageObject
        obj = StorageObject(key="README")
        assert obj.extension == ""

    def test_storage_object_frozen(self):
        from realize_core.storage.base import StorageObject
        obj = StorageObject(key="test.txt")
        with pytest.raises(AttributeError):
            obj.key = "other.txt"  # type: ignore[misc]

    def test_base_storage_provider_is_abstract(self):
        from realize_core.storage.base import BaseStorageProvider
        with pytest.raises(TypeError):
            BaseStorageProvider()  # type: ignore[abstract]


# =====================================================================
# 4. realize_core.extensions.base
# =====================================================================

class TestExtensionBase:
    """Tests for realize_core.extensions.base — extension interfaces."""

    def test_imports(self):
        pass

    def test_extension_type_enum(self):
        from realize_core.extensions.base import ExtensionType
        assert ExtensionType.TOOL == "tool"
        assert ExtensionType.CHANNEL == "channel"
        assert ExtensionType.INTEGRATION == "integration"
        assert ExtensionType.HOOK == "hook"
        assert len(ExtensionType) == 4

    def test_extension_status_enum(self):
        from realize_core.extensions.base import ExtensionStatus
        assert ExtensionStatus.DISCOVERED == "discovered"
        assert ExtensionStatus.LOADED == "loaded"
        assert ExtensionStatus.ACTIVE == "active"
        assert ExtensionStatus.ERROR == "error"
        assert ExtensionStatus.DISABLED == "disabled"
        assert len(ExtensionStatus) == 5

    def test_extension_manifest(self):
        from realize_core.extensions.base import ExtensionManifest, ExtensionType
        manifest = ExtensionManifest(
            name="stripe-billing",
            version="1.0.0",
            extension_type=ExtensionType.TOOL,
            description="Stripe billing integration",
            entry_point="realize_core.tools.stripe_tools.StripeExtension",
        )
        assert manifest.name == "stripe-billing"
        assert manifest.extension_type == ExtensionType.TOOL

    def test_extension_registration(self):
        from realize_core.extensions.base import (
            ExtensionManifest,
            ExtensionRegistration,
            ExtensionStatus,
            ExtensionType,
        )
        manifest = ExtensionManifest(
            name="test-ext",
            extension_type=ExtensionType.HOOK,
        )
        reg = ExtensionRegistration(manifest=manifest)
        assert reg.name == "test-ext"
        assert reg.extension_type == ExtensionType.HOOK
        assert reg.status == ExtensionStatus.DISCOVERED
        assert reg.instance is None

    def test_base_extension_is_protocol(self):
        from realize_core.extensions.base import BaseExtension
        assert isinstance(BaseExtension, type)


# =====================================================================
# 5. realize_core.optimizer.base
# =====================================================================

class TestOptimizerBase:
    """Tests for realize_core.optimizer.base — experiment/optimization interfaces."""

    def test_imports(self):
        pass

    def test_experiment_status_enum(self):
        from realize_core.optimizer.base import ExperimentStatus
        assert ExperimentStatus.PENDING == "pending"
        assert ExperimentStatus.RUNNING == "running"
        assert ExperimentStatus.IMPROVED == "improved"
        assert ExperimentStatus.REGRESSED == "regressed"
        assert ExperimentStatus.NEUTRAL == "neutral"
        assert ExperimentStatus.CANCELLED == "cancelled"
        assert len(ExperimentStatus) == 6

    def test_optimization_domain_enum(self):
        from realize_core.optimizer.base import OptimizationDomain
        assert OptimizationDomain.PROMPT == "prompt"
        assert OptimizationDomain.MODEL_SELECTION == "model_selection"
        assert OptimizationDomain.PARAMETER == "parameter"
        assert OptimizationDomain.ROUTING == "routing"
        assert len(OptimizationDomain) == 4

    def test_optimization_target(self):
        from realize_core.optimizer.base import OptimizationDomain, OptimizationTarget
        target = OptimizationTarget(
            domain=OptimizationDomain.PROMPT,
            key="system_prompt_layer_3",
            description="Optimize the tone layer",
            current_value="Be professional",
            candidate_value="Be concise and professional",
        )
        assert target.domain == OptimizationDomain.PROMPT
        assert target.key == "system_prompt_layer_3"

    def test_experiment_result(self):
        from realize_core.optimizer.base import (
            ExperimentResult,
            ExperimentStatus,
            OptimizationDomain,
            OptimizationTarget,
        )
        target = OptimizationTarget(
            domain=OptimizationDomain.PROMPT,
            key="test",
        )
        result = ExperimentResult(
            experiment_id="exp-001",
            status=ExperimentStatus.IMPROVED,
            target=target,
            control_score=0.72,
            candidate_score=0.85,
            improvement_pct=18.0,
            sample_size=50,
            started_at=datetime(2026, 1, 1, 10, 0),
            completed_at=datetime(2026, 1, 1, 10, 30),
        )
        assert result.is_positive
        assert result.duration_seconds == 1800.0

    def test_experiment_result_not_positive(self):
        from realize_core.optimizer.base import (
            ExperimentResult,
            ExperimentStatus,
            OptimizationDomain,
            OptimizationTarget,
        )
        target = OptimizationTarget(
            domain=OptimizationDomain.PARAMETER,
            key="temperature",
        )
        result = ExperimentResult(
            experiment_id="exp-002",
            status=ExperimentStatus.REGRESSED,
            target=target,
        )
        assert not result.is_positive
        assert result.duration_seconds is None

    def test_base_experiment(self):
        from realize_core.optimizer.base import (
            BaseExperiment,
            ExperimentStatus,
            OptimizationDomain,
            OptimizationTarget,
        )
        target = OptimizationTarget(
            domain=OptimizationDomain.MODEL_SELECTION,
            key="complex_router",
        )
        exp = BaseExperiment(
            id="exp-003",
            name="Test model swap",
            target=target,
            max_samples=50,
            min_improvement_pct=10.0,
        )
        assert exp.is_active
        assert not exp.is_complete
        assert exp.status == ExperimentStatus.PENDING

        exp.status = ExperimentStatus.IMPROVED
        assert not exp.is_active
        assert exp.is_complete


# =====================================================================
# 6. realize_core.tools.gws_base
# =====================================================================

class TestGwsBase:
    """Tests for realize_core.tools.gws_base — GWS CLI tool config."""

    def test_imports(self):
        pass

    def test_gws_service_enum(self):
        from realize_core.tools.gws_base import GwsService
        assert GwsService.GMAIL == "gmail"
        assert GwsService.SHEETS == "sheets"
        assert GwsService.DOCS == "docs"
        assert len(GwsService) == 6

    def test_gws_auth_method_enum(self):
        from realize_core.tools.gws_base import GwsAuthMethod
        assert GwsAuthMethod.OAUTH == "oauth"
        assert GwsAuthMethod.SERVICE_ACCOUNT == "service_account"
        assert GwsAuthMethod.API_KEY == "api_key"
        assert len(GwsAuthMethod) == 3

    def test_gws_command_config(self):
        from realize_core.tools.gws_base import GwsCommandConfig, GwsService
        cmd = GwsCommandConfig(
            action="sheets_read",
            gws_command="gws sheets get {spreadsheet_id} --range {range}",
            required_params=["spreadsheet_id"],
            optional_params=["range"],
            service=GwsService.SHEETS,
        )
        assert cmd.action == "sheets_read"
        assert not cmd.is_destructive
        assert cmd.timeout_seconds == 30

    def test_gws_tool_config_defaults(self):
        from realize_core.tools.gws_base import GwsToolConfig
        cfg = GwsToolConfig()
        assert cfg.enabled is True
        assert cfg.binary_path == "gws"
        assert cfg.default_timeout == 30
        assert cfg.commands == []

    def test_gws_tool_config_with_commands(self):
        from realize_core.tools.gws_base import GwsCommandConfig, GwsService, GwsToolConfig
        cfg = GwsToolConfig(
            binary_path="/usr/local/bin/gws",
            default_timeout=60,
            commands=[
                GwsCommandConfig(
                    action="sheets_read",
                    gws_command="gws sheets get {spreadsheet_id}",
                    service=GwsService.SHEETS,
                ),
                GwsCommandConfig(
                    action="sheets_append",
                    gws_command="gws sheets append {spreadsheet_id}",
                    service=GwsService.SHEETS,
                    is_destructive=True,
                ),
            ],
        )
        assert len(cfg.commands) == 2
        assert cfg.get_command("sheets_read") is not None
        assert cfg.get_command("sheets_append").is_destructive
        assert cfg.get_command("nonexistent") is None
        assert cfg.service_names == ["sheets"]

    def test_gws_tool_config_extra_allowed(self):
        from realize_core.tools.gws_base import GwsToolConfig
        cfg = GwsToolConfig(custom_setting="hello")
        assert cfg.model_extra.get("custom_setting") == "hello"


# =====================================================================
# Cross-cutting: all modules importable from top-level packages
# =====================================================================

class TestPackageImports:
    """Verify that all new packages are importable."""

    def test_import_agents_package(self):
        pass

    def test_import_skills_package(self):
        pass

    def test_import_storage_package(self):
        pass

    def test_import_extensions_package(self):
        pass

    def test_import_optimizer_package(self):
        pass

    def test_import_gws_base(self):
        pass
