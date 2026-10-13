"""Export → clean restore (production acceptance, audit 2026-10-13 item 9).

An installation with a venture, operational rows (approvals, decisions,
skill runs, an agent token, a sign-in session, a conversation), an approved
pack verification and a custom pack under ``REALIZE_PACKS_PATH`` is exported
through the real ``POST /api/storage/export`` route, restored into a fresh,
empty folder with ``python cli.py storage restore`` (a real subprocess), and
compared with the original:

- the same ventures and files, byte for byte;
- the same database rows, with sign-in sessions left out on purpose;
- the same resolved packs and levels (``python cli.py packs inventory --compare``,
  also a real subprocess);
- no API key, JWT secret, password hash, session cookie or agent token secret
  anywhere in the ZIP (``.env``, ``users.yaml`` and ``.credentials`` stay out,
  as docs/self-hosting-guide.md says).

The restore command itself (refusing a non-empty target and unsafe archives)
is covered at the bottom.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import secrets
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = str(REPO_ROOT / "cli.py")

#: Operational tables a restore must bring back unchanged.
KEPT_TABLES = ("approval_queue", "decision_writes", "skill_runs", "agent_tokens", "activity_events")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _clean_env(**extra: str) -> dict[str, str]:
    """The test process's environment without RealizeOS settings or any API key."""
    drop = ("REALIZE_", "MCP_", "KB_PATH", "DATA_PATH")
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(drop) and not k.endswith(("_API_KEY", "_SECRET", "_TOKEN"))
    }
    env.update({"PYTHON_DOTENV_DISABLED": "1", "PYTHONIOENCODING": "utf-8", **extra})
    return env


def _cli(*args: str, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, CLI, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(cwd),
        timeout=180,
    )


def _tree(root: Path) -> dict[str, bytes]:
    """Every non-hidden file under ``root`` (relative POSIX path → bytes)."""
    if not root.is_dir():
        return {}
    out: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_file() and not any(part.startswith(".") for part in rel.parts):
            out[rel.as_posix()] = path.read_bytes()
    return out


def _rows(db: Path, table: str) -> list[tuple]:
    with sqlite3.connect(db) as conn:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        return conn.execute(f"SELECT * FROM {table} ORDER BY {cols[0]}").fetchall()


@pytest.fixture
def install(tmp_path, monkeypatch):
    """A populated installation in ``tmp_path/old``, with its secrets."""
    from realize_core.db.migrations import run_migrations
    from realize_core.db.schema import init_schema, set_db_path
    from realize_core.governance import decision_log
    from realize_core.governance.gates import Decider, create_approval_request, decide_approval
    from realize_core.memory import conversation, store
    from realize_core.migration.engine import MigrationEngine
    from realize_core.packs import clear_cache, loader, state
    from realize_core.packs.verify import request_verification
    from realize_core.security import session_store
    from realize_core.security.agent_tokens import create_token
    from realize_core.skills import resume_store

    kb = tmp_path / "old"
    data = kb / "data"
    custom = tmp_path / "old-custom-packs"
    secret = {
        "api_key": secrets.token_urlsafe(48),
        "jwt_secret": secrets.token_urlsafe(48),
        "llm_key": "sk-ant-" + secrets.token_urlsafe(24),
        "password_hash": "$2b$12$" + secrets.token_urlsafe(40)[:53],
    }

    # The venture's brain and config.
    _write(
        kb / "realize-os.yaml",
        "name: Acme\nsystems:\n  - key: acme\n    name: Acme Build\n    directory: systems/acme\n"
        "  - key: other\n    name: Other\n    directory: systems/other\nfeatures:\n  packs: true\n",
    )
    _write(kb / "systems" / "acme" / "F-foundations" / "venture-identity.md", "# Acme\nTowers in Lisbon.\n")
    _write(kb / "systems" / "acme" / "B-brain" / "site-notes.md", "Crane booked for Tuesday. Código: ação.\n")
    _write(kb / "systems" / "acme" / "packs.yaml", "market: [zz, pt]\n")
    _write(kb / "systems" / "acme" / "F-foundations" / "overrides" / "defaults.yaml", "units: imperial\n")
    _write(kb / "systems" / "other" / "F-foundations" / "venture-identity.md", "# Other\n")
    _write(kb / "shared" / "identity.md", "# Owner\nDana runs the practice.\n")
    # What must never travel in an export.
    _write(
        kb / ".env",
        f"REALIZE_API_KEY={secret['api_key']}\nREALIZE_JWT_SECRET={secret['jwt_secret']}\n"
        f"ANTHROPIC_API_KEY={secret['llm_key']}\n",
    )
    _write(
        kb / "users.yaml",
        "users:\n"
        f'  - email: owner@example.com\n    role: owner\n    password_hash: "{secret["password_hash"]}"\n'
        f'  - email: dana@example.com\n    role: operator\n    ventures: [acme]\n    password_hash: "{secret["password_hash"]}"\n',
    )
    _write(kb / ".credentials" / "tokens.json", '{"refresh_token": "' + secret["llm_key"] + '"}')
    # A custom pack in REALIZE_PACKS_PATH.
    zz = custom / "market" / "zz"
    _write(zz / "pack.yaml", "id: zz\nkind: market\nversion: 2.1.0\ntitle: Zed\ndefaults: {currency: ZED}\n")
    _write(
        zz / "rules" / "tax.md",
        "---\nid: zz.tax\nstatement: Works carry a 9% tax.\nsource: https://zz.example/tax\n"
        "as_of: '2026-10-13'\nreview_by: '2099-01-01'\nverification: 1\n---\nBody.\n",
    )

    monkeypatch.chdir(kb)  # users.yaml is read from the working directory
    for name, value in (
        ("DATA_PATH", str(data)),
        (loader.PACKS_PATH_ENV, str(custom)),
        ("REALIZE_CONFIG", str(kb / "realize-os.yaml")),
        ("REALIZE_API_KEY", secret["api_key"]),
        ("REALIZE_JWT_SECRET", secret["jwt_secret"]),
    ):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(state, "state_path", lambda: state.state_path_in(data))
    monkeypatch.setattr(store, "DB_PATH", data / "memory.db")
    monkeypatch.setattr(decision_log, "_kb_path", lambda kb_path=None: Path(kb_path) if kb_path else kb)
    conversation._conversations.clear()
    conversation._hydrated.clear()
    ops = data / "realize_data.db"
    data.mkdir(parents=True)
    set_db_path(ops)
    init_schema(ops)
    run_migrations(ops)
    MigrationEngine(db_path=ops).migrate_up()
    store.init_db()
    clear_cache()

    owner = Decider(user_id="owner@example.com", role="owner", allowed_ventures=None)
    # An approved pack verification (whole shipped pack) and an approved card of the custom pack.
    whole = request_verification("acme", kind="market", pack_id="pt", level=2, reviewer="Ana Silva, advogada (OA 1)")
    card = request_verification("acme", kind="market", pack_id="zz", level=2, reviewer="Z. Reviewer", cards=["zz.tax"])
    for approval_id in (whole, card):
        outcome = asyncio.run(decide_approval(approval_id, True, decider=owner))
        assert outcome["execution"]["success"] is True
        assert outcome["decision_log"]["logged"] is True
    # A held write rejected, and one still waiting.
    rejected = create_approval_request(
        "acme", "writer", "send_email", {"to": "client@example.com"}, action_name="gmail_send", params={"to": "x"}
    )
    asyncio.run(decide_approval(rejected, False, decision_note="Not yet", decider=owner))
    create_approval_request("acme", "writer", "data_write", {"sheet": "costs"}, action_name="sheets_append")
    # A paused skill, an agent token, a dashboard session and a conversation.
    resume_store.save(
        "run-1",
        approval_id=None,
        user_id="dana@example.com",
        system_key="acme",
        skill_name="weekly_report",
        step_id="confirm",
        kind="human",
        context={"user_message": "weekly report"},
        remaining_steps=[{"id": "send", "type": "agent"}],
    )
    token, token_secret = create_token(
        name="acme-agent", user_email="dana@example.com", ventures=["acme"], known_ventures=["acme", "other"]
    )
    session = session_store.create_session("owner@example.com", "owner")
    conversation.add_message("acme", "owner@example.com", "user", "Where is the crane?")
    secret.update(agent_token=token_secret, session_id=session.session_id, csrf=session.csrf_token)

    yield {"kb": kb, "data": data, "custom": custom, "tmp": tmp_path, "secret": secret, "token_id": token.id}
    set_db_path(None)
    clear_cache()
    conversation._conversations.clear()
    conversation._hydrated.clear()


def _export(kb: Path, target: Path) -> zipfile.ZipFile:
    """Run the real export route and save the ZIP to ``target``."""
    from realize_api.routes import storage_settings

    app = FastAPI()
    app.include_router(storage_settings.router, prefix="/api")
    app.state.kb_path = kb
    res = TestClient(app).post("/api/storage/export")
    assert res.status_code == 200, res.text
    target.write_bytes(res.content)
    return zipfile.ZipFile(io.BytesIO(res.content))


def test_export_restores_into_a_clean_install_with_the_same_brain(install):
    kb, data, custom, tmp = install["kb"], install["data"], install["custom"], install["tmp"]
    archive_path = tmp / "realizeos-export.zip"
    archive = _export(kb, archive_path)
    restored = tmp / "new-server" / "realizeos"
    env = _clean_env()

    # Restore the way the docs say: into a new, empty folder.
    result = _cli("storage", "restore", str(archive_path), "--directory", str(restored), env=env, cwd=tmp)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"DATA_PATH={restored / 'data'}" in result.stdout
    assert f"REALIZE_PACKS_PATH={restored / 'custom-packs'}" in result.stdout
    assert "users.yaml" in result.stdout  # tells the operator what to copy by hand

    # Same ventures and files, byte for byte.
    for tree in ("systems", "shared"):
        assert _tree(restored / tree) == _tree(kb / tree), tree
    assert (restored / "realize-os.yaml").read_bytes() == (kb / "realize-os.yaml").read_bytes()
    assert _tree(restored / "custom-packs") == _tree(custom)
    decisions = _tree(restored / "systems" / "acme" / "B-brain" / "decisions")
    assert len(decisions) == 3  # two approved verifications and the rejected email

    # Same operational rows; sign-in sessions are left out on purpose.
    new_ops = restored / "data" / "realize_data.db"
    for table in KEPT_TABLES:
        assert _rows(new_ops, table) == _rows(data / "realize_data.db", table), table
    statuses = sorted(
        (r[0] or "", r[1] or "")
        for r in sqlite3.connect(new_ops).execute("SELECT status, execution_status FROM approval_queue")
    )
    assert statuses == [("approved", "succeeded"), ("approved", "succeeded"), ("pending", ""), ("rejected", "")]
    assert len(_rows(data / "realize_data.db", "user_sessions")) == 1  # the live server keeps its session
    assert _rows(new_ops, "user_sessions") == []
    tokens = sqlite3.connect(new_ops).execute("SELECT id, token_hash FROM agent_tokens").fetchall()
    assert tokens == [(install["token_id"], hashlib.sha256(install["secret"]["agent_token"].encode()).hexdigest())]
    assert _rows(restored / "data" / "memory.db", "conversations") == _rows(data / "memory.db", "conversations")
    assert (restored / "data" / "packs" / "verification.json").read_bytes() == (
        data / "packs" / "verification.json"
    ).read_bytes()

    # Same resolved packs and levels, checked by the CLI the docs name.
    inventory = restored / "packs-inventory.json"
    same = _cli(
        "packs",
        "inventory",
        "--kb",
        str(restored),
        "--compare",
        str(inventory),
        env=_clean_env(DATA_PATH=str(restored / "data"), REALIZE_PACKS_PATH=str(restored / "custom-packs")),
        cwd=restored,
    )
    assert same.returncode == 0, same.stdout + same.stderr
    assert "Same packs, levels and resolved rules" in same.stdout
    # The check has teeth: without the custom packs folder it lists what is missing.
    missing = _cli(
        "packs",
        "inventory",
        "--kb",
        str(restored),
        "--compare",
        str(inventory),
        env=_clean_env(DATA_PATH=str(restored / "data")),
        cwd=restored,
    )
    assert missing.returncode == 1
    assert "pack market/zz is missing" in missing.stdout

    # No secret anywhere in the ZIP, names or contents.
    names = archive.namelist()
    assert not any(n.startswith((".env", ".credentials", "users.yaml")) or "/." in n for n in names)
    blob = b"".join(archive.read(n) for n in names)
    for label, value in install["secret"].items():
        assert value.encode() not in blob, f"{label} leaked into the export"


def test_restore_refuses_a_folder_that_is_not_empty(install):
    kb, tmp = install["kb"], install["tmp"]
    archive_path = tmp / "export.zip"
    _export(kb, archive_path)
    target = tmp / "occupied"
    _write(target / "realize-os.yaml", "name: keep me\n")

    result = _cli("storage", "restore", str(archive_path), "--directory", str(target), env=_clean_env(), cwd=tmp)

    assert result.returncode == 1
    assert "is not empty" in result.stderr
    assert _tree(target) == {"realize-os.yaml": b"name: keep me\n"}


# ---------------------------------------------------------------------------
# The restore function: only an export's layout, only into an empty folder
# ---------------------------------------------------------------------------


def _zip(path: Path, entries: dict[str, bytes], *, link: str | None = None, raw: str | None = None) -> Path:
    """An archive with ``entries``, optionally a symlink member and a member with a raw, unconverted name."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
        if link:
            info = zipfile.ZipInfo(link)
            info.external_attr = (0o120777 << 16) | 0
            zf.writestr(info, "/etc/passwd")
        if raw:
            info = zipfile.ZipInfo("placeholder")
            info.filename = raw  # as a hostile archive stores it (ZipInfo would turn os.sep into /)
            zf.writestr(info, b"x")
    return path


GOOD = {"realize-os.yaml": b"systems: []\n", "systems/acme/B-brain/a.md": b"a", "data/packs/verification.json": b"{}"}


def test_restore_unpacks_the_layout_into_a_missing_folder(tmp_path):
    from realize_core.storage.restore import restore_export

    result = restore_export(_zip(tmp_path / "x.zip", GOOD), tmp_path / "new")

    assert _tree(tmp_path / "new") == {
        "data/packs/verification.json": b"{}",
        "realize-os.yaml": b"systems: []\n",
        "systems/acme/B-brain/a.md": b"a",
    }
    assert result.data_path == (tmp_path / "new" / "data").absolute()
    assert result.packs_path is None
    assert result.inventory is None
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []  # no staging left behind


def test_restore_uses_an_empty_existing_folder(tmp_path):
    from realize_core.storage.restore import restore_export

    (tmp_path / "empty").mkdir()
    restore_export(_zip(tmp_path / "x.zip", GOOD), tmp_path / "empty")
    assert (tmp_path / "empty" / "systems" / "acme" / "B-brain" / "a.md").read_bytes() == b"a"


@pytest.mark.parametrize(
    "bad",
    [
        {"../outside.md": b"x"},
        {"../../evil": b"x"},
        {"systems/../../outside.md": b"x"},
        {"systems/./acme/x.md": b"x"},
        {"systems//acme/x.md": b"x"},
        {"/abs": b"x"},
        {"/etc/cron.d/x": b"x"},
        {"//server/share/x": b"x"},
        {"C:/Windows/x": b"x"},
        {"systems/acme/x\x01.md": b"x"},  # control character (zipfile itself cuts names at NUL)
        {"systems\\..\\x": b"x"},
        {".env": b"REALIZE_API_KEY=x"},
        {"users.yaml": b"users: []"},
        {"static/index.html": b"<script>"},
    ],
)
def test_restore_refuses_entries_outside_an_exports_layout(tmp_path, bad):
    from realize_core.storage.restore import RestoreError, restore_export

    with pytest.raises(RestoreError):
        restore_export(_zip(tmp_path / "x.zip", {**GOOD, **bad}), tmp_path / "new")
    assert not (tmp_path / "new").exists()
    assert not (tmp_path / "outside.md").exists()
    assert not (tmp_path / "evil").exists()


@pytest.mark.parametrize("raw", ["C:\\x", "..\\x", "systems\\..\\..\\evil", "\\\\server\\share\\x"])
def test_restore_refuses_backslash_and_drive_names(tmp_path, raw):
    """Names as a hostile archive stores them, backslashes and all."""
    from realize_core.storage.restore import RestoreError, restore_export

    with pytest.raises(RestoreError):
        restore_export(_zip(tmp_path / "x.zip", GOOD, raw=raw), tmp_path / "new")
    assert not (tmp_path / "new").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.zip"]


def test_restore_refuses_device_files(tmp_path):
    from realize_core.storage.restore import RestoreError, restore_export

    path = tmp_path / "dev.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in GOOD.items():
            zf.writestr(name, content)
        info = zipfile.ZipInfo("systems/acme/console")
        info.external_attr = (0o020644 << 16) | 0  # a character device
        zf.writestr(info, b"")
    with pytest.raises(RestoreError, match="device or special file"):
        restore_export(path, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_restore_caps_size_and_entries(tmp_path):
    from realize_core.storage.restore import RestoreError, restore_export

    big = _zip(tmp_path / "big.zip", {**GOOD, "systems/acme/big.md": b"0" * 50_000})
    with pytest.raises(RestoreError, match="at most 10000 bytes"):
        restore_export(big, tmp_path / "new", max_total_bytes=10_000)
    with pytest.raises(RestoreError, match="at most 2"):
        restore_export(big, tmp_path / "new", max_members=2)
    assert not (tmp_path / "new").exists()
    # Within the limits the same archive restores.
    restore_export(big, tmp_path / "new", max_total_bytes=100_000, max_members=10)
    assert (tmp_path / "new" / "systems" / "acme" / "big.md").stat().st_size == 50_000


def test_a_destination_resolving_outside_the_folder_is_refused(tmp_path):
    """The check is on resolved paths: a link inside the target can't redirect a member."""
    from realize_core.storage.restore import RestoreError, check_member

    target, outside = tmp_path / "target", tmp_path / "outside"
    target.mkdir()
    outside.mkdir()
    try:
        (target / "systems").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks can't be created here: {exc}")
    with pytest.raises(RestoreError, match="resolves outside"):
        check_member(zipfile.ZipInfo("systems/acme/a.md"), target)
    assert check_member(zipfile.ZipInfo("realize-os.yaml"), target) is not None


def test_restore_refuses_links_and_non_exports(tmp_path):
    from realize_core.storage.restore import RestoreError, restore_export

    with pytest.raises(RestoreError, match="is a link"):
        restore_export(_zip(tmp_path / "l.zip", GOOD, link="systems/acme/passwd"), tmp_path / "new")
    with pytest.raises(RestoreError, match="not a RealizeOS export"):
        restore_export(_zip(tmp_path / "d.zip", {"data/memory.db": b"x"}), tmp_path / "new")
    (tmp_path / "plain.zip").write_bytes(b"not a zip")
    with pytest.raises(RestoreError, match="not a readable ZIP"):
        restore_export(tmp_path / "plain.zip", tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_a_damaged_archive_leaves_the_target_untouched(tmp_path):
    from realize_core.storage.restore import RestoreError, restore_export

    path = _zip(tmp_path / "x.zip", {**GOOD, "systems/acme/big.md": b"pelican " * 4000})
    raw = bytearray(path.read_bytes())
    at = raw.find(b"pelican pelican")
    raw[at : at + 7] = b"PELICAN"  # stored entries: flips content, so the CRC check fails
    path.write_bytes(bytes(raw))
    (tmp_path / "new").mkdir()

    with pytest.raises(RestoreError, match="damaged"):
        restore_export(path, tmp_path / "new")
    assert list((tmp_path / "new").iterdir()) == []
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


# ---------------------------------------------------------------------------
# Names Windows rewrites or reserves (security review S8), and colons (packs review)
# ---------------------------------------------------------------------------


def _leftovers(parent: Path) -> list[str]:
    """Staging folders a restore left next to its target."""
    return sorted(p.name for p in parent.iterdir() if ".restore-" in p.name)


WINDOWS_ONLY_NAMES = [
    "systems/.. /.. /x.md",  # Windows drops the trailing space: ".." once written
    "systems/acme./x.md",
    "systems/acme /x.md",
    "systems/acme/notes.md.",
    "systems/acme/notes.md ",
    "systems/.../x.md",
    "systems/CON/x.md",
    "systems/acme/nul.txt",
    "systems/acme/Aux",
    "data/COM1",
    "data/lpt9.db",
    "custom-packs/prn .md",
    "systems/acme/C:x.md",  # drive-relative on Windows
    "systems/c:/x.md",
    "systems/acme./a:b.md",  # a colon and a trailing dot
    "systems/C:/a:b.md",
]


def test_restore_refuses_a_real_parent_segment_everywhere(tmp_path):
    from realize_core.storage.restore import RestoreError, restore_export

    with pytest.raises(RestoreError):
        restore_export(_zip(tmp_path / "x.zip", {**GOOD, "systems/../ ../x.md": b"x"}), tmp_path / "new")
    assert not (tmp_path / "new").exists()
    assert _leftovers(tmp_path) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows rewrites or reserves these names")
@pytest.mark.parametrize("name", WINDOWS_ONLY_NAMES)
def test_windows_skips_names_it_would_rewrite_or_reserve(tmp_path, name):
    from realize_core.storage.restore import restore_export

    result = restore_export(_zip(tmp_path / "x.zip", {**GOOD, name: b"x"}), tmp_path / "new")
    assert name in result.skipped
    assert name not in result.files
    assert (tmp_path / "new").is_dir()  # the rest of the export restored
    assert not (tmp_path / "x.md").exists()  # ".. /.. /x.md" never escaped
    assert _leftovers(tmp_path) == []


@pytest.mark.skipif(os.name == "nt", reason="these are ordinary names on Linux and macOS")
@pytest.mark.parametrize("name", WINDOWS_ONLY_NAMES)
def test_posix_restores_names_only_windows_rewrites(tmp_path, name):
    from realize_core.storage.restore import restore_export

    result = restore_export(_zip(tmp_path / "x.zip", {**GOOD, name: b"x"}), tmp_path / "new")
    assert (tmp_path / "new").joinpath(*name.split("/")).read_bytes() == b"x"
    assert result.skipped == []
    assert not (tmp_path / "x.md").exists()


@pytest.mark.parametrize(
    "name", ["systems/acme/console.md", "systems/acme/con-notes.md", "data/com10.db", "systems/a.b/c", "data/.hidden"]
)
def test_names_close_to_reserved_ones_still_restore(tmp_path, name):
    from realize_core.storage.restore import restore_export

    restore_export(_zip(tmp_path / "x.zip", {**GOOD, name: b"ok"}), tmp_path / "new")
    assert (tmp_path / "new").joinpath(*name.split("/")).read_bytes() == b"ok"


def _extended(path: Path) -> str:
    """``path`` in a form that keeps a trailing dot or space on Windows."""
    return "\\\\?\\" + str(path) if os.name == "nt" else str(path)


def test_staging_cleanup_removes_names_windows_cannot_reach_normally(tmp_path):
    """A staging folder holding ``acme.`` or ``notes `` is still deleted, never left behind."""
    from realize_core.storage.restore import _remove_staging

    staging = tmp_path / ".new.restore-abc"
    odd = staging / "systems" / "acme." / "notes "
    os.makedirs(_extended(odd))
    with open(_extended(odd / "a.md."), "wb") as fh:
        fh.write(b"x")
    _remove_staging(staging)
    assert not os.path.exists(_extended(staging))
    _remove_staging(staging)  # already gone: no error


COLON_NAME = "systems/acme/B-brain/standup 10:30.md"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file names can hold a colon")
def test_colons_in_names_restore_on_posix(tmp_path):
    from realize_core.storage.restore import restore_export

    result = restore_export(_zip(tmp_path / "x.zip", {**GOOD, COLON_NAME: b"notes"}), tmp_path / "new")
    assert (tmp_path / "new" / "systems" / "acme" / "B-brain" / "standup 10:30.md").read_bytes() == b"notes"
    assert COLON_NAME in result.files
    assert result.skipped == []


@pytest.mark.skipif(os.name != "nt", reason="Windows can't store a colon in a file name")
def test_colons_in_names_are_skipped_with_a_warning_on_windows(tmp_path, caplog):
    from realize_core.storage.restore import restore_export

    with caplog.at_level("WARNING", logger="realize_core.storage.restore"):
        result = restore_export(_zip(tmp_path / "x.zip", {**GOOD, COLON_NAME: b"notes"}), tmp_path / "new")
    brain = tmp_path / "new" / "systems" / "acme" / "B-brain"
    assert result.skipped == [COLON_NAME]
    assert COLON_NAME not in result.files
    assert [p.name for p in brain.iterdir()] == ["a.md"]  # no alternate data stream written on a.md either
    assert "standup 10:30.md" in caplog.text
    assert _leftovers(tmp_path) == []


def test_restore_cli_reports_skipped_names(tmp_path, monkeypatch):
    from realize_core.cli_app import app
    from realize_core.storage import restore
    from typer.testing import CliRunner

    monkeypatch.setattr(restore, "_names_may_hold_colons", lambda: False)  # as on Windows
    archive = _zip(tmp_path / "x.zip", {**GOOD, COLON_NAME: b"notes"})
    result = CliRunner().invoke(app, ["storage", "restore", str(archive), "--directory", str(tmp_path / "new")])
    assert result.exit_code == 0, result.output
    assert "Skipped 1 file" in result.output
    assert COLON_NAME in result.output
    assert not (tmp_path / "new" / "systems" / "acme" / "B-brain" / "standup 10:30.md").exists()


@pytest.mark.parametrize("bad", ["../x:y.md", "users.yaml:x"])
@pytest.mark.parametrize("posix", [True, False])
def test_colon_names_that_are_unsafe_otherwise_still_refuse_the_restore(tmp_path, monkeypatch, bad, posix):
    from realize_core.storage import restore

    monkeypatch.setattr(restore, "_names_may_hold_colons", lambda: posix)
    with pytest.raises(restore.RestoreError):
        restore.restore_export(_zip(tmp_path / "x.zip", {**GOOD, bad: b"x"}), tmp_path / "new")
    assert not (tmp_path / "new").exists()
