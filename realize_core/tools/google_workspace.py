"""
Google Workspace tool functions and Claude tool schemas.
21 tools: Gmail (8), Calendar (4), Drive (9).

All functions use asyncio.to_thread() to wrap the synchronous google-api-python-client.
"""
import asyncio
import base64
import logging
from datetime import UTC, datetime, timedelta
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


# =====================================================================
# Service builders (lazy, cached per call)
# =====================================================================

def _gmail_service():
    from googleapiclient.discovery import build

    from realize_core.tools.google_auth import get_credentials
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Google credentials not available. See docs for OAuth setup.")
    return build("gmail", "v1", credentials=creds)


def _calendar_service():
    from googleapiclient.discovery import build

    from realize_core.tools.google_auth import get_credentials
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Google credentials not available. See docs for OAuth setup.")
    return build("calendar", "v3", credentials=creds)


def _drive_service():
    from googleapiclient.discovery import build

    from realize_core.tools.google_auth import get_credentials
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


def _gmail_reply_sync(
    message_id: str, body: str, reply_all: bool = False,
) -> dict:
    """Reply to an existing email thread."""
    service = _gmail_service()
    # Fetch original message to get thread ID and headers
    original = service.users().messages().get(
        userId="me", id=message_id, format="metadata",
        metadataHeaders=["From", "To", "Cc", "Subject", "Message-ID"],
    ).execute()
    headers = {
        h["name"]: h["value"]
        for h in original.get("payload", {}).get("headers", [])
    }
    thread_id = original.get("threadId", "")

    # Build reply recipients
    reply_to = headers.get("From", "")
    subject = headers.get("Subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    message = MIMEText(body)
    message["to"] = reply_to
    message["subject"] = subject
    if reply_all and headers.get("Cc"):
        message["cc"] = headers["Cc"]
    if headers.get("Message-ID"):
        message["In-Reply-To"] = headers["Message-ID"]
        message["References"] = headers["Message-ID"]

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    result = service.users().messages().send(
        userId="me", body={"raw": raw, "threadId": thread_id},
    ).execute()
    return {
        "id": result.get("id"),
        "threadId": result.get("threadId"),
        "status": "replied",
        "to": reply_to,
    }


async def gmail_reply(
    message_id: str, body: str, reply_all: bool = False,
) -> dict:
    """Reply to an email thread (async)."""
    return await asyncio.to_thread(_gmail_reply_sync, message_id, body, reply_all)


def _gmail_forward_sync(message_id: str, to: str, note: str = "") -> dict:
    """Forward an email to another recipient."""
    service = _gmail_service()
    original = service.users().messages().get(
        userId="me", id=message_id, format="full",
    ).execute()
    headers = {
        h["name"]: h["value"]
        for h in original.get("payload", {}).get("headers", [])
    }

    # Extract original body
    orig_body = ""
    payload = original.get("payload", {})
    if payload.get("body", {}).get("data"):
        orig_body = base64.urlsafe_b64decode(
            payload["body"]["data"]
        ).decode("utf-8", errors="replace")
    elif payload.get("parts"):
        for part in payload["parts"]:
            if (
                part.get("mimeType") == "text/plain"
                and part.get("body", {}).get("data")
            ):
                orig_body = base64.urlsafe_b64decode(
                    part["body"]["data"]
                ).decode("utf-8", errors="replace")
                break

    # Compose forwarded message
    fwd_body = ""
    if note:
        fwd_body += f"{note}\n\n"
    fwd_body += "---------- Forwarded message ----------\n"
    fwd_body += f"From: {headers.get('From', '')}\n"
    fwd_body += f"Date: {headers.get('Date', '')}\n"
    fwd_body += f"Subject: {headers.get('Subject', '')}\n"
    fwd_body += f"To: {headers.get('To', '')}\n\n"
    fwd_body += orig_body[:3000]

    subject = headers.get("Subject", "")
    if not subject.lower().startswith("fwd:"):
        subject = f"Fwd: {subject}"

    message = MIMEText(fwd_body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    result = service.users().messages().send(
        userId="me", body={"raw": raw},
    ).execute()
    return {
        "id": result.get("id"),
        "threadId": result.get("threadId"),
        "status": "forwarded",
        "to": to,
    }


async def gmail_forward(message_id: str, to: str, note: str = "") -> dict:
    """Forward an email to another address (async)."""
    return await asyncio.to_thread(_gmail_forward_sync, message_id, to, note)


def _gmail_triage_sync(
    message_ids: list[str],
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    mark_read: bool = False,
    archive: bool = False,
) -> dict:
    """
    Bulk triage emails: add/remove labels, mark read, archive.

    This is the primary inbox management action for agents that
    process email on a schedule.
    """
    service = _gmail_service()
    add_label_ids = list(add_labels or [])
    remove_label_ids = list(remove_labels or [])

    if mark_read:
        remove_label_ids.append("UNREAD")
    if archive:
        remove_label_ids.append("INBOX")

    body: dict = {}
    if add_label_ids:
        body["addLabelIds"] = add_label_ids
    if remove_label_ids:
        body["removeLabelIds"] = remove_label_ids

    if not body:
        return {"status": "no_changes", "count": 0}

    results = []
    for msg_id in message_ids:
        try:
            service.users().messages().modify(
                userId="me", id=msg_id, body=body,
            ).execute()
            results.append({"id": msg_id, "status": "updated"})
        except Exception as e:
            results.append({"id": msg_id, "status": "error", "error": str(e)[:200]})

    return {
        "status": "triaged",
        "count": len(results),
        "results": results,
    }


async def gmail_triage(
    message_ids: list[str],
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    mark_read: bool = False,
    archive: bool = False,
) -> dict:
    """Bulk triage emails (async)."""
    return await asyncio.to_thread(
        _gmail_triage_sync, message_ids,
        add_labels, remove_labels, mark_read, archive,
    )


def _gmail_add_label_sync(message_ids: list[str], label_name: str) -> dict:
    """Add a label to one or more messages (creates label if needed)."""
    service = _gmail_service()

    # Resolve or create the label
    labels_resp = service.users().labels().list(userId="me").execute()
    label_id = None
    for label in labels_resp.get("labels", []):
        if label.get("name", "").lower() == label_name.lower():
            label_id = label["id"]
            break

    if not label_id:
        # Create the label
        created = service.users().labels().create(
            userId="me",
            body={"name": label_name, "labelListVisibility": "labelShow",
                  "messageListVisibility": "show"},
        ).execute()
        label_id = created["id"]

    # Apply to messages
    for msg_id in message_ids:
        service.users().messages().modify(
            userId="me", id=msg_id,
            body={"addLabelIds": [label_id]},
        ).execute()

    return {
        "status": "labeled",
        "label": label_name,
        "label_id": label_id,
        "count": len(message_ids),
    }


async def gmail_add_label(message_ids: list[str], label_name: str) -> dict:
    """Add a label to messages (creates label if needed, async)."""
    return await asyncio.to_thread(_gmail_add_label_sync, message_ids, label_name)


# =====================================================================
# Calendar Tools
# =====================================================================

def _calendar_list_events_sync(
    time_min: str = None, time_max: str = None, calendar_id: str = "primary", max_results: int = 10
) -> list[dict]:
    service = _calendar_service()
    now = datetime.now(UTC)
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
    from googleapiclient.discovery import build as _build

    from realize_core.tools.google_auth import get_credentials
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
    from googleapiclient.discovery import build as _build

    from realize_core.tools.google_auth import get_credentials
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


def _drive_upload_sync(
    file_path: str,
    title: str | None = None,
    folder_id: str | None = None,
    mime_type: str | None = None,
) -> dict:
    """Upload a local file to Google Drive."""
    import os

    from googleapiclient.http import MediaFileUpload
    service = _drive_service()

    if not os.path.isfile(file_path):
        return {"error": f"File not found: {file_path}"}

    file_name = title or os.path.basename(file_path)
    file_metadata: dict[str, Any] = {"name": file_name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(
        file_path, mimetype=mime_type, resumable=True,
    )
    result = service.files().create(
        body=file_metadata, media_body=media,
        fields="id, name, mimeType, webViewLink, size",
    ).execute()

    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "mimeType": result.get("mimeType", ""),
        "webViewLink": result.get("webViewLink", ""),
        "size": result.get("size", ""),
        "status": "uploaded",
    }


async def drive_upload(
    file_path: str,
    title: str | None = None,
    folder_id: str | None = None,
    mime_type: str | None = None,
) -> dict:
    """Upload a local file to Google Drive (async)."""
    return await asyncio.to_thread(
        _drive_upload_sync, file_path, title, folder_id, mime_type,
    )


def _drive_download_sync(file_id: str, output_path: str) -> dict:
    """Download a file from Google Drive to a local path."""
    import os

    service = _drive_service()
    meta = service.files().get(
        fileId=file_id, fields="id, name, mimeType",
    ).execute()
    mime_type = meta.get("mimeType", "")
    name = meta.get("name", "download")

    # Google Workspace files need export
    export_map = {
        "application/vnd.google-apps.document": (
            "application/pdf", ".pdf"
        ),
        "application/vnd.google-apps.spreadsheet": (
            "text/csv", ".csv"
        ),
        "application/vnd.google-apps.presentation": (
            "application/pdf", ".pdf"
        ),
    }

    if mime_type in export_map:
        export_mime, ext = export_map[mime_type]
        content = service.files().export(
            fileId=file_id, mimeType=export_mime,
        ).execute()
        final_path = output_path
        if os.path.isdir(output_path):
            final_path = os.path.join(output_path, f"{name}{ext}")
        with open(final_path, "wb") as f:
            if isinstance(content, bytes):
                f.write(content)
            else:
                f.write(str(content).encode("utf-8"))
    else:
        content = service.files().get_media(fileId=file_id).execute()
        final_path = output_path
        if os.path.isdir(output_path):
            final_path = os.path.join(output_path, name)
        with open(final_path, "wb") as f:
            if isinstance(content, bytes):
                f.write(content)
            else:
                f.write(str(content).encode("utf-8"))

    return {
        "id": file_id,
        "name": name,
        "output_path": final_path,
        "status": "downloaded",
    }


async def drive_download(file_id: str, output_path: str) -> dict:
    """Download a file from Google Drive (async)."""
    return await asyncio.to_thread(_drive_download_sync, file_id, output_path)


def _drive_set_permissions_sync(
    file_id: str,
    email: str,
    role: str = "reader",
    send_notification: bool = True,
) -> dict:
    """
    Set permissions on a Drive file/folder.

    Args:
        file_id: The file ID to share.
        email: Email address to share with.
        role: Permission role — reader, writer, commenter, or owner.
        send_notification: Whether to send a notification email.
    """
    service = _drive_service()
    permission = {
        "type": "user",
        "role": role,
        "emailAddress": email,
    }
    result = service.permissions().create(
        fileId=file_id,
        body=permission,
        sendNotificationEmail=send_notification,
        fields="id, type, role, emailAddress",
    ).execute()
    return {
        "id": result.get("id"),
        "file_id": file_id,
        "email": email,
        "role": role,
        "status": "shared",
    }


async def drive_set_permissions(
    file_id: str,
    email: str,
    role: str = "reader",
    send_notification: bool = True,
) -> dict:
    """Set file permissions (async)."""
    return await asyncio.to_thread(
        _drive_set_permissions_sync,
        file_id, email, role, send_notification,
    )


def _drive_move_sync(
    file_id: str,
    target_folder_id: str,
) -> dict:
    """Move a file to a different Drive folder."""
    service = _drive_service()
    file_info = service.files().get(
        fileId=file_id, fields="parents, name",
    ).execute()
    previous_parents = ",".join(file_info.get("parents", []))
    result = service.files().update(
        fileId=file_id,
        addParents=target_folder_id,
        removeParents=previous_parents,
        fields="id, name, parents",
    ).execute()
    return {
        "id": result.get("id"),
        "name": result.get("name", ""),
        "target_folder": target_folder_id,
        "status": "moved",
    }


async def drive_move(file_id: str, target_folder_id: str) -> dict:
    """Move a file between Drive folders (async)."""
    return await asyncio.to_thread(_drive_move_sync, file_id, target_folder_id)


# =====================================================================
# Tool Schemas + Registry
# =====================================================================

GOOGLE_TOOL_SCHEMAS = [
    # --- Gmail (8 tools) ---
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
    {"name": "gmail_reply", "description": "Reply to an existing email thread. Write operation.",
     "input_schema": {"type": "object", "properties": {
         "message_id": {"type": "string", "description": "ID of the message to reply to"},
         "body": {"type": "string", "description": "Reply body text"},
         "reply_all": {"type": "boolean", "description": "Reply to all recipients", "default": False}},
         "required": ["message_id", "body"]}},
    {"name": "gmail_forward", "description": "Forward an email to another address. Write operation.",
     "input_schema": {"type": "object", "properties": {
         "message_id": {"type": "string", "description": "ID of the message to forward"},
         "to": {"type": "string", "description": "Recipient email address"},
         "note": {"type": "string", "description": "Optional note to include above the forwarded message"}},
         "required": ["message_id", "to"]}},
    {"name": "gmail_triage", "description": "Bulk triage emails: add/remove labels, mark read, archive. Write operation.",
     "input_schema": {"type": "object", "properties": {
         "message_ids": {"type": "array", "items": {"type": "string"}, "description": "List of message IDs to triage"},
         "add_labels": {"type": "array", "items": {"type": "string"}, "description": "Label IDs to add"},
         "remove_labels": {"type": "array", "items": {"type": "string"}, "description": "Label IDs to remove"},
         "mark_read": {"type": "boolean", "description": "Mark messages as read", "default": False},
         "archive": {"type": "boolean", "description": "Archive messages (remove from INBOX)", "default": False}},
         "required": ["message_ids"]}},
    {"name": "gmail_add_label", "description": "Add a label to messages (creates label if needed). Write operation.",
     "input_schema": {"type": "object", "properties": {
         "message_ids": {"type": "array", "items": {"type": "string"}, "description": "List of message IDs"},
         "label_name": {"type": "string", "description": "Label name (created if it doesn't exist)"}},
         "required": ["message_ids", "label_name"]}},
    # --- Calendar (4 tools, unchanged) ---
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
    # --- Drive (9 tools) ---
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
    {"name": "drive_upload", "description": "Upload a local file to Google Drive. Write operation.",
     "input_schema": {"type": "object", "properties": {
         "file_path": {"type": "string", "description": "Local path of the file to upload"},
         "title": {"type": "string", "description": "Optional title (defaults to filename)"},
         "folder_id": {"type": "string", "description": "Optional target folder ID"},
         "mime_type": {"type": "string", "description": "Optional MIME type override"}},
         "required": ["file_path"]}},
    {"name": "drive_download", "description": "Download a file from Google Drive to local path.",
     "input_schema": {"type": "object", "properties": {
         "file_id": {"type": "string", "description": "Drive file ID to download"},
         "output_path": {"type": "string", "description": "Local path to save the file"}},
         "required": ["file_id", "output_path"]}},
    {"name": "drive_set_permissions", "description": "Share a Drive file with an email address. Write operation.",
     "input_schema": {"type": "object", "properties": {
         "file_id": {"type": "string", "description": "Drive file ID to share"},
         "email": {"type": "string", "description": "Email address to share with"},
         "role": {"type": "string", "description": "Permission role: reader, writer, commenter, or owner", "default": "reader"},
         "send_notification": {"type": "boolean", "description": "Send notification email", "default": True}},
         "required": ["file_id", "email"]}},
    {"name": "drive_move", "description": "Move a file to a different Drive folder. Write operation.",
     "input_schema": {"type": "object", "properties": {
         "file_id": {"type": "string", "description": "File ID to move"},
         "target_folder_id": {"type": "string", "description": "Target folder ID"}},
         "required": ["file_id", "target_folder_id"]}},
]

WRITE_TOOLS = {
    "gmail_send", "gmail_create_draft", "gmail_reply", "gmail_forward",
    "gmail_triage", "gmail_add_label",
    "calendar_create_event", "calendar_update_event",
    "drive_create_doc", "drive_append_doc", "drive_upload",
    "drive_set_permissions", "drive_move",
}
READ_TOOLS = {
    "gmail_search", "gmail_read",
    "calendar_list_events", "calendar_find_free_time",
    "drive_search", "drive_list_folder", "drive_read_content", "drive_download",
}

TOOL_FUNCTIONS = {
    # Gmail (8)
    "gmail_search": gmail_search, "gmail_read": gmail_read,
    "gmail_send": gmail_send, "gmail_create_draft": gmail_create_draft,
    "gmail_reply": gmail_reply, "gmail_forward": gmail_forward,
    "gmail_triage": gmail_triage, "gmail_add_label": gmail_add_label,
    # Calendar (4)
    "calendar_list_events": calendar_list_events, "calendar_create_event": calendar_create_event,
    "calendar_update_event": calendar_update_event, "calendar_find_free_time": calendar_find_free_time,
    # Drive (9)
    "drive_search": drive_search, "drive_list_folder": drive_list_folder,
    "drive_read_content": drive_read_content, "drive_create_doc": drive_create_doc,
    "drive_append_doc": drive_append_doc, "drive_upload": drive_upload,
    "drive_download": drive_download, "drive_set_permissions": drive_set_permissions,
    "drive_move": drive_move,
}
