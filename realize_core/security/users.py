"""
User loading for dashboard authentication.

Load order:
1. ``users.yaml`` in the working directory — preferred for multi-user setups.
2. ``REALIZE_ADMIN_USER`` + ``REALIZE_ADMIN_PASSWORD_HASH`` env vars — fallback
   for single-owner deployments (compatible with the simplest .env setup).

If neither is configured, no users are available and login is impossible —
the API still runs (programmatic callers can use ``REALIZE_API_KEY``), but the
dashboard is effectively read-locked.

Passwords are stored as bcrypt hashes only. Plaintext is never persisted.

Public API:
    get_user(email) -> User | None
    list_users() -> list[User]
    verify_password(email, plaintext) -> User | None
    hash_password(plaintext) -> str
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

USERS_FILE = "users.yaml"
VALID_ROLES = ("owner", "admin", "viewer")


@dataclass(frozen=True)
class User:
    """A dashboard user. Password hashes are intentionally not exposed via ``__repr__``."""

    email: str
    role: str
    password_hash: str

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"User(email={self.email!r}, role={self.role!r}, password_hash=<redacted>)"


def _load_yaml_users(path: Path) -> list[User]:
    """Parse ``users.yaml``. Returns [] on any structural problem (logged)."""
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed — cannot load users.yaml")
        return []

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.error("Failed to read %s: %s", path, exc)
        return []

    raw_users = data.get("users") if isinstance(data, dict) else None
    if not isinstance(raw_users, list):
        logger.warning("%s: top-level 'users' key missing or not a list", path)
        return []

    users: list[User] = []
    for idx, entry in enumerate(raw_users):
        if not isinstance(entry, dict):
            logger.warning("%s[%d]: not a mapping, skipped", path, idx)
            continue
        email = (entry.get("email") or "").strip().lower()
        role = (entry.get("role") or "viewer").strip().lower()
        password_hash = entry.get("password_hash") or ""

        if not email or not password_hash:
            logger.warning("%s[%d]: missing email or password_hash, skipped", path, idx)
            continue
        if role not in VALID_ROLES:
            logger.warning(
                "%s[%d]: invalid role %r (expected one of %s), skipped",
                path, idx, role, VALID_ROLES,
            )
            continue

        users.append(User(email=email, role=role, password_hash=password_hash))

    return users


def _load_env_user() -> list[User]:
    """Construct a single-owner user from environment variables, if set."""
    email = (os.environ.get("REALIZE_ADMIN_USER") or "").strip().lower()
    password_hash = os.environ.get("REALIZE_ADMIN_PASSWORD_HASH") or ""
    if not email or not password_hash:
        return []
    return [User(email=email, role="owner", password_hash=password_hash)]


def list_users() -> list[User]:
    """
    Load all configured users.

    Tries ``users.yaml`` first. Falls back to env vars only when the yaml file
    is missing (NOT when it's present but empty — an empty file is a deliberate
    "no users" state).
    """
    yaml_path = Path(USERS_FILE)
    if yaml_path.is_file():
        return _load_yaml_users(yaml_path)
    return _load_env_user()


def get_user(email: str) -> User | None:
    """Look up a user by email (case-insensitive)."""
    if not email:
        return None
    target = email.strip().lower()
    for user in list_users():
        if user.email == target:
            return user
    return None


def hash_password(plaintext: str) -> str:
    """
    Hash a plaintext password with bcrypt (cost factor 12).

    Cost 12 is the OWASP 2024 recommendation — roughly 250ms on a modern CPU,
    expensive enough to deter offline cracking, fast enough not to slow login.
    """
    import bcrypt

    if not plaintext:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(email: str, plaintext: str) -> User | None:
    """
    Verify credentials. Returns the User on match, None on any mismatch.

    Always runs bcrypt even when the user does not exist, to keep response
    time roughly constant and resist user-enumeration timing attacks.
    """
    import bcrypt

    user = get_user(email)
    # Dummy hash used when the user is absent — same cost as a real check.
    fallback_hash = b"$2b$12$" + b"x" * 53

    target_hash = (user.password_hash if user else fallback_hash.decode("ascii")).encode("utf-8")
    try:
        ok = bcrypt.checkpw((plaintext or "").encode("utf-8"), target_hash)
    except (ValueError, TypeError):
        # Malformed stored hash — treat as failure but still constant-time-ish.
        ok = False

    return user if (ok and user is not None) else None
