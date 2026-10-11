"""Create the Hebrew webinar demo venture in this project.

Run from the project root (where realize-os.yaml lives):

    python scripts/seed_webinar_demo.py [--key tower-b-demo]

Then set the Google Drive and Sheets ids in the venture's skills
(systems/<key>/R-routines/skills/*.yaml, the `variables:` block) and reindex
the knowledge base (`python cli.py index`).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from realize_core.demo_seed import DEMO_KEY, seed_webinar_demo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="Project root (default: current directory)")
    parser.add_argument("--key", default=DEMO_KEY, help=f"Venture key (default: {DEMO_KEY})")
    args = parser.parse_args()

    try:
        result = seed_webinar_demo(args.root, key=args.key)
    except FileExistsError:
        print(f"Venture '{args.key}' already exists. Use --key for another one.")
        return 1

    print(f"Created '{result['key']}' with {result['documents']} demo documents in {result['venture_dir']}")
    print("Next: set the Drive/Sheets ids in its skills' `variables:` block, then run `python cli.py index`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
