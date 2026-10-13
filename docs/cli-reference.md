# CLI Reference

> Full command tree for the RealizeOS operator CLI (`realize-os` / `python cli.py`).

## Global Options

| Option | Description |
|--------|-------------|
| `--profile NAME` | Named profile from `~/.realize-os/config.toml`. Overrides default for one call. |
| `--format FORMAT` | Output format: `table` (default), `json`, `yaml`. |
| `--install-completion` | Install shell completion (bash/zsh/fish/PowerShell). |
| `--help` | Show help and exit. |

## Command Tree

```
realize-os
├── init [--template NAME] [--setup PATH]       Deploy & initialize
├── serve [--port PORT] [--reload]              Start API + dashboard
├── bot                                          Start Telegram bot
├── status                                       Show system status
├── audit [--quick]                              Run audit playbook
├── index                                        Rebuild KB search index
├── setup                                        Interactive setup wizard
├── doctor                                       Diagnose installation issues
├── version                                      Print version
│
├── chat MESSAGE [--system KEY] [--agent KEY]    One-shot chat
├── ask QUERY                                    Smart-routed question
├── repl [--system KEY] [--agent KEY]            Interactive REPL
│
├── venture
│   ├── list                                     List ventures
│   ├── create KEY [--template NAME]             Create a venture
│   └── delete KEY                               Delete a venture
│
├── kb
│   ├── search QUERY [--venture KEY] [--limit N] Search knowledge base
│   ├── get DOC_ID                               Retrieve a document
│   └── reindex [--venture KEY]                  Rebuild search index
│
├── workflow
│   ├── list                                     List workflows
│   └── run NAME [--input JSON]                  Run a workflow
│
├── skill
│   ├── list                                     List skills
│   └── trigger NAME                             Trigger a skill
│
├── evolution
│   ├── run                                      Run evolution engine
│   ├── suggestions [--status STATE]             List suggestions
│   ├── approve ID                               Approve a suggestion
│   └── dismiss ID                               Dismiss a suggestion
│
├── mcp
│   ├── serve [--port PORT] [--allow-admin]      Start API + MCP server
│   ├── stdio --user EMAIL [--venture KEY]       Serve MCP over stdin/stdout (local agents)
│   │         [--directory DIR] [--allow-admin]
│   ├── status                                   Show MCP health
│   └── token [--user USER] [--role ROLE]        Issue bearer token
│
├── wedge                                        Self-serve tender register pilot
│   ├── invite EMAIL                             Add an invite-only pilot user
│   ├── funnel [--days N] [--format json]        Runs, users and calls per market
│   └── purge [--days N]                         Delete expired runs now
│
├── config
│   ├── show [KEY]                               Show config value(s)
│   ├── set KEY VALUE                            Set a config value
│   ├── unset KEY                                Remove a config key
│   └── profile
│       ├── list                                 List profiles
│       ├── add NAME [--endpoint URL]            Add/update a profile
│       ├── set-default NAME                     Set default profile
│       └── show [NAME]                          Show profile details
│
└── devmode
    ├── setup                                    Generate AI context files
    ├── check                                    Run system health check
    ├── scaffold --name NAME                     Scaffold an extension
    ├── snapshot                                 Create git safety snapshot
    ├── rollback --tag TAG                       Rollback to snapshot
    ├── diff [--tag TAG]                         Show diff vs snapshot
    └── status                                   Show devmode status
```

## Deployment Commands

### `realize-os init`

Initialize a new RealizeOS system.

```bash
realize-os init --template consulting    # From a business template
realize-os init --setup setup.yaml       # From a setup file
```

### `realize-os serve`

Start the API server and dashboard.

```bash
realize-os serve                         # Default: port 8080
realize-os serve --port 9090 --reload    # Custom port + hot-reload
```

### `realize-os bot`

Start the Telegram bot interface.

```bash
realize-os bot
```

## Operator Commands

### `realize-os chat`

Send a one-shot message to a running RealizeOS instance.

```bash
realize-os chat "What's my pipeline status?"
realize-os chat "Draft an email to investors" --system arena --agent writer
realize-os --format json chat "status check"   # JSON output
```

### `realize-os ask`

Shortcut for `chat` with smart routing — the system picks the best agent.

```bash
realize-os ask "summarize yesterday's emails"
```

### `realize-os repl`

Launch an interactive chat session with prompt-toolkit.

```bash
realize-os repl
realize-os repl --system realization-il --agent strategist
```

**REPL slash commands:**

| Command | Description |
|---------|-------------|
| `/system KEY` | Switch system |
| `/agent KEY` | Switch agent |
| `/session ID` | Resume a session |
| `/clear` | Clear screen |
| `/help` | Show help |
| `/exit` | Exit REPL |

### `realize-os kb search`

Search the knowledge base.

```bash
realize-os kb search "investment thesis"
realize-os kb search "Q3 revenue" --venture personal-investments --limit 5
realize-os --format json kb search "market analysis"
```

### `realize-os mcp token`

Issue a bearer token for MCP client configuration.

```bash
realize-os mcp token                     # Default: user=owner, role=owner
realize-os mcp token --user admin --role admin
```

Use the output token in Claude Desktop's `mcpServers` config or any MCP client.

### `realize-os mcp stdio`

Serve the MCP server over stdin/stdout for an agent on the same computer (Claude Code, Claude Desktop, Cursor). No port is opened. The agent starts this command itself; see [connect-your-agent.md](connect-your-agent.md).

```bash
python cli.py mcp stdio --directory /path/to/RealizeOS --user dana@example.com
python cli.py mcp stdio --directory /path/to/RealizeOS --user owner@example.com --venture tower-b
```

- `--user` is required and must be a `users.yaml` entry: its role and ventures apply. There is no default user and it is never read from the environment.
- `--venture` (repeatable) narrows the session to some of that user's ventures.
- `--directory` (or `--root`) is the absolute path of the RealizeOS folder (`realize-os.yaml`, `users.yaml`, `.env`, data, KB). Without it, the folder RealizeOS is installed in is used, never the working directory.
- `--allow-admin` serves admin tools (owner only). Over stdio, `mcp.allow_admin` doesn't turn them on.
- MCP must be on (`MCP_ENABLED=true`). stdout carries only JSON-RPC; logs go to stderr. It exits with code 2 and a reason on stderr when it refuses to start.

### `realize-os wedge`

Host the [self-serve tender register](self-serve-wedge.md) pilot. Run these on the server, in the directory that holds `users.yaml` and the database.

```bash
realize-os wedge invite dana@example.com   # viewer limited to an empty sandbox venture; prints the password once
realize-os wedge funnel --days 30          # runs, users and call requests per market, from recorded runs
realize-os wedge purge                     # delete runs older than 30 days unless the user opted in
```

`invite` only works on a pilot host: `features.wedge` on and `mcp.tools` limited to the pilot tools, so it can't open the practice's own server to outsiders. It rewrites `users.yaml` (comments are not kept; the previous file is saved as `users.yaml.bak`). If the file is read-only, it prints the entry to add by hand. It refuses to create `users.yaml`: once that file exists it replaces a single-owner `REALIZE_ADMIN_USER` login, so create it with your own owner account first.

## Multi-Instance Profiles

Profiles let you manage multiple RealizeOS instances from one CLI:

```bash
# Add profiles
realize-os config profile add local --endpoint http://localhost:8080
realize-os config profile add prod --endpoint https://my-vps:8080

# Switch
realize-os --profile prod status
realize-os --profile prod chat "check health"

# Set default
realize-os config profile set-default prod
```

Profile configuration lives in `~/.realize-os/config.toml`.

## Output Formats

Every list/get command supports `--format`:

```bash
realize-os venture list                              # Pretty table
realize-os --format json venture list                # JSON (pipe to jq)
realize-os --format yaml evolution suggestions       # YAML
```

## Backwards Compatibility

All existing `python cli.py <verb>` forms continue to work:

```bash
python cli.py serve           # Still works
python cli.py init --template consulting  # Still works
python cli.py status          # Still works
```

The `python cli.py` entrypoint is a lightweight shim that delegates to the same Typer app as `realize-os`.
