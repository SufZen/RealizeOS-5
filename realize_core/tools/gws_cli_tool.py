"""
GWS CLI Tool: Generic shell executor wrapping the ``gws`` CLI.

Provides a BaseTool implementation that maps RealizeOS tool actions
to ``gws`` CLI commands. This allows agents to interact with Google
Workspace services via the CLI binary without requiring native API
client code for every operation.

The tool is configured via ``GwsToolConfig`` (from ``gws_base.py``),
which can be loaded from ``realize-os.yaml`` under ``tools.gws``.

Example config::

    tools:
      gws:
        enabled: true
        binary_path: gws
        commands:
          - action: sheets_get
            gws_command: "gws sheets get {spreadsheet_id}"
            required_params: [spreadsheet_id]
            service: sheets
"""
import asyncio
import json
import logging
import shutil
import subprocess
from typing import Any

from realize_core.tools.base_tool import (
    BaseTool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)
from realize_core.tools.gws_base import GwsToolConfig

logger = logging.getLogger(__name__)

# Default timeout for gws commands (seconds)
_DEFAULT_TIMEOUT = 30


class GwsCliTool(BaseTool):
    """
    Generic shell executor that wraps the ``gws`` command-line tool.

    Each action defined in ``GwsToolConfig.commands`` becomes a tool
    schema that agents can invoke. The tool builds the CLI command
    from the template, executes it in a subprocess, and returns the
    output as a ``ToolResult``.
    """

    def __init__(self, config: GwsToolConfig | None = None):
        self._config = config or GwsToolConfig()

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "gws_cli"

    @property
    def description(self) -> str:
        return (
            "Google Workspace CLI wrapper — executes gws commands "
            "for Gmail, Calendar, Drive, Sheets, and Docs operations."
        )

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.PRODUCTIVITY

    def get_schemas(self) -> list[ToolSchema]:
        """Build tool schemas from the configured command list."""
        schemas: list[ToolSchema] = []
        for cmd in self._config.commands:
            properties: dict[str, Any] = {}
            for param in cmd.required_params:
                properties[param] = {
                    "type": "string",
                    "description": f"Required parameter: {param}",
                }
            for param in cmd.optional_params:
                properties[param] = {
                    "type": "string",
                    "description": f"Optional parameter: {param}",
                }
            schemas.append(
                ToolSchema(
                    name=cmd.action,
                    description=cmd.description or f"Execute gws command: {cmd.gws_command}",
                    input_schema={
                        "type": "object",
                        "properties": properties,
                        "required": cmd.required_params,
                    },
                    category=ToolCategory.PRODUCTIVITY,
                    requires_auth=True,
                    is_destructive=cmd.is_destructive,
                )
            )
        return schemas

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        """
        Execute a gws CLI command.

        Looks up the command config by action name, renders the template
        with the provided params, and runs it in a subprocess.
        """
        cmd_config = self._config.get_command(action)
        if not cmd_config:
            return ToolResult.fail(f"Unknown gws action: '{action}'")

        # Validate required params
        missing = [p for p in cmd_config.required_params if p not in params]
        if missing:
            return ToolResult.fail(
                f"Missing required parameters for '{action}': {', '.join(missing)}"
            )

        # Build the command string
        try:
            cmd_str = self._render_command(cmd_config.gws_command, params)
        except KeyError as e:
            return ToolResult.fail(f"Missing template parameter: {e}")

        timeout = cmd_config.timeout_seconds or self._config.default_timeout

        # Execute in a thread to avoid blocking the event loop
        return await asyncio.to_thread(
            self._run_command, cmd_str, timeout
        )

    def is_available(self) -> bool:
        """Check if the gws binary is installed and the tool is enabled."""
        if not self._config.enabled:
            return False
        return shutil.which(self._config.binary_path) is not None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_command(template: str, params: dict[str, Any]) -> str:
        """
        Render a command template with the given parameters.

        Supports ``{param_name}`` placeholders. Parameters that are not
        in the template are appended as ``--param_name value`` flags.
        """
        # First, substitute placeholders in the template
        rendered = template
        used_params: set[str] = set()

        for key, value in params.items():
            placeholder = f"{{{key}}}"
            if placeholder in rendered:
                rendered = rendered.replace(placeholder, str(value))
                used_params.add(key)

        # Append unused params as CLI flags
        for key, value in params.items():
            if key not in used_params and value is not None:
                flag = key.replace("_", "-")
                rendered += f" --{flag} {_shell_escape(str(value))}"

        return rendered

    @staticmethod
    def _run_command(cmd_str: str, timeout: int) -> ToolResult:
        """
        Run a shell command and return a ToolResult.

        Captures stdout and stderr. Returns success if exit code is 0.
        """
        logger.info("Executing gws command: %s", cmd_str)
        try:
            result = subprocess.run(
                cmd_str,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode == 0:
                # Try to parse JSON output
                data = _try_parse_json(stdout)
                return ToolResult.ok(
                    output=stdout or "(no output)",
                    data=data,
                    exit_code=0,
                )
            else:
                error_msg = stderr or stdout or f"Command exited with code {result.returncode}"
                return ToolResult.fail(
                    error=error_msg,
                    output=stdout,
                    exit_code=result.returncode,
                )

        except subprocess.TimeoutExpired:
            return ToolResult.fail(
                error=f"Command timed out after {timeout}s: {cmd_str[:100]}",
            )
        except FileNotFoundError:
            return ToolResult.fail(
                error="gws binary not found. Install with: pip install gws-cli",
            )
        except Exception as e:
            logger.error("gws command execution error: %s", e, exc_info=True)
            return ToolResult.fail(error=f"Command execution failed: {str(e)[:300]}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shell_escape(value: str) -> str:
    """
    Basic shell escaping for parameter values.

    Wraps values with spaces or special characters in double quotes.
    """
    if not value:
        return '""'
    # If the value contains spaces or shell metacharacters, quote it
    needs_quoting = any(c in value for c in ' \t\n"\'\\|&;$(){}[]<>!#*?~`')
    if needs_quoting:
        # Escape existing double quotes and backslashes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _try_parse_json(text: str) -> Any:
    """Attempt to parse text as JSON; return None on failure."""
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_tool(config: GwsToolConfig | None = None) -> GwsCliTool:
    """Factory function for tool registry auto-discovery."""
    return GwsCliTool(config=config)
