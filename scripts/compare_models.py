"""Ask the same fixed questions of two models and write the answers side by side.

Manual only: it spends real tokens on both models and is never run by pytest or
PR CI. Use it before moving a tier (for example LLM_MODEL_FAST) to a cheaper
model, so a person can judge whether the answers got worse.

    python scripts/compare_models.py questions.txt \\
        --before gemini/gemini-2.5-flash --after gemini/gemini-3.1-flash-lite \\
        --out compare.md

``questions.txt`` holds one question per line (blank lines and lines starting
with # are skipped). Each question goes through ``route_completion`` with the
model pinned, so the call is costed and counted like any other (hourly limit
and the monthly cap included). A failed call is reported in the table, not
retried on another provider: the point is to see this model's answer.

Keys come from the environment or ./.env. Nothing is written except ``--out``.
Exit status: 0 when every call answered, 1 when one failed, 2 on a setup error.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

SYSTEM_PROMPT = "Answer briefly and accurately. If you do not know, say so."


def read_questions(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def _cell(text: str) -> str:
    return " ".join((text or "").split()).replace("|", "\\|")


async def ask(model: str, question: str) -> tuple[str, float, float, bool]:
    """One pinned call: (text or error, cost in USD, seconds, ok)."""
    from realize_core.llm.router import route_completion

    started = time.monotonic()
    response = await route_completion(
        system_prompt=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
        model=model,
        max_retries=0,
    )
    seconds = time.monotonic() - started
    if response.ok:
        return response.text, response.cost_usd, seconds, True
    return f"ERROR: {response.error or response.text}", response.cost_usd, seconds, False


async def compare(questions: list[str], before: str, after: str) -> tuple[str, bool]:
    rows = ["| # | Question | " + before + " | " + after + " |", "|---|---|---|---|"]
    totals = {before: [0.0, 0.0], after: [0.0, 0.0]}
    all_ok = True
    for i, question in enumerate(questions, 1):
        cells = []
        for model in (before, after):
            text, cost, seconds, ok = await ask(model, question)
            all_ok = all_ok and ok
            totals[model][0] += cost
            totals[model][1] += seconds
            cells.append(_cell(text))
        rows.append(f"| {i} | {_cell(question)} | {cells[0]} | {cells[1]} |")
    n = max(len(questions), 1)
    summary = [
        "",
        "| Model | Total cost (USD) | Avg seconds |",
        "|---|---|---|",
        *(f"| {m} | {c:.4f} | {s / n:.1f} |" for m, (c, s) in totals.items()),
    ]
    return "\n".join(rows + summary) + "\n", all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("questions", type=Path, help="text file, one question per line")
    parser.add_argument("--before", required=True, help="LiteLLM model string used today")
    parser.add_argument("--after", required=True, help="LiteLLM model string to try")
    parser.add_argument("--out", type=Path, default=Path("compare.md"))
    args = parser.parse_args(argv)

    if not args.questions.is_file():
        print(f"No such file: {args.questions}", file=sys.stderr)
        return 2
    questions = read_questions(args.questions)
    if not questions:
        print("No questions in the file.", file=sys.stderr)
        return 2

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    report, all_ok = asyncio.run(compare(questions, args.before, args.after))
    args.out.write_text(report, encoding="utf-8")
    print(f"Wrote {args.out} ({len(questions)} questions)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
