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

<!-- TODO(agent-tokens): confirm command/flags after the agent-token PR merges -->

For an outside agent that connects over the network with a header, use an agent token limited to one venture. Create it on the RealizeOS server:

```bash
python cli.py agent-token create --user dana@example.com --venture tower-b --name "Dana's Claude"
```

The agent sends it as `Authorization: Bearer <token>`. The token acts as that user, limited to that venture, and it can be revoked on its own without touching anyone else's access.

Never give an agent the shared `REALIZE_API_KEY`. The API key is an owner with access to every venture, it can't be limited, and revoking it breaks every other integration that uses it.

Local stdio connections don't use a token: they name the user with `--user` (see [Claude Code](#claude-code)).

## What the agent can and can't do

- **Reads are limited to the person's ventures.** A user or token limited to some ventures gets only those. Tools that span every venture (evolution, cross-venture search, admin) return `MCP_FORBIDDEN`. Venture lists are filtered.
- **The role decides the tools.** A `viewer` can only read. A `user` can also chat and run workflows. An `operator` can also decide approvals. Admin tools are off unless `mcp.allow_admin` is on, and then only for an owner.
- **Writes wait for a person.** <!-- TODO(agent-tokens): confirm command/flags after the agent-token PR merges --> Changes an outside agent asks for (running a workflow that writes, logging a decision, anything touching money, contracts or people) are held as approval requests. A person approves or rejects them in the dashboard. The agent can't approve its own requests.
- **Everything is on the record.** Every tool call is written to the audit log under the person's identity (channel `mcp`), including refusals.

## Claude Code

Verified on 2026-10-13 with Claude Code 2.1.143 (Windows 11): stdio, Streamable HTTP and HTTP+SSE. `claude mcp get` showed each server as connected, and tool calls through `claude -p` returned the scoped results described above.

### Local (stdio)

```bash
claude mcp add realize-os -- python /path/to/RealizeOS/cli.py mcp stdio --directory /path/to/RealizeOS --user dana@example.com
```

- `--user` is required and must be in `users.yaml`. There is no default user, and it is never read from environment variables.
- `--venture tower-b` narrows the session further (repeatable). It must be one of the user's ventures.
- `--directory` is the RealizeOS folder, where `realize-os.yaml`, `users.yaml` and `.env` live. Pass it: agents don't start the command in that folder.
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
| The stdio server disconnects at once | It refused to start: no `--user`, user not in `users.yaml`, MCP off, unknown `--venture` | Read the last line of the server's log (stderr). It exits with code 2. |
| The client reports invalid JSON from the stdio server | Something other than RealizeOS wrote to stdout, usually a wrapper (a shell profile that echoes, `conda run`, a batch file) | Start Python directly as the command. RealizeOS itself writes only JSON-RPC to stdout and sends logs, `print()` output and child processes to stderr. |
| The stdio server can't find the config or users | It started in another folder | Pass `--directory /path/to/RealizeOS`. |
| `404` or a hanging connection | Transport and URL don't match | Streamable HTTP (`type: http`) uses `/mcp`; HTTP+SSE (`type: sse`) uses `/mcp/sse`. `mcp.streamable_http: false` turns `/mcp` off. |
