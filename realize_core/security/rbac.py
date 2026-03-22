"""
Enhanced RBAC with YAML-defined roles for RealizeOS.

Extends the base RBAC in `__init__.py` with:
- YAML-loaded custom role definitions
- System-scoped permissions (per-venture access control)
- Permission inheritance (role hierarchies)
- Runtime role creation and modification
- Integration with JWT claims
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from realize_core.security.jwt_auth import TokenClaims

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class RBACRole:
    """A role definition with permissions and optional inheritance."""
    name: str
    description: str = ""
    permissions: set[str] = field(default_factory=set)
    inherits_from: str | None = None
    system_scopes: list[str] = field(default_factory=list)  # empty = all systems
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "permissions": sorted(self.permissions),
            "inherits_from": self.inherits_from,
            "system_scopes": self.system_scopes,
        }


@dataclass
class AccessDecision:
    """Result of an access check."""
    allowed: bool
    role: str
    permission: str
    system_key: str = ""
    reason: str = ""

    @property
    def denied(self) -> bool:
        return not self.allowed


# ---------------------------------------------------------------------------
# Built-in permissions
# ---------------------------------------------------------------------------

# Organized by domain
PERMISSIONS = {
    # System
    "system:read",
    "system:write",
    "system:manage",
    "system:delete",
    # Agents
    "agents:read",
    "agents:write",
    "agents:execute",
    "agents:manage",
    # Tools
    "tools:use",
    "tools:browser",
    "tools:google",
    "tools:web",
    # Content
    "content:generate",
    "content:images",
    "content:publish",
    # Pipeline
    "pipeline:execute",
    "pipeline:approve",
    "pipeline:admin",
    # Admin
    "admin:users",
    "admin:audit",
    "admin:schedules",
    "admin:webhooks",
    "admin:security",
}


# ---------------------------------------------------------------------------
# Built-in roles (hierarchical)
# ---------------------------------------------------------------------------

_BUILTIN_ROLES: dict[str, RBACRole] = {
    "owner": RBACRole(
        name="owner",
        description="Full access to everything",
        permissions=set(PERMISSIONS),  # All permissions
    ),
    "admin": RBACRole(
        name="admin",
        description="Full access except user management",
        permissions=PERMISSIONS - {"admin:users", "admin:security"},
        inherits_from=None,
    ),
    "operator": RBACRole(
        name="operator",
        description="Operational access: execute, approve, manage agents",
        permissions={
            "system:read", "system:write",
            "agents:read", "agents:write", "agents:execute",
            "tools:use", "tools:web",
            "content:generate",
            "pipeline:execute", "pipeline:approve",
            "admin:schedules",
        },
    ),
    "user": RBACRole(
        name="user",
        description="Standard: read/write, use tools, generate content",
        permissions={
            "system:read", "system:write",
            "agents:read", "agents:execute",
            "tools:use", "tools:web",
            "content:generate",
        },
    ),
    "viewer": RBACRole(
        name="viewer",
        description="Read-only access",
        permissions={
            "system:read",
            "agents:read",
        },
    ),
    "guest": RBACRole(
        name="guest",
        description="Minimal read access",
        permissions={
            "system:read",
        },
    ),
}


# ---------------------------------------------------------------------------
# RBAC Manager
# ---------------------------------------------------------------------------

class RBACManager:
    """
    Role-Based Access Control manager.

    Supports:
    - Built-in roles with permission hierarchies
    - Custom roles loaded from YAML
    - System-scoped permissions (per-venture)
    - Runtime role creation
    """

    def __init__(self):
        self._roles: dict[str, RBACRole] = dict(_BUILTIN_ROLES)

    # ---- Role management ----

    def get_role(self, name: str) -> RBACRole | None:
        """Get a role by name."""
        return self._roles.get(name)

    def register_role(self, role: RBACRole) -> None:
        """Register or update a role."""
        self._roles[role.name] = role
        logger.info("Registered RBAC role '%s' (%d permissions)", role.name, len(role.permissions))

    def list_roles(self) -> list[RBACRole]:
        """List all registered roles."""
        return list(self._roles.values())

    def role_names(self) -> list[str]:
        """List all role names."""
        return list(self._roles.keys())

    # ---- Permission resolution ----

    def resolve_permissions(self, role_name: str) -> set[str]:
        """
        Get the full set of permissions for a role, including inherited ones.

        Follows the ``inherits_from`` chain up to 10 levels deep.
        """
        permissions: set[str] = set()
        visited: set[str] = set()
        current = role_name

        for _ in range(10):  # Max inheritance depth
            if not current or current in visited:
                break
            visited.add(current)

            role = self._roles.get(current)
            if not role:
                break

            permissions |= role.permissions
            current = role.inherits_from

        return permissions

    # ---- Access checks ----

    def check_access(
        self,
        role_name: str,
        permission: str,
        system_key: str = "",
    ) -> AccessDecision:
        """
        Check if a role has a specific permission.

        Args:
            role_name: The role to check.
            permission: The permission string (e.g., "agents:execute").
            system_key: Optional system scope.

        Returns:
            AccessDecision with allowed/denied and reason.
        """
        role = self._roles.get(role_name)
        if not role:
            return AccessDecision(
                allowed=False,
                role=role_name,
                permission=permission,
                system_key=system_key,
                reason=f"Unknown role '{role_name}'",
            )

        # Check system scope (if role has scopes and a system is specified)
        if system_key and role.system_scopes:
            if system_key not in role.system_scopes:
                return AccessDecision(
                    allowed=False,
                    role=role_name,
                    permission=permission,
                    system_key=system_key,
                    reason=f"Role '{role_name}' not scoped to system '{system_key}'",
                )

        # Check permission (including inherited)
        all_perms = self.resolve_permissions(role_name)
        allowed = permission in all_perms

        return AccessDecision(
            allowed=allowed,
            role=role_name,
            permission=permission,
            system_key=system_key,
            reason="" if allowed else f"Role '{role_name}' lacks permission '{permission}'",
        )

    def check_jwt_access(
        self,
        claims: TokenClaims,
        permission: str,
        system_key: str = "",
    ) -> AccessDecision:
        """
        Check access using JWT claims.

        Uses the role from claims, and also checks JWT scopes.
        """
        # First check role-based access
        decision = self.check_access(claims.role, permission, system_key)
        if not decision.allowed:
            return decision

        # If JWT has explicit scopes, enforce them too
        if claims.scopes:
            if permission not in claims.scopes:
                return AccessDecision(
                    allowed=False,
                    role=claims.role,
                    permission=permission,
                    system_key=system_key,
                    reason=f"Permission '{permission}' not in token scopes",
                )

        return decision

    # ---- YAML loading ----

    def load_from_yaml(self, yaml_path: str | Path) -> int:
        """
        Load custom roles from a YAML file.

        Format:
        ```yaml
        roles:
          content-creator:
            description: "Can generate content but not manage agents"
            permissions:
              - system:read
              - system:write
              - content:generate
              - content:images
              - content:publish
              - tools:use
            inherits_from: null
            system_scopes:
              - my-business

          super-admin:
            description: "All permissions, inherits from owner"
            inherits_from: owner
        ```

        Returns:
            Number of roles loaded.
        """
        path = Path(yaml_path)
        if not path.exists():
            logger.warning("RBAC config not found: %s", path)
            return 0

        try:
            import yaml
        except ImportError:
            logger.warning("pyyaml not installed — cannot load RBAC config")
            return 0

        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        count = 0
        for name, role_def in config.get("roles", {}).items():
            perms = set(role_def.get("permissions", []))
            role = RBACRole(
                name=name,
                description=role_def.get("description", ""),
                permissions=perms,
                inherits_from=role_def.get("inherits_from"),
                system_scopes=role_def.get("system_scopes", []),
                metadata=role_def.get("metadata", {}),
            )
            self.register_role(role)
            count += 1

        logger.info("Loaded %d custom roles from %s", count, path)
        return count


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_rbac_manager: RBACManager | None = None


def get_rbac_manager() -> RBACManager:
    """Get or create the global RBAC manager."""
    global _rbac_manager
    if _rbac_manager is None:
        _rbac_manager = RBACManager()
    return _rbac_manager
