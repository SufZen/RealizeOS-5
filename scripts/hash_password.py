#!/usr/bin/env python3
"""
Generate a bcrypt password hash for users.yaml.

Usage:
    python scripts/hash_password.py                  # interactive (hidden input)
    python scripts/hash_password.py 'myPassword'     # one-shot (avoid in shell history)

Output is a single line — the bcrypt hash. Paste it under ``password_hash:``
in users.yaml. Example:

    users:
      - email: owner@example.com
        role: owner
        password_hash: $2b$12$KIXrx...

Cost factor 12 is the OWASP recommendation as of 2024.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    # Make ``realize_core`` importable when run from the repo root.
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

    from realize_core.security.users import hash_password

    if len(argv) > 1:
        password = argv[1]
    else:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm:  ")
        if password != confirm:
            print("error: passwords do not match", file=sys.stderr)
            return 2

    if len(password) < 8:
        print(
            "warning: password is shorter than 8 characters — "
            "consider something longer for a production deployment",
            file=sys.stderr,
        )

    try:
        print(hash_password(password))
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
