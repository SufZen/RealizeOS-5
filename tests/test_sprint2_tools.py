"""
Sprint 2 Tests — GWS CLI Tool and Google Sheets/Workspace tools.

Tests the new Sprint 2 modules:
  1. GwsCliTool — command rendering, schema generation, availability
  2. google_sheets — schema exports, function registry, read/write sets
  3. google_workspace — new Gmail+Drive tools, expanded registries
  4. google_auth — expanded scopes
  5. tool_registry — new module discovery entries
"""
import asyncio

# =====================================================================
# 1. GWS CLI Tool
# =====================================================================

class TestGwsCliTool:
    """Tests for realize_core.tools.gws_cli_tool."""

    def test_imports(self):
        pass

    def test_default_config(self):
        from realize_core.tools.gws_cli_tool import GwsCliTool
        tool = GwsCliTool()
        assert tool.name == "gws_cli"
        assert tool.category.value == "productivity"
        assert tool.get_schemas() == []

    def test_schemas_from_config(self):
        from realize_core.tools.gws_base import GwsCommandConfig, GwsService, GwsToolConfig
        from realize_core.tools.gws_cli_tool import GwsCliTool

        config = GwsToolConfig(commands=[
            GwsCommandConfig(
                action="sheets_get",
                gws_command="gws sheets get {spreadsheet_id}",
                required_params=["spreadsheet_id"],
                optional_params=["range"],
                service=GwsService.SHEETS,
                description="Read a spreadsheet",
            ),
            GwsCommandConfig(
                action="sheets_append",
                gws_command="gws sheets append {spreadsheet_id}",
                required_params=["spreadsheet_id"],
                service=GwsService.SHEETS,
                is_destructive=True,
            ),
        ])
        tool = GwsCliTool(config=config)
        schemas = tool.get_schemas()
        assert len(schemas) == 2

        read_schema = schemas[0]
        assert read_schema.name == "sheets_get"
        assert read_schema.description == "Read a spreadsheet"
        assert not read_schema.is_destructive
        assert read_schema.requires_auth
        assert "spreadsheet_id" in read_schema.input_schema["required"]

        write_schema = schemas[1]
        assert write_schema.name == "sheets_append"
        assert write_schema.is_destructive

    def test_render_command_basic(self):
        from realize_core.tools.gws_cli_tool import GwsCliTool
        result = GwsCliTool._render_command(
            "gws sheets get {spreadsheet_id}",
            {"spreadsheet_id": "abc123"},
        )
        assert result == "gws sheets get abc123"

    def test_render_command_with_extra_params(self):
        from realize_core.tools.gws_cli_tool import GwsCliTool
        result = GwsCliTool._render_command(
            "gws sheets get {spreadsheet_id}",
            {"spreadsheet_id": "abc", "range": "Sheet1!A1:D10"},
        )
        assert "gws sheets get abc" in result
        assert '--range "Sheet1!A1:D10"' in result

    def test_render_command_no_extra_for_none(self):
        from realize_core.tools.gws_cli_tool import GwsCliTool
        result = GwsCliTool._render_command(
            "gws test {id}",
            {"id": "123", "optional": None},
        )
        assert result == "gws test 123"

    def test_is_available_disabled(self):
        from realize_core.tools.gws_base import GwsToolConfig
        from realize_core.tools.gws_cli_tool import GwsCliTool
        config = GwsToolConfig(enabled=False)
        tool = GwsCliTool(config=config)
        assert not tool.is_available()

    def test_execute_missing_params(self):
        from realize_core.tools.gws_base import GwsCommandConfig, GwsService, GwsToolConfig
        from realize_core.tools.gws_cli_tool import GwsCliTool

        config = GwsToolConfig(commands=[
            GwsCommandConfig(
                action="test_action",
                gws_command="gws test {id}",
                required_params=["id"],
                service=GwsService.SHEETS,
            ),
        ])
        tool = GwsCliTool(config=config)
        result = asyncio.run(
            tool.execute("test_action", {}),
        )
        assert not result.success
        assert "Missing required parameters" in result.error

    def test_execute_unknown_action(self):
        from realize_core.tools.gws_cli_tool import GwsCliTool
        tool = GwsCliTool()
        result = asyncio.run(
            tool.execute("nonexistent", {}),
        )
        assert not result.success
        assert "Unknown gws action" in result.error

    def test_factory(self):
        from realize_core.tools.gws_cli_tool import GwsCliTool, get_tool
        tool = get_tool()
        assert isinstance(tool, GwsCliTool)

    def test_shell_escape(self):
        from realize_core.tools.gws_cli_tool import _shell_escape
        assert _shell_escape("simple") == "simple"
        assert _shell_escape("has space") == '"has space"'
        assert _shell_escape('has"quote') == '"has\\"quote"'
        assert _shell_escape("") == '""'

    def test_try_parse_json(self):
        from realize_core.tools.gws_cli_tool import _try_parse_json
        assert _try_parse_json('{"key": "value"}') == {"key": "value"}
        assert _try_parse_json("not json") is None
        assert _try_parse_json("") is None
        assert _try_parse_json(None) is None


# =====================================================================
# 2. Google Sheets
# =====================================================================

class TestGoogleSheets:
    """Tests for realize_core.tools.google_sheets — native Sheets API."""

    def test_imports(self):
        pass

    def test_schema_count(self):
        from realize_core.tools.google_sheets import SHEETS_TOOL_SCHEMAS
        assert len(SHEETS_TOOL_SCHEMAS) == 3

    def test_schema_names(self):
        from realize_core.tools.google_sheets import SHEETS_TOOL_SCHEMAS
        names = {s["name"] for s in SHEETS_TOOL_SCHEMAS}
        assert names == {"sheets_read", "sheets_append", "sheets_create"}

    def test_read_schema_required(self):
        from realize_core.tools.google_sheets import SHEETS_TOOL_SCHEMAS
        read_schema = next(
            s for s in SHEETS_TOOL_SCHEMAS if s["name"] == "sheets_read"
        )
        assert "spreadsheet_id" in read_schema["input_schema"]["required"]

    def test_append_schema_required(self):
        from realize_core.tools.google_sheets import SHEETS_TOOL_SCHEMAS
        append_schema = next(
            s for s in SHEETS_TOOL_SCHEMAS if s["name"] == "sheets_append"
        )
        required = append_schema["input_schema"]["required"]
        assert "spreadsheet_id" in required
        assert "values" in required

    def test_create_schema_required(self):
        from realize_core.tools.google_sheets import SHEETS_TOOL_SCHEMAS
        create_schema = next(
            s for s in SHEETS_TOOL_SCHEMAS if s["name"] == "sheets_create"
        )
        assert "title" in create_schema["input_schema"]["required"]

    def test_read_write_sets(self):
        from realize_core.tools.google_sheets import SHEETS_READ_TOOLS, SHEETS_WRITE_TOOLS
        assert SHEETS_READ_TOOLS == {"sheets_read"}
        assert SHEETS_WRITE_TOOLS == {"sheets_append", "sheets_create"}

    def test_tool_functions_mapped(self):
        from realize_core.tools.google_sheets import SHEETS_TOOL_FUNCTIONS
        assert len(SHEETS_TOOL_FUNCTIONS) == 3
        assert all(callable(fn) for fn in SHEETS_TOOL_FUNCTIONS.values())

    def test_functions_are_async(self):
        import asyncio

        from realize_core.tools.google_sheets import sheets_append, sheets_create, sheets_read
        assert asyncio.iscoroutinefunction(sheets_read)
        assert asyncio.iscoroutinefunction(sheets_append)
        assert asyncio.iscoroutinefunction(sheets_create)


# =====================================================================
# 3. Google Workspace — expanded tools
# =====================================================================

class TestGoogleWorkspaceExpanded:
    """Tests for the expanded google_workspace.py (21 tools)."""

    def test_tool_count(self):
        from realize_core.tools.google_workspace import GOOGLE_TOOL_SCHEMAS
        assert len(GOOGLE_TOOL_SCHEMAS) == 21

    def test_new_gmail_tools_exist(self):
        from realize_core.tools.google_workspace import TOOL_FUNCTIONS
        new_tools = ["gmail_reply", "gmail_forward", "gmail_triage", "gmail_add_label"]
        for tool_name in new_tools:
            assert tool_name in TOOL_FUNCTIONS, f"{tool_name} missing"
            assert callable(TOOL_FUNCTIONS[tool_name])

    def test_new_drive_tools_exist(self):
        from realize_core.tools.google_workspace import TOOL_FUNCTIONS
        new_tools = ["drive_upload", "drive_download", "drive_set_permissions", "drive_move"]
        for tool_name in new_tools:
            assert tool_name in TOOL_FUNCTIONS, f"{tool_name} missing"
            assert callable(TOOL_FUNCTIONS[tool_name])

    def test_write_tools_updated(self):
        from realize_core.tools.google_workspace import WRITE_TOOLS
        assert "gmail_reply" in WRITE_TOOLS
        assert "gmail_forward" in WRITE_TOOLS
        assert "gmail_triage" in WRITE_TOOLS
        assert "gmail_add_label" in WRITE_TOOLS
        assert "drive_upload" in WRITE_TOOLS
        assert "drive_set_permissions" in WRITE_TOOLS
        assert "drive_move" in WRITE_TOOLS
        # Existing ones still present
        assert "gmail_send" in WRITE_TOOLS
        assert "calendar_create_event" in WRITE_TOOLS

    def test_read_tools_updated(self):
        from realize_core.tools.google_workspace import READ_TOOLS
        assert "drive_download" in READ_TOOLS
        # Existing ones still present
        assert "gmail_search" in READ_TOOLS
        assert "gmail_read" in READ_TOOLS
        assert "drive_search" in READ_TOOLS

    def test_schema_names_complete(self):
        from realize_core.tools.google_workspace import GOOGLE_TOOL_SCHEMAS, TOOL_FUNCTIONS
        schema_names = {s["name"] for s in GOOGLE_TOOL_SCHEMAS}
        func_names = set(TOOL_FUNCTIONS.keys())
        assert schema_names == func_names, f"Mismatch: {schema_names ^ func_names}"

    def test_all_functions_are_async(self):
        import asyncio

        from realize_core.tools.google_workspace import TOOL_FUNCTIONS
        for name, fn in TOOL_FUNCTIONS.items():
            assert asyncio.iscoroutinefunction(fn), f"{name} is not async"

    def test_gmail_triage_schema(self):
        from realize_core.tools.google_workspace import GOOGLE_TOOL_SCHEMAS
        schema = next(s for s in GOOGLE_TOOL_SCHEMAS if s["name"] == "gmail_triage")
        assert "message_ids" in schema["input_schema"]["required"]
        props = schema["input_schema"]["properties"]
        assert "mark_read" in props
        assert "archive" in props

    def test_drive_upload_schema(self):
        from realize_core.tools.google_workspace import GOOGLE_TOOL_SCHEMAS
        schema = next(s for s in GOOGLE_TOOL_SCHEMAS if s["name"] == "drive_upload")
        assert "file_path" in schema["input_schema"]["required"]

    def test_drive_permissions_schema(self):
        from realize_core.tools.google_workspace import GOOGLE_TOOL_SCHEMAS
        schema = next(
            s for s in GOOGLE_TOOL_SCHEMAS if s["name"] == "drive_set_permissions"
        )
        required = schema["input_schema"]["required"]
        assert "file_id" in required
        assert "email" in required


# =====================================================================
# 4. Google Auth — expanded scopes
# =====================================================================

class TestGoogleAuthExpanded:
    """Tests that the Sheets scope has been added."""

    def test_sheets_scope_present(self):
        from realize_core.tools.google_auth import SCOPES
        assert "https://www.googleapis.com/auth/spreadsheets" in SCOPES

    def test_existing_scopes_unchanged(self):
        from realize_core.tools.google_auth import SCOPES
        assert "https://www.googleapis.com/auth/calendar" in SCOPES
        assert "https://www.googleapis.com/auth/drive" in SCOPES
        assert "https://www.googleapis.com/auth/gmail.modify" in SCOPES
        assert "https://mail.google.com/" in SCOPES

    def test_scope_count(self):
        from realize_core.tools.google_auth import SCOPES
        # 7 original + 1 new sheets scope = 8
        assert len(SCOPES) == 8


# =====================================================================
# 5. Tool Registry — new discovery entries
# =====================================================================

class TestToolRegistryExpanded:
    """Tests that tool_registry includes new modules in discovery."""

    def test_registry_imports(self):
        pass

    def test_registry_singleton(self):
        from realize_core.tools.tool_registry import get_tool_registry
        r1 = get_tool_registry()
        r2 = get_tool_registry()
        assert r1 is r2

    def test_auto_discover_has_new_modules(self):
        """Verify the known_modules list includes gws_cli_tool and google_sheets_tool."""
        import inspect

        from realize_core.tools.tool_registry import ToolRegistry

        source = inspect.getsource(ToolRegistry.auto_discover)
        assert "realize_core.tools.gws_cli_tool" in source
        assert "realize_core.tools.google_sheets_tool" in source
