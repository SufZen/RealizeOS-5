"""
Tests for Operator Approval Tool — Intent 3.1.

Covers:
- ApprovalRequest creation and serialization
- ApprovalStore CRUD (create, get, resolve, list pending)
- ApprovalTool execute (request_decision, request_credential, request_input)
- Timeout / expiry detection
- Tool registration and schema
- DB migration v3
"""

from __future__ import annotations

import asyncio

import pytest
from realize_core.tools.approval import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStore,
    ApprovalTool,
    get_tool,
)
from realize_core.tools.base_tool import ToolCategory

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------


def run_async(coro):
    """Run an async function synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
#  ApprovalRequest
# ---------------------------------------------------------------------------


class TestApprovalRequest:
    """Test the ApprovalRequest model."""

    def test_create_request(self):
        req = ApprovalRequest(
            action=ApprovalAction.REQUEST_DECISION,
            description="Approve sending email to client",
            agent_key="writer",
            system_key="agency",
        )
        assert req.id is not None
        assert req.action == ApprovalAction.REQUEST_DECISION
        assert req.status == ApprovalStatus.PENDING
        assert req.description == "Approve sending email to client"
        assert req.response is None

    def test_request_with_options(self):
        req = ApprovalRequest(
            action=ApprovalAction.REQUEST_DECISION,
            description="Choose pricing tier",
            agent_key="analyst",
            system_key="saas",
            options=["basic", "pro", "enterprise"],
        )
        assert req.options == ["basic", "pro", "enterprise"]

    def test_serialization_roundtrip(self):
        req = ApprovalRequest(
            action=ApprovalAction.REQUEST_CREDENTIAL,
            description="Need API key for analytics",
            agent_key="analyst",
            system_key="saas",
            metadata={"credential_type": "api_key"},
        )
        d = req.to_dict()
        restored = ApprovalRequest.from_dict(d)
        assert restored.id == req.id
        assert restored.action == ApprovalAction.REQUEST_CREDENTIAL
        assert restored.description == req.description
        assert restored.metadata == req.metadata

    def test_expiry_detection(self):
        req = ApprovalRequest(
            action=ApprovalAction.REQUEST_INPUT,
            description="Test expiry",
            agent_key="test",
            system_key="test",
            timeout_seconds=0,  # Immediately expired
        )
        assert req.is_expired

    def test_not_expired(self):
        req = ApprovalRequest(
            action=ApprovalAction.REQUEST_INPUT,
            description="Test not expired",
            agent_key="test",
            system_key="test",
            timeout_seconds=3600,
        )
        assert not req.is_expired


# ---------------------------------------------------------------------------
#  ApprovalStore
# ---------------------------------------------------------------------------


class TestApprovalStore:
    """Test the in-memory ApprovalStore."""

    @pytest.fixture
    def store(self):
        return ApprovalStore()

    @pytest.fixture
    def pending_request(self, store):
        req = ApprovalRequest(
            action=ApprovalAction.REQUEST_DECISION,
            description="Approve campaign launch",
            agent_key="strategist",
            system_key="agency",
        )
        return store.create(req)

    def test_create_and_get(self, store, pending_request):
        retrieved = store.get(pending_request.id)
        assert retrieved is not None
        assert retrieved.id == pending_request.id
        assert retrieved.status == ApprovalStatus.PENDING

    def test_get_nonexistent(self, store):
        assert store.get("nonexistent") is None

    def test_resolve_approve(self, store, pending_request):
        resolved = store.resolve(
            pending_request.id,
            ApprovalStatus.APPROVED,
            response="Go ahead",
            responded_by="ceo",
        )
        assert resolved is not None
        assert resolved.status == ApprovalStatus.APPROVED
        assert resolved.response == "Go ahead"
        assert resolved.responded_by == "ceo"
        assert resolved.responded_at is not None

    def test_resolve_reject(self, store, pending_request):
        resolved = store.resolve(
            pending_request.id,
            ApprovalStatus.REJECTED,
            response="Not yet",
        )
        assert resolved.status == ApprovalStatus.REJECTED

    def test_resolve_nonexistent(self, store):
        result = store.resolve("nonexistent", ApprovalStatus.APPROVED)
        assert result is None

    def test_resolve_already_resolved(self, store, pending_request):
        store.resolve(pending_request.id, ApprovalStatus.APPROVED)
        # Trying to resolve again should get the already-resolved request
        result = store.resolve(pending_request.id, ApprovalStatus.REJECTED)
        assert result.status == ApprovalStatus.APPROVED  # Not changed

    def test_get_pending(self, store):
        for i in range(3):
            store.create(
                ApprovalRequest(
                    action=ApprovalAction.REQUEST_DECISION,
                    description=f"Task {i}",
                    agent_key="agent",
                    system_key="venture",
                )
            )
        pending = store.get_pending()
        assert len(pending) == 3

    def test_get_pending_filtered(self, store):
        store.create(
            ApprovalRequest(
                action=ApprovalAction.REQUEST_DECISION,
                description="Agency task",
                agent_key="agent",
                system_key="agency",
            )
        )
        store.create(
            ApprovalRequest(
                action=ApprovalAction.REQUEST_DECISION,
                description="SaaS task",
                agent_key="agent",
                system_key="saas",
            )
        )
        assert len(store.get_pending("agency")) == 1
        assert len(store.get_pending("saas")) == 1

    def test_expired_requests_excluded(self, store):
        req = ApprovalRequest(
            action=ApprovalAction.REQUEST_INPUT,
            description="Expired",
            agent_key="agent",
            system_key="test",
            timeout_seconds=0,
        )
        store.create(req)
        assert len(store.get_pending()) == 0
        # The request should now have expired status
        refreshed = store.get(req.id)
        assert refreshed.status == ApprovalStatus.EXPIRED


# ---------------------------------------------------------------------------
#  ApprovalTool
# ---------------------------------------------------------------------------


class TestApprovalTool:
    """Test the ApprovalTool BaseTool implementation."""

    @pytest.fixture
    def tool(self):
        return ApprovalTool()

    def test_tool_properties(self, tool):
        assert tool.name == "approval"
        assert tool.category == ToolCategory.AUTOMATION
        assert tool.is_available()

    def test_schemas(self, tool):
        schemas = tool.get_schemas()
        assert len(schemas) == 3
        names = {s.name for s in schemas}
        assert names == {"request_decision", "request_credential", "request_input"}

    def test_claude_schemas(self, tool):
        claude_schemas = tool.get_claude_schemas()
        assert len(claude_schemas) == 3
        for schema in claude_schemas:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema

    def test_request_decision(self, tool):
        result = run_async(tool.execute("request_decision", {
            "description": "Approve sending proposal to client",
            "agent_key": "strategist",
            "system_key": "agency",
        }))
        assert result.success
        assert "Approval request created" in result.output
        assert result.data is not None
        assert result.data["action"] == "request_decision"
        assert result.metadata.get("requires_human") is True

    def test_request_credential(self, tool):
        result = run_async(tool.execute("request_credential", {
            "description": "Need Stripe API key for payment processing",
            "credential_type": "api_key",
            "agent_key": "developer",
            "system_key": "saas",
        }))
        assert result.success
        assert "Approval request created" in result.output
        assert result.data["action"] == "request_credential"

    def test_request_input(self, tool):
        result = run_async(tool.execute("request_input", {
            "description": "What tone should the blog post use?",
            "prompt": "Choose: professional, casual, technical",
            "agent_key": "writer",
            "system_key": "agency",
        }))
        assert result.success
        assert result.data["action"] == "request_input"

    def test_missing_description(self, tool):
        result = run_async(tool.execute("request_decision", {}))
        assert not result.success
        assert "Description is required" in result.error

    def test_unknown_action(self, tool):
        result = run_async(tool.execute("unknown_action", {"description": "test"}))
        assert not result.success
        assert "Unknown approval action" in result.error

    def test_store_access(self, tool):
        """Tool provides access to its store for API integration."""
        run_async(tool.execute("request_decision", {
            "description": "Test store access",
            "agent_key": "test",
            "system_key": "test",
        }))
        pending = tool.store.get_pending()
        assert len(pending) == 1

    def test_request_with_options(self, tool):
        result = run_async(tool.execute("request_decision", {
            "description": "Choose deployment target",
            "options": ["staging", "production"],
            "agent_key": "devops",
            "system_key": "saas",
        }))
        assert result.success
        assert result.data["options"] == ["staging", "production"]


# ---------------------------------------------------------------------------
#  Factory & Registration
# ---------------------------------------------------------------------------


class TestToolFactory:
    """Test tool factory and registration."""

    def test_get_tool_factory(self):
        tool = get_tool()
        assert isinstance(tool, ApprovalTool)
        assert tool.name == "approval"

    def test_registry_integration(self):
        """Approval tool registers with ToolRegistry."""
        from realize_core.tools.tool_registry import ToolRegistry

        registry = ToolRegistry()
        tool = get_tool()
        assert registry.register(tool) is True
        assert registry.get_tool("approval") is not None
        assert registry.get_tool_for_action("request_decision") is tool


# ---------------------------------------------------------------------------
#  DB Migration
# ---------------------------------------------------------------------------


class TestMigrationV3:
    """Test that migration v3 creates the approval_requests table."""

    def test_migration_registered(self):
        from realize_core.db.migrations import MIGRATIONS

        assert 3 in MIGRATIONS

    def test_migration_creates_table(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        # Create minimal schema_version table
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version VALUES (2)")
        conn.commit()

        from realize_core.db.migrations import MIGRATIONS

        MIGRATIONS[3](conn)
        conn.commit()

        # Verify table exists
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='approval_requests'"
        ).fetchall()
        assert len(tables) == 1

        # Verify can insert
        conn.execute(
            """INSERT INTO approval_requests
               (id, action, description, agent_key, system_key, expires_at)
               VALUES ('test-1', 'request_decision', 'Test', 'agent', 'system',
                       '2026-12-31T00:00:00')"""
        )
        conn.commit()

        row = conn.execute("SELECT * FROM approval_requests WHERE id = 'test-1'").fetchone()
        assert row is not None
        conn.close()
