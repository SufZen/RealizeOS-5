#!/usr/bin/env python3
"""Production smoke test: run the image the way docker-compose.prod.yml does, then check it.

The container gets what the production compose file gives it: a read-only
root filesystem, a ``/tmp`` tmpfs, ``no-new-privileges``, named volumes for
``/app/data`` and ``/app/shared``, ``realize-os.yaml`` and ``.credentials``
bind-mounted read-only, ``systems/`` and ``packs-custom/`` bind-mounted
writable, and production settings (``REALIZE_ENV=production``, an API key,
JWT on with a strong secret, CORS origins). The secrets are generated for
each run and never written to disk.

Then, from this machine (stdlib only: urllib, subprocess):

1. ``/api/health`` is ``ok``; the API refuses a request without credentials;
   the API key, a JWT minted with it, and a dashboard sign-in all work.
2. Creating a venture is refused cleanly (``realize-os.yaml`` is read-only)
   and a venture file is written under the writable ``systems/`` mount.
3. A market pack review runs in the container the documented way (copy the
   shipped pack into ``REALIZE_PACKS_PATH``, ``packs review-sheet``,
   ``packs review-submit``); the owner approves the ``pack_verify`` request
   over the API; the approval's ``execution_status`` is ``succeeded`` and
   ``DATA_PATH/packs/verification.json`` is in the data volume.
4. ``POST /api/storage/export`` works with only ``/tmp`` writable and carries
   the verification state, the custom pack and the venture file, and no secret.
5. The container is restarted, then recreated from the image on the same
   volumes; each time the database rows, the sign-in session, the pack levels
   (``packs inventory --compare``) and the venture file are still there.
6. The container logs show no write refused by the read-only filesystem.

Usage::

    docker build -t realizeos-5:smoke .
    python scripts/prod_smoke.py --image realizeos-5:smoke

Exits 0 when every check passes, 1 otherwise (with the container log).
Needs Docker (a Linux engine). Everything it creates (container, volumes, a
temp folder) is removed at the end unless ``--keep`` is given.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any

VENTURE = "acme"
PACK = "pt"
OWNER_EMAIL = "owner@smoke.realizeos.test"
REVIEWER = "Smoke Reviewer, CI check (0000)"
#: The container's tmpfs (the only writable path outside the mounts), not a host temp folder.
CONTAINER_TMP = "/tmp"  # noqa: S108
SHEET = f"{CONTAINER_TMP}/sheet.csv"
FILLED = f"{CONTAINER_TMP}/filled.csv"
CONFIG_YAML = f"""\
name: "Production smoke"
systems:
  - key: {VENTURE}
    name: "Acme Build"
    directory: systems/{VENTURE}
features:
  packs: true
"""

#: Log lines that mean something tried to write outside the writable mounts.
READ_ONLY_FAILURES = ("read-only file system", "[errno 30]", "[errno 13]", "permissionerror")

#: Copy the shipped pack into the writable pack folder (as docs/packs.md says to change one).
COPY_PACK = (
    "import os, shutil; from realize_core.packs.loader import default_packs_root; "
    f"shutil.copytree(default_packs_root() / 'market' / '{PACK}', "
    f"os.path.join(os.environ['REALIZE_PACKS_PATH'], 'market', '{PACK}'), "
    "ignore=shutil.ignore_patterns('reviews'))"
)

#: A reviewer who marks every row correct (what a filled sheet looks like).
FILL_SHEET = """
import csv, io, sys
text = open(sys.argv[1], encoding='utf-8-sig').read()
head = text.split('\\n', 1)[0]
delimiter = ';' if head.count(';') > head.count(',') else ','
rows = list(csv.reader(io.StringIO(text, newline=''), delimiter=delimiter))
header, body = rows[0], rows[1:]
for row in body:
    row[header.index('verdict')] = 'correct'
    row[header.index('facts_corrected')] = '0'
out = io.StringIO()
csv.writer(out, delimiter=delimiter, lineterminator='\\r\\n').writerows([header, *body])
open(sys.argv[2], 'w', encoding='utf-8-sig', newline='').write(out.getvalue())
"""

#: Read the verification state straight from the data volume (another container, read-only mount).
READ_STATE = (
    "import json; s = json.load(open('/data/packs/verification.json', encoding='utf-8')); "
    f"print(json.dumps(s['packs']['market/{PACK}']['pack']))"
)


class SmokeError(Exception):
    """A check failed; the message says which and why."""


def check(condition: bool, message: str) -> None:
    """Fail the smoke test with ``message`` unless ``condition`` holds."""
    if not condition:
        raise SmokeError(message)


def ok(message: str) -> None:
    """Report one passed check."""
    print(f"ok - {message}", flush=True)


class Response:
    """An HTTP response: status, headers and body."""

    def __init__(self, status: int, headers: dict[str, list[str]], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body

    def json(self) -> Any:
        """The body parsed as JSON."""
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        """The body as text (for failure messages)."""
        return self.body.decode("utf-8", errors="replace")[:2000]


def http(
    method: str, url: str, *, headers: dict[str, str] | None = None, body: Any = None, timeout: float = 60
) -> Response:
    """One HTTP request with urllib; HTTP errors come back as responses, not exceptions."""
    data = None
    all_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        all_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=all_headers)  # noqa: S310 — local http
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as res:
            return Response(res.status, _headers(res.headers), res.read())
    except urllib.error.HTTPError as exc:
        return Response(exc.code, _headers(exc.headers), exc.read())


def _headers(message: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, value in message.items():
        out.setdefault(key.lower(), []).append(value)
    return out


class Smoke:
    """One smoke run: a temp folder, two volumes, one container (recreated once)."""

    def __init__(self, image: str, *, keep: bool = False, startup_timeout: float = 120) -> None:
        self.image = image
        self.keep = keep
        self.startup_timeout = startup_timeout
        suffix = uuid.uuid4().hex[:10]
        self.name = f"realizeos-smoke-{suffix}"
        self.volumes = {"data": f"realizeos-smoke-{suffix}-data", "shared": f"realizeos-smoke-{suffix}-shared"}
        self.work = Path(tempfile.mkdtemp(prefix="realizeos-prod-smoke-")).resolve()
        self.base = ""
        self.api_key = secrets.token_urlsafe(48)
        self.jwt_secret = secrets.token_urlsafe(48)
        self.password = secrets.token_urlsafe(24)
        self.password_hash = ""
        self.session = ""
        self.marker = f"Crane booked for Tuesday ({secrets.token_hex(8)})."
        self.approval_id = ""
        self.inventory = ""
        self.running = False

    # -- docker -------------------------------------------------------------

    def docker(
        self, *args: str, input_text: str | None = None, check_rc: bool = True, timeout: float = 300
    ) -> subprocess.CompletedProcess:
        """Run a docker command; secrets reach it through the environment, never the arguments."""
        env = {
            **os.environ,
            "REALIZE_API_KEY": self.api_key,
            "REALIZE_JWT_SECRET": self.jwt_secret,
            "REALIZE_ADMIN_PASSWORD_HASH": self.password_hash,
        }
        result = subprocess.run(
            ["docker", *args],
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            check=False,
        )
        if check_rc and result.returncode != 0:
            raise SmokeError(f"docker {' '.join(args[:3])} failed ({result.returncode}): {result.stderr[-2000:]}")
        return result

    def exec(self, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess:
        """Run a command inside the container, as its user, with its environment."""
        interactive = ["-i"] if input_text is not None else []
        return self.docker("exec", *interactive, self.name, *args, input_text=input_text, check_rc=False)

    def prepare(self) -> None:
        """Write the host side of the deployment and hash the dashboard password."""
        self.docker("version", "--format", "{{.Server.Version}}")
        (self.work / "realize-os.yaml").write_text(CONFIG_YAML, encoding="utf-8")
        venture = self.work / "systems" / VENTURE
        (venture / "F-foundations").mkdir(parents=True)
        (venture / "A-agents").mkdir()
        (venture / "F-foundations" / "venture-identity.md").write_text("# Acme Build\nTowers.\n", encoding="utf-8")
        (venture / "packs.yaml").write_text(f"market: [{PACK}]\n", encoding="utf-8")
        (self.work / ".credentials").mkdir()
        (self.work / "packs-custom").mkdir()
        # The container runs as uid 1000; the host folders it writes must allow that.
        for root in (self.work / "systems", self.work / "packs-custom"):
            for path in [root, *root.rglob("*")]:
                path.chmod(0o777 if path.is_dir() else 0o666)
        hashed = self.docker(
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            self.image,
            "python",
            "-c",
            "import bcrypt, sys; print(bcrypt.hashpw(sys.stdin.read().strip().encode(), bcrypt.gensalt()).decode())",
            input_text=self.password,
        )
        self.password_hash = hashed.stdout.strip()
        check(self.password_hash.startswith("$2"), "bcrypt hash of the dashboard password")
        for volume in self.volumes.values():
            self.docker("volume", "create", volume)
        ok(f"prepared {self.work} and volumes {', '.join(self.volumes.values())}")

    def start(self) -> None:
        """Run the container as docker-compose.prod.yml does and wait for /api/health."""
        w = self.work
        self.docker(
            "run",
            "-d",
            "--name",
            self.name,
            "--read-only",
            "--tmpfs",
            f"{CONTAINER_TMP}:size=256M",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            "2g",
            "-p",
            "127.0.0.1::8080",
            "-v",
            f"{self.volumes['data']}:/app/data",
            "-v",
            f"{self.volumes['shared']}:/app/shared",
            "-v",
            f"{w / 'realize-os.yaml'}:/app/realize-os.yaml:ro",
            "-v",
            f"{w / 'systems'}:/app/systems",
            "-v",
            f"{w / '.credentials'}:/app/.credentials:ro",
            "-v",
            f"{w / 'packs-custom'}:/app/packs-custom",
            "-e",
            "DATA_PATH=/app/data",
            "-e",
            "KB_PATH=/app",
            "-e",
            "REALIZE_HOST=0.0.0.0",
            "-e",
            "REALIZE_PORT=8080",
            "-e",
            "REALIZE_PACKS_PATH=/app/packs-custom",
            "-e",
            "REALIZE_ENV=production",
            "-e",
            "REALIZE_API_KEY",
            "-e",
            "REALIZE_JWT_ENABLED=true",
            "-e",
            "REALIZE_JWT_SECRET",
            "-e",
            "CORS_ORIGINS=https://smoke.realizeos.test",
            "-e",
            f"REALIZE_ADMIN_USER={OWNER_EMAIL}",
            "-e",
            "REALIZE_ADMIN_PASSWORD_HASH",
            self.image,
        )
        self.running = True
        self.wait_healthy()

    def wait_healthy(self) -> None:
        """Find the published port and wait until /api/health answers ``ok``."""
        port = self.docker("port", self.name, "8080/tcp").stdout.strip().splitlines()[0].rsplit(":", 1)[-1]
        self.base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + self.startup_timeout
        last = "no answer"
        while time.monotonic() < deadline:
            state = self.docker("inspect", "-f", "{{.State.Running}}", self.name).stdout.strip()
            check(state == "true", f"the container stopped during startup:\n{self.logs()[-4000:]}")
            try:
                res = http("GET", f"{self.base}/api/health", timeout=5)
                last = f"{res.status} {res.text()}"
                if res.status == 200:
                    check(res.json().get("status") == "ok", f"/api/health is not ok: {res.text()}")
                    ok(f"/api/health is ok on {self.base}")
                    return
            except OSError as exc:
                last = str(exc)
            time.sleep(1)
        raise SmokeError(f"/api/health did not answer in {self.startup_timeout:.0f}s ({last})")

    def logs(self) -> str:
        """The container's log so far (stdout and stderr)."""
        result = self.docker("logs", self.name, check_rc=False)
        return result.stdout + result.stderr

    def check_logs(self, when: str) -> None:
        """No write was refused by the read-only filesystem."""
        lines = [line for line in self.logs().splitlines() if any(p in line.lower() for p in READ_ONLY_FAILURES)]
        check(not lines, f"writes refused {when}:\n" + "\n".join(lines[:20]))
        ok(f"no write refused by the read-only filesystem ({when})")

    # -- checks -------------------------------------------------------------

    @property
    def owner(self) -> dict[str, str]:
        """Headers of the owner's API-key requests."""
        return {"X-API-Key": self.api_key}

    def check_auth(self) -> None:
        """Auth is on; API key, JWT and dashboard sign-in work."""
        res = http("GET", f"{self.base}/api/ventures")
        check(res.status == 401, f"an anonymous request should get 401, got {res.status}")
        res = http("GET", f"{self.base}/api/ventures", headers=self.owner)
        check(res.status == 200, f"API-key request failed: {res.status} {res.text()}")
        body = res.json()
        check([v["key"] for v in body["ventures"]] == [VENTURE], f"unexpected ventures: {body}")
        check(body.get("config_writable") is False, "realize-os.yaml should be reported read-only")
        ok("API key works; anonymous requests get 401; the config is reported read-only")

        res = http("POST", f"{self.base}/api/auth/token", body={"api_key": self.api_key, "user_id": "smoke-ci"})
        check(res.status == 200, f"JWT mint failed: {res.status} {res.text()}")
        jwt = res.json()["access_token"]
        res = http("GET", f"{self.base}/api/auth/me", headers={"Authorization": f"Bearer {jwt}"})
        check(res.status == 200 and res.json().get("user_id") == "smoke-ci", f"JWT rejected: {res.text()}")
        ok("a JWT minted with the API key is accepted")

        res = http("POST", f"{self.base}/api/auth/login", body={"email": OWNER_EMAIL, "password": self.password})
        check(res.status == 200, f"dashboard sign-in failed: {res.status} {res.text()}")
        cookies = res.headers.get("set-cookie", [])
        found = [m.group(1) for c in cookies if (m := re.match(r"realize_session=([^;]+)", c))]
        check(bool(found), f"no session cookie in {cookies}")
        self.session = found[0]
        self.check_session("after sign-in")

    def check_session(self, when: str) -> None:
        """The dashboard session (stored in the operational DB) is valid."""
        res = http("GET", f"{self.base}/api/auth/session", headers={"Cookie": f"realize_session={self.session}"})
        check(res.status == 200 and res.json().get("authenticated") is True, f"session lost {when}: {res.text()}")
        ok(f"dashboard session valid {when}")

    def check_ventures(self) -> None:
        """A venture can't be created (read-only config); a venture file can be written."""
        res = http("POST", f"{self.base}/api/ventures", headers=self.owner, body={"key": "beta"})
        check(res.status == 503, f"creating a venture should be refused with 503, got {res.status} {res.text()}")
        check(not (self.work / "systems" / "beta").exists(), "a refused venture left a folder behind")
        ok("venture creation is refused cleanly while realize-os.yaml is read-only")

        path = f"systems/{VENTURE}/B-brain/smoke-note.md"
        res = http(
            "POST",
            f"{self.base}/api/ventures/{VENTURE}/kb/file",
            headers=self.owner,
            body={"path": path, "content": self.marker},
        )
        check(res.status == 200, f"writing a venture file failed: {res.status} {res.text()}")
        self.check_venture_file("after writing it")

    def check_venture_file(self, when: str) -> None:
        """The venture file is readable through the API and on the host mount."""
        path = f"systems/{VENTURE}/B-brain/smoke-note.md"
        res = http("GET", f"{self.base}/api/ventures/{VENTURE}/kb/file?path={path}", headers=self.owner)
        check(res.status == 200 and self.marker in res.text(), f"venture file not readable {when}: {res.text()}")
        on_host = self.work / path
        check(on_host.is_file() and on_host.read_text(encoding="utf-8") == self.marker, f"venture file {when}")
        ok(f"venture file present {when}")

    def check_pack_review(self) -> None:
        """Review a pack in the container, approve the level change, find it in the data volume."""
        for label, args in (
            ("copy the shipped pack into REALIZE_PACKS_PATH", ("python", "-c", COPY_PACK)),
            ("export the review sheet", ("python", "cli.py", "packs", "review-sheet", PACK, "--out", SHEET)),
            ("fill the review sheet", ("python", "-c", FILL_SHEET, SHEET, FILLED)),
        ):
            result = self.exec(*args)
            check(result.returncode == 0, f"{label} failed: {result.stdout[-1500:]}{result.stderr[-1500:]}")
        result = self.exec(
            "python",
            "cli.py",
            "packs",
            "review-submit",
            PACK,
            "--sheet",
            FILLED,
            "--reviewer",
            REVIEWER,
            "--venture",
            VENTURE,
            "--whole-pack",
        )
        check(result.returncode == 0, f"review-submit failed: {result.stdout[-2000:]}{result.stderr[-2000:]}")
        queued = re.search(r"Approval queued: (\S+)", result.stdout)
        check(queued is not None, f"no approval id in: {result.stdout[-1500:]}")
        self.approval_id = queued.group(1)
        records = list((self.work / "packs-custom" / "market" / PACK / "reviews").glob("*.yaml"))
        check(len(records) == 1, f"expected one review record in the writable pack folder, found {records}")
        ok(f"pack review submitted in the container; pack_verify {self.approval_id} queued")

        res = http("GET", f"{self.base}/api/approvals?venture_key={VENTURE}", headers=self.owner)
        pending = [a for a in res.json().get("approvals", []) if a["id"] == self.approval_id]
        check(len(pending) == 1 and pending[0]["action_type"] == "pack_verify", f"not pending: {res.text()}")
        res = http("POST", f"{self.base}/api/approvals/{self.approval_id}/approve", headers=self.owner, body={})
        check(res.status == 200, f"approval failed: {res.status} {res.text()}")
        approval = res.json()
        check(approval.get("execution_status") == "succeeded", f"execution_status is not succeeded: {approval}")
        output = json.loads(approval.get("result_json") or "{}").get("output", "")
        check("raised to verification 2" in output, f"unexpected approval output: {output!r}")
        ok("the owner's approval applied the verification (execution_status succeeded)")
        self.check_state("after the approval")

        result = self.exec("python", "cli.py", "packs", "inventory")
        check(result.returncode == 0, f"packs inventory failed: {result.stderr[-1500:]}")
        inventory = json.loads(result.stdout)
        packs = {(p["kind"], p["id"]): p for p in inventory["packs"]}
        pack = packs.get(("market", PACK)) or {}
        check(pack.get("verification") == 2 and pack.get("source") == "custom", f"inventory shows {pack or inventory}")
        check(inventory["ventures"][VENTURE]["packs"][0]["verification"] == 2, "the venture doesn't resolve level 2")
        self.inventory = result.stdout
        ok(f"packs inventory: market/{PACK} from REALIZE_PACKS_PATH at verification 2")

    def check_state(self, when: str) -> None:
        """``DATA_PATH/packs/verification.json`` is in the data volume, with the approved level."""
        result = self.docker(
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{self.volumes['data']}:/data:ro",
            self.image,
            "python",
            "-c",
            READ_STATE,
            check_rc=False,
        )
        check(result.returncode == 0, f"verification.json not readable in the data volume {when}: {result.stderr}")
        state = json.loads(result.stdout)
        check(state.get("level") == 2 and state.get("approval_id") == self.approval_id, f"state {when}: {state}")
        ok(f"data volume holds packs/verification.json at level 2 {when}")

    def check_export(self) -> None:
        """The export is built in /tmp and carries the brain, the pack state and no secret."""
        res = http("POST", f"{self.base}/api/storage/export", headers=self.owner, timeout=120)
        check(res.status == 200, f"export failed: {res.status} {res.text()}")
        archive = zipfile.ZipFile(io.BytesIO(res.body))
        names = set(archive.namelist())
        for name in (
            "realize-os.yaml",
            f"systems/{VENTURE}/B-brain/smoke-note.md",
            "data/realize_data.db",
            "data/packs/verification.json",
            f"custom-packs/market/{PACK}/pack.yaml",
            "packs-inventory.json",
        ):
            check(name in names, f"{name} missing from the export")
        blob = b"".join(archive.read(n) for n in names)
        for label, value in (
            ("API key", self.api_key),
            ("JWT secret", self.jwt_secret),
            ("password hash", self.password_hash),
            ("session cookie", self.session),
        ):
            check(value.encode() not in blob, f"the {label} is in the export")
        ok(f"export built with only /tmp writable ({len(names)} files, no secrets)")

    def check_persisted(self, when: str) -> None:
        """What the first run wrote is still there."""
        self.check_venture_file(when)
        self.check_session(when)
        res = http("GET", f"{self.base}/api/approvals?status=approved&venture_key={VENTURE}", headers=self.owner)
        rows = [a for a in res.json().get("approvals", []) if a["id"] == self.approval_id]
        check(len(rows) == 1 and rows[0].get("execution_status") == "succeeded", f"approval {when}: {res.text()}")
        ok(f"approval row and its outcome persisted {when}")
        self.check_state(when)
        result = self.exec(
            "python", "cli.py", "packs", "inventory", "--compare", "/dev/stdin", input_text=self.inventory
        )
        check(result.returncode == 0, f"pack levels differ {when}: {result.stdout[-2000:]}{result.stderr[-1000:]}")
        ok(f"packs inventory identical {when}")
        decisions = [p for p in (self.work / "systems" / VENTURE / "B-brain" / "decisions").glob("*") if p.is_file()]
        logged = [p for p in decisions if self.approval_id in p.read_text(encoding="utf-8", errors="replace")]
        check(len(logged) == 1, f"expected the approval's decision in the venture, found {decisions}")
        ok(f"decision log entry present {when}")

    def run(self) -> None:
        """Every check, in order."""
        self.prepare()
        self.start()
        self.check_auth()
        self.check_ventures()
        self.check_pack_review()
        self.check_export()
        self.check_logs("in the first run")

        self.docker("restart", "--time", "20", self.name)
        self.wait_healthy()
        self.check_persisted("after docker restart")

        self.docker("rm", "-f", self.name)
        self.running = False
        self.start()
        self.check_persisted("after recreating the container")
        self.check_logs("after recreating the container")

    def cleanup(self) -> None:
        """Remove the container, the volumes and the temp folder (unless --keep)."""
        if self.keep:
            print(f"kept: container {self.name}, volumes {list(self.volumes.values())}, folder {self.work}")
            return
        self.docker("rm", "-f", self.name, check_rc=False)
        for volume in self.volumes.values():
            self.docker("volume", "rm", "-f", volume, check_rc=False)
        # Files the container wrote belong to its uid: remove them from inside a container.
        self.docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "0:0",
            "-v",
            f"{self.work}:/smoke",
            self.image,
            "sh",
            "-c",
            "rm -rf /smoke/systems /smoke/packs-custom",
            check_rc=False,
        )
        shutil.rmtree(self.work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    """Run the smoke test; 0 when every check passes."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--image", required=True, help="Image to test, e.g. realizeos-5:smoke")
    parser.add_argument("--keep", action="store_true", help="Leave the container, volumes and folder for debugging")
    parser.add_argument("--startup-timeout", type=float, default=120, help="Seconds to wait for /api/health")
    args = parser.parse_args(argv)
    if shutil.which("docker") is None:
        print("FAIL - docker is not on PATH", file=sys.stderr)
        return 1

    smoke = Smoke(args.image, keep=args.keep, startup_timeout=args.startup_timeout)
    try:
        smoke.run()
    except (SmokeError, subprocess.TimeoutExpired, OSError, ValueError, KeyError) as exc:
        print(f"FAIL - {exc}", file=sys.stderr, flush=True)
        if smoke.running:
            print("---- container log ----", file=sys.stderr)
            print(smoke.logs()[-8000:], file=sys.stderr, flush=True)
        return 1
    finally:
        smoke.cleanup()
    print("PASS - production smoke test", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
