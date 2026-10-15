"""Provider-neutral gate: no feature may depend on a named LLM provider.

Every feature must work on every provider (Anthropic, Gemini, OpenAI, Ollama,
anything LiteLLM routes to). Only the provider adapters may name a provider.
This script greps ``realize_core/``, ``realize_api/``, ``cli.py``, ``scripts/``
and ``plugins/`` (this gate script excepted) for code that does:

    direct-client-call     call_claude*() / call_gemini*()
    direct-client-import   an import of claude_client / gemini_client
    provider-by-name       get_provider_by_name("...") with a literal name
    provider-compare       == / != against a provider-name string literal
    provider-in            "gemini" in model   (literal on the left of `in`)
    provider-in-list       x in ("claude", ...)  (not `for x in (...)` loops)
    provider-prefix        .startswith("claude...") / .endswith(...)
    provider-key-env       os.getenv / os.environ reads of ANTHROPIC_API_KEY,
                           GOOGLE_AI_API_KEY, GOOGLE_API_KEY or OPENAI_API_KEY
                           (use realize_core.llm.registry.any_provider_available)

A provider-name literal is a quoted string starting with claude, anthropic,
gemini, openai or ollama (any case), e.g. "claude", 'gemini/', "openai-x".

It is a simple line-by-line regex heuristic, not a parser: it misses
comparisons split over several lines and ignores dict tables. Comment lines
are skipped.

Exemptions:
- whole files and folders in ALLOWED (the provider adapters, the alias and
  configuration tables, setup flows);
- one line, with an inline ``# provider-neutral: ok <reason>`` pragma. The
  reason is required; a bare pragma is itself reported.

Usage:
    python scripts/check_provider_neutral.py            # scan the default roots
    python scripts/check_provider_neutral.py PATH ...   # scan files or folders

Exit status 1 lists the offenders; 0 when the tree is clean. Standard library only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = ("realize_core", "realize_api", "cli.py", "scripts", "plugins")
#: Never scanned: this gate names every pattern it looks for.
EXCLUDED = ("scripts/check_provider_neutral.py",)

#: Repo-relative files, or folders ending in "/", that may name providers.
ALLOWED = (
    "realize_core/llm/providers/",  # the adapters, _litellm_adapter.py included
    "realize_core/llm/claude_client.py",
    "realize_core/llm/claude_models.py",
    "realize_core/llm/gemini_client.py",
    "realize_core/llm/litellm_provider.py",
    "realize_core/llm/registry.py",  # alias table
    "realize_core/config.py",
    "realize_api/routes/setup.py",
    "realize_core/devmode/context_generator.py",
    "realize_core/setup_wizard.py",
    "realize_core/init.py",
)
# Everything else that must name a provider uses a line pragma, so the rest of
# its file stays checked (e.g. realize_core/tools/base_tool.py's wire-format names).

PRAGMA = re.compile(r"#\s*provider-neutral:\s*ok\b(?P<reason>.*)$")

_NAME = r"[\"'](?:claude|anthropic|gemini|openai|ollama)[^\"'\s]*[\"']"
_KEY = r"[\"'](?:ANTHROPIC|GOOGLE_AI|GOOGLE|OPENAI)_API_KEY[\"']"
RULES: dict[str, re.Pattern[str]] = {
    # First: a key name such as "ANTHROPIC_API_KEY" also looks like a provider literal.
    "provider-key-env": re.compile(
        rf"(?:\bgetenv\(|\benviron(?:\.get\(|\[))\s*{_KEY}|{_KEY}\s+(?:not\s+)?in\s+(?:os\.)?environ\b"
    ),
    "direct-client-call": re.compile(r"\bcall_(?:claude|gemini)\w*"),
    "direct-client-import": re.compile(r"^\s*(?:from|import)\s+[\w.]*\b(?:claude_client|gemini_client)\b"),
    "provider-by-name": re.compile(r"get_provider_by_name\(\s*[\"']"),
    "provider-compare": re.compile(rf"(?:==|!=)\s*{_NAME}|{_NAME}\s*(?:==|!=)", re.IGNORECASE),
    "provider-in": re.compile(rf"{_NAME}\s+(?:not\s+)?in\b", re.IGNORECASE),
    "provider-in-list": re.compile(rf"^(?!\s*(?:async\s+)?for\b).*\bin\s*[\(\[{{][^)\]}}]*{_NAME}", re.IGNORECASE),
    "provider-prefix": re.compile(rf"\.(?:startswith|endswith)\(\s*\(?[^)]*{_NAME}", re.IGNORECASE),
}


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_allowed(rel: str) -> bool:
    """True when a repo-relative path is on the allow-list."""
    return any(rel.startswith(entry) if entry.endswith("/") else rel == entry for entry in ALLOWED)


def scan_text(text: str, rel: str) -> list[str]:
    """Offences in one file's text, as ``path:line: [rule] code``."""
    offences = []
    for number, line in enumerate(text.splitlines(), 1):
        code = line.strip()
        if not code or code.startswith("#"):
            continue
        pragma = PRAGMA.search(line)
        if pragma and pragma.group("reason").strip():
            continue
        for rule, pattern in RULES.items():
            if pattern.search(line):
                offences.append(f"{rel}:{number}: [{rule}] {code}")
                break
        else:
            if pragma:
                offences.append(f"{rel}:{number}: [pragma-without-reason] {code}")
    return offences


def _files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    return files


def scan(paths: list[Path], root: Path = REPO) -> list[str]:
    """Offences in every *.py under ``paths`` that is not allow-listed."""
    offences = []
    for path in _files(paths):
        rel = _relative(path, root)
        if rel in EXCLUDED or is_allowed(rel):
            continue
        offences.extend(scan_text(path.read_text(encoding="utf-8", errors="replace"), rel))
    return offences


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    paths = [Path(a) for a in args] or [REPO / r for r in DEFAULT_ROOTS]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print(f"No such path: {', '.join(missing)}")
        return 2
    offences = scan(paths)
    if offences:
        print("Provider-specific code outside the provider adapters:\n")
        print("\n".join(offences))
        print(
            f"\n{len(offences)} offence(s). Use a capability (Capability.*, tools_format, "
            "supports_pdf_input) or the registry instead of a provider name, or add "
            "'# provider-neutral: ok <reason>' if the line genuinely must name one."
        )
        return 1
    print("Provider-neutral check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
