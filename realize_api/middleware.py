"""
API Middleware: Authentication and request processing.
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Simple API key authentication middleware."""

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health endpoints and docs
        if request.url.path in ("/health", "/status", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        # Check API key
        auth_header = request.headers.get("Authorization", "")
        api_key_header = request.headers.get("X-API-Key", "")
        query_key = request.query_params.get("api_key", "")

        provided_key = ""
        if auth_header.startswith("Bearer "):
            provided_key = auth_header[7:]
        elif api_key_header:
            provided_key = api_key_header
        elif query_key:
            provided_key = query_key

        if provided_key != self.api_key:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid or missing API key"},
            )

        return await call_next(request)
