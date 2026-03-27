"""
Standardized API response helpers for consistent envelope format.

Usage:
    from realize_api.response import api_response, api_error

    @router.get("/example")
    async def example():
        return api_response({"items": [1, 2, 3]}, message="Fetched successfully")
"""

from __future__ import annotations

from typing import Any


def api_response(
    data: Any = None,
    *,
    message: str | None = None,
) -> dict:
    """
    Wrap data in a standardized success envelope.

    Returns:
        {"success": True, "data": <data>, "message": <optional>}
    """
    result: dict[str, Any] = {"success": True, "data": data}
    if message:
        result["message"] = message
    return result


def api_error(
    error: str,
    *,
    detail: Any = None,
) -> dict:
    """
    Build a standardized error envelope (for use in error handlers).

    Returns:
        {"success": False, "error": <error>, "detail": <optional>}
    """
    result: dict[str, Any] = {"success": False, "error": error}
    if detail is not None:
        result["detail"] = detail
    return result
