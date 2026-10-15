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

It is a regex heuristic, not a parser, applied per statement: the tokenizer
joins a statement wrapped over several lines (inside brackets), so
``os.environ.get(\\n    "OPENAI_API_KEY", ""\\n)`` is caught like the one-line
form. It ignores dict tables. Comment lines are skipped.

Exemptions:
- whole files and folders in ALLOWED (the provider adapters, the alias and
  configuration tables, setup flows);
- one statement, with an inline ``# provider-neutral: ok <reason>`` pragma on
  any of its lines. The reason is required; a bare pragma is itself reported.

Usage:
    python scripts/check_provider_neutral.py            # scan the default roots
    python scripts/check_provider_neutral.py PATH ...   # scan files or folders

Exit status 1 lists the offenders; 0 when the tree is clean. Standard library only.
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
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
    # `^` rules are MULTILINE: a statement is matched as joined lines, and the
    # anchor must hold at the start of any of its lines. `[ \t]` (not `\s`) keeps
    # the anchored prefix on one line; `.` never crosses a line.
    "direct-client-import": re.compile(
        r"^[ \t]*(?:from|import)[ \t]+[\w.]*\b(?:claude_client|gemini_client)\b"
        # `from pkg import (a, claude_client)`, the list possibly wrapped
        r"|^[ \t]*from[ \t]+[\w.]+[ \t]+import[ \t]*\(?[^)#]*?\b(?:claude_client|gemini_client)\b",
        re.MULTILINE,
    ),
    "provider-by-name": re.compile(r"get_provider_by_name\(\s*[\"']"),
    # A wrapped operand may sit in parentheses: `x == (\n    "claude"\n)`.
    "provider-compare": re.compile(rf"(?:==|!=)\s*\(?\s*{_NAME}|{_NAME}\s*\)?\s*(?:==|!=)", re.IGNORECASE),
    "provider-in": re.compile(rf"{_NAME}\s+(?:not\s+)?in\b", re.IGNORECASE),
    "provider-in-list": re.compile(
        rf"^(?![ \t]*(?:async[ \t]+)?for\b).*\bin\s*[\(\[{{][^)\]}}]*{_NAME}", re.IGNORECASE | re.MULTILINE
    ),
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


_NON_CODE_TOKENS = frozenset(
    {tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER}
)


def _statements(lines: list[str]) -> list[list[int]]:
    """Group 1-based physical line numbers into logical statements.

    A statement wrapped over several lines (inside brackets, or a multi-line
    string) is one group; comment-only and blank lines belong to none. If the
    file does not tokenize, every line is its own statement (the old behaviour).
    """
    source = "\n".join(lines) + "\n"
    groups: list[list[int]] = []
    start: int | None = None
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in _NON_CODE_TOKENS:
                continue
            if start is None:
                start = tok.start[0]
            if tok.type == tokenize.NEWLINE:
                groups.append(list(range(start, tok.end[0] + 1)))
                start = None
    except (tokenize.TokenError, SyntaxError):  # IndentationError is a SyntaxError
        return [[n] for n in range(1, len(lines) + 1)]
    if start is not None:  # a last statement without a NEWLINE token
        groups.append(list(range(start, len(lines) + 1)))
    return groups


def scan_text(text: str, rel: str) -> list[str]:
    """Offences in one file's text, as ``path:line: [rule] code``.

    Each rule is matched against a whole statement, so a call wrapped over
    several lines is caught; the reported line is where the match starts. A
    pragma with a reason on any line of the statement exempts it.
    """
    lines = text.split("\n")
    offences = []
    for numbers in _statements(lines):
        kept = [n for n in numbers if lines[n - 1].strip() and not lines[n - 1].strip().startswith("#")]
        if not kept:
            continue
        joined = "\n".join(lines[n - 1] for n in kept)
        pragmas = [(n, PRAGMA.search(lines[n - 1])) for n in kept]
        if any(p and p.group("reason").strip() for _, p in pragmas):
            continue
        for rule, pattern in RULES.items():
            match = pattern.search(joined)
            if match:
                number = kept[joined.count("\n", 0, match.start())]
                offences.append(f"{rel}:{number}: [{rule}] {lines[number - 1].strip()}")
                break
        else:
            offences.extend(f"{rel}:{n}: [pragma-without-reason] {lines[n - 1].strip()}" for n, p in pragmas if p)
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
