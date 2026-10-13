# Upgrade to RealizeOS 5.30

This guide is for servers on **5.24.0** (the previous published release) or **5.14.0**. Both upgrade straight to 5.30; there is nothing to install in between.

## Before you start

1. **Back up.** In the dashboard, **Settings → Storage & Backup → Export** (or `POST /api/storage/export`). Also keep a copy of `realize-os.yaml`, `users.yaml` and `.env`; the export leaves out secrets on purpose.
2. **Note your version.** `GET /api/status` (signed in) or `realize-os version` shows what's running.

## Upgrade

- **Docker:** set `REALIZE_VERSION=5.30.0` (or pull `latest`) and recreate the container: `docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d`.
- **pip:** `pip install -U "realize-os==5.30.0"`, then restart the service.

The database migrates itself at startup (migrations 012–014, plus 009–011 from 5.14). If a migration fails, `/api/health` reports `unavailable` and the log names the step; the server doesn't start half-migrated.

## What changes for you

### Database (automatic)

| Migration | What it adds |
|---|---|
| 012 `agent_tokens` | Venture-scoped tokens for outside agents (stored as hashes) |
| 013 `decision_writes` | Durable decision-log writes, retried after a failure |
| 014 `wedge_contact_followup` | Contact-queue columns for the self-serve pilot |

From 5.14 you also get 009 (MCP OAuth clients and tokens), 010 (paused skill runs) and 011 (pilot runs).

### Data folders

- **Pack verification state** is now operational data in `DATA_PATH/packs/verification.json`, not edits to pack files. The shipped `packs/` folder can stay read-only (it is in the production image). Levels you approved before 5.30 were written into the pack files; they still load.
- **Custom packs** can live in an optional writable folder, `REALIZE_PACKS_PATH`; a pack there wins over a shipped pack with the same id. In Docker, mount it as a volume.

### New settings (all optional)

| Setting | Default | What it does |
|---|---|---|
| `features.agent_tokens` | on | Venture-scoped agent tokens. Inert until an owner creates one; turning it off stops every token at once |
| `features.packs` | off | Profession and market packs: context, skills, agents, schemas and trust defaults (which only tighten) |
| `features.wedge` | off | The self-serve tender register pilot (host it as its own instance; see [self-serve-wedge.md](self-serve-wedge.md)) |
| `mcp.tools` / `MCP_TOOLS` | all | Serve only these MCP tools; a malformed value serves none |
| `MCP_RATE_LIMIT_PER_MINUTE` | `API_RATE_LIMIT_PER_MINUTE` | Per-caller limit on MCP tool calls |
| `REALIZE_PACKS_PATH` | unset | Writable folder for the firm's own packs |

From 5.14 you also get `API_RATE_LIMIT_PER_MINUTE` (HTTP requests per caller, default 120), `REALIZE_TRUSTED_PROXIES` (trust `X-Forwarded-For` only from these networks), `CLAUDE_SONNET_MODEL` / `CLAUDE_OPUS_MODEL` (defaults are the newest models), and `REALIZE_DB_PATH`. See [`.env.example`](../.env.example).

### Behaviour you'll notice

- **Venture skills load at startup.** Before 5.30 the server only loaded a venture's own skills after a skill was installed from the library, so after a restart chat matched only the built-in defaults. Skills are now found through each venture's configured `directory`, so a venture whose folder name differs from its key finds them too.
- **Approvals.** Expired items have their own state and can't be decided. Deciding something that expired or that someone else already decided returns `409` with the item's current state; it used to be `404`. An approved action shows whether it succeeded, failed or has an unknown outcome. Only an owner with access to every venture can approve or reject a pack verification.
- **Outside agents are governed.** An agent token or a local stdio session (`realize-os mcp stdio`) reads within its ventures. Its workflow and skill runs wait for a person's approval, and it can never approve, reject or change settings. See [connect-your-agent.md](connect-your-agent.md).
- **Sheets.** Rows are appended `RAW` by default, and any text that could start a formula is stored as text. Skills that write amounts send them as numbers.
- **Exports** no longer include dashboard sessions, and a new `realize-os storage restore` unpacks an export into an empty folder.
- **Release tags.** A manual release must be dispatched on its tag: `gh workflow run release.yml --ref vX.Y.Z -f tag=vX.Y.Z`.

## After the upgrade

1. `GET /api/health` shows `ok`, and `GET /api/status` shows version 5.30.0.
2. Open **Approvals**: anything that expired while the server was down now shows as expired, not held.
3. If you use packs: `realize-os packs inventory --compare <inventory from your export>` confirms you resolve the same packs and levels.
4. If outside agents connect with the shared API key, move each one to its own token: `realize-os agent-token create --name … --user … --venture …`.

## Rolling back

Restore the 5.24.0 (or 5.14.0) image or package and the backup you took. The migrations only add tables and columns, so the older version ignores them. Pack verification state recorded in 5.30 lives only in `DATA_PATH/packs/verification.json`, which older versions don't read.
