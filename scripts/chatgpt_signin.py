"""Sign in with ChatGPT so RealizeOS can use the owner's ChatGPT plan.

Run on the machine that has a browser (the 127.0.0.1 callback must reach it),
then copy the credential file to the server over SSH. Commands:

    # Create the server's host ID once (here, in a folder you then copy to the server)
    python scripts/chatgpt_signin.py host-id --data <folder>

    # On your computer: sign in for that host, write the credential file
    python scripts/chatgpt_signin.py login --host-id urn:uuid:... --out chatgpt_plan.json

    # On your computer: list the models this plan allows
    python scripts/chatgpt_signin.py models --creds chatgpt_plan.json

    # Anywhere: one short test request
    python scripts/chatgpt_signin.py check --creds chatgpt_plan.json --model <slug>

``login`` opens the browser, waits on http://127.0.0.1:<port>/auth/callback,
checks ``state``, trades the code for tokens and confirms the plan scope was
granted. The file is written with owner-only permissions. It holds live tokens:
never commit it, paste it or log it. Copy it only over SSH (scp).

Exit status: 0 on success, 1 on failure.
"""

from __future__ import annotations

import argparse
import asyncio
import http.server
import json
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from realize_core.llm import chatgpt_plan  # noqa: E402

MODELS_URL = "https://api.openai.com/v1/models"


class CallbackServer:
    """Listens on 127.0.0.1:<port>/auth/callback; bound before the browser opens.

    Accepts only a callback whose ``state`` matches this sign-in (or an OAuth
    error for it); anything else gets 400 and the wait goes on. Each connection
    has a socket timeout, and the whole wait is bounded.
    """

    def __init__(self, port: int, state: str):
        self.result: dict[str, str] = {}
        self.done = threading.Event()
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            timeout = 10  # seconds per connection: a stalled client cannot block shutdown

            def do_GET(self):
                url = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                if url.path != chatgpt_plan.CALLBACK_PATH or query.get("state") != state:
                    self.send_response(400)
                    self.end_headers()
                    return
                outer.result.update(query)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<p>Received. You can close this tab and go back to the terminal.</p>")
                outer.done.set()

            def log_message(self, *args):  # keep codes and tokens out of the terminal
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
        self.thread.start()

    def wait(self, timeout: float) -> dict[str, str]:
        try:
            if not self.done.wait(timeout):
                raise SystemExit("No sign-in within the time limit.")
            return dict(self.result)
        finally:
            self.server.shutdown()
            self.server.server_close()


def cmd_host_id(args) -> int:
    base = Path(args.data) if args.data else None
    print(chatgpt_plan.host_id(base))
    return 0


def _inside_git_checkout(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in path.resolve().parents)


def cmd_login(args) -> int:
    out = Path(args.out)
    if _inside_git_checkout(out):
        print("Refusing to write live tokens inside a git checkout. Use --out in a private folder (e.g. %TEMP%).")
        return 1
    previous = chatgpt_plan.load_credentials(out) if out.exists() else None
    client_id = previous.client_id if previous else None
    request = chatgpt_plan.build_authorize_request(args.host_id, port=args.port, client_id=client_id)

    try:
        listener = CallbackServer(args.port, request.state)  # bind first, then open the browser
    except OSError as e:
        print(f"Port {args.port} is not free on 127.0.0.1 ({e.strerror}). Try --port with another number.")
        return 1
    print("Opening the browser to sign in with ChatGPT. If it does not open, paste this URL:")
    print(request.url)
    webbrowser.open(request.url)
    query = listener.wait(args.timeout)

    if query.get("error"):
        print(f"Sign-in stopped: {query['error']}")
        return 1
    issued = query.get("client_id") or client_id
    if request.first_registration and not query.get("client_id"):
        print("Sign-in incomplete: no client ID was issued.")
        return 1
    if client_id and query.get("client_id") and query["client_id"] != client_id:
        print("Sign-in rejected: a different client ID came back.")
        return 1
    try:
        creds = chatgpt_plan.exchange_code(
            request,
            query.get("code", ""),
            issued,
            args.host_id,
            expected_subject=previous.subject if previous else None,
        )
    except chatgpt_plan.TokenError as e:
        print(f"Sign-in failed: {e.code}")
        return 1
    chatgpt_plan.save_credentials(creds, out)
    print(f"Signed in as {creds.email or 'your ChatGPT account'}. Credential file: {out}")
    print("Copy it to the server with scp, into DATA_PATH as chatgpt_plan.json. Do not commit or paste it.")
    return 0


def cmd_models(args) -> int:
    import httpx

    token = chatgpt_plan.valid_access_token(Path(args.creds))
    response = httpx.get(MODELS_URL, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if response.status_code != 200:
        print(f"Could not list models: HTTP {response.status_code}")
        return 1
    body = response.json()
    rows = body.get("models") or body.get("data") or []
    for m in rows:
        if m.get("visibility", "list") == "list":
            print(f"{m.get('slug') or m.get('id')}\t{m.get('display_name', '')}")
    return 0


def cmd_check(args) -> int:
    import os

    from realize_core.llm.providers.chatgpt_plan_provider import ChatGPTPlanProvider

    os.environ["CHATGPT_PLAN_MODEL"] = args.model
    provider = ChatGPTPlanProvider(credentials_file=Path(args.creds))
    response = asyncio.run(
        provider.complete("Answer in one short sentence.", [{"role": "user", "content": "Say hello."}])
    )
    if response.ok:
        print(json.dumps({"ok": True, "model": response.model, "text": response.text[:200]}, ensure_ascii=False))
        return 0
    print(json.dumps({"ok": False, "error": response.error}))
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("host-id", help="print (and create once) this host's ID")
    p.add_argument("--data", help="data folder (default DATA_PATH)")
    p.set_defaults(func=cmd_host_id)

    p = sub.add_parser("login", help="browser sign-in; writes the credential file")
    p.add_argument("--host-id", required=True, help="the server's host ID (from host-id)")
    p.add_argument("--out", required=True, help="where to write the credential file (outside any git checkout)")
    p.add_argument("--port", type=int, default=chatgpt_plan.DEFAULT_PORT)
    p.add_argument("--timeout", type=float, default=300.0)
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("models", help="list the models this plan allows")
    p.add_argument("--creds", default="chatgpt_plan.json")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("check", help="one short test request")
    p.add_argument("--creds", default="chatgpt_plan.json")
    p.add_argument("--model", required=True)
    p.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
