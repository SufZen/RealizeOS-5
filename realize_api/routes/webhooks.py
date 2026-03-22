"""
Webhook receiver — accept events from external services.

Supports configurable webhook triggers in realize-os.yaml:
  webhook_triggers:
    - source: github
      event_type: push
      skill: content_pipeline
    - source: stripe
      event_type: invoice.paid
      skill: invoice_processor

Events are logged to the activity system and can trigger skills/workflows.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory log of recent webhook events
_recent_events: list[dict] = []
MAX_RECENT = 50


@router.post("/webhooks/{source}")
async def receive_webhook(source: str, request: Request):
    """
    Receive a webhook event from an external service.

    Args:
        source: The webhook source identifier (github, stripe, custom, etc.)
    """
    config = getattr(request.app.state, "config", {})

    # Verify webhook secret if configured
    webhook_secret = config.get("features", {}).get("webhook_secret", "")
    if webhook_secret:
        signature = request.headers.get("X-Webhook-Signature", "")
        body_bytes = await request.body()
        expected = hmac.new(webhook_secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        body = await request.json()
    except Exception:
        body = {"raw": (await request.body()).decode("utf-8", errors="replace")[:2000]}

    # Build event record
    event = {
        "source": source,
        "event_type": _detect_event_type(source, body, request.headers),
        "payload": body,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "headers": {
            "content-type": request.headers.get("content-type", ""),
            "user-agent": request.headers.get("user-agent", ""),
        },
    }

    # Store in recent events
    _recent_events.insert(0, event)
    if len(_recent_events) > MAX_RECENT:
        _recent_events.pop()

    # Log to activity system
    try:
        from realize_core.activity.logger import log_event
        log_event(
            venture_key="shared",
            actor_type="webhook",
            actor_id=source,
            action="webhook_received",
            entity_type="event",
            entity_id=event["event_type"],
            details=str(body)[:500],
        )
    except Exception:
        pass

    # Check for matching webhook triggers
    triggers = config.get("webhook_triggers", [])
    matched = []
    for trigger in triggers:
        if trigger.get("source") == source:
            trigger_event = trigger.get("event_type", "")
            if not trigger_event or trigger_event in event["event_type"]:
                matched.append(trigger)

    # Execute matched triggers
    for trigger in matched:
        skill_name = trigger.get("skill", "")
        if skill_name:
            logger.info(f"Webhook trigger matched: {source}/{event['event_type']} -> skill:{skill_name}")
            try:
                from realize_core.activity.logger import log_event as _log
                _log(
                    venture_key="shared",
                    actor_type="webhook",
                    actor_id=source,
                    action="webhook_trigger_fired",
                    entity_type="skill",
                    entity_id=skill_name,
                )
            except Exception:
                pass

    return {
        "status": "received",
        "source": source,
        "event_type": event["event_type"],
        "triggers_matched": len(matched),
    }


@router.get("/webhooks/events")
async def list_webhook_events():
    """List recent webhook events."""
    return {
        "events": [
            {
                "source": e["source"],
                "event_type": e["event_type"],
                "received_at": e["received_at"],
                "payload_preview": str(e["payload"])[:200],
            }
            for e in _recent_events[:20]
        ],
        "total": len(_recent_events),
    }


def _detect_event_type(source: str, body: dict, headers) -> str:
    """Detect the event type from the webhook payload or headers."""
    # GitHub
    if source == "github":
        return headers.get("X-GitHub-Event", body.get("action", "unknown"))

    # Stripe
    if source == "stripe":
        return body.get("type", "unknown")

    # Generic
    if "event" in body:
        return str(body["event"])
    if "type" in body:
        return str(body["type"])
    if "event_type" in body:
        return str(body["event_type"])
    if "action" in body:
        return str(body["action"])

    return "unknown"
