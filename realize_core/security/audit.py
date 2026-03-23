"""
Enhanced audit logging for RealizeOS.

Provides:
- Structured audit events with rich metadata
- In-memory ring buffer with configurable capacity
- File-based persistent log (append-only JSONL)
- Queryable by user, action, outcome, time range
- Correlation IDs for request tracing
- Integration points for injection events and RBAC decisions
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class AuditEvent:
    """A structured audit log entry."""

    timestamp: float
    user_id: str
    action: str
    outcome: str = "success"  # success, denied, error, blocked
    channel: str = ""  # dashboard, api, telegram, etc.
    system_key: str = ""  # Which venture/system
    resource_type: str = ""  # agent, pipeline, file, system, etc.
    resource_id: str = ""  # Specific resource identifier
    details: str = ""  # Human-readable context
    ip_address: str = ""  # Client IP (if available)
    correlation_id: str = ""  # Request trace ID
    severity: str = "info"  # info, warning, critical
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to single-line JSON."""
        return json.dumps(self.to_dict(), separators=(",", ":"))


# ---------------------------------------------------------------------------
# Audit Logger
# ---------------------------------------------------------------------------


class AuditLogger:
    """
    Thread-safe, persistent audit logger.

    Features:
    - In-memory ring buffer for fast queries
    - Optional JSONL file persistence
    - Query by user, action, outcome, severity, time range
    """

    def __init__(
        self,
        max_entries: int = 10000,
        log_dir: str | Path | None = None,
    ):
        self._entries: list[AuditEvent] = []
        self._max_entries = max_entries
        self._lock = Lock()
        self._log_file: Path | None = None

        # Set up file logging
        if log_dir:
            self._log_file = Path(log_dir) / "audit.jsonl"
            self._log_file.parent.mkdir(parents=True, exist_ok=True)

    # ---- Logging ----

    def log(
        self,
        user_id: str,
        action: str,
        outcome: str = "success",
        channel: str = "",
        system_key: str = "",
        resource_type: str = "",
        resource_id: str = "",
        details: str = "",
        ip_address: str = "",
        correlation_id: str = "",
        severity: str = "info",
        metadata: dict | None = None,
    ) -> AuditEvent:
        """
        Record an audit event.

        Returns:
            The created AuditEvent.
        """
        event = AuditEvent(
            timestamp=time.time(),
            user_id=user_id,
            action=action,
            outcome=outcome,
            channel=channel,
            system_key=system_key,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            correlation_id=correlation_id,
            severity=severity,
            metadata=metadata or {},
        )

        with self._lock:
            self._entries.append(event)

            # Trim ring buffer
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]

        # Persist to file (best-effort)
        if self._log_file:
            try:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(event.to_json() + "\n")
            except OSError as exc:
                logger.warning("Failed to write audit log: %s", exc)

        # Log security-relevant events
        if outcome in ("denied", "blocked"):
            logger.warning(
                "AUDIT [%s] %s %s → %s (%s)",
                severity.upper(),
                user_id,
                action,
                outcome,
                details,
            )
        elif severity == "critical":
            logger.error(
                "AUDIT [CRITICAL] %s %s → %s (%s)",
                user_id,
                action,
                outcome,
                details,
            )

        return event

    # ---- Convenience methods ----

    def log_access_denied(
        self,
        user_id: str,
        action: str,
        permission: str,
        role: str = "",
        **kwargs,
    ) -> AuditEvent:
        """Log an access denied event."""
        return self.log(
            user_id=user_id,
            action=action,
            outcome="denied",
            severity="warning",
            details=f"Permission '{permission}' denied for role '{role}'",
            **kwargs,
        )

    def log_injection_blocked(
        self,
        user_id: str,
        risk_score: float,
        categories: list[str] | set[str],
        **kwargs,
    ) -> AuditEvent:
        """Log a blocked prompt injection attempt."""
        return self.log(
            user_id=user_id,
            action="injection_blocked",
            outcome="blocked",
            severity="critical",
            details=f"Risk score: {risk_score:.0%}, categories: {', '.join(categories)}",
            resource_type="input",
            metadata={"risk_score": risk_score, "categories": list(categories)},
            **kwargs,
        )

    def log_token_event(
        self,
        user_id: str,
        action: str,
        token_type: str = "access",
        **kwargs,
    ) -> AuditEvent:
        """Log a JWT token event (creation, refresh, revocation)."""
        return self.log(
            user_id=user_id,
            action=action,
            resource_type="token",
            resource_id=token_type,
            **kwargs,
        )

    # ---- Queries ----

    def query(
        self,
        user_id: str = "",
        action: str = "",
        outcome: str = "",
        severity: str = "",
        system_key: str = "",
        since: float = 0.0,
        until: float = 0.0,
        limit: int = 50,
    ) -> list[AuditEvent]:
        """
        Query audit log entries with filters.

        Args:
            user_id: Filter by user.
            action: Filter by action.
            outcome: Filter by outcome (success, denied, error, blocked).
            severity: Filter by severity (info, warning, critical).
            system_key: Filter by system/venture.
            since: Unix timestamp lower bound.
            until: Unix timestamp upper bound.
            limit: Maximum entries to return.

        Returns:
            Matching entries (most recent first).
        """
        with self._lock:
            results = list(self._entries)

        if user_id:
            results = [e for e in results if e.user_id == user_id]
        if action:
            results = [e for e in results if e.action == action]
        if outcome:
            results = [e for e in results if e.outcome == outcome]
        if severity:
            results = [e for e in results if e.severity == severity]
        if system_key:
            results = [e for e in results if e.system_key == system_key]
        if since > 0:
            results = [e for e in results if e.timestamp >= since]
        if until > 0:
            results = [e for e in results if e.timestamp <= until]

        return list(reversed(results[-limit:]))

    def get_security_events(self, limit: int = 100) -> list[AuditEvent]:
        """Get recent security-relevant events (denied, blocked, critical)."""
        return (
            self.query(limit=limit, outcome="")
            or [
                e for e in self.query(limit=limit * 2) if e.outcome in ("denied", "blocked") or e.severity == "critical"
            ][:limit]
        )

    def get_stats(self) -> dict:
        """Get aggregate statistics."""
        with self._lock:
            entries = list(self._entries)

        total = len(entries)
        if not total:
            return {"total": 0}

        outcomes: dict[str, int] = {}
        actions: dict[str, int] = {}
        users: set[str] = set()

        for e in entries:
            outcomes[e.outcome] = outcomes.get(e.outcome, 0) + 1
            actions[e.action] = actions.get(e.action, 0) + 1
            users.add(e.user_id)

        return {
            "total": total,
            "unique_users": len(users),
            "outcomes": outcomes,
            "top_actions": dict(sorted(actions.items(), key=lambda x: -x[1])[:10]),
        }

    # ---- Properties ----

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def log_file(self) -> Path | None:
        return self._log_file


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get or create the global audit logger."""
    global _audit_logger
    if _audit_logger is None:
        log_dir = os.environ.get("REALIZE_AUDIT_LOG_DIR", "")
        _audit_logger = AuditLogger(
            log_dir=log_dir if log_dir else None,
        )
    return _audit_logger
