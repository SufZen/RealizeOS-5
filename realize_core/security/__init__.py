"""
Security module for RealizeOS.

Provides:
- Secret vault: encrypted storage for API keys and tokens
- Permission model: RBAC with YAML-defined roles
- User profiles: multi-user session management
- Audit log: records all significant actions
- Prompt injection protection: basic input sanitization
"""

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ===========================================================================
# Permission Model (RBAC)
# ===========================================================================


class Permission(Enum):
    """Granular permissions for RealizeOS actions."""

    # System access
    READ_SYSTEM = "read_system"
    WRITE_SYSTEM = "write_system"
    MANAGE_SYSTEMS = "manage_systems"

    # Tool access
    USE_TOOLS = "use_tools"
    USE_BROWSER = "use_browser"  # Browser automation (risky)
    USE_GOOGLE = "use_google"  # Google Workspace access
    USE_WEB = "use_web"  # Web search/fetch

    # Admin
    MANAGE_USERS = "manage_users"
    VIEW_AUDIT_LOG = "view_audit_log"
    MANAGE_SCHEDULES = "manage_schedules"
    MANAGE_WEBHOOKS = "manage_webhooks"

    # Content
    GENERATE_CONTENT = "generate_content"
    GENERATE_IMAGES = "generate_images"


@dataclass
class Role:
    """A named set of permissions."""

    name: str
    permissions: set[Permission]
    description: str = ""

    def has_permission(self, perm: Permission) -> bool:
        return perm in self.permissions


# Predefined roles
ROLES = {
    "owner": Role(
        name="owner",
        description="Full access to everything",
        permissions=set(Permission),  # All permissions
    ),
    "admin": Role(
        name="admin",
        description="Full access except user management",
        permissions={
            Permission.READ_SYSTEM,
            Permission.WRITE_SYSTEM,
            Permission.MANAGE_SYSTEMS,
            Permission.USE_TOOLS,
            Permission.USE_BROWSER,
            Permission.USE_GOOGLE,
            Permission.USE_WEB,
            Permission.VIEW_AUDIT_LOG,
            Permission.MANAGE_SCHEDULES,
            Permission.MANAGE_WEBHOOKS,
            Permission.GENERATE_CONTENT,
            Permission.GENERATE_IMAGES,
        },
    ),
    "user": Role(
        name="user",
        description="Standard access: read/write, use tools, generate content",
        permissions={
            Permission.READ_SYSTEM,
            Permission.WRITE_SYSTEM,
            Permission.USE_TOOLS,
            Permission.USE_WEB,
            Permission.GENERATE_CONTENT,
        },
    ),
    "guest": Role(
        name="guest",
        description="Read-only access, no tools or generation",
        permissions={
            Permission.READ_SYSTEM,
        },
    ),
}


# ===========================================================================
# User Profiles
# ===========================================================================


@dataclass
class UserProfile:
    """A registered user with role-based access."""

    user_id: str
    display_name: str
    role: str = "guest"
    channel_ids: dict[str, str] = field(default_factory=dict)  # channel → platform_id
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def role_obj(self) -> Role:
        return ROLES.get(self.role, ROLES["guest"])

    def has_permission(self, perm: Permission) -> bool:
        return self.role_obj.has_permission(perm)


class UserManager:
    """Manages user profiles and authentication."""

    def __init__(self):
        self._users: dict[str, UserProfile] = {}
        self._channel_index: dict[str, str] = {}  # "channel:platform_id" → user_id

    def register_user(self, profile: UserProfile) -> bool:
        """Register a new user."""
        if profile.user_id in self._users:
            return False
        self._users[profile.user_id] = profile
        for channel, platform_id in profile.channel_ids.items():
            self._channel_index[f"{channel}:{platform_id}"] = profile.user_id
        logger.info(f"Registered user '{profile.display_name}' (role={profile.role})")
        return True

    def get_user(self, user_id: str) -> UserProfile | None:
        """Get a user by ID."""
        return self._users.get(user_id)

    def get_user_by_channel(self, channel: str, platform_id: str) -> UserProfile | None:
        """Get a user by their channel-specific ID (e.g., Telegram user ID)."""
        key = f"{channel}:{platform_id}"
        uid = self._channel_index.get(key)
        return self._users.get(uid) if uid else None

    def check_permission(self, user_id: str, perm: Permission) -> bool:
        """Check if a user has a specific permission."""
        user = self._users.get(user_id)
        if not user:
            return False
        return user.has_permission(perm)

    def update_role(self, user_id: str, new_role: str) -> bool:
        """Change a user's role."""
        user = self._users.get(user_id)
        if not user or new_role not in ROLES:
            return False
        user.role = new_role
        logger.info(f"Updated user '{user_id}' role to '{new_role}'")
        return True

    def load_from_yaml(self, yaml_path: str | Path):
        """
        Load users from YAML config.

        Format:
        ```yaml
        users:
          asaf:
            display_name: "Asaf"
            role: owner
            channels:
              telegram: "123456789"
              whatsapp: "972501234567"
        ```
        """
        path = Path(yaml_path)
        if not path.exists():
            return

        try:
            import yaml
        except ImportError:
            logger.warning("pyyaml not installed")
            return

        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        for uid, cfg in config.get("users", {}).items():
            self.register_user(
                UserProfile(
                    user_id=uid,
                    display_name=cfg.get("display_name", uid),
                    role=cfg.get("role", "user"),
                    channel_ids=cfg.get("channels", {}),
                    metadata=cfg.get("metadata", {}),
                )
            )

    @property
    def user_count(self) -> int:
        return len(self._users)


# ===========================================================================
# Audit Log
# ===========================================================================


@dataclass
class AuditEntry:
    """A single audit log entry."""

    timestamp: float
    user_id: str
    action: str
    channel: str = ""
    system_key: str = ""
    details: str = ""
    outcome: str = "success"  # success, denied, error


class AuditLog:
    """Append-only audit log for security-relevant events."""

    def __init__(self, max_entries: int = 10000):
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries

    def log(
        self,
        user_id: str,
        action: str,
        channel: str = "",
        system_key: str = "",
        details: str = "",
        outcome: str = "success",
    ):
        """Record an audit event."""
        entry = AuditEntry(
            timestamp=time.time(),
            user_id=user_id,
            action=action,
            channel=channel,
            system_key=system_key,
            details=details,
            outcome=outcome,
        )
        self._entries.append(entry)

        # Trim if over limit
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

        if outcome == "denied":
            logger.warning(f"DENIED: {user_id} attempted {action} ({details})")

    def get_entries(
        self,
        user_id: str = "",
        action: str = "",
        outcome: str = "",
        limit: int = 50,
    ) -> list[AuditEntry]:
        """Query audit log entries with optional filters."""
        results = self._entries
        if user_id:
            results = [e for e in results if e.user_id == user_id]
        if action:
            results = [e for e in results if e.action == action]
        if outcome:
            results = [e for e in results if e.outcome == outcome]
        return results[-limit:]

    @property
    def entry_count(self) -> int:
        return len(self._entries)


# ===========================================================================
# Prompt Injection Protection
# ===========================================================================

# Patterns that suggest prompt injection attempts
_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard above",
    "forget everything",
    "new instructions:",
    "system prompt:",
    "you are now",
    "pretend you are",
    "act as if you are",
    "roleplay as",
    "jailbreak",
    "do anything now",
    "dan mode",
]


def check_injection(text: str) -> tuple[bool, str]:
    """
    Check if a message appears to contain prompt injection.

    Returns:
        (is_suspicious, matched_pattern)
    """
    text_lower = text.lower()
    for pattern in _INJECTION_PATTERNS:
        if pattern in text_lower:
            return True, pattern
    return False, ""


def sanitize_input(text: str, max_length: int = 50000) -> str:
    """
    Sanitize user input before processing.

    - Truncates overly long messages
    - Strips control characters (except newlines/tabs)
    """
    if len(text) > max_length:
        text = text[:max_length] + "\n\n[...message truncated at limit]"

    # Remove control characters except \n, \r, \t
    cleaned = "".join(c for c in text if c in ("\n", "\r", "\t") or (ord(c) >= 32))
    return cleaned


# ===========================================================================
# Secret Vault (Simple)
# ===========================================================================


class SecretVault:
    """
    Simple secret management.

    Loads secrets from environment variables and .env files.
    Provides a centralized access point without exposing raw values in logs.
    """

    def __init__(self):
        self._secrets: dict[str, str] = {}

    def load_from_env(self, prefix: str = "REALIZE_"):
        """Load secrets from environment variables with a given prefix."""
        for key, value in os.environ.items():
            if key.startswith(prefix):
                self._secrets[key] = value

    def load_from_dotenv(self, env_path: str | Path = ".env"):
        """Load secrets from a .env file."""
        path = Path(env_path)
        if not path.exists():
            return

        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    self._secrets[key.strip()] = value.strip().strip('"').strip("'")

    def get(self, key: str, default: str = "") -> str:
        """Get a secret by key."""
        return self._secrets.get(key, os.environ.get(key, default))

    def has(self, key: str) -> bool:
        """Check if a secret exists."""
        return key in self._secrets or key in os.environ

    def mask(self, key: str) -> str:
        """Get a masked version of a secret (for logging)."""
        value = self.get(key)
        if not value:
            return "[not set]"
        if len(value) <= 8:
            return "****"
        return value[:4] + "****" + value[-4:]

    @property
    def secret_count(self) -> int:
        return len(self._secrets)


# ===========================================================================
# Singletons
# ===========================================================================

_user_manager: UserManager | None = None
_audit_log: AuditLog | None = None
_vault: SecretVault | None = None


def get_user_manager() -> UserManager:
    global _user_manager
    if _user_manager is None:
        _user_manager = UserManager()
    return _user_manager


def get_audit_log() -> AuditLog:
    global _audit_log
    if _audit_log is None:
        _audit_log = AuditLog()
    return _audit_log


def get_vault() -> SecretVault:
    global _vault
    if _vault is None:
        _vault = SecretVault()
    return _vault
