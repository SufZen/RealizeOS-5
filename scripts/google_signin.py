"""Sign in to Google once so the Drive and Sheets tools can work.

Run from the project root, after saving a Google Cloud "Desktop app" OAuth
client as .credentials/client_secrets.json:

    python scripts/google_signin.py [--no-browser]

A browser tab asks for consent; the token is saved to .credentials/tokens.json.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from realize_core.tools.google_signin import SignInError, sign_in


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-browser", action="store_true", help="Print the URL instead of opening a browser")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        path = sign_in(open_browser=not args.no_browser)
    except SignInError as exc:
        print(f"Google sign-in failed: {exc}")
        return 1
    print(f"Signed in. Token saved to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
