"""Live smoke test of the webinar storyline on ONE real LLM provider.

Manual or nightly only: it spends real tokens on the provider you name and is
never run by pytest or PR CI. Every other feature test uses fakes.

    python scripts/provider_smoke.py --provider gemini
    python scripts/provider_smoke.py --provider ollama --keep
    python scripts/provider_smoke.py --provider claude --dry-run   # no LLM call

What it does, in a fresh temporary project (REALIZE_ROOT, KB_PATH and
DATA_PATH all point there, so no real data is touched):

1. seeds the Hebrew webinar demo (realize_core.demo_seed) and indexes its KB;
2. asks "כמה נשאר לנו נטו בתקציב?" through the full chat pipeline and checks
   the answer cites [S1] and its trail has at least one source;
3. runs the payment skill: the payment row must wait for approval, then be
   written once on approval, with real values (no template labels, no {...}).

Google Sheets and Drive are stubbed: reads return fixed demo rows and writes
are only recorded. Nothing is ever written to a real Google Sheet.

Only the named provider answers (LLM_PRIMARY and LLM_FALLBACK are set to it,
LLM_MODEL_* overrides are cleared), so a broken provider cannot hide behind
another one. Keys come from the environment or ./.env. The script refuses to
run when REALIZE_ROOT (or --root) is under D:/realization-demo.

Exit status: 0 when every check passes, 1 when one fails, 2 on a setup error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import posixpath
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PROVIDERS = ("claude", "gemini", "openai", "ollama")
PROTECTED_ROOT = Path("D:/realization-demo")
QUESTION = "כמה נשאר לנו נטו בתקציב?"
PAYMENT_MESSAGE = "קיבלנו דרישת תשלום 4: 360,000 € על סיום השלד"
TEMPLATE_LABELS = {"contractor", "milestone", "verdict", "missing evidence"}
PLACEHOLDER = re.compile(r"\{[^{}]*\}")
FEATURES_YAML = "features:\n  agent_tools: true\n  enforce_gates: true\n  cite_sources: true\nsystems: []\n"

MILESTONES = [["4", "שלד — קומות 4-6 וגג", "10%", "360000", "אישור מפקח, תמונות מתוארכות, דוח מדידה"]]
BUDGET = [['סה"כ', "6000000", "5640000", "2926000"]]
TENDER_TEXT = "תנאי המכרז, סעיף 6.1: על המציע להיות רשום ב-IMPIC."


@dataclass
class Result:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


def is_protected(path: str | Path) -> bool:
    """True when ``path`` is D:/realization-demo or inside it (case-insensitive, any OS)."""
    text = str(path).replace("\\", "/")
    if not re.match(r"^(?:[A-Za-z]:)?/", text):
        text = Path(os.path.abspath(text)).as_posix()
    resolved = posixpath.normpath(text).lower()
    protected = PROTECTED_ROOT.as_posix().lower()
    return resolved == protected or resolved.startswith(protected + "/")


def row_problems(rows) -> list[str]:
    """Why an appended payment row is not real data (empty list when it is)."""
    if not isinstance(rows, list) or not rows or not all(isinstance(r, list) for r in rows):
        return [f"not a list of rows: {rows!r}"]
    problems = []
    for cell in (c for row in rows for c in row):
        if isinstance(cell, str):
            if PLACEHOLDER.search(cell):
                problems.append(f"placeholder {cell!r}")
            elif cell.strip().lower() in TEMPLATE_LABELS:
                problems.append(f"template label {cell!r}")
    return problems


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path.cwd() / ".env")


def _isolate(root: Path, provider: str) -> None:
    """Point every store at ``root`` and pin routing to ``provider``. Call before importing realize_core."""
    os.environ.update(
        {
            "REALIZE_ROOT": str(root),
            "KB_PATH": str(root),
            "DATA_PATH": str(root / "data"),
            "REALIZE_CONFIG": str(root / "realize-os.yaml"),
            "LLM_PRIMARY": provider,
            "LLM_FALLBACK": provider,
        }
    )
    for tier in ("FAST", "STANDARD", "DEEP"):
        os.environ.pop(f"LLM_MODEL_{tier}", None)
    os.environ.setdefault("KB_EMBED_MODEL", "none")  # keyword search; no model download
    os.chdir(root)


def _stub_google():
    """A Sheets/Drive stand-in behind the approval gate: reads are fixtures, writes are recorded."""
    import realize_core.tools.tool_registry as tr
    from realize_core.governance.tool_gate import ToolGate
    from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

    class StubGoogle(BaseTool):
        name = "stub_google"
        description = "Stubbed Google Sheets and Drive (smoke test)"
        category = ToolCategory.PRODUCTIVITY

        def __init__(self):
            self.appended: list[dict] = []

        def get_schemas(self):
            read = {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "range": {"type": "string"}}}
            rows = {"type": "array", "items": {"type": "array", "items": {}}}
            append = {"type": "object", "properties": {**read["properties"], "values": rows}}
            doc = {"type": "object", "properties": {"file_id": {"type": "string"}}}
            return [
                ToolSchema("sheets_read", "Read a sheet range", read),
                ToolSchema("sheets_append", "Append rows to a sheet", append, is_destructive=True),
                ToolSchema("drive_read_content", "Read a Drive file", doc),
            ]

        def is_available(self):
            return True

        async def execute(self, action, params):
            if action == "sheets_append":
                self.appended.append(params)
                return ToolResult.ok(output=f"recorded {len(params.get('values') or [])} row(s); nothing was written")
            if action == "sheets_read":
                rows = MILESTONES if params.get("range") == "Milestones" else BUDGET
                return ToolResult.ok(output=json.dumps(rows, ensure_ascii=False))
            if action == "drive_read_content":
                return ToolResult.ok(output=TENDER_TEXT)
            return ToolResult.fail(f"unknown action {action}")

    tr._registry = None
    registry = tr.get_tool_registry()
    stub = StubGoogle()
    registry.register(stub)
    registry.set_gate(ToolGate(config={}))
    return stub


def _prepare(root: Path) -> dict:
    """Seed the demo, migrate the stores and index the KB. Returns the runtime."""
    from realize_core.db.migrations import run_migrations
    from realize_core.db.schema import init_schema, set_db_path
    from realize_core.demo_seed import seed_webinar_demo
    from realize_core.engine import load_runtime
    from realize_core.kb.indexer import index_kb_files
    from realize_core.memory.store import init_db
    from realize_core.migration.engine import MigrationEngine
    from realize_core.skills.detector import reload_skills

    (root / "realize-os.yaml").write_text(FEATURES_YAML, encoding="utf-8")
    seed = seed_webinar_demo(root)
    db = root / "data" / "realize_data.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    set_db_path(db)
    init_schema(db)
    run_migrations(db)
    MigrationEngine(db_path=db).migrate_up()
    init_db()
    runtime = load_runtime()
    index_kb_files(str(root), force=True, systems_config=runtime["systems"])
    reload_skills(kb_path=root)
    return {**runtime, "key": seed["key"]}


def _pending_approvals() -> list[str]:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        return [r[0] for r in conn.execute("SELECT id FROM approval_queue WHERE status = 'pending'")]
    finally:
        conn.close()


async def _check_question(runtime: dict) -> list[Result]:
    from realize_core.agents.trail import TrailRecorder
    from realize_core.base_handler import process_message

    key = runtime["key"]
    recorder = TrailRecorder()
    answer = await process_message(
        system_key=key,
        user_id="smoke",
        message=QUESTION,
        kb_path=runtime["kb_path"],
        system_config=runtime["systems"][key],
        shared_config=runtime["shared_config"],
        channel="api",
        features=runtime["features"],
        all_systems=runtime["systems"],
        emit=recorder,
    )
    trail = recorder.to_dict()
    sources = trail["sources"]
    notices = [s.get("code") for s in trail["steps"] if s.get("type") == "notice"]
    preview = " ".join(answer.split())[:120]
    return [
        Result("Budget answer cites [S1]", "PASS" if "[S1]" in answer else "FAIL", preview),
        Result(
            "Trail has a source",
            "PASS" if sources else "FAIL",
            ", ".join(Path(s["path"]).name for s in sources) or "no sources",
        ),
        Result("No tool notice", "PASS" if not notices else "FAIL", ", ".join(notices) or "tools ran normally"),
    ]


async def _check_payment(runtime: dict, stub) -> list[Result]:
    from realize_core.governance.gates import decide_approval
    from realize_core.skills.detector import find_skill
    from realize_core.skills.executor import execute_skill

    key = runtime["key"]
    owner, skill = find_skill("payment_milestone_check", key)
    if skill is None:
        return [Result("Payment skill found", "FAIL", f"not loaded for {key}")]
    variables = {**skill.get("variables", {}), "milestones_sheet_id": "smoke-sheet", "payments_sheet_id": "smoke-sheet"}
    before = set(_pending_approvals())
    out = await execute_skill(
        skill={**skill, "variables": variables},
        user_message=PAYMENT_MESSAGE,
        system_key=key,
        user_id="smoke",
        kb_path=runtime["kb_path"],
        system_config=runtime["systems"][key],
        shared_config=runtime["shared_config"],
        channel="api",
    )
    pending = [a for a in _pending_approvals() if a not in before]
    results = [
        Result(
            "Payment row held for approval",
            "PASS" if len(pending) == 1 and not stub.appended else "FAIL",
            " ".join(out.split())[:120],
        )
    ]
    if len(pending) != 1:
        return results
    await decide_approval(pending[0], approve=True, decided_by="smoke", channel="smoke")
    rows = [a.get("values") for a in stub.appended]
    if len(rows) != 1:
        return [*results, Result("Approved row recorded once", "FAIL", f"{len(rows)} append(s)")]
    problems = row_problems(rows[0])
    return [
        *results,
        Result("Approved row recorded once", "PASS", "stubbed Sheets: nothing written to Google"),
        Result(
            "Row has real values",
            "FAIL" if problems else "PASS",
            "; ".join(problems) or json.dumps(rows[0], ensure_ascii=False)[:120],
        ),
    ]


def _dry_checks(runtime: dict) -> list[Result]:
    from realize_core.kb.indexer import semantic_search
    from realize_core.skills.detector import detect_skill

    key = runtime["key"]
    hits = semantic_search(QUESTION, system_key=key)
    skill = detect_skill(PAYMENT_MESSAGE, key)
    return [
        Result(
            "KB finds the budget",
            "PASS" if any(Path(h["path"]).name == "budget.md" for h in hits) else "FAIL",
            ", ".join(Path(h["path"]).name for h in hits) or "no hits",
        ),
        Result(
            "Payment message triggers the skill",
            "PASS" if skill and skill["name"] == "payment_milestone_check" else "FAIL",
            skill["name"] if skill else "no skill",
        ),
    ]


async def run(provider: str, root: Path, dry_run: bool) -> list[Result]:
    from realize_core.llm.registry import get_registry

    runtime = _prepare(root)
    stub = _stub_google()
    results = [Result("Demo seeded and indexed", "PASS", f"{root}")]
    results += _dry_checks(runtime)
    if dry_run:
        return [*results, Result("LLM checks", "SKIP", "--dry-run: no LLM call made")]

    registry = get_registry()
    available = registry.list_available()
    if provider not in available:
        return [
            *results,
            Result(f"Provider {provider} available", "FAIL", f"available: {', '.join(available) or 'none'}"),
        ]
    results.append(Result(f"Provider {provider} available", "PASS", f"chain: {', '.join(registry.fallback_chain())}"))
    results += await _check_question(runtime)
    results += await _check_payment(runtime, stub)
    return results


def _print_table(provider: str, results: list[Result]) -> None:
    width = max(len(r.name) for r in results)
    print(f"\nProvider smoke: {provider}\n")
    for r in results:
        print(f"{r.status:<4}  {r.name.ljust(width)}  {r.detail}")
    failed = sum(r.status == "FAIL" for r in results)
    print(f"\n{'FAIL' if failed else 'PASS'}: {len(results) - failed}/{len(results)} checks passed")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Hebrew output on Windows consoles
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", required=True, choices=PROVIDERS, help="The one provider to test")
    parser.add_argument("--root", help="Empty folder for the temporary project (default: a new temp folder)")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary project afterwards")
    parser.add_argument("--dry-run", action="store_true", help="Seed and check the KB and skills; no LLM call")
    args = parser.parse_args(argv)

    _load_env()
    for label, value in (("REALIZE_ROOT", os.environ.get("REALIZE_ROOT")), ("--root", args.root)):
        if value and is_protected(value):
            print(f"Refusing to run: {label} ({value}) is under {PROTECTED_ROOT}. Use a scratch folder.")
            return 2
    if args.root:
        root = Path(args.root).resolve()
        if root.exists() and any(root.iterdir()):
            print(f"--root must be an empty folder: {root}")
            return 2
        root.mkdir(parents=True, exist_ok=True)
    else:
        root = Path(tempfile.mkdtemp(prefix="realize-smoke-"))

    start = Path.cwd()
    _isolate(root, args.provider)
    try:
        results = asyncio.run(run(args.provider, root, args.dry_run))
    finally:
        os.chdir(start)
        if not args.keep and not args.root:
            shutil.rmtree(root, ignore_errors=True)
    _print_table(args.provider, results)
    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
