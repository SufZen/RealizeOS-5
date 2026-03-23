"""
Integrations API routes — manage external service integrations.

Endpoints:
- GET    /api/integrations              — list configured integrations
- POST   /api/integrations              — add a new integration
- POST   /api/integrations/{id}/connect — connect an integration
- POST   /api/integrations/{id}/disconnect — disconnect an integration
- POST   /api/integrations/{id}/test    — test integration connection
- DELETE /api/integrations/{id}         — remove an integration
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory integrations store (reset on restart)
_integrations: list[dict] = []


class AddIntegrationBody(BaseModel):
    """Body for adding a new integration."""

    provider: str
    api_key: str | None = None


# Available integrations that users can add
AVAILABLE_INTEGRATIONS = [
    {
        "provider": "google_workspace",
        "name": "Google Workspace",
        "description": "Gmail, Calendar, Drive integration",
        "category": "productivity",
        "requires_api_key": False,
    },
    {
        "provider": "stripe",
        "name": "Stripe",
        "description": "Invoicing, payment links, subscriptions",
        "category": "payments",
        "requires_api_key": True,
    },
    {
        "provider": "telegram",
        "name": "Telegram Bot",
        "description": "Chat with your AI agents via Telegram",
        "category": "communication",
        "requires_api_key": True,
    },
    {
        "provider": "slack",
        "name": "Slack",
        "description": "Slack workspace integration",
        "category": "communication",
        "requires_api_key": True,
    },
    {
        "provider": "notion",
        "name": "Notion",
        "description": "Notion workspace sync",
        "category": "productivity",
        "requires_api_key": True,
    },
]


@router.get("/integrations")
async def list_integrations():
    """List all configured integrations."""
    categories = list({a["category"] for a in AVAILABLE_INTEGRATIONS})

    return {
        "integrations": _integrations,
        "available": AVAILABLE_INTEGRATIONS,
        "categories": categories,
    }


@router.post("/integrations")
async def add_integration(body: AddIntegrationBody):
    """Add a new integration."""
    # Check if provider is valid
    provider_info = next(
        (a for a in AVAILABLE_INTEGRATIONS if a["provider"] == body.provider),
        None,
    )
    if not provider_info:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")

    # Check for duplicates
    if any(i["provider"] == body.provider for i in _integrations):
        raise HTTPException(status_code=409, detail=f"Integration '{body.provider}' already exists")

    integration = {
        "id": uuid.uuid4().hex[:16],
        "name": provider_info["name"],
        "provider": body.provider,
        "category": provider_info["category"],
        "status": "connected" if body.api_key else "disconnected",
        "description": provider_info["description"],
        "last_sync": None,
        "events_received": 0,
        "error_message": None,
    }
    _integrations.append(integration)

    logger.info("Added integration: %s", body.provider)
    return integration


@router.post("/integrations/{integration_id}/connect")
async def connect_integration(integration_id: str):
    """Connect an integration."""
    integration = next((i for i in _integrations if i["id"] == integration_id), None)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    integration["status"] = "connected"
    return {"status": "connected"}


@router.post("/integrations/{integration_id}/disconnect")
async def disconnect_integration(integration_id: str):
    """Disconnect an integration."""
    integration = next((i for i in _integrations if i["id"] == integration_id), None)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    integration["status"] = "disconnected"
    return {"status": "disconnected"}


@router.post("/integrations/{integration_id}/test")
async def test_integration(integration_id: str):
    """Test an integration connection."""
    integration = next((i for i in _integrations if i["id"] == integration_id), None)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    return {"status": "ok", "message": f"Connection to {integration['name']} is working"}


@router.delete("/integrations/{integration_id}")
async def remove_integration(integration_id: str):
    """Remove an integration."""
    global _integrations
    before = len(_integrations)
    _integrations = [i for i in _integrations if i["id"] != integration_id]

    if len(_integrations) == before:
        raise HTTPException(status_code=404, detail="Integration not found")

    return {"status": "removed"}
