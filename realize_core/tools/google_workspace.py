"""
Google Workspace tool functions and Claude tool schemas.
13 tools: Gmail (4), Calendar (4), Drive (5).

All functions use asyncio.to_thread() to wrap the synchronous google-api-python-client.
"""
import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


# =====================================================================
# Service builders (lazy, cached per call)
# =====================================================================

def _gmail_service():
    from realize_core.tools.google_auth import get_credentials
    from googleapiclient.discovery import build
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Google credentials not available. See docs for OAuth setup.")
    return build("gmail", "v1", credentials=creds)


def _calendar_service():
    from realize_core.tools.google_auth import get_credentials
    from googleapiclient.discovery import build
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Google credentials not available. See docs for OAuth setup.")
    return build("calendar", "v3", credentials=creds)


def _drive_service():
    from realize_core.tools.google_auth import get_credentials
    from googleapiclient.discovery import build
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Google credentials not available. See docs for OAuth setup.")
    return build("drive", "v3", credentials=creds)


# =====================================================================
# Gmail Tools
# =====================================================================

def _gmail_search_sync(query: str, max_results: int = 5) -> list[dict]:
    service = _gmail_service()
    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    messages = results.get("messages", [])
    output = []
    for msg_stub in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_stub["id"], format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        output.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "snippet": msg.get("snippet", ""),
            "date": headers.get("Date", ""),
        })
    return output


async def gmail_search(query: str, max_results: int = 5) -> list[dict]:
    return await asyncio.to_thread(_gmail_search_sync, query, max_results)


def _gmail_read_sync(message_id: str) -> dict:
    service = _gmail_service()
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = ""
    payload = msg.get("payload", {})
    if payload.get("body", {}).get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    elif payload.get("parts"):
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                break
    return {
        "id": msg["id"], "from": headers.get("From", ""),
        "to": headers.get("To", ""), "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""), "body": body[:3000],
    }


async def gmail_read(message_id: str) -> dict:
    return await asyncio.to_thread(_gmail_read_sync, message_id)


def _gmail_send_sync(to: str, subject: str, body: str, cc: str = None) -> dict:
    service = _gmail_service()
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = cc
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"id": result.get("id"), "threadId": result.get("threadId"), "status": "sent"}


async def gmail_send(to: str, subject: str, body: str, cc: str = None) -> dict:
    return await asyncio.to_thread(_gmail_send_sync, to, subject, body, cc)


def _gmail_create_draft_sync(to: str, subject: str, body: str, cc: str = None) -> dict:
    service = _gmail_service()
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = cc
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    result = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return {"id": result.get("id"), "message_id": result.get("message", {}).get("id"), "status": "draft_created"}


async def gmail_create_draft(to: str, subject: str, body: str, cc: str = None) -> dict:
    return await asyncio.to_thread(_gmail_create_draft_sync, to, subject, body, cc)


# =====================================================================
# Calendar Tools
# =====================================================================

def _calendar_list_events_sync(
    time_min: str = None, time_max: str = None, calendar_id: str = "primary", max_results: int = 10
) -> list[dict]:
    service = _calendar_service()
    now = datetime.now(timezone.utc)
    if not time_min:
        time_min = now.isoformat()
    if not time_max:
        time_max = (now + timedelta(days=7)).isoformat()
    results = service.events().list(
        calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
        maxResults=max_results, singleEvents=True, orderBy="startTime"
    ).execute()
    events = []
    for event in results.get("items", []):
        start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
        end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date", ""))
        attendees = [a.get("email", "") for a in event.get("attendees", [])]
        events.append({
            "id": event.get("id"), "summary": event.get("summary", "(No title)"),
            "start": start, "end": end, "location": event.get("location", ""),
            "attendees": attendees, "status": event.get("status", ""),
        })
    return events


async def calendar_list_events(
    time_min: str = None, time_max: str = None, calendar_id: str = "primary", max_results: int = 10
) -> list[dict]:
    return await asyncio.to_thread(_calendar_list_events_sync, time_min, time_max, calendar_id, max_results)


def _calendar_create_event_sync(
    summary: str, start: str, end: str,
    description: str = None, attendees: list[str] = None, calendar_id: str = "primary"
) -> dict:
    service = _calendar_service()
    event_body = {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}}
    if description:
        event_body["description"] = description
    if attendees:
        event_body["attendees"] = [{"email": e} for e in attendees]
    result = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    return {
        "id": result.get("id"), "summary": result.get("summary"),
        "start": result.get("start", {}).get("dateTime", ""),
        "end": result.get("end", {}).get("dateTime", ""),
        "htmlLink": result.get("htmlLink", ""),
    }


async def calendar_create_event(
    summary: str, start: str, end: str,
    description: str = None, attendees: list[str] = None, calendar_id: str = "primary"
) -> dict:
    return await asyncio.to_thread(
        _calendar_create_event_sync, summary, start, end, description, attendees, calendar_id
    )


def _calendar_update_event_sync(event_id: str, calendar_id: str = "primary", **updates) -> dict:
    service = _calendar_service()
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    for key, value in updates.items():
        if key in ("start", "end") and isinstance(value, str):
            event[key] = {"dateTime": value}
        elif key == "attendees" and isinstance(value, list):
            event["attendees"] = [{"email": e} for e in value]
        else:
            event[key] = value
    result = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
    return {
        "id": result.get("id"), "summary": result.get("summary"),
        "start": result.get("start", {}).get("dateTime", ""),
        "end": result.get("end", {}).get("dateTime", ""), "status": "updated",
    }


async def calendar_update_event(event_id: str, calendar_id: str = "primary", **updates) -> dict:
    return await asyncio.to_thread(_calendar_update_event_sync, event_id, calendar_id, **updates)


def _calendar_find_free_time_sync(time_min: str, time_max: str, calendar_ids: list[str] = None) -> list[dict]:
    service = _calendar_service()
    if not calendar_ids:
        calendar_ids = ["primary"]
    body = {"timeMin": time_min, "timeMax": time_max, "items": [{"id": cid} for cid in calendar_ids]}
    result = service.freebusy().query(body=body).execute()
    busy_slots = []
    for cal_id, cal_data in result.get("calendars", {}).items():
        for busy in cal_data.get("busy", []):
            busy_slots.append({"start": busy["start"], "end": busy["end"], "calendar": cal_id})
    return busy_slots


async def calendar_find_free_time(time_min: str, time_max: str, calendar_ids: list[str] = None) -> list[dict]:
    return await asyncio.to_thread(_calendar_find_free_time_sync, time_min, time_max, calendar_ids)


# =====================================================================
# Drive Tools
# =====================================================================

def _drive_search_sync(query: str, max_results: int = 10) -> list[dict]:
    service = _drive_service()
    safe_query = query.replace("\\", "\\\\").replace("'", "\\'")
    results = service.files().list(
        q=f"fullText contains '{safe_query}' and trashed = false",
        pageSize=max_results,
        fields="files(id, name, mimeType, modifiedTime, webViewLink)",
        orderBy="modifiedTime desc",
    ).execute()
    return [
        {"id": f.get("id"), "name": f.get("name"), "mimeType": f.get("mimeType", ""),
         "modifiedTime": f.get("modifiedTime", ""), "webViewLink": f.get("webViewLink", "")}
        for f in results.get("files", [])
    ]


async def drive_search(query: str, max_results: int = 10) -> list[dict]:
    return await asyncio.to_thread(_drive_search_sync, query, max_results)


def _drive_list_folder_sync(folder_id: str = "root", max_results: int = 20) -> list[dict]:
    service = _drive_service()
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        pageSize=max_results, fields="files(id, name, mimeType, modifiedTime)", orderBy="name",
    ).execute()
    return [
        {"id": f.get("id"), "name": f.get("name"), "mimeType": f.get("mimeType", ""),
         "modifiedTime": f.get("modifiedTime", "")}
        for f in results.get("files", [])
    ]


async def drive_list_folder(folder_id: str = "root", max_results: int = 20) -> list[dict]:
    return await asyncio.to_thread(_drive_list_folder_sync, folder_id, max_results)


def _drive_read_content_sync(file_id: str) -> dict:
    service = _drive_service()
    meta = service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
    mime_type = meta.get("mimeType", "")
    name = meta.get("name", "")
    export_map = {
        "application/vnd.google-apps.document": ("text/plain", "text"),
        "application/vnd.google-apps.spreadsheet": ("text/csv", "csv"),
        "application/vnd.google-apps.presentation": ("text/plain", "text"),
    }
    if mime_type in export_map:
        export_mime, fmt = export_map[mime_type]
        content = service.files().export(fileId=file_id, mimeType=export_mime).execute()
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        if len(content) > 8000:
            content = content[:8000] + "\n\n... (truncated)"
        return {"id": file_id, "name": name, "mimeType": mime_type, "format": fmt, "content": content}
    try:
        content = service.files().get_media(fileId=file_id).execute()
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        if len(content) > 8000:
            content = content[:8000] + "\n\n... (truncated)"
        return {"id": file_id, "name": name, "mimeType": mime_type, "format": "raw", "content": content}
    except Exception:
        return {"id": file_id, "name": name, "mimeType": mime_type, "error": "Cannot read content of this file type"}


async def drive_read_content(file_id: str) -> dict:
    return await asyncio.to_thread(_drive_read_content_sync, file_id)


def _drive_create_doc_sync(title: str, content: str = "", folder_id: str = None) -> dict:
    from realize_core.tools.google_auth import get_credentials
    from googleapiclient.discovery import build as _build
    service = _drive_service()
    file_metadata = {"name": title, "mimeType": "application/vnd.google-apps.document"}
    if folder_id:
        file_metadata["parents"] = [folder_id]
    doc = service.files().create(body=file_metadata, fields="id, name, webViewLink").execute()
    if content:
        creds = get_credentials()
        docs_service = _build("docs", "v1", credentials=creds)
        docs_service.documents().batchUpdate(
            documentId=doc["id"],
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        ).execute()
    return {"id": doc["id"], "name": doc["name"], "webViewLink": doc.get("webViewLink", ""), "status": "created"}


async def drive_create_doc(title: str, content: str = "", folder_id: str = None) -> dict:
    return await asyncio.to_thread(_drive_create_doc_sync, title, content, folder_id)


def _drive_append_doc_sync(file_id: str, content: str) -> dict:
    from realize_core.tools.google_auth import get_credentials
    from googleapiclient.discovery import build as _build
    creds = get_credentials()
    docs_service = _build("docs", "v1", credentials=creds)
    doc = docs_service.documents().get(documentId=file_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1
    docs_service.documents().batchUpdate(
        documentId=file_id,
        body={"requests": [{"insertText": {"location": {"index": end_index}, "text": "\n" + content}}]},
    ).execute()
    return {"id": file_id, "title": doc.get("title", ""), "status": "appended", "chars_added": len(content)}


async def drive_append_doc(file_id: str, content: str) -> dict:
    return await asyncio.to_thread(_drive_append_doc_sync, file_id, content)


# =====================================================================
# Tool Schemas + Registry
# =====================================================================

GOOGLE_TOOL_SCHEMAS = [
    {"name": "gmail_search", "description": "Search emails in Gmail by sender, subject, keywords, or date.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Gmail search query (e.g., 'from:name subject:budget', 'is:unread')"},
         "max_results": {"type": "integer", "description": "Maximum results (default: 5)", "default": 5}},
         "required": ["query"]}},
    {"name": "gmail_read", "description": "Read full content of an email by message ID.",
     "input_schema": {"type": "object", "properties": {
         "message_id": {"type": "string", "description": "Gmail message ID"}}, "required": ["message_id"]}},
    {"name": "gmail_send", "description": "Send an email. Write operation — requires confirmation.",
     "input_schema": {"type": "object", "properties": {
         "to": {"type": "string"}, "subject": {"type": "string"},
         "body": {"type": "string"}, "cc": {"type": "string"}}, "required": ["to", "subject", "body"]}},
    {"name": "gmail_create_draft", "description": "Create a draft email. Write operation — requires confirmation.",
     "input_schema": {"type": "object", "properties": {
         "to": {"type": "string"}, "subject": {"type": "string"},
         "body": {"type": "string"}, "cc": {"type": "string"}}, "required": ["to", "subject", "body"]}},
    {"name": "calendar_list_events", "description": "List upcoming calendar events within a time range.",
     "input_schema": {"type": "object", "properties": {
         "time_min": {"type": "string"}, "time_max": {"type": "string"},
         "calendar_id": {"type": "string", "default": "primary"},
         "max_results": {"type": "integer", "default": 10}}}},
    {"name": "calendar_create_event", "description": "Create a calendar event. Write operation.",
     "input_schema": {"type": "object", "properties": {
         "summary": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
         "description": {"type": "string"}, "attendees": {"type": "array", "items": {"type": "string"}},
         "calendar_id": {"type": "string"}}, "required": ["summary", "start", "end"]}},
    {"name": "calendar_update_event", "description": "Update an existing calendar event. Write operation.",
     "input_schema": {"type": "object", "properties": {
         "event_id": {"type": "string"}, "summary": {"type": "string"},
         "start": {"type": "string"}, "end": {"type": "string"},
         "calendar_id": {"type": "string"}}, "required": ["event_id"]}},
    {"name": "calendar_find_free_time", "description": "Find busy/free time slots across calendars.",
     "input_schema": {"type": "object", "properties": {
         "time_min": {"type": "string"}, "time_max": {"type": "string"},
         "calendar_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["time_min", "time_max"]}},
    {"name": "drive_search", "description": "Search for files in Google Drive.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"}, "max_results": {"type": "integer", "default": 10}}, "required": ["query"]}},
    {"name": "drive_list_folder", "description": "List contents of a Google Drive folder.",
     "input_schema": {"type": "object", "properties": {
         "folder_id": {"type": "string", "default": "root"}, "max_results": {"type": "integer", "default": 20}}}},
    {"name": "drive_read_content", "description": "Read text content of a Google Doc/Sheet/file.",
     "input_schema": {"type": "object", "properties": {"file_id": {"type": "string"}}, "required": ["file_id"]}},
    {"name": "drive_create_doc", "description": "Create a new Google Doc. Write operation.",
     "input_schema": {"type": "object", "properties": {
         "title": {"type": "string"}, "content": {"type": "string"},
         "folder_id": {"type": "string"}}, "required": ["title"]}},
    {"name": "drive_append_doc", "description": "Append text to an existing Google Doc. Write operation.",
     "input_schema": {"type": "object", "properties": {
         "file_id": {"type": "string"}, "content": {"type": "string"}}, "required": ["file_id", "content"]}},
]

WRITE_TOOLS = {"gmail_send", "gmail_create_draft", "calendar_create_event", "calendar_update_event",
               "drive_create_doc", "drive_append_doc"}
READ_TOOLS = {"gmail_search", "gmail_read", "calendar_list_events", "calendar_find_free_time",
              "drive_search", "drive_list_folder", "drive_read_content"}

TOOL_FUNCTIONS = {
    "gmail_search": gmail_search, "gmail_read": gmail_read,
    "gmail_send": gmail_send, "gmail_create_draft": gmail_create_draft,
    "calendar_list_events": calendar_list_events, "calendar_create_event": calendar_create_event,
    "calendar_update_event": calendar_update_event, "calendar_find_free_time": calendar_find_free_time,
    "drive_search": drive_search, "drive_list_folder": drive_list_folder,
    "drive_read_content": drive_read_content, "drive_create_doc": drive_create_doc,
    "drive_append_doc": drive_append_doc,
}
