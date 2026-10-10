"""
Outbound URL guard — prevents server-side request forgery (SSRF).

Anything that fetches a URL supplied by a user or an agent (KB ingestion,
web tools) must go through :func:`guarded_get`. It only allows http(s),
resolves the host, and refuses addresses on the server's own network:
loopback, private ranges, link-local (including cloud metadata such as
169.254.169.254), multicast, reserved and unspecified. Redirects are
followed manually so every hop is checked.

Self-hosters who deliberately ingest intranet pages can allow *private*
ranges with ``ingestion.allow_private_urls: true`` in ``realize-os.yaml``.
Loopback, link-local/metadata and the other special ranges stay blocked
even then.

Limitation: the check resolves DNS before httpx connects, so a hostile DNS
server could still rebind between the two lookups. This guard removes the
direct attack (a URL naming an internal host or IP), which is what CodeQL
``py/full-ssrf`` reports.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlsplit

import httpx

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = {"http", "https"}
_REDIRECT_CODES = {301, 302, 303, 307, 308}

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class UnsafeURLError(ValueError):
    """Raised when a URL targets a scheme or address that must not be fetched."""


def _is_forbidden(ip: IPAddress, *, allow_private: bool) -> bool:
    """Return True when *ip* must never be contacted.

    ``allow_private`` relaxes only RFC 1918 / ULA ranges; loopback,
    link-local (cloud metadata), multicast, reserved and unspecified
    addresses are always refused.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    return ip.is_private and not allow_private


def _resolve(host: str) -> list[IPAddress]:
    """Resolve *host* to all of its IP addresses (blocking)."""
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Cannot resolve host '{host}'") from exc
    return [ipaddress.ip_address(info[4][0].split("%", 1)[0]) for info in infos]


def check_url(url: str, *, allow_private: bool = False) -> None:
    """Validate *url* for outbound fetching, raising :class:`UnsafeURLError`.

    Args:
        url: Absolute URL to check.
        allow_private: Permit private (RFC 1918 / ULA) addresses.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeURLError("Only http and https URLs can be fetched")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    for ip in _resolve(host):
        if _is_forbidden(ip, allow_private=allow_private):
            raise UnsafeURLError(f"Refusing to fetch '{host}': it resolves to a non-public address")


async def guarded_get(
    url: str,
    *,
    allow_private: bool = False,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    max_redirects: int = 5,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.Response:
    """GET *url*, checking the target (and every redirect hop) first.

    Raises:
        UnsafeURLError: The URL, or a redirect target, is not allowed.
        httpx.HTTPError: Network or protocol failure.

    ``transport`` is a test seam (e.g. ``httpx.MockTransport``).
    """
    current = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport) as client:
        for _ in range(max_redirects + 1):
            await asyncio.to_thread(check_url, current, allow_private=allow_private)
            resp = await client.get(current, headers=headers)
            location = resp.headers.get("location")
            if resp.status_code not in _REDIRECT_CODES or not location:
                return resp
            current = urljoin(current, location)
    raise UnsafeURLError(f"Too many redirects (>{max_redirects})")
