# Connect your agent

RealizeOS holds the company brain. You bring the agent you already use: Claude Code, Claude Desktop, Claude.ai and Cowork, ChatGPT, Cursor or any other agent that speaks the [Model Context Protocol](https://modelcontextprotocol.io). This page has one guide per agent. Each guide says when and how it was tested, or that it hasn't been tested yet.

For the server side (tool families, configuration keys, OAuth internals, error codes) see [mcp-server.md](mcp-server.md).

## Three ways in

| Way | Endpoint | Use it when | Agents |
|---|---|---|---|
| Local (stdio) | `python cli.py mcp stdio` | The agent runs on the same computer as RealizeOS. No port is opened. | Claude Code, Claude Desktop, Cursor |
| Network, with a header | `https://<host>/mcp` (Streamable HTTP), or `/mcp/sse` for older clients | The agent can send an `Authorization` header. | Claude Code, Cursor, scripts, n8n |
| Connector, with OAuth | `https://<host>/mcp` on a public HTTPS host | The agent signs in through a browser and can't send a fixed header. | Claude.ai, Claude Desktop and Cowork connectors, ChatGPT |

## Verification status

| Agent | Route | Status |
|---|---|---|
| Claude Code | stdio, Streamable HTTP, HTTP+SSE | Verified on 2026-10-13 with Claude Code 2.1.143 on Windows 11 |
| Claude Desktop | stdio (`claude_desktop_config.json`) | Not yet verified in Claude Desktop. The same command was verified through Claude Code and the MCP Python SDK. |
| Claude Desktop, Claude.ai, Cowork | Custom connector (OAuth) | Not yet verified: needs a public HTTPS host |
| ChatGPT | Custom MCP server (OAuth) | Not yet verified: needs a public HTTPS host |
| Cursor and other clients | stdio or HTTP with a header | Not yet verified |
| MCP Python SDK client | stdio | Verified on 2026-10-13 with `mcp` 1.27.1 (`tests/test_mcp_stdio.py`, run in CI) |

What "verified" covered: the agent connected, listed the tools, and called them as a user limited to one venture. `list_ventures` showed only that venture, `kb_search` found a document in it, and `get_system` for another venture returned `MCP_FORBIDDEN`.

## Before you start

1. **Turn MCP on.** In `.env`: `MCP_ENABLED=true` (or `mcp.enabled: true` in `realize-os.yaml`).
2. **Decide who the agent works for.** Every connection acts as one person in `users.yaml`. Their role decides which tools work, and their `ventures` decide which client brains the agent can see:

   ```yaml
   users:
     - email: dana@example.com
       role: operator
       ventures: [tower-b]      # leave out for every venture
       password_hash: "$2b$12$..."
   ```

3. **Optionally limit the tools.** `mcp.tools` (env `MCP_TOOLS`) serves only the tools you name, for example a read-only set. See [mcp-server.md](mcp-server.md#enable-it).

## Agent tokens (one agent, one client's brain)

For an outside agent that connects over the network with a header, use an agent token limited to one client's ventures. Create it on the RealizeOS server, in the RealizeOS folder (where `users.yaml` lives):

```bash
python cli.py agent-token create --name dana-claude --user dana@example.com --venture tower-b --expires-in-days 90
```

- `--name` is a label for people (letters, digits, spaces, dots, dashes, underscores).
- `--user` is the `users.yaml` person the agent works for. Their role applies, and the agent never sees more than their ventures.
- `--venture` is required: repeat it, or separate with commas, for more than one. Each must be one of the user's ventures.
- `--expires-in-days` is optional (1-3650).

It prints the token (`rzag_<id>_<secret>`) once; RealizeOS keeps only a hash. The agent sends it as `Authorization: Bearer <token>` (or `X-API-Key: <token>`), never in the URL. An owner or admin can do the same over REST: `POST /api/agent-tokens` with `{"name", "user", "ventures", "expires_in_days"}` (see [api-reference.md](api-reference.md#agent-tokens)).

`python cli.py agent-token list` shows every token without secrets, and `python cli.py agent-token revoke <id>` stops one at once. Revoking also withdraws that agent's writes still waiting for approval. Removing the user from `users.yaml`, or taking away all of the token's ventures, also stops it.

Never give an agent the shared `REALIZE_API_KEY`. The API key is an owner with access to every venture, it can't be limited, and revoking it breaks every other integration that uses it.

Agent tokens need auth on (`REALIZE_API_KEY` or JWT): with auth off the API is open and a token limits nothing. Pilot accounts (`pilot: true`) can't have one.

Local stdio connections don't use a token: they name the user with `--user` (see [Claude Code](#claude-code)), and they are governed the same way (below).

## What the agent can and can't do

These rules apply to an **agent token** and to a **local stdio session**: the client of a stdio session is always an AI agent, so RealizeOS treats it as an outside agent too. OAuth connectors (Claude.ai, ChatGPT) act as the person who signed in and follow that person's rules; to govern such an agent as an agent, give it an agent token instead.

- **Reads are limited to the agent's ventures.** A token sees the ventures it names (within its user's). A stdio session sees `--venture`, else the user's ventures, else every venture configured when it starts. Tools that span every venture (`realize_status`, `kb_get_document`, `list_suggestions`) return `MCP_FORBIDDEN`. Venture lists are filtered.
- **The role is the upper bound.** A `viewer`'s agent can only read. A `user`'s or `operator`'s agent can chat and ask for workflow runs.
- **Writes wait for a person.** `run_workflow` and `trigger_skill` don't run: they come back as `{"status": "pending_approval", "approval_id": "…"}` and wait in the dashboard's approval queue (as `mcp:run_workflow`, from `agent:<id>` or `agent:stdio:<email>`). When a person approves, the run happens once, as the agent and within its ventures; a held write expires after 24 hours. `log_decision` only proposes a decision for a person to confirm. When the agent chats (`realize_chat`, or `/api/chat` with a token), every write tool the internal agent calls is held for a person too, whatever the trust level; a phrase that matches a workflow doesn't start it (use `trigger_skill`); and the agent can't answer a paused workflow's question. Follow an item with `list_approvals` (`venture_key` and `approval_id`): it shows the outcome (`pending_approval`, `succeeded`, `rejected`, `unknown_outcome` after a restart, …) and the result of the agent's own writes, not other people's details.
- **People decide.** An agent can't approve, reject or dismiss anything, including its own requests: `approve_request`, `reject_request`, `approve_suggestion` and `dismiss_suggestion` return `MCP_AGENT_CANNOT_DECIDE`. Over REST, approve and reject return `403`.
- **Some tools aren't for agents.** `create_venture`, `delete_venture`, `update_setting`, `reload_agents` and `run_evolution` return `MCP_AGENT_REFUSED`, even with `--allow-admin`: an owner does those in the dashboard or CLI. So does any new tool until someone decides its rule.
- **It acts as itself.** An agent can't chat as, or read the history of, another user, whatever its user's role. Over REST, an agent token may read within its ventures and chat; every other REST write returns `403`.
- **Everything is on the record.** Every tool call is written to the audit log (channel `mcp`), including refusals and held writes. A token's calls are logged as `agent:<id>`; a stdio session's under its user's email.

Details and the full per-tool table: [mcp-server.md](mcp-server.md#governed-writes-from-outside-agents).

## Claude Code

Verified on 2026-10-13 with Claude Code 2.1.143 (Windows 11): stdio, Streamable HTTP and HTTP+SSE. `claude mcp get` showed each server as connected, and tool calls through `claude -p` returned the scoped results described above.

### Local (stdio)

```bash
claude mcp add realize-os -- python /path/to/RealizeOS/cli.py mcp stdio --directory /path/to/RealizeOS --user dana@example.com
```

- `--user` is required and must be in `users.yaml`. There is no default user, and it is never read from environment variables.
- `--venture tower-b` narrows the session further (repeatable). It must be one of the user's ventures.
- `--directory` (or `--root`) is the absolute path of the RealizeOS folder, where `realize-os.yaml`, `users.yaml`, `.env` and the data live. Without it, RealizeOS uses the folder it is installed in. It never reads them from the folder the agent happens to start it in, so files left in that folder can't change who the agent is or what it can do.
- Admin tools stay off over stdio unless you add `--allow-admin` (and the user is an owner). `mcp.allow_admin` doesn't turn them on here. Even then, an agent can't call them (see [What the agent can and can't do](#what-the-agent-can-and-cant-do)).
- The session is governed as an outside agent: workflow runs wait for a person's approval, and it can't approve or reject.
- Use the full path of the Python that runs RealizeOS if `python` isn't on the agent's `PATH`. `python -c "import sys; print(sys.executable)"` prints it.
- `claude mcp add --scope project …` writes `.mcp.json` in the current folder so the team shares it. Without `--scope` it is stored for you only.

Anyone who can run this command on the computer can pick any `--user`: on one computer, it limits what the agent sees, it doesn't keep out people who already have the files. For an agent that should see one client, name a user limited to that venture, or add `--venture`.

### Over the network (header)

```bash
claude mcp add --transport http realize-os https://realizeos.example.com/mcp \
  --header "Authorization: Bearer <agent token>"
```

For a server that only has the older transport, use `--transport sse` with `https://realizeos.example.com/mcp/sse`. Keep tokens out of a shared `.mcp.json`: Claude Code expands environment variables there, for example `"Authorization": "Bearer ${REALIZE_AGENT_TOKEN}"`.

## Claude Desktop

### Local (stdio)

Not yet verified in Claude Desktop itself. The command below is the one verified through Claude Code and the MCP Python SDK on 2026-10-13.

Open the config file from **Settings → Developer → Edit Config**. It is at:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

macOS:

```json
{
  "mcpServers": {
    "realize-os": {
      "command": "/usr/local/bin/python3",
      "args": [
        "/Users/dana/RealizeOS/cli.py", "mcp", "stdio",
        "--directory", "/Users/dana/RealizeOS",
        "--user", "dana@example.com"
      ]
    }
  }
}
```

Windows (double the backslashes):

```json
{
  "mcpServers": {
    "realize-os": {
      "command": "C:\\Program Files\\Python312\\python.exe",
      "args": [
        "C:\\RealizeOS\\cli.py", "mcp", "stdio",
        "--directory", "C:\\RealizeOS",
        "--user", "dana@example.com"
      ]
    }
  }
}
```

Quit and reopen Claude Desktop. If the server doesn't appear, read its log: the reason it refused to start is the last line (macOS `~/Library/Logs/Claude/mcp-server-realize-os.log`, Windows `%APPDATA%\Claude\logs\`).

### Custom connector (OAuth)

Not yet verified: needs a public HTTPS host.

Claude reaches custom connectors from Anthropic's servers, not from your computer, so `localhost` won't work. Serve RealizeOS on a public HTTPS host with OAuth on, then add a custom connector with the URL `https://<host>/mcp`. The server setup and the sign-in steps are in [mcp-server.md](mcp-server.md#connect-claudeai-custom-connector-oauth).

## Claude.ai and Cowork

Not yet verified: needs a public HTTPS host.

Claude.ai (web), Claude Desktop and Cowork use the same custom connectors. Add the connector once, as in [Custom connector (OAuth)](#custom-connector-oauth); the person signs in on the RealizeOS page with their `users.yaml` account and gets that account's role and ventures. The default `mcp.oauth.redirect_hosts` already allows `claude.ai` and `claude.com`.

## ChatGPT

Not yet verified: needs a public HTTPS host. Written from OpenAI's documentation as of 2026-10-13 ([connect a custom MCP server](https://developers.openai.com/apps-sdk/deploy/connect-chatgpt), [authentication](https://developers.openai.com/plugins/build/auth)). OpenAI renames these menus often; follow their current guide for the clicks.

What ChatGPT needs, and the RealizeOS side of each:

| ChatGPT needs | RealizeOS |
|---|---|
| A public HTTPS URL that speaks Streamable HTTP | `https://<host>/mcp`. ChatGPT doesn't use `/mcp/sse`. |
| OAuth authorization code with PKCE (`S256`) | Supported (`MCP_OAUTH_ENABLED=true`, `MCP_PUBLIC_URL=https://<host>`). |
| Client registration | ChatGPT prefers Client ID Metadata Documents and falls back to dynamic registration, which RealizeOS serves at `/register`. |
| Redirect back to `chatgpt.com` | Add `chatgpt.com` to `mcp.oauth.redirect_hosts`. ChatGPT uses either `https://chatgpt.com/connector_platform_oauth_redirect` or `https://chatgpt.com/connector/oauth/<id>`; the host entry covers both. |

Setting `redirect_hosts` replaces the defaults, so list the Claude and loopback hosts too:

```yaml
mcp:
  enabled: true
  public_url: https://realizeos.example.com
  oauth:
    enabled: true
    redirect_hosts: [claude.ai, claude.com, chatgpt.com, localhost, 127.0.0.1]
```

Then, in ChatGPT: turn on developer mode (in a workspace, an admin may have to allow it), add a custom MCP server with the URL `https://<host>/mcp` and OAuth authentication, sign in on the RealizeOS page and allow access. OpenAI's help center lists developer mode for Business, Enterprise and Edu workspaces on the web; check what your plan includes.

## Cursor and other MCP clients

Not yet verified.

Cursor reads `~/.cursor/mcp.json` (or `.cursor/mcp.json` in a project). Local:

```json
{
  "mcpServers": {
    "realize-os": {
      "command": "python",
      "args": ["/path/to/RealizeOS/cli.py", "mcp", "stdio", "--directory", "/path/to/RealizeOS", "--user", "dana@example.com"]
    }
  }
}
```

Over the network:

```json
{
  "mcpServers": {
    "realize-os": {
      "url": "https://realizeos.example.com/mcp",
      "headers": { "Authorization": "Bearer <agent token>" }
    }
  }
}
```

Any other MCP client works the same way: either start the stdio command, or point it at `/mcp` (Streamable HTTP) with an `Authorization` header, or at `/mcp/sse` if it only speaks the older transport. With RealizeOS in Docker, use the network route (`http://localhost:8080/mcp`); stdio through `docker compose exec -T api python cli.py mcp stdio …` should work but is not yet verified.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `401` from `/mcp`, no `WWW-Authenticate` header | No credential, or a wrong one, and OAuth is off | Send `Authorization: Bearer <agent token>` (or a JWT). Check the token hasn't expired or been revoked. |
| `401` with `WWW-Authenticate: Bearer resource_metadata=".../.well-known/oauth-protected-resource/mcp"` | OAuth is on and the client hasn't signed in | Connectors: finish the browser sign-in. Header clients: the header is missing or wrong. |
| Sign-in fails with "redirect_uri host is not allowed on this server" | The agent's redirect host isn't in `mcp.oauth.redirect_hosts` | Add it (`chatgpt.com` for ChatGPT). Setting the list replaces the defaults, so keep `claude.ai`, `claude.com` and loopback. |
| `MCP_FORBIDDEN`: "You don't have access to venture '…'" | The venture is outside the user's ventures, the token's venture or `--venture` | Name one of the allowed ventures; `list_ventures` shows them. |
| `MCP_FORBIDDEN`: "… spans every venture" | The tool needs someone without a venture limit | Ask an owner or admin, or use a venture-specific tool (`venture_kb_search`). |
| `MCP_INSUFFICIENT_SCOPE` | The role lacks the permission (for example a `viewer` running a workflow) | Use a user with the right role. |
| A tool is missing from the list | Its family is off (`expose_kb`, `expose_ops`, `allow_admin`) or `mcp.tools` doesn't name it | Check the `mcp:` block; the server logs `families=` and `tools=` at startup. |
| The stdio server disconnects at once | It refused to start: no `--user`, user not in `users.yaml`, MCP off, unknown `--venture`, a relative `--directory` | Read the last line of the server's log (stderr). It exits with code 2. |
| The client reports invalid JSON from the stdio server | Something other than RealizeOS wrote to stdout, usually a wrapper (a shell profile that echoes, `conda run`, a batch file) | Start Python directly as the command. RealizeOS itself writes only JSON-RPC to stdout and sends logs, `print()` output and child processes to stderr. |
| The stdio server can't find the config or users ("No users.yaml in …") | Without `--directory` it reads the folder RealizeOS is installed in, which isn't your RealizeOS folder (for example a `pip` install) | Pass `--directory /absolute/path/to/RealizeOS`. |
| Admin tools are missing over stdio | Over stdio they need `--allow-admin` on the command line | Add `--allow-admin` (owner only). An agent still can't call them (`MCP_AGENT_REFUSED`). |
| `{"status": "pending_approval"}` instead of a result | The agent asked for a write; a person decides | Approve it in the dashboard's approval queue, then follow it with `list_approvals`. |
| `MCP_AGENT_CANNOT_DECIDE` or `MCP_AGENT_REFUSED` | People decide approvals; some tools aren't for agents | A person does it in the dashboard or CLI. |
| `401` with `"error": "invalid_token"` | The agent token was revoked, expired, or its user was removed or lost its ventures | Create a new token (`python cli.py agent-token create …`). |
| `404` or a hanging connection | Transport and URL don't match | Streamable HTTP (`type: http`) uses `/mcp`; HTTP+SSE (`type: sse`) uses `/mcp/sse`. `mcp.streamable_http: false` turns `/mcp` off. |
