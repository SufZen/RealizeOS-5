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

## Verifying the deployment

1. `docker compose up -d` (or `python cli.py serve`).
2. `curl -fsS http://<host>:<port>/api/health` — should return 200 with no auth.
3. `curl -fsS http://<host>:<port>/api/dashboard` — should return **401** (proves auth is on).
4. `curl -fsS http://<host>:<port>/.env` — should return **404** (proves the SPA catch-all blocks dotfiles).
5. Visit the dashboard in a browser — you should land on `/login`.
6. Log in with the user you configured — every nav item should load successfully.

## Common issues

- **`docker ps` shows a random host port like `0.0.0.0:32776→8080/tcp`**.
  `REALIZE_PORT` from `.env` isn't reaching compose. Either pass `--env-file .env`
  or set the variable in the shell before `docker compose up`.
- **CORS preflight 400s in the browser**. `CORS_ORIGINS` must include the
  exact protocol+host the browser sends, e.g. `https://app.example.com` (no trailing slash).
- **Login succeeds but every API call returns 401 right after**. Your reverse
  proxy is stripping cookies or downgrading `Secure`. Confirm with the
  `realize_session` cookie visible in DevTools → Application → Cookies.
