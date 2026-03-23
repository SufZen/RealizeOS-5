"""
Native Google Sheets tool functions and Claude tool schemas.

Provides direct Google Sheets API access for:
  - sheets_read:   Read cell data from a spreadsheet range
  - sheets_append: Append rows to a spreadsheet
  - sheets_create: Create a new spreadsheet

All functions use asyncio.to_thread() to wrap the synchronous
google-api-python-client, following the same pattern as google_workspace.py.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


# =====================================================================
# Service builder
# =====================================================================


def _sheets_service():
    """Build and return a Google Sheets API v4 service client."""
    from googleapiclient.discovery import build

    from realize_core.tools.google_auth import get_credentials

    creds = get_credentials()
    if not creds:
        raise RuntimeError("Google credentials not available. See docs for OAuth setup.")
    return build("sheets", "v4", credentials=creds)


def _drive_service():
    """Build Drive service (needed for spreadsheet creation in folders)."""
    from googleapiclient.discovery import build

    from realize_core.tools.google_auth import get_credentials

    creds = get_credentials()
    if not creds:
        raise RuntimeError("Google credentials not available. See docs for OAuth setup.")
    return build("drive", "v3", credentials=creds)


# =====================================================================
# Sheets Tools — Sync implementations
# =====================================================================


def _sheets_read_sync(
    spreadsheet_id: str,
    range: str = "Sheet1",
    value_render_option: str = "FORMATTED_VALUE",
) -> dict:
    """
    Read values from a spreadsheet range.

    Args:
        spreadsheet_id: The ID of the spreadsheet to read.
        range: A1 notation range (e.g. "Sheet1!A1:D10" or "Sheet1").
        value_render_option: How values should be represented
            (FORMATTED_VALUE, UNFORMATTED_VALUE, or FORMULA).

    Returns:
        Dict with spreadsheetId, range, values (2D list), and metadata.
    """
    service = _sheets_service()
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueRenderOption=value_render_option,
        )
        .execute()
    )

    values = result.get("values", [])
    return {
        "spreadsheet_id": spreadsheet_id,
        "range": result.get("range", range),
        "values": values,
        "row_count": len(values),
        "col_count": len(values[0]) if values else 0,
    }


def _sheets_append_sync(
    spreadsheet_id: str,
    range: str = "Sheet1",
    values: list[list[Any]] | None = None,
    value_input_option: str = "USER_ENTERED",
    insert_data_option: str = "INSERT_ROWS",
) -> dict:
    """
    Append rows to a spreadsheet.

    Args:
        spreadsheet_id: The ID of the spreadsheet.
        range: Target sheet/range (e.g. "Sheet1" or "Sheet1!A:D").
        values: 2D list of values to append (each inner list is a row).
        value_input_option: How input data is interpreted
            (RAW or USER_ENTERED).
        insert_data_option: How the input data should be inserted
            (OVERWRITE or INSERT_ROWS).

    Returns:
        Dict with update metadata (updated range, rows, etc.).
    """
    if not values:
        return {"error": "No values provided to append"}

    service = _sheets_service()
    body = {"values": values}
    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption=value_input_option,
            insertDataOption=insert_data_option,
            body=body,
        )
        .execute()
    )

    updates = result.get("updates", {})
    return {
        "spreadsheet_id": spreadsheet_id,
        "updated_range": updates.get("updatedRange", ""),
        "updated_rows": updates.get("updatedRows", 0),
        "updated_columns": updates.get("updatedColumns", 0),
        "updated_cells": updates.get("updatedCells", 0),
        "status": "appended",
    }


def _sheets_create_sync(
    title: str,
    sheet_names: list[str] | None = None,
    folder_id: str | None = None,
) -> dict:
    """
    Create a new Google Spreadsheet.

    Args:
        title: Title of the new spreadsheet.
        sheet_names: Optional list of sheet names to create
            (default: one sheet named "Sheet1").
        folder_id: Optional Google Drive folder ID to place
            the spreadsheet in.

    Returns:
        Dict with spreadsheet ID, URL, and sheet metadata.
    """
    service = _sheets_service()

    # Build the sheet properties
    sheets = []
    if sheet_names:
        for idx, name in enumerate(sheet_names):
            sheets.append(
                {
                    "properties": {
                        "sheetId": idx,
                        "title": name,
                        "index": idx,
                    }
                }
            )

    body: dict[str, Any] = {
        "properties": {"title": title},
    }
    if sheets:
        body["sheets"] = sheets

    result = service.spreadsheets().create(body=body).execute()

    spreadsheet_id = result.get("spreadsheetId", "")
    url = result.get("spreadsheetUrl", "")

    # Move to folder if specified
    if folder_id and spreadsheet_id:
        try:
            drive = _drive_service()
            # Get current parents
            file_info = drive.files().get(fileId=spreadsheet_id, fields="parents").execute()
            previous_parents = ",".join(file_info.get("parents", []))
            # Move to the target folder
            drive.files().update(
                fileId=spreadsheet_id,
                addParents=folder_id,
                removeParents=previous_parents,
                fields="id, parents",
            ).execute()
        except Exception as e:
            logger.warning(
                "Created spreadsheet but failed to move to folder %s: %s",
                folder_id,
                e,
            )

    created_sheets = [
        {
            "sheetId": s.get("properties", {}).get("sheetId"),
            "title": s.get("properties", {}).get("title", ""),
        }
        for s in result.get("sheets", [])
    ]

    return {
        "spreadsheet_id": spreadsheet_id,
        "title": title,
        "url": url,
        "sheets": created_sheets,
        "status": "created",
    }


# =====================================================================
# Async wrappers
# =====================================================================


async def sheets_read(
    spreadsheet_id: str,
    range: str = "Sheet1",
    value_render_option: str = "FORMATTED_VALUE",
) -> dict:
    """Read values from a Google Sheets range (async)."""
    return await asyncio.to_thread(_sheets_read_sync, spreadsheet_id, range, value_render_option)


async def sheets_append(
    spreadsheet_id: str,
    range: str = "Sheet1",
    values: list[list[Any]] | None = None,
    value_input_option: str = "USER_ENTERED",
    insert_data_option: str = "INSERT_ROWS",
) -> dict:
    """Append rows to a Google Sheets spreadsheet (async)."""
    return await asyncio.to_thread(
        _sheets_append_sync,
        spreadsheet_id,
        range,
        values,
        value_input_option,
        insert_data_option,
    )


async def sheets_create(
    title: str,
    sheet_names: list[str] | None = None,
    folder_id: str | None = None,
) -> dict:
    """Create a new Google Spreadsheet (async)."""
    return await asyncio.to_thread(_sheets_create_sync, title, sheet_names, folder_id)


# =====================================================================
# Tool Schemas + Registry mappings
# =====================================================================

SHEETS_TOOL_SCHEMAS = [
    {
        "name": "sheets_read",
        "description": ("Read cell data from a Google Sheets spreadsheet. Returns a 2D array of values."),
        "input_schema": {
            "type": "object",
            "properties": {
                "spreadsheet_id": {
                    "type": "string",
                    "description": "The spreadsheet ID (from the URL).",
                },
                "range": {
                    "type": "string",
                    "description": (
                        "A1 notation range (e.g. 'Sheet1!A1:D10'). Default: 'Sheet1' (entire first sheet)."
                    ),
                    "default": "Sheet1",
                },
                "value_render_option": {
                    "type": "string",
                    "description": ("How to render values: FORMATTED_VALUE, UNFORMATTED_VALUE, or FORMULA."),
                    "default": "FORMATTED_VALUE",
                },
            },
            "required": ["spreadsheet_id"],
        },
    },
    {
        "name": "sheets_append",
        "description": ("Append rows to a Google Sheets spreadsheet. Write operation — requires confirmation."),
        "input_schema": {
            "type": "object",
            "properties": {
                "spreadsheet_id": {
                    "type": "string",
                    "description": "The spreadsheet ID.",
                },
                "range": {
                    "type": "string",
                    "description": ("Target sheet/range (e.g. 'Sheet1' or 'Sheet1!A:D')."),
                    "default": "Sheet1",
                },
                "values": {
                    "type": "array",
                    "description": "2D array of values — each inner array is a row.",
                    "items": {
                        "type": "array",
                        "items": {},
                    },
                },
                "value_input_option": {
                    "type": "string",
                    "description": "RAW or USER_ENTERED (default).",
                    "default": "USER_ENTERED",
                },
            },
            "required": ["spreadsheet_id", "values"],
        },
    },
    {
        "name": "sheets_create",
        "description": ("Create a new Google Spreadsheet. Write operation — requires confirmation."),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the new spreadsheet.",
                },
                "sheet_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": ("Optional list of sheet tab names to create. Default: one sheet named 'Sheet1'."),
                },
                "folder_id": {
                    "type": "string",
                    "description": ("Optional Google Drive folder ID to place the spreadsheet in."),
                },
            },
            "required": ["title"],
        },
    },
]

SHEETS_WRITE_TOOLS = {"sheets_append", "sheets_create"}
SHEETS_READ_TOOLS = {"sheets_read"}

SHEETS_TOOL_FUNCTIONS = {
    "sheets_read": sheets_read,
    "sheets_append": sheets_append,
    "sheets_create": sheets_create,
}
