"""
Security middleware for the RealizeOS API.

Provides HTTP-layer security by wiring the existing realize_core security
modules into the FastAPI request pipeline:

- RateLimitMiddleware — per-tenant request/cost limiting
- InjectionGuardMiddleware — scan request bodies for prompt injection
- AuditMiddleware — record every request in the audit log
- SecurityHeadersMiddleware — set X-Frame-Options, etc.

Authentication itself lives in ``realize_api.middleware.AuthMiddleware``
(unified cookie + API key + JWT) — separated so this file stays focused on
the cross-cutting "every request" concerns.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Paths that bypass ALL security middleware (health probes, docs, static)
_PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/status",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/health",
        "/api/status",
        "/favicon.svg",
        "/icons.svg",
    }
)


def _is_public(path: str) -> bool:
    """Check if a path should bypass security middleware."""
    return path in _PUBLIC_PATHS or path.startswith("/assets/")


# ---------------------------------------------------------------------------
# 1. Rate Limit Middleware
# ---------------------------------------------------------------------------



class _MCPStreamBypassMixin:
    """Let /mcp/* stream through unbuffered. BaseHTTPMiddleware buffers responses,
    which breaks the built-in MCP SSE transport (/mcp/sse + /mcp/messages/)."""

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").startswith("/mcp/"):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


class RateLimitMiddleware(_MCPStreamBypassMixin, BaseHTTPMiddleware):
    """
    Enforces per-tenant request-rate and cost limits.

    Uses ``realize_core.utils.rate_limiter.RateLimiter`` under the hood.
    Tenant is identified by X-Tenant-ID header or falls back to client IP.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        try:
            from realize_core.utils.rate_limiter import get_rate_limiter

            limiter = get_rate_limiter(request.app)
            tenant = request.headers.get(
                "X-Tenant-ID",
                request.client.host if request.client else "anonymous",
            )

            if not limiter.check_rate_limit(tenant):
                logger.warning("Rate limit hit for tenant %s on %s", tenant, request.url.path)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": "Too many requests — please slow down.",
                        "retry_after_seconds": 60,
                    },
                    headers={"Retry-After": "60"},
                )

            # Record the request AFTER we know it's allowed
            limiter.record_request(tenant)
        except Exception as exc:
            # Fail open — don't block requests if the limiter itself breaks
            logger.debug("Rate limiter unavailable: %s", exc)

        return await call_next(request)


# ---------------------------------------------------------------------------
# 2. Injection Guard Middleware
# ---------------------------------------------------------------------------


class InjectionGuardMiddleware(_MCPStreamBypassMixin, BaseHTTPMiddleware):
    """
    Scan POST/PUT/PATCH request bodies for prompt injection patterns.

    Uses ``realize_core.security.injection.scan_injection``.
    - Blocks requests with risk_score >= 0.7
    - Logs warnings for scores in [0.4, 0.7)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.body()
                if body:
                    text = body.decode("utf-8", errors="replace")

                    from realize_core.security.injection import scan_injection

                    result = scan_injection(text)

                    if result.should_block:
                        logger.warning(
                            "INJECTION BLOCKED on %s — score=%.2f categories=%s",
                            request.url.path,
                            result.risk_score,
                            result.categories,
                        )
                        # Record in audit log best-effort
                        try:
                            from realize_core.security.audit import get_audit_logger

                            audit = get_audit_logger()
                            audit.log_injection_blocked(
                                user_id=request.headers.get("X-User-ID", "unknown"),
                                risk_score=result.risk_score,
                                categories=result.categories,
                                channel="api",
                                ip_address=request.client.host if request.client else "",
                            )
                        except Exception as exc:
                            logger.debug("Audit log for injection block failed: %s", exc)

                        return JSONResponse(
                            status_code=400,
                            content={
                                "error": "input_rejected",
                                "message": "Your input was flagged by our security system. Please rephrase.",
                                "risk_score": result.risk_score,
                            },
                        )

                    if result.needs_review:
                        logger.info(
                            "Injection review on %s — score=%.2f",
                            request.url.path,
                            result.risk_score,
                        )
                        # Audit log needs_review events for security review
                        try:
                            from realize_core.security.audit import get_audit_logger

                            audit = get_audit_logger()
                            audit.log(
                                user_id="system",
                                action="injection_needs_review",
                                outcome="flagged",
                                details=f"Score: {result.risk_score:.2f}, path: {request.url.path}",
                                ip_address=request.client.host if request.client else "",
                                severity="warning",
                            )
                        except Exception:
                            pass
            except Exception as exc:
                # Fail open — don't block requests if scanning itself breaks
                logger.debug("Injection scan failed: %s", exc)

        return await call_next(request)


# ---------------------------------------------------------------------------
# 3. Audit Middleware
# ---------------------------------------------------------------------------


class AuditMiddleware(_MCPStreamBypassMixin, BaseHTTPMiddleware):
    """
    Record every API request in the audit log.

    Adds a correlation ID (X-Request-ID) to each request for tracing.
    Logs method, path, status, latency, and user info.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        correlation_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:16])
        start = time.time()

        response = await call_next(request)

        latency_ms = (time.time() - start) * 1000
        response.headers["X-Request-ID"] = correlation_id

        # Record audit event best-effort
        try:
            from realize_core.security.audit import get_audit_logger

            audit = get_audit_logger()
            outcome = "success" if response.status_code < 400 else "error"
            severity = "info"
            if response.status_code >= 500:
                severity = "critical"
            elif response.status_code >= 400:
                severity = "warning"

            audit.log(
                user_id=request.headers.get("X-User-ID", "anonymous"),
                action=f"{request.method} {request.url.path}",
                outcome=outcome,
                channel="api",
                ip_address=request.client.host if request.client else "",
                correlation_id=correlation_id,
                severity=severity,
                metadata={
                    "status_code": response.status_code,
                    "latency_ms": round(latency_ms, 1),
                },
            )
        except Exception as exc:
            logger.debug("Audit logging failed: %s", exc)

        return response


# ---------------------------------------------------------------------------
# 4. Security Headers Middleware
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware(_MCPStreamBypassMixin, BaseHTTPMiddleware):
    """
    Add standard security response headers to every API response.

    Headers:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: geolocation=(), camera=(), microphone=()
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"

        return response
