"""Prepare and check a live rehearsal of the Hebrew webinar demo.

Run from the project root, after scripts/seed_webinar_demo.py:

    python scripts/rehearse_webinar_demo.py set-ids --sheet <sheet id> --tender-doc <doc id>
    python scripts/rehearse_webinar_demo.py check

`check` is read-only: it never writes to Google. See docs/webinar-demo.md.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from realize_core.demo_rehearsal import preflight, set_demo_ids
from realize_core.demo_seed import DEMO_KEY


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="Project root (default: current directory)")
    parser.add_argument("--key", default=DEMO_KEY, help=f"Demo venture key (default: {DEMO_KEY})")
    sub = parser.add_subparsers(dest="command", required=True)
    ids = sub.add_parser("set-ids", help="Write the Google ids into the demo skills")
    ids.add_argument("--sheet", required=True, help="The project Google Sheet id")
    ids.add_argument("--tender-doc", required=True, help="The tender document's Google Drive id")
    sub.add_parser("check", help="Check everything the live demo needs (read-only)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    _load_env()

    if args.command == "set-ids":
        try:
            changed = set_demo_ids(args.root, args.sheet, args.tender_doc, key=args.key)
        except (FileNotFoundError, ValueError) as exc:
            print(exc)
            return 1
        print(f"Updated {len(changed)} skill files: {', '.join(changed) or 'none'}")
        print("Next: python scripts/rehearse_webinar_demo.py check")
        return 0

    checks = asyncio.run(preflight(args.root, key=args.key))
    width = max(len(c.name) for c in checks)
    for c in checks:
        mark = "OK  " if c.ok else "FIX "
        print(f"{mark} {c.name.ljust(width)}  {c.detail}")
        if not c.ok and c.fix:
            print(f"     {' ' * width}  -> {c.fix}")
    failed = sum(not c.ok for c in checks)
    print(f"\n{len(checks) - failed}/{len(checks)} ready." + (" Ready to rehearse." if not failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
