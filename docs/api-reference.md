# API Reference

## Base URL

```
http://localhost:8080
```

## Authentication

If `REALIZE_API_KEY` is set, include it in requests:

```
Authorization: Bearer YOUR_API_KEY
```
or
```
X-API-Key: YOUR_API_KEY
```

## Endpoints

### POST /api/chat

Send a message and receive an AI response.

**Request:**
```json
{
  "message": "Help me draft a strategy for Q2",
  "system_key": "consulting",
  "user_id": "user-123",
  "agent_key": "analyst",
  "channel": "api"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| message | string | yes | The user's message |
| system_key | string | yes | Target system key |
| user_id | string | no | User identifier (default: "api-user") |
| agent_key | string | no | Force a specific agent |
| channel | string | no | Channel for formatting (default: "api") |

**Response:**
```json
{
  "response": "Here's my analysis of Q2 strategy...",
  "system_key": "consulting",
  "agent_key": "analyst",
  "user_id": "user-123"
}
```

### GET /api/conversations/{system_key}/{user_id}

Get conversation history.

**Query params:** `limit` (int, default 50)

### DELETE /api/conversations/{system_key}/{user_id}

Clear conversation history.

### GET /api/systems

List all configured systems.

### GET /api/systems/{system_key}

Get system details (agents, routing, venture config).

### GET /api/systems/{system_key}/agents

List agents for a system.

### GET /api/systems/{system_key}/skills

List available skills for a system.

### GET /api/systems/{system_key}/sessions/{user_id}

Get active creative session.

### POST /api/systems/reload

Reload system configurations from YAML (hot reload).

### GET /health

Basic health check. Returns `{"status": "ok"}`.

### GET /status

Detailed status: systems, LLM providers, tool availability, memory stats.
