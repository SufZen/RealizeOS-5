"""
Web Tools: Search the web and fetch/read web pages.

Two capabilities:
1. web_search — Search the web using Brave Search API
2. web_fetch — Fetch a URL and extract clean readable content

Architecture Note:
    This module contains the raw implementation functions and Pydantic
    schemas.  The ``BaseTool`` interface is provided by
    ``realize_core.tools.web_tool.WebTool``, which delegates to these
    functions.  This split pattern allows unit-testing the logic
    independently of the tool registry interface.
"""

import ipaddress
import logging
import os
import re
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# SSRF protection
_BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data", "javascript"}


def _validate_url(url: str) -> str | None:
    """Validate URL for SSRF protection. Returns error or None if safe."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"

    scheme = (parsed.scheme or "").lower()
    if scheme in _BLOCKED_SCHEMES:
        return f"Blocked protocol: {scheme}://"
    if scheme not in ("http", "https", ""):
        return f"Unsupported protocol: {scheme}://"

    hostname = parsed.hostname or ""
    if not hostname:
        return "No hostname in URL"

    blocked_hosts = {"localhost", "metadata.google.internal", "169.254.169.254"}
    if hostname.lower() in blocked_hosts:
        return f"Blocked internal hostname: {hostname}"

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return f"Blocked private/internal IP: {hostname}"
    except ValueError:
        pass

    return None


BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": "RealizeOS/1.0"},
        )
    return _http_client


async def close_http_client():
    """Close the global HTTP client. Call during shutdown."""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


async def web_search(query: str, count: int = 5, freshness: str = None) -> list[dict]:
    """
    Search the web using Brave Search API.

    Args:
        query: Search query string.
        count: Number of results (1-20, default 5).
        freshness: Optional filter: "pd" (past day), "pw" (week), "pm" (month), "py" (year).

    Returns:
        List of result dicts: {title, url, description, age, extra_snippets}.
    """
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        return [{"error": "Brave Search API key not configured. Set BRAVE_API_KEY in .env"}]

    client = _get_http_client()
    params = {"q": query, "count": min(count, 20)}
    if freshness:
        params["freshness"] = freshness

    try:
        resp = await client.get(
            BRAVE_SEARCH_URL,
            params=params,
            headers={"Accept": "application/json", "Accept-Encoding": "gzip", "X-Subscription-Token": api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "age": item.get("age", ""),
                    "extra_snippets": item.get("extra_snippets", []),
                }
            )
        logger.info(f"Web search '{query}': {len(results)} results")
        return results
    except httpx.HTTPStatusError as e:
        logger.error(f"Brave Search HTTP error: {e.response.status_code}")
        return [{"error": f"Search API error: {e.response.status_code}"}]
    except Exception as e:
        logger.error(f"Web search error: {e}", exc_info=True)
        return [{"error": f"Search failed: {str(e)[:200]}"}]


# ---------------------------------------------------------------------------
# Web Fetch
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\n{3,}")


def _simple_html_to_text(html: str) -> str:
    """Basic HTML-to-text fallback when trafilatura is not available."""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(br|p|div|h[1-6]|li|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    text = _WHITESPACE_RE.sub("\n\n", text).strip()
    return text


async def web_fetch(url: str, max_chars: int = 8000, extract_mode: str = "auto") -> dict:
    """
    Fetch a URL and return its content as clean readable text.

    Args:
        url: The URL to fetch.
        max_chars: Maximum characters to return (default 8000).
        extract_mode: "auto", "trafilatura", "simple", or "raw".

    Returns:
        Dict with {url, title, content, content_length, truncated}.
    """
    # SSRF protection
    url_error = _validate_url(url)
    if url_error:
        return {"error": f"URL blocked: {url_error}", "url": url}

    client = _get_http_client()
    try:
        resp = await client.get(
            url,
            headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"},
        )
        resp.raise_for_status()
        html = resp.text
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        content = ""
        if extract_mode in ("auto", "trafilatura"):
            try:
                import trafilatura

                content = (
                    trafilatura.extract(
                        html,
                        include_links=True,
                        include_tables=True,
                        favor_recall=True,
                        url=url,
                    )
                    or ""
                )
            except ImportError:
                content = _simple_html_to_text(html) if extract_mode == "auto" else ""
            except Exception:
                content = _simple_html_to_text(html)
        elif extract_mode == "simple":
            content = _simple_html_to_text(html)
        elif extract_mode == "raw":
            content = html
        else:
            content = _simple_html_to_text(html)
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars] + "\n\n[...truncated]"
        return {"url": url, "title": title, "content": content, "content_length": len(content), "truncated": truncated}
    except httpx.HTTPStatusError as e:
        return {"url": url, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"url": url, "error": f"Fetch failed: {str(e)[:200]}"}


# ---------------------------------------------------------------------------
# Claude Tool Schemas + Registry
# ---------------------------------------------------------------------------

WEB_TOOL_SCHEMAS = [
    {
        "name": "web_search",
        "description": "Search the web using Brave Search. Returns titles, URLs, and descriptions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "count": {"type": "integer", "description": "Number of results (1-20, default 5).", "default": 5},
                "freshness": {
                    "type": "string",
                    "enum": ["pd", "pw", "pm", "py"],
                    "description": "Freshness filter: pd/pw/pm/py or omit for all time.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": "Fetch a web page and extract readable content as clean text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch."},
                "max_chars": {"type": "integer", "description": "Max characters (default 8000).", "default": 8000},
            },
            "required": ["url"],
        },
    },
]

TOOL_FUNCTIONS = {"web_search": web_search, "web_fetch": web_fetch}
WEB_READ_TOOLS = {"web_search", "web_fetch"}
WEB_WRITE_TOOLS: set[str] = set()
