# API Reference

## Base URL

```
http://localhost:8080
```

## Authentication

RealizeOS supports three authentication methods:

### API Key (simple)

If `REALIZE_API_KEY` is set, include it in requests:

```
Authorization: Bearer YOUR_API_KEY
```
or
```
X-API-Key: YOUR_API_KEY
```

### JWT (multi-user)

If `REALIZE_JWT_ENABLED=true`, obtain a token first:

```bash
# Get tokens
curl -X POST http://localhost:8080/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'

# Use the access token
curl -H "Authorization: Bearer <access_token>" http://localhost:8080/api/systems
```

### No Auth (development)

If neither `REALIZE_API_KEY` nor JWT is configured, the API runs in open mode (suitable for local development).

---

## Chat

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

---

## Authentication

### POST /api/auth/token

Generate JWT access + refresh token pair.

**Request:**
```json
{
  "username": "admin",
  "password": "your-password"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### POST /api/auth/refresh

Refresh an expired access token.

**Request:**
```json
{
  "refresh_token": "eyJ..."
}
```

### GET /api/auth/me

Verify current token and return user claims.

---

## Systems

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

---

## Ventures

### GET /api/ventures

List all ventures with their configuration and status.

### POST /api/ventures

Create a new venture.

**Request:**
```json
{
  "key": "my-venture",
  "name": "My Venture",
  "description": "Venture description",
  "template": "consulting"
}
```

### GET /api/ventures/{key}

Get venture details.

### PUT /api/ventures/{key}

Update venture configuration.

### DELETE /api/ventures/{key}

Delete a venture (requires confirmation).

---

## Venture Agents

### GET /api/ventures/{key}/agents

List all agents for a venture.

### POST /api/ventures/{key}/agents

Create a new agent within a venture.

### GET /api/ventures/{key}/agents/{agent_key}

Get agent definition and configuration.

### PUT /api/ventures/{key}/agents/{agent_key}

Update an agent definition.

### DELETE /api/ventures/{key}/agents/{agent_key}

Delete an agent from a venture.

---

## Venture Knowledge Base

### GET /api/ventures/{key}/kb

Browse the FABRIC directory structure for a venture.

### GET /api/ventures/{key}/kb/{path}

Read a file from the venture knowledge base.

### PUT /api/ventures/{key}/kb/{path}

Create or update a file in the venture knowledge base.

### DELETE /api/ventures/{key}/kb/{path}

Delete a file from the venture knowledge base.

---

## Workflows

### GET /api/workflows

List all workflows.

### POST /api/workflows

Create a new workflow.

### GET /api/workflows/{id}

Get workflow details and execution status.

### POST /api/workflows/{id}/execute

Execute a workflow.

---

## Approvals

### GET /api/approvals

List pending approval requests.

### POST /api/approvals/{id}/approve

Approve an approval request.

### POST /api/approvals/{id}/reject

Reject an approval request.

---

## Extensions

### GET /api/extensions

List all extensions and their status.

### POST /api/extensions/install

Install a new extension.

### DELETE /api/extensions/{name}

Uninstall an extension.

---

## Webhooks

### GET /api/webhooks

List registered webhooks.

### POST /api/webhooks

Register a new webhook.

### DELETE /api/webhooks/{id}

Delete a webhook.

### POST /api/webhooks/{id}/test

Send a test event to a webhook.

---

## Settings

### GET /api/settings

Get general system settings.

### PUT /api/settings

Update general system settings.

### Settings Sub-Categories

| Endpoint | Description |
|----------|-------------|
| `GET/PUT /api/settings/llm` | LLM provider configuration and routing |
| `GET/PUT /api/settings/memory` | Memory and learning log settings |
| `GET/PUT /api/settings/security` | Security configuration |
| `GET/PUT /api/settings/tools` | Tool availability and configuration |
| `GET/PUT /api/settings/trust` | Trust and approval gate settings |
| `GET/PUT /api/settings/skills` | Skill configuration |
| `GET /api/settings/reports` | System reports and analytics |

---

## Storage

### GET /api/settings/storage

Get storage configuration (local/S3).

### PUT /api/settings/storage

Update storage configuration.

### POST /api/settings/storage/test

Test storage connection.

### POST /api/settings/storage/sync

Trigger a sync operation.

---

## Security

### GET /api/security/scan

Run the security posture scanner and return results.

### GET /api/security/audit

Get audit log entries.

---

## Evolution

### GET /api/evolution/suggestions

Get self-improvement suggestions (gap detection, skill suggestions).

### POST /api/evolution/accept/{id}

Accept a suggestion.

### POST /api/evolution/reject/{id}

Reject a suggestion.

---

## Activity

### GET /api/activity/stream

SSE (Server-Sent Events) activity feed streaming real-time agent actions.

### GET /api/activity

Get recent activity log entries.

---

## Dashboard

### GET /api/dashboard/overview

Get dashboard overview statistics (ventures, agents, activity counts).

---

## Developer Mode

### GET /api/devmode/status

Get developer mode status and configuration.

### POST /api/devmode/setup

Generate AI tool context files.

### GET /api/devmode/health

Run developer mode health check.

---

## Health

### GET /api/health

Basic health check. Returns `{"status": "ok"}`.

**Alias:** Also available at `GET /health` (root path).

### GET /status

Detailed status: systems, LLM providers, tool availability, memory stats.
