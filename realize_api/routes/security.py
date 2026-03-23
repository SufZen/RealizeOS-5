"""
Security audit API routes — query audit log from the dashboard.

Endpoints:
- GET  /api/security/audit — query audit events with filters
- GET  /api/security/audit/stats — aggregate statistics
- GET  /api/security/audit/events — recent security events (denied, blocked)
- GET  /api/security/status — overall security posture
"""

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from realize_api.dependencies import CurrentUser, require_permission

router = APIRouter(prefix="/security", tags=["Security"])
logger = logging.getLogger(__name__)


@router.get("/audit")
async def query_audit(
    user_id: str = Query("", description="Filter by user ID"),
    action: str = Query("", description="Filter by action"),
    outcome: str = Query("", description="Filter by outcome"),
    severity: str = Query("", description="Filter by severity"),
    limit: int = Query(50, ge=1, le=500),
    _user: CurrentUser = Depends(require_permission("admin:audit")),
):
    """Query the audit log with optional filters."""
    try:
        from realize_core.security.audit import get_audit_logger

        audit = get_audit_logger()
        events = audit.query(
            user_id=user_id,
            action=action,
            outcome=outcome,
            severity=severity,
            limit=limit,
        )
        return {
            "events": [e.to_dict() for e in events],
            "count": len(events),
            "total": audit.entry_count,
        }
    except Exception as exc:
        logger.debug("Audit query failed: %s", exc)
        return {"events": [], "count": 0, "total": 0}


@router.get("/audit/stats")
async def audit_stats(
    _user: CurrentUser = Depends(require_permission("admin:audit")),
):
    """Get aggregate audit statistics."""
    try:
        from realize_core.security.audit import get_audit_logger

        return get_audit_logger().get_stats()
    except Exception as exc:
        logger.debug("Audit stats failed: %s", exc)
        return {"total": 0}


@router.get("/audit/events")
async def security_events(
    limit: int = Query(50, ge=1, le=200),
    _user: CurrentUser = Depends(require_permission("admin:security")),
):
    """Get recent security-relevant events (denied, blocked, critical)."""
    try:
        from realize_core.security.audit import get_audit_logger

        audit = get_audit_logger()
        events = audit.get_security_events(limit=limit)
        return {
            "events": [e.to_dict() for e in events],
            "count": len(events),
        }
    except Exception as exc:
        logger.debug("Security events query failed: %s", exc)
        return {"events": [], "count": 0}


@router.get("/status")
async def security_status(
    _user: CurrentUser = Depends(require_permission("admin:security")),
):
    """Overall security posture: which features are active."""
    jwt_enabled = os.environ.get("REALIZE_JWT_ENABLED", "").lower() in ("true", "1", "yes")
    api_key_set = bool(os.environ.get("REALIZE_API_KEY"))

    # Check rate limiter config
    rate_limit = 30
    cost_limit = 5.0
    try:
        from realize_core.utils.rate_limiter import get_rate_limiter

        rl = get_rate_limiter()
        rate_limit = rl.requests_per_minute
        cost_limit = rl.cost_per_hour_usd
    except Exception:
        pass

    # Check RBAC roles
    roles = []
    try:
        from realize_core.security.rbac import get_rbac_manager

        roles = get_rbac_manager().role_names()
    except Exception:
        pass

    # Run scanner if available
    scan_result = None
    try:
        from realize_core.security.scanner import run_security_scan

        scan_result = run_security_scan(Path("."))
    except Exception:
        pass

    return {
        "features": {
            "api_key_auth": api_key_set,
            "jwt_auth": jwt_enabled,
            "rate_limiting": True,
            "injection_guard": True,
            "audit_logging": True,
            "rbac": True,
        },
        "rate_limit": {
            "requests_per_minute": rate_limit,
            "cost_per_hour_usd": cost_limit,
        },
        "rbac_roles": roles,
        "scanner": scan_result,
    }
