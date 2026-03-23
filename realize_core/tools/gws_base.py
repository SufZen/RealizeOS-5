"""
Google Workspace CLI tool base interfaces.

Defines the configuration schema for the generic shell executor
that wraps the `gws` CLI for Google Workspace operations.

Used by Agent 4's Sprint 2 gws_cli_tool implementation.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GwsService(StrEnum):
    """Google Workspace services accessible via the gws CLI."""

    GMAIL = "gmail"
    CALENDAR = "calendar"
    DRIVE = "drive"
    SHEETS = "sheets"
    DOCS = "docs"
    ADMIN = "admin"


class GwsAuthMethod(StrEnum):
    """Authentication methods for gws CLI."""

    OAUTH = "oauth"
    SERVICE_ACCOUNT = "service_account"
    API_KEY = "api_key"


# ---------------------------------------------------------------------------
# Pydantic config model
# ---------------------------------------------------------------------------


class GwsCommandConfig(BaseModel):
    """Configuration for a single gws CLI command mapping."""

    action: str = Field(description="The RealizeOS action name (e.g. 'sheets_read')")
    gws_command: str = Field(description="The gws CLI command template (e.g. 'gws sheets get {spreadsheet_id}')")
    description: str = ""
    required_params: list[str] = Field(default_factory=list)
    optional_params: list[str] = Field(default_factory=list)
    service: GwsService = GwsService.SHEETS
    is_destructive: bool = False
    timeout_seconds: int = 30


class GwsToolConfig(BaseModel):
    """
    Configuration schema for the gws shell executor tool.

    Loaded from realize-os.yaml under ``tools.gws``.

    Example YAML::

        tools:
          gws:
            enabled: true
            binary_path: gws
            auth_method: oauth
            credentials_path: .credentials/gws-creds.json
            default_timeout: 30
            commands:
              - action: sheets_read
                gws_command: "gws sheets get {spreadsheet_id} --range {range}"
                required_params: [spreadsheet_id]
                optional_params: [range]
                service: sheets
    """

    enabled: bool = True
    binary_path: str = Field(
        default="gws",
        description="Path to the gws CLI binary",
    )
    auth_method: GwsAuthMethod = GwsAuthMethod.OAUTH
    credentials_path: str = Field(
        default=".credentials/gws-creds.json",
        description="Path to the gws credentials file",
    )
    default_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Default timeout in seconds for gws commands",
    )
    commands: list[GwsCommandConfig] = Field(
        default_factory=list,
        description="List of gws CLI command mappings",
    )

    model_config = {"extra": "allow"}

    def get_command(self, action: str) -> GwsCommandConfig | None:
        """Look up a command config by action name."""
        for cmd in self.commands:
            if cmd.action == action:
                return cmd
        return None

    @property
    def service_names(self) -> list[str]:
        """Unique service names used across all commands."""
        return list({cmd.service.value for cmd in self.commands})
