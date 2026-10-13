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
import os
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
        "/api/health",
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
    """Let /mcp and /mcp/* stream through unbuffered. BaseHTTPMiddleware buffers
    responses, which breaks the built-in MCP transports (/mcp/sse + /mcp/messages/,
    and Streamable HTTP on /mcp)."""

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope.get("type") == "http" and (path == "/mcp" or path.startswith("/mcp/")):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


def _trusted_proxies() -> list:
    """Networks whose X-Forwarded-For is believed (``REALIZE_TRUSTED_PROXIES``, comma-separated)."""
    import ipaddress

    nets = []
    for item in os.getenv("REALIZE_TRUSTED_PROXIES", "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid REALIZE_TRUSTED_PROXIES entry: %r", item)
    return nets


def _client_address(request: Request) -> str:
    """The real client IP: the peer, or X-Forwarded-For's last untrusted hop behind a trusted proxy."""
    import ipaddress

    peer = request.client.host if request.client else ""
    proxies = _trusted_proxies()

    def trusted(addr: str) -> bool:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        return any(ip in net for net in proxies)

    if not peer or not proxies or not trusted(peer):
        return peer or "anonymous"
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    for hop in reversed(hops):  # walk back from our proxy; the first untrusted hop is the client
        if not trusted(hop):
            return hop
    return peer


def _rate_limit_key(request: Request) -> str:
    """Bucket for a request: the signed-in principal, else the client address.

    Keyed on identity, a user's dashboard traffic is one bucket wherever it
    comes from, and host-local callers sharing the proxy's address (Hermes,
    cron, Kuma) no longer share one bucket once they authenticate. Each agent
    token (STORY-37) has its own bucket, apart from the person it acts for.
    """
    agent_token_id = getattr(request.state, "agent_token_id", None)
    if agent_token_id:
        return f"agent:{agent_token_id}"
    user_id = getattr(request.state, "user_id", None)
    if user_id and user_id != "anonymous":
        return f"user:{user_id}"
    return f"ip:{_client_address(request)}"


class RateLimitMiddleware(_MCPStreamBypassMixin, BaseHTTPMiddleware):
    """
    Enforces per-caller request-rate and cost limits.

    Uses ``realize_core.utils.rate_limiter.RateLimiter`` under the hood. The
    caller is the authenticated identity (auth runs before this middleware),
    else the client address (see :func:`_rate_limit_key`). A client-sent
    ``X-Tenant-ID`` is not trusted: it let anyone pick a fresh bucket (QA 5.14 S-3).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        try:
            from realize_core.utils.rate_limiter import get_rate_limiter

            limiter = get_rate_limiter(request.app)
            tenant = _rate_limit_key(request)

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
