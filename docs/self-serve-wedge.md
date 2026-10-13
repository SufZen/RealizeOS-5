# Self-serve tender register (pilot)

A free workflow that anyone can run from their own AI agent, in any market, with no consultant involved. It is the first value RealizeOS gives a new user (ADR 0005, Play W). Everything after it (the firm's own brain, governance, verified market packs) is delivered by the practice or a local partner.

## How it works

1. The user connects their agent (Claude, ChatGPT or another MCP client) to a RealizeOS server with the pilot on.
2. The agent calls `tender_register_method` with the project's market, if known. It gets:
   - the steps
   - the register format
   - the market's local terms and sourced rule cards, with their verification level
3. The agent reads the tender PDF itself and builds the register.
4. The agent calls `tender_register_submit`. RealizeOS then:
   - checks the register: duplicates, categories, items without a page
   - returns it as a finished document in English, Hebrew or Portuguese, stating its verification level and limits
   - offers a hand-off: book an Audit Sprint, or a local partner where one exists
5. If the user wants to talk, the agent calls `request_audit_call` with a contact the user chose to share.

Without a market pack, the document says plainly that local rules are unverified general knowledge (level 0).

## Turn it on

```yaml
features:
  wedge: true
wedge:
  booking_url: https://example.com/audit-sprint
  partners:
    pt: {name: "Partner name", url: "https://partner.example"}
```

## Limits

- Up to 300 register items per run (about a 50-page tender), and 10 runs per user per day.
- No document text is stored, only counts, market and verification level.
- Runs are deleted after 30 days unless the user asked to be contacted (daily, see [Retention](#retention)).

## Host the pilot

Run the pilot as its own instance, with its own data, `users.yaml` and domain. Never turn it on in the practice's server that holds client brains: pilot users are outsiders.

The hosted profile serves only the pilot tools. No model runs on the RealizeOS side (the user's agent does the reading), so it needs no LLM keys.

`realize-os.yaml`:

```yaml
features:
  wedge: true
mcp:
  enabled: true
  expose_kb: false
  expose_ops: false
  allow_admin: false
  public_url: https://pilot.example.com
  tools: [tender_register_method, tender_register_submit, request_audit_call, realize_health]
  oauth:
    enabled: true
    redirect_hosts: [claude.ai, claude.com, chatgpt.com]   # chatgpt.com for ChatGPT; see connect-your-agent.md
wedge:
  booking_url: https://example.com/audit-sprint
  partners:
    pt: {name: "Partner name", url: "https://partner.example"}
```

`.env`: production posture (`REALIZE_ENV=production`, `REALIZE_API_KEY`, `REALIZE_JWT_ENABLED=true` and a strong `REALIZE_JWT_SECRET`), plus `MCP_PUBLIC_URL` if you prefer it to the YAML. Behind a reverse proxy, set `REALIZE_TRUSTED_PROXIES` so rate limits see real client addresses, and start uvicorn with `--proxy-headers` (see [mcp-server.md](mcp-server.md#connect-claudeai-custom-connector-oauth)).

With `docker-compose.prod.yml`, use a separate project and data volume, and bind-mount a writable `users.yaml` (the container's root is read-only):

```yaml
    volumes:
      - ./users.yaml:/app/users.yaml
```

```bash
docker compose -p realizeos-pilot -f docker-compose.prod.yml up -d
```

### Invite users

Sign-in is by invitation for now; there is no public sign-up. `invite` refuses to run unless this instance is a pilot host (`features.wedge` on and `mcp.tools` limited to the four tools above).

```bash
realize-os wedge invite dana@example.com
```

This adds a `viewer` limited to an empty sandbox venture of their own (`pilot-<hash>`) and prints a password once. Send them the password privately, with the connector URL (`https://pilot.example.com/mcp`) and the guide for their agent ([connect-your-agent.md](connect-your-agent.md)). Their agent signs in with OAuth and sees only the pilot tools. Inside Docker, run it with `docker compose -p realizeos-pilot exec api python cli.py wedge invite …`.

### Retention

While `features.wedge` is on, the server deletes runs older than 30 days (unless the user asked to be contacted) at startup and then daily. `realize-os wedge purge` does it on demand.

### Before going live

- [ ] Connector sign-in tested end to end from Claude and from ChatGPT against the public URL.
- [ ] `booking_url` and partners point at real pages.
- [ ] `realize-os wedge funnel` shows the test runs, and `purge` removes them.

## Measuring it

`realize-os wedge funnel` (or `realize_core.wedge.funnel(days=30)`) returns runs, users and call requests per market, from recorded runs only. The pilot passes if 30% of users who run it request a call, and at least one comes from outside Israel.

Connection guides for each agent: [connect-your-agent.md](connect-your-agent.md).
