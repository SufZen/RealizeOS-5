# Production Deployment Checklist

RealizeOS ships with a developer-friendly default configuration. Switching to
production mode enables strict validation of auth and CORS settings. This
checklist walks through every variable the validator requires, why it exists,
and how to generate values.

## Required environment variables

Set these in `.env` before starting the API with `REALIZE_ENV=production`:

| Variable | Purpose | How to generate |
|---|---|---|
| `REALIZE_ENV=production` | Activates strict validation | literal value |
| `REALIZE_API_KEY` | Auth for programmatic callers (CLI, bot) | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `REALIZE_JWT_ENABLED=true` | Enables JWT verification for Bearer tokens | literal value |
| `REALIZE_JWT_SECRET` | Signing key for JWTs (32+ chars) | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CORS_ORIGINS` | Allowed browser origins | your domain(s), comma-separated |

If any are missing, the API refuses to start and reports **every** missing
variable in one error — you don't have to iterate.

## Dashboard users

The browser dashboard uses cookie-session auth (v5.2.0+). Configure at least
one user before you can log in.

### Option A — `users.yaml` (recommended)

```bash
cp users.yaml.example users.yaml
python scripts/hash_password.py     # prompts for the password, prints a bcrypt hash
# paste the hash under password_hash in users.yaml
```

`users.yaml` is gitignored — never commit real hashes.

### Option B — single owner via env

```bash
export REALIZE_ADMIN_USER=owner@example.com
export REALIZE_ADMIN_PASSWORD_HASH="$(python scripts/hash_password.py 'your-password')"
```

(`users.yaml` overrides env if both are present.)

### Roles and venture scope

Every write is checked against the user's role (see `users.yaml.example`):
`viewer` is read-only, `user` can chat and edit venture files, `operator` can
also approve held actions, `admin` and `owner` can change settings. A request to
raise a shared pack's verification (`pack_verify`) changes what every venture
sees, so only an `owner` without a `ventures` limit can approve or reject it.

Add `ventures: [key, ...]` to a user to limit them to those ventures. They see
only those ventures in the dashboard (the venture switcher is locked when there
is one), the API and MCP. Another venture's data returns 403 or "not found",
wherever the venture is named (path, query or anywhere in a JSON body). The
system-wide areas (settings, security, setup, integrations, storage, tools,
shared files, evolution, pipelines, LLM usage and `/api/memory/stats`) are
closed to them, reads included, and their pages are hidden; changes that affect
every venture (agent definitions, routing, reloads) are refused. Lists and
searches that don't name a venture (memory search, approvals, missions, the
Dream Inbox and its counts) cover only their ventures. Knowledge-base files are checked against the
venture's own directory, not just the knowledge base.

Leave `ventures` out for access to every venture; a `ventures` entry that is
empty or malformed skips that user. Every dashboard request re-checks the user
in `users.yaml`: removing a user ends their sessions, and role changes apply
immediately. API-key callers and JWTs minted with the API key are service
identities, unrestricted unless the token carries `venture:<key>` scopes. API-key callers and users without `ventures` see everything. A JWT
can be narrowed further with `venture:<key>` scopes.

## Writable locations

The production compose file runs the container with a read-only root
filesystem. RealizeOS writes only to:

| Location | What |
|---|---|
| `DATA_PATH` (`/app/data`, named volume) | Databases, Synapse, audit log, `packs/verification.json` (approved pack levels) |
| `/app/systems`, `/app/shared` | The ventures' knowledge (bind mount and named volume) |
| `REALIZE_PACKS_PATH` (optional mount) | Your own or modified profession and market packs |
| `/tmp` (tmpfs) | Temporary files, such as an export being built |

The shipped packs in `/app/packs` stay read-only: a pack verification approval
is recorded in `DATA_PATH`, never in the pack files. See
[self-hosting-guide.md](self-hosting-guide.md#volume-mounts).

## Verifying the deployment

1. `docker compose up -d` (or `python cli.py serve`).
2. `curl -fsS http://<host>:<port>/api/health` — should return 200 with no auth.
3. `curl -fsS http://<host>:<port>/api/dashboard` — should return **401** (proves auth is on).
4. `curl -fsS http://<host>:<port>/.env` — should return **404** (proves the SPA catch-all blocks dotfiles).
5. Visit the dashboard in a browser — you should land on `/login`.
6. Log in with the user you configured — every nav item should load successfully.

## Production smoke test (read-only container)

`scripts/prod_smoke.py` runs an image the way `docker-compose.prod.yml` does and checks it end to end. CI runs it on every push and pull request (job **Production smoke (read-only container)** in `.github/workflows/ci.yml`); run it yourself before a release or after changing the Dockerfile:

```bash
docker build -t realizeos-5:smoke .
python scripts/prod_smoke.py --image realizeos-5:smoke     # add --keep to leave everything for debugging
```

It needs Docker with a Linux engine and Python 3.11+ (standard library only). It starts the container with a read-only root filesystem, a `/tmp` tmpfs, `no-new-privileges`, named volumes for `/app/data` and `/app/shared`, `realize-os.yaml` and `.credentials` mounted read-only, `systems/` and `packs-custom/` (as `REALIZE_PACKS_PATH`) mounted writable, and production settings (`REALIZE_ENV=production`, an API key, JWT on with a strong secret, `CORS_ORIGINS`, a dashboard owner). The secrets are generated for each run and never written to disk. Then it checks:

1. `/api/health` is `ok`; a request without credentials gets 401; the API key, a JWT minted with it and a dashboard sign-in work.
2. Creating a venture is refused with 503 (the config is read-only) and leaves nothing behind; a venture file is written through the API into the `systems/` mount.
3. A market pack review runs in the container the documented way: the shipped pack is copied into `REALIZE_PACKS_PATH`, `packs review-sheet` and `packs review-submit --whole-pack` queue a `pack_verify` request, the owner approves it over the API, the approval's `execution_status` is `succeeded`, and `packs/verification.json` is in the data volume at level 2.
4. `POST /api/storage/export` works with only `/tmp` writable, and the ZIP has the venture file, the verification state and the custom pack, and none of the API key, the JWT secret, the password hash or the session cookie.
5. After `docker restart`, and again after the container is removed and recreated from the image on the same volumes: the venture file, the sign-in session, the approval and its outcome, the decision-log entry, the verification state and the pack inventory (`packs inventory --compare`) are all unchanged.
6. The container log shows no write refused by the read-only filesystem.

It exits 1 at the first failed check, printing the container log, and removes the container, volumes and temp folder either way (unless `--keep`).

## Backups and moving to another server

The storage export is the complete backup; `python cli.py storage restore <zip> --directory <new folder>` restores it on a new server. What is and isn't in the ZIP, and the steps for Docker, are in [self-hosting-guide.md](self-hosting-guide.md#backups).

## Common issues

- **`docker ps` shows a random host port like `0.0.0.0:32776→8080/tcp`**.
  `REALIZE_PORT` from `.env` isn't reaching compose. Either pass `--env-file .env`
  or set the variable in the shell before `docker compose up`.
- **CORS preflight 400s in the browser**. `CORS_ORIGINS` must include the
  exact protocol+host the browser sends, e.g. `https://app.example.com` (no trailing slash).
- **Login succeeds but every API call returns 401 right after**. Your reverse
  proxy is stripping cookies or downgrading `Secure`. Confirm with the
  `realize_session` cookie visible in DevTools → Application → Cookies.
