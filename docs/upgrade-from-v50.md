# Upgrade from RealizeOS 5.0.x to 5.1.0

This guide covers what changed in 5.1.0 and how to migrate.

## What's New

### Built-in MCP Server

RealizeOS 5.1.0 ships a **built-in MCP server** that exposes your instance to any MCP-speaking agent (Claude Desktop, Cursor, n8n, cloud routines). This is the headline feature — RealizeOS stops being "API + dashboard" and becomes an integration hub.

- **24 tools** across 4 families: Chat & Status, KB Read, Ops, Admin
- **HTTP+SSE transport** at `/mcp/sse` + `/mcp/messages/{session}`
- **Same auth** — Bearer JWT or API key, reuses existing roles and audit logs
- **Off by default** — enable with `MCP_ENABLED=true` or `mcp.enabled: true` in config

See [docs/mcp-server.md](mcp-server.md) for full details.

### First-Class Operator CLI

The Python CLI has been rewritten from `argparse` to **Typer** with 19 command groups:

- `realize-os chat / ask / repl` — talk to your instance from the terminal
- `realize-os kb search / get / reindex` — knowledge base operations
- `realize-os workflow / skill / evolution` — workflow and self-improvement management
- `realize-os mcp serve / status / token` — MCP server management
- `realize-os config profile / show / set / unset` — multi-instance profiles and config management

See [docs/cli-reference.md](cli-reference.md) for the full command tree.

### CI Hardening

- Docker Compose validation no longer fails when `.env` is missing (env-file fix)
- Gitleaks allowlist for known false positives (now blocking on real leaks)
- Safety dependency scanning promoted to blocking

## What Changed

### Entry Point

The canonical CLI entry point is now `realize-os` (installed via `pip install realize-os`).

**`python cli.py` still works** — it's a lightweight shim that delegates to the same Typer app. No existing scripts or workflows need to change.

### New Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `typer` | ≥0.12 | CLI framework |
| `rich` | ≥13.0 | Pretty terminal output |
| `tomli_w` | ≥1.0 | TOML writing for profiles |
| `prompt-toolkit` | ≥3.0 | Interactive REPL |
| `httpx` | ≥0.27 | HTTP client for CLI→API calls |

All are pure-Python and install automatically with `pip install realize-os`.

### New Config Section

If you enable the MCP server, add to your `realize-os.yaml`:

```yaml
mcp:
  enabled: true
  allow_admin: false      # Enable admin tools (venture CRUD, settings)
  expose_kb: true          # Enable KB search tools
  expose_ops: true         # Enable workflow/skill/evolution tools
```

Or use environment variables:

```bash
MCP_ENABLED=true
MCP_ALLOW_ADMIN=false
```

### New Files

| Path | Purpose |
|------|---------|
| `realize_core/mcp_server/` | Built-in MCP server package |
| `realize_core/cli_app/` | Typer-based operator CLI |
| `realize_api/routes/mcp.py` | MCP SSE + messages endpoints |
| `~/.realize-os/config.toml` | CLI profile configuration (user-local) |

## Migration Steps

### 1. Update dependencies

```bash
pip install -e .
# or
pip install -r requirements.txt
```

### 2. (Optional) Enable MCP server

```bash
realize-os config set mcp.enabled true
realize-os mcp serve
```

### 3. (Optional) Set up CLI profiles

```bash
realize-os config profile add prod --endpoint https://my-vps:8080
realize-os --profile prod status
```

### 4. Update any scripts

Replace `python cli.py` with `realize-os` if desired (both work):

```diff
- python cli.py serve --port 8080
+ realize-os serve --port 8080
```

## What's Deprecated

Nothing is removed or broken. `python cli.py <verb>` continues to work identically. The only deprecation is cosmetic: documentation now shows `realize-os` as the primary entry point.

## What's NOT in 5.1.0

- **stdio MCP transport** — deferred to 5.2.0
- **Streamable HTTP MCP** — spec still evolving
- **Coverage threshold enforcement** — planned for follow-up
