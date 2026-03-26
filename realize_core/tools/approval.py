"""
Operator Approval Tool — Agents can pause and request human intervention.

Provides three actions:
- ``request_decision``: Ask the operator to approve or reject an action
- ``request_credential``: Request a credential (API key, password, etc.)
- ``request_input``: Request free-form input from the operator

Approval requests are persisted to the database and can be resolved
via the API or dashboard. Each request has a configurable timeout.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from realize_core.tools.base_tool import (
    BaseTool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)

logger = logging.getLogger(__name__)


class ApprovalAction(str, Enum):
    """Types of approval requests an agent can make."""

    REQUEST_DECISION = "request_decision"
    REQUEST_CREDENTIAL = "request_credential"
    REQUEST_INPUT = "request_input"


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalRequest:
    """Represents a single approval request."""

    def __init__(
        self,
        action: ApprovalAction,
        description: str,
        agent_key: str,
        system_key: str,
        session_id: str = "",
        options: list[str] | None = None,
        timeout_seconds: int = 3600,
        metadata: dict[str, Any] | None = None,
    ):
        self.id = str(uuid.uuid4())
        self.action = action
        self.description = description
        self.agent_key = agent_key
        self.system_key = system_key
        self.session_id = session_id
        self.options = options or []
        self.status = ApprovalStatus.PENDING
        self.response: str | None = None
        self.responded_by: str | None = None
        self.created_at = datetime.now(timezone.utc)
        self.expires_at = self.created_at + timedelta(seconds=timeout_seconds)
        self.responded_at: datetime | None = None
        self.metadata = metadata or {}

    @property
    def is_expired(self) -> bool:
        return (
            self.status == ApprovalStatus.PENDING
            and datetime.now(timezone.utc) > self.expires_at
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action.value,
            "description": self.description,
            "agent_key": self.agent_key,
            "system_key": self.system_key,
            "session_id": self.session_id,
            "options": self.options,
            "status": self.status.value,
            "response": self.response,
            "responded_by": self.responded_by,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApprovalRequest:
        req = cls(
            action=ApprovalAction(data["action"]),
            description=data["description"],
            agent_key=data["agent_key"],
            system_key=data["system_key"],
            session_id=data.get("session_id", ""),
            options=data.get("options", []),
        )
        req.id = data["id"]
        req.status = ApprovalStatus(data.get("status", "pending"))
        req.response = data.get("response")
        req.responded_by = data.get("responded_by")
        req.created_at = datetime.fromisoformat(data["created_at"])
        req.expires_at = datetime.fromisoformat(data["expires_at"])
        if data.get("responded_at"):
            req.responded_at = datetime.fromisoformat(data["responded_at"])
        req.metadata = data.get("metadata", {})
        return req


# ---------------------------------------------------------------------------
# In-memory store (production uses DB via ApprovalStore)
# ---------------------------------------------------------------------------


class ApprovalStore:
    """
    In-memory approval store with optional database persistence.

    Production deployments should use the DB-backed variant.
    """

    def __init__(self, db_path: str | None = None):
        self._requests: dict[str, ApprovalRequest] = {}
        self._db_path = db_path

    def create(self, request: ApprovalRequest) -> ApprovalRequest:
        """Store a new approval request."""
        self._requests[request.id] = request
        if self._db_path:
            self._persist(request)
        return request

    def get(self, request_id: str) -> ApprovalRequest | None:
        """Get a request by ID, checking for expiry."""
        req = self._requests.get(request_id)
        if req and req.is_expired:
            req.status = ApprovalStatus.EXPIRED
        return req

    def resolve(
        self,
        request_id: str,
        status: ApprovalStatus,
        response: str = "",
        responded_by: str = "operator",
    ) -> ApprovalRequest | None:
        """
        Resolve an approval request.

        Args:
            request_id: The request to resolve.
            status: Approved or rejected.
            response: Operator's response text.
            responded_by: Who responded.

        Returns:
            Updated request, or None if not found.
        """
        req = self.get(request_id)
        if not req:
            return None

        if req.status != ApprovalStatus.PENDING:
            logger.warning("Cannot resolve non-pending request %s (status=%s)", request_id, req.status)
            return req

        req.status = status
        req.response = response
        req.responded_by = responded_by
        req.responded_at = datetime.now(timezone.utc)

        if self._db_path:
            self._persist_resolution(req)

        return req

    def get_pending(self, system_key: str | None = None) -> list[ApprovalRequest]:
        """Get all pending requests, optionally filtered by system."""
        pending = []
        for req in self._requests.values():
            if req.is_expired:
                req.status = ApprovalStatus.EXPIRED
                continue
            if req.status != ApprovalStatus.PENDING:
                continue
            if system_key and req.system_key != system_key:
                continue
            pending.append(req)
        return sorted(pending, key=lambda r: r.created_at, reverse=True)

    def _persist(self, request: ApprovalRequest):
        """Persist request to database."""
        try:
            import sqlite3

            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT OR REPLACE INTO approval_requests
                   (id, action, description, agent_key, system_key, session_id,
                    options, status, response, responded_by,
                    created_at, expires_at, responded_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.id,
                    request.action.value,
                    request.description,
                    request.agent_key,
                    request.system_key,
                    request.session_id,
                    ",".join(request.options),
                    request.status.value,
                    request.response,
                    request.responded_by,
                    request.created_at.isoformat(),
                    request.expires_at.isoformat(),
                    request.responded_at.isoformat() if request.responded_at else None,
                    str(request.metadata),
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to persist approval request: %s", e)

    def _persist_resolution(self, request: ApprovalRequest):
        """Update resolution in database."""
        self._persist(request)


# ---------------------------------------------------------------------------
# Approval Tool (BaseTool implementation)
# ---------------------------------------------------------------------------


class ApprovalTool(BaseTool):
    """
    Tool that allows agents to pause and request human intervention.

    Actions:
    - request_decision: Ask operator to approve/reject
    - request_credential: Request a credential
    - request_input: Request free-form text input
    """

    def __init__(self, store: ApprovalStore | None = None):
        self._store = store or ApprovalStore()

    @property
    def name(self) -> str:
        return "approval"

    @property
    def description(self) -> str:
        return "Request human operator approval, credentials, or input"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.AUTOMATION

    def is_available(self) -> bool:
        return True

    def get_schemas(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="request_decision",
                description=(
                    "Pause execution and ask the human operator to approve or reject "
                    "an action before proceeding. Use when an action is high-impact, "
                    "irreversible, or outside your authorized scope."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "What you want the operator to decide on",
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of choices (default: approve/reject)",
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "How long to wait for a response (default: 3600)",
                            "default": 3600,
                        },
                    },
                    "required": ["description"],
                },
                category=ToolCategory.AUTOMATION,
                is_destructive=False,
            ),
            ToolSchema(
                name="request_credential",
                description=(
                    "Request an API key, password, or other credential from the operator. "
                    "Use when you need access to a service but don't have the credential."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "What credential you need and why",
                        },
                        "credential_type": {
                            "type": "string",
                            "description": "Type of credential (api_key, password, token, etc.)",
                            "default": "api_key",
                        },
                    },
                    "required": ["description"],
                },
                category=ToolCategory.AUTOMATION,
                is_destructive=False,
            ),
            ToolSchema(
                name="request_input",
                description=(
                    "Request free-form text input from the operator. "
                    "Use when you need clarification, additional context, or instructions."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "What input you need from the operator",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Optional prompt text to show the operator",
                        },
                    },
                    "required": ["description"],
                },
                category=ToolCategory.AUTOMATION,
                is_destructive=False,
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        """Execute an approval action."""
        try:
            action_enum = ApprovalAction(action)
        except ValueError:
            return ToolResult.fail(f"Unknown approval action: {action}")

        description = params.get("description", "")
        if not description:
            return ToolResult.fail("Description is required")

        request = ApprovalRequest(
            action=action_enum,
            description=description,
            agent_key=params.get("agent_key", "unknown"),
            system_key=params.get("system_key", "default"),
            session_id=params.get("session_id", ""),
            options=params.get("options", []),
            timeout_seconds=params.get("timeout_seconds", 3600),
            metadata={
                "credential_type": params.get("credential_type"),
                "prompt": params.get("prompt"),
            },
        )

        self._store.create(request)

        logger.info(
            "Approval request created: %s (action=%s, agent=%s)",
            request.id,
            action,
            request.agent_key,
        )

        return ToolResult.ok(
            output=(
                f"⏳ Approval request created (ID: {request.id}). "
                f"Waiting for operator response. "
                f"Request: {description}"
            ),
            data=request.to_dict(),
            requires_human=True,
            request_id=request.id,
        )

    @property
    def store(self) -> ApprovalStore:
        """Access the approval store (for API/dashboard integration)."""
        return self._store


def get_tool() -> ApprovalTool:
    """Factory function for auto-discovery."""
    return ApprovalTool()
