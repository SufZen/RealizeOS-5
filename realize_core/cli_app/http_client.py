"""HTTP client for operator CLI commands.

All new CLI commands (chat, ask, kb, workflow, skill, evolution) talk
to a running RealizeOS API instance via HTTP.  This module provides
a small wrapper around ``httpx`` that picks up the active profile's
endpoint and API-key-env to build headers.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import httpx

from realize_core.cli_app.profiles import ProfileManager

logger = logging.getLogger(__name__)

_TIMEOUT = 60.0  # generous for long-running chat calls


def _resolve_api_key(profile_name: str | None = None) -> str:
    """Return the API key from the env-var specified in the active profile."""
    pm = ProfileManager()
    p = pm.get_profile(profile_name)
    key = os.environ.get(p.api_key_env, "")
    if not key:
        logger.warning(
            "API key env var '%s' is empty (profile: %s). Set it or use `realize-os config profile add` to configure.",
            p.api_key_env,
            p.name,
        )
    return key


def api_client(profile_name: str | None = None) -> httpx.Client:
    """Build an ``httpx.Client`` pointed at the active profile's endpoint."""
    pm = ProfileManager()
    p = pm.get_profile(profile_name)
    api_key = _resolve_api_key(profile_name)

    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key

    return httpx.Client(
        base_url=p.endpoint,
        headers=headers,
        timeout=_TIMEOUT,
    )


def api_get(
    path: str,
    *,
    profile: str | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """GET *path* from the active profile's endpoint. Returns parsed JSON."""
    with api_client(profile) as client:
        resp = client.get(path, params=params)
        if resp.status_code != 200:
            _handle_error(resp)
        return resp.json()


def api_post(
    path: str,
    *,
    profile: str | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    """POST *path* with JSON body. Returns parsed JSON."""
    with api_client(profile) as client:
        resp = client.post(path, json=json_body or {})
        if resp.status_code not in (200, 201):
            _handle_error(resp)
        return resp.json()


def _handle_error(resp: httpx.Response) -> None:
    """Print a user-friendly error and exit."""
    try:
        detail = resp.json().get("detail", resp.text)
    except (ValueError, KeyError):
        detail = resp.text
    print(f"Error {resp.status_code}: {detail}", file=sys.stderr)
    sys.exit(1)
