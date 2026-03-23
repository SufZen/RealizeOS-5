"""
Centralized error types and exception handlers for the RealizeOS API.

Provides:
- Custom exception classes with HTTP status codes
- Structured JSON error responses
- Exception handlers for FastAPI registration
- API-key masking utility for safe logging
"""

import logging
import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception classes
# ---------------------------------------------------------------------------


class RealizeError(Exception):
    """Base exception for all RealizeOS API errors."""

    status_code: int = 500
    error_type: str = "internal_error"

    def __init__(self, detail: str = "Internal server error", **kwargs):
        self.detail = detail
        self.extra = kwargs
        super().__init__(detail)


class RealizeValidationError(RealizeError):
    """Input validation failure — 422."""

    status_code = 422
    error_type = "validation_error"

    def __init__(self, detail: str = "Validation error", field: str = "", **kwargs):
        self.field = field
        super().__init__(detail, **kwargs)


class RealizeNotFoundError(RealizeError):
    """Resource not found — 404."""

    status_code = 404
    error_type = "not_found"

    def __init__(self, resource: str = "Resource", identifier: str = "", **kwargs):
        detail = f"{resource} not found" + (f": {identifier}" if identifier else "")
        super().__init__(detail, **kwargs)


class RealizeRateLimitError(RealizeError):
    """Rate limit exceeded — 429."""

    status_code = 429
    error_type = "rate_limit_exceeded"

    def __init__(self, retry_after: int = 60, **kwargs):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s", **kwargs)


class RealizeAuthError(RealizeError):
    """Authentication failure — 401."""

    status_code = 401
    error_type = "authentication_error"

    def __init__(self, detail: str = "Authentication required", **kwargs):
        super().__init__(detail, **kwargs)


class RealizePermissionError(RealizeError):
    """Authorization failure — 403."""

    status_code = 403
    error_type = "permission_denied"

    def __init__(self, detail: str = "Insufficient permissions", **kwargs):
        super().__init__(detail, **kwargs)


class RealizeConfigError(RealizeError):
    """Configuration error — 503."""

    status_code = 503
    error_type = "configuration_error"

    def __init__(self, detail: str = "System not configured", **kwargs):
        super().__init__(detail, **kwargs)


# ---------------------------------------------------------------------------
# Structured error response builder
# ---------------------------------------------------------------------------


def _error_response(status_code: int, error_type: str, detail: str, **extra) -> JSONResponse:
    """Build a consistent JSON error response."""
    body: dict = {
        "error": detail,
        "type": error_type,
    }
    if extra:
        body["detail"] = extra
    return JSONResponse(status_code=status_code, content=body)


# ---------------------------------------------------------------------------
# Exception handlers (register these on the FastAPI app)
# ---------------------------------------------------------------------------


async def handle_realize_error(request: Request, exc: RealizeError) -> JSONResponse:
    """Handle all RealizeError subclasses."""
    log_method = logger.warning if exc.status_code < 500 else logger.error
    log_method(
        "[%s] %s %s → %d %s",
        exc.error_type,
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    resp = _error_response(exc.status_code, exc.error_type, exc.detail)

    # Add Retry-After header for rate limit errors
    if isinstance(exc, RealizeRateLimitError):
        resp.headers["Retry-After"] = str(exc.retry_after)

    return resp


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic / FastAPI validation errors with structured output."""
    errors = exc.errors()
    detail = "; ".join(
        f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg', 'invalid')}"
        for e in errors
    )
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, detail)
    return _error_response(422, "validation_error", detail)


async def handle_generic_error(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors — log full trace, return safe message."""
    logger.error(
        "Unhandled error on %s %s: %s",
        request.method,
        request.url.path,
        mask_sensitive(str(exc)),
        exc_info=True,
    )
    return _error_response(500, "internal_error", "Internal server error")


def register_error_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on a FastAPI app."""
    app.add_exception_handler(RealizeError, handle_realize_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_generic_error)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

# Patterns that look like API keys / secrets
_SECRET_PATTERNS = [
    re.compile(r"(sk-ant-api\d{2}-)\S+", re.IGNORECASE),  # Anthropic
    re.compile(r"(sk-proj-)\S+", re.IGNORECASE),  # OpenAI
    re.compile(r"(AIza)\S+", re.IGNORECASE),  # Google
    re.compile(r"(Bearer\s+)\S+", re.IGNORECASE),  # Bearer tokens
    re.compile(r"(REALIZE_API_KEY=)\S+", re.IGNORECASE),
    re.compile(r"(REALIZE_JWT_SECRET=)\S+", re.IGNORECASE),
]


def mask_sensitive(text: str) -> str:
    """Mask API keys and secrets in text, keeping only last 4 chars."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + "***" + m.group(0)[-4:], text)
    return text
