"""Sign-in page that finishes an MCP OAuth authorize request (issue #21).

``/authorize`` (from the MCP SDK) parks the request and redirects here. The
user signs in with their ``users.yaml`` email and password and allows (or
denies) the connection; we then send them back to the client with a code.

This is a small server-rendered page, not part of the dashboard SPA, so it
works for any OAuth client without a build step. Failed sign-ins are
audited and limited per client IP.
"""

from __future__ import annotations

import html
import logging
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

logger = logging.getLogger(__name__)

#: Failed sign-ins allowed per client IP (and per account, see below) inside
#: :data:`_FAIL_WINDOW` seconds. The per-account limit stops a slow guess
#: spread over many IPs; the per-IP one stops one source trying many accounts.
#: Behind a reverse proxy, run uvicorn with ``--proxy-headers`` (and
#: ``--forwarded-allow-ips``) so the IP is the real client, not the proxy.
MAX_FAILED_SIGNINS = 10
#: Higher than the per-IP limit, so no single IP can lock someone's account:
#: locking it takes failures from at least three IPs. At 30 guesses per
#: 15 minutes, guessing a password online is still far too slow to work.
MAX_FAILED_PER_ACCOUNT = 30
_FAIL_WINDOW = 15 * 60
#: Cap on tracked keys so a flood of made-up emails can't grow memory forever.
_MAX_TRACKED = 10_000
_failures: dict[str, deque[float]] = defaultdict(deque)

_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
}


def routes() -> list[Route]:
    """Starlette routes for the sign-in page."""
    from realize_core.mcp_server.oauth import LOGIN_PATH

    return [Route(LOGIN_PATH, endpoint=oauth_login, methods=["GET", "POST"])]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _keys(ip: str, email: str) -> list[str]:
    keys = [f"ip:{ip}"]
    if email:
        keys.append(f"account:{email.strip().lower()}")
    return keys


def _recent(key: str) -> int:
    """Failures for ``key`` still inside the window (expired ones are dropped)."""
    attempts = _failures.get(key)
    if not attempts:
        return 0
    cutoff = time.monotonic() - _FAIL_WINDOW
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    if not attempts:
        del _failures[key]
        return 0
    return len(attempts)


def _too_many_failures(ip: str, email: str) -> bool:
    return any(
        _recent(key) >= (MAX_FAILED_PER_ACCOUNT if key.startswith("account:") else MAX_FAILED_SIGNINS)
        for key in _keys(ip, email)
    )


def _record_failure(ip: str, email: str) -> None:
    keys = _keys(ip, email)
    if len(_failures) + len(keys) > _MAX_TRACKED:
        for key in list(_failures):
            _recent(key)
        # Still full of live entries: drop the keys that failed longest ago.
        while _failures and len(_failures) + len(keys) > _MAX_TRACKED:
            del _failures[min(_failures, key=lambda k: _failures[k][-1])]
    now = time.monotonic()
    for key in keys:
        _failures[key].append(now)


def _audit(user_id: str, action: str, outcome: str, ip: str, client_id: str) -> None:
    try:
        from realize_core.security.audit import get_audit_logger

        get_audit_logger().log(
            user_id=user_id,
            action=action,
            outcome=outcome,
            channel="mcp",
            ip_address=ip,
            severity="info" if outcome == "success" else "warning",
            metadata={"client_id": client_id},
        )
    except Exception as exc:
        logger.debug("Audit log for %s skipped: %s", action, exc)


async def oauth_login(request: Request) -> Response:
    """GET shows the sign-in form; POST signs in and allows or denies."""
    provider = getattr(request.app.state, "mcp_oauth", None)
    if provider is None:
        return _page("Not available", "<p>OAuth sign-in is not enabled on this RealizeOS.</p>", status=404)

    if request.method == "GET":
        pending = await provider.get_pending(request.query_params.get("request", ""))
        if pending is None:
            return _expired()
        return _form(pending)

    form = await request.form()
    pending = await provider.get_pending(str(form.get("request", "")))
    if pending is None:
        return _expired()
    ip = _client_ip(request)
    client_id = pending.client.client_id or ""

    if form.get("action") != "allow":
        _audit("anonymous", "mcp_oauth_denied", "denied", ip, client_id)
        return RedirectResponse(provider.deny(pending), status_code=302, headers=_HEADERS)

    email = str(form.get("email", "")).strip()
    if _too_many_failures(ip, email):
        logger.warning("MCP OAuth sign-in locked for %s / %s: too many failed attempts", ip, email.lower())
        _audit((email or "unknown").lower(), "mcp_oauth_login_locked", "denied", ip, client_id)
        return _form(pending, error="Too many failed sign-ins. Try again in 15 minutes.", status=429)

    from realize_core.security.users import verify_password

    user = verify_password(email, str(form.get("password", "")))
    if user is None:
        _record_failure(ip, email)
        _audit((email or "unknown").lower(), "mcp_oauth_login_failed", "error", ip, client_id)
        return _form(pending, error="Email or password is wrong.", email=email, status=401)

    # A success clears the account's count, not the IP's: one valid account
    # mustn't reset the limit for an IP that is guessing at others.
    _failures.pop(f"account:{user.email}", None)
    redirect = await provider.approve(pending, user.email)
    if redirect is None:
        return _expired()
    _audit(user.email, "mcp_oauth_authorized", "success", ip, client_id)
    logger.info("MCP OAuth: %s connected client %s", user.email, client_id)
    return RedirectResponse(redirect, status_code=302, headers=_HEADERS)


def _expired() -> Response:
    return _page(
        "Link expired",
        "<p>This sign-in link has expired or was already used. Start the connection again from your app.</p>",
        status=400,
    )


def _form(pending, *, error: str = "", email: str = "", status: int = 200) -> Response:
    client = pending.client
    name = html.escape(client.client_name or "An MCP client")
    redirect_host = html.escape(urlparse(str(pending.params.redirect_uri)).hostname or str(pending.params.redirect_uri))
    error_html = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ""
    body = f"""
      <p><strong>{name}</strong> wants to connect to RealizeOS as you.</p>
      <p class="muted">After you allow it, you will be sent back to <strong>{redirect_host}</strong>.
      It gets the same access you have: your role and your ventures.</p>
      {error_html}
      <form method="post">
        <input type="hidden" name="request" value="{html.escape(pending.request_id)}">
        <label>Email<input type="email" name="email" value="{html.escape(email)}" autocomplete="username" required></label>
        <label>Password<input type="password" name="password" autocomplete="current-password" required></label>
        <div class="actions">
          <button type="submit" name="action" value="allow">Sign in and allow</button>
          <button type="submit" name="action" value="deny" class="secondary" formnovalidate>Deny</button>
        </div>
      </form>
    """
    return _page("Connect to RealizeOS", body, status=status)


def _page(title: str, body: str, *, status: int = 200) -> HTMLResponse:
    page = f"""<!DOCTYPE html>
<html lang="en" dir="auto"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; --fg:#111; --bg:#f7f7f8; --card:#fff; --muted:#555; --accent:#2b59c3; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --fg:#eee; --bg:#111318; --card:#1b1e25; --muted:#aaa; --accent:#7aa2ff; }} }}
  body {{ font-family: system-ui, sans-serif; background: var(--bg); color: var(--fg); margin: 0; padding: 48px 16px; }}
  main {{ max-width: 420px; margin: 0 auto; background: var(--card); border-radius: 12px; padding: 28px; }}
  h1 {{ font-size: 1.3rem; margin: 0 0 16px; }}
  .muted {{ color: var(--muted); font-size: .92rem; }}
  .error {{ color: #c62828; }}
  label {{ display: block; margin: 14px 0 0; font-size: .92rem; }}
  input {{ display: block; width: 100%; box-sizing: border-box; margin-top: 4px; padding: 9px 10px; font: inherit; }}
  .actions {{ display: flex; gap: 10px; margin-top: 20px; }}
  button {{ font: inherit; padding: 9px 14px; border-radius: 8px; border: 0; background: var(--accent); color: #fff; cursor: pointer; }}
  button.secondary {{ background: transparent; color: var(--fg); border: 1px solid var(--muted); }}
</style></head>
<body><main><h1>{html.escape(title)}</h1>{body}</main></body></html>"""
    return HTMLResponse(page, status_code=status, headers=_HEADERS)
