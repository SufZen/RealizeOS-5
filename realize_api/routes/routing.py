"""
Routing API routes — routing configuration and analytics.

Endpoints:
- GET    /api/routing                         — get current routing config
- PUT    /api/routing                         — update routing config
- GET    /api/routing/analytics               — routing decision analytics
- POST   /api/routing/test                    — test routing for a message
- GET    /api/routing/agents/{agent_key}/stats — per-agent routing stats
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory analytics store (reset on restart)
_routing_analytics: list[dict] = []


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class UpdateRoutingBody(BaseModel):
    """Body for updating routing configuration."""

    system_key: str
    agent_routing: dict[str, list[str]] = Field(
        ...,
        description="Mapping of agent_key → keyword list",
    )
    default_agent: str = "orchestrator"


class TestRoutingBody(BaseModel):
    """Body for testing routing with a sample message."""

    message: str
    system_key: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/routing")
async def get_routing_config(request: Request, system_key: str | None = None):
    """
    Get current routing configuration.

    Query params:
    - system_key: return routing for a specific system (optional)
    """
    systems = getattr(request.app.state, "systems", {})

    if system_key:
        if system_key not in systems:
            raise HTTPException(
                status_code=404,
                detail=f"System '{system_key}' not found",
            )
        sys_conf = systems[system_key]
        return {
            "system_key": system_key,
            "agent_routing": sys_conf.get("agent_routing", {}),
            "routing": sys_conf.get("routing", {}),
            "agents": list(sys_conf.get("agents", {}).keys()),
        }

    # Return routing for all systems
    routing_configs = []
    for key, conf in systems.items():
        routing_configs.append(
            {
                "system_key": key,
                "agent_routing": conf.get("agent_routing", {}),
                "routing": conf.get("routing", {}),
                "agents": list(conf.get("agents", {}).keys()),
            }
        )

    return {"routing_configs": routing_configs, "total_systems": len(routing_configs)}


@router.put("/routing")
async def update_routing(body: UpdateRoutingBody, request: Request):
    """Update routing configuration for a system."""
    systems = getattr(request.app.state, "systems", {})

    if body.system_key not in systems:
        raise HTTPException(
            status_code=404,
            detail=f"System '{body.system_key}' not found",
        )

    # Update the in-memory routing config
    systems[body.system_key]["agent_routing"] = body.agent_routing

    logger.info(
        "Updated routing for system '%s': %d agents configured",
        body.system_key,
        len(body.agent_routing),
    )

    return {
        "status": "updated",
        "system_key": body.system_key,
        "agents_configured": list(body.agent_routing.keys()),
    }


@router.post("/routing/test")
async def test_routing(body: TestRoutingBody, request: Request):
    """
    Test which agent a message would be routed to.

    Does NOT execute the message — just shows routing decisions.
    """
    from realize_core.base_handler import select_agent

    systems = getattr(request.app.state, "systems", {})

    if body.system_key not in systems:
        raise HTTPException(
            status_code=404,
            detail=f"System '{body.system_key}' not found",
        )

    sys_conf = systems[body.system_key]
    agent_routing = sys_conf.get("agent_routing", {})

    # If no explicit routing defined, derive from agent keys
    if not agent_routing:
        for agent_key in sys_conf.get("agents", {}):
            keywords = agent_key.replace("_", " ").split()
            agent_routing[agent_key] = keywords

    selected = select_agent(agent_routing, body.message)

    # Calculate scores for all agents for transparency
    msg_lower = body.message.lower()
    scores = {}
    for agent, keywords in agent_routing.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > 0:
            scores[agent] = {"score": score, "matched_keywords": [kw for kw in keywords if kw in msg_lower]}

    # Track analytics
    _routing_analytics.append(
        {
            "system_key": body.system_key,
            "message_preview": body.message[:100],
            "selected_agent": selected,
            "scores": scores,
        }
    )

    return {
        "selected_agent": selected,
        "scores": scores,
        "message_preview": body.message[:100],
        "system_key": body.system_key,
    }


@router.get("/routing/analytics")
async def get_routing_analytics(
    request: Request,
    system_key: str | None = None,
    limit: int = 50,
):
    """
    Get routing decision analytics.

    Query params:
    - system_key: filter by system
    - limit: max entries to return (default 50)
    """
    entries = _routing_analytics

    if system_key:
        entries = [e for e in entries if e.get("system_key") == system_key]

    # Most recent first
    entries = list(reversed(entries[-limit:]))

    # Compute aggregate stats
    agent_counts: dict[str, int] = {}
    for entry in entries:
        agent = entry.get("selected_agent", "unknown")
        agent_counts[agent] = agent_counts.get(agent, 0) + 1

    return {
        "entries": entries,
        "total": len(entries),
        "agent_distribution": agent_counts,
    }


@router.get("/routing/agents/{agent_key}/stats")
async def get_agent_routing_stats(agent_key: str, request: Request):
    """Get routing stats for a specific agent."""
    entries = [e for e in _routing_analytics if e.get("selected_agent") == agent_key]

    # Most common matched keywords
    keyword_counts: dict[str, int] = {}
    for entry in entries:
        agent_scores = entry.get("scores", {}).get(agent_key, {})
        for kw in agent_scores.get("matched_keywords", []):
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

    top_keywords = sorted(keyword_counts.items(), key=lambda x: -x[1])[:10]

    return {
        "agent_key": agent_key,
        "total_routes": len(entries),
        "top_keywords": [{"keyword": kw, "count": c} for kw, c in top_keywords],
    }
