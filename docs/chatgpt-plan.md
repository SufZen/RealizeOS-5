# Using your ChatGPT plan as the LLM

RealizeOS can send text completions to OpenAI on your ChatGPT plan instead of an
API key, through OpenAI's token sharing for open-source and self-hosted apps.
Plan calls cost no API-key money and are not stopped by
`COST_LIMIT_PER_MONTH_USD`: the monthly cap guards billable providers only, so
when it is reached the plan (and a local Ollama) keep answering while paid
fallbacks stop. If your account has ChatGPT credit use enabled, plan calls may
draw credits; that is governed by the account's usage settings, not by RealizeOS.

**Preview.** OpenAI marks token sharing as a preview. Read the limits before you
depend on it: <https://developers.openai.com/siwc/token-sharing-open-source>.

- It is for the plan owner's own use. Do not give other people access to an
  instance that runs on your plan.
- OpenAI asks paid or remotely hosted apps to fill in an interest form:
  <https://openai.com/form/sign-in-with-chatgpt-interest/>.
- On Plus, the five-hour usage limit is shared with every other app on the same
  plan (Codex included). Heavy RealizeOS use can use up the window for those apps.
- Revoking access for one server is not available yet. If the credential file
  leaks, disconnect the app in ChatGPT settings.

## What this version does

| Works | Not yet |
|---|---|
| Text completions on every tier you route to it | Tool use (tool-using agents go to a provider with tools) |
| JSON replies (asked for in the instructions) | Images, PDFs, audio |
| Automatic pause and fallback when the plan's usage limit is reached | Telling the user in chat that the fallback answered |

## Setup on a server

The sign-in callback goes to `http://127.0.0.1:1455/auth/callback` on the
machine that runs the browser. On a server you sign in on your own computer and
copy the credential file over SSH. This is the flow OpenAI describes for VMs.

1. **On your computer**, in a private folder outside any git checkout, create
   the server's host ID once (it goes to the server with the sign-in):

   ```bash
   python scripts/chatgpt_signin.py host-id --data ~/rz-plan
   ```

2. **Sign in** for that host. The listener on 127.0.0.1 starts before the browser
   opens; approve plan use. The script refuses to write inside a git checkout.

   ```bash
   python scripts/chatgpt_signin.py login --host-id <the printed ID> --out ~/rz-plan/chatgpt_plan.json
   python scripts/chatgpt_signin.py models --creds ~/rz-plan/chatgpt_plan.json
   python scripts/chatgpt_signin.py check --creds ~/rz-plan/chatgpt_plan.json --model <a slug from the list>
   ```

3. **Copy both files to the server** into `DATA_PATH`, owned by the RealizeOS user
   with mode 600, then delete your local folder. The server does every refresh
   from now on, and each refresh replaces the refresh token, so a second copy
   would stop working anyway.

   ```bash
   scp ~/rz-plan/chatgpt_plan.json ~/rz-plan/chatgpt_plan_host_id server:/path/to/data/
   ssh server "chown <realize user> /path/to/data/chatgpt_plan* && chmod 600 /path/to/data/chatgpt_plan*"
   rm -r ~/rz-plan
   ```

   On Windows, `chmod` does not set an ACL: keep the folder under your own
   profile (for example `%TEMP%`) and delete it after the copy.

4. **Set the environment** and restart:

   ```bash
   CHATGPT_PLAN_MODEL=<slug>
   LLM_PRIMARY=chatgpt_plan
   LLM_FALLBACK=gemini            # the cheap fallback; list Claude here too if you want it
   LLM_MODEL_FAST=                # leave empty so the fast tier also uses the plan
   LLM_MODEL_DEEP=<model string>  # optional: pin heavy work to another model
   COST_LIMIT_PER_MONTH_USD=20    # caps what the fallback and pinned models spend
   CHATGPT_PLAN_PAUSE_SECONDS=1800
   ```

## How the fallback works

| Plan answer | What RealizeOS does |
|---|---|
| `subscription_sharing_usage_limit_exceeded` (429) | Pauses the plan for `CHATGPT_PLAN_PAUSE_SECONDS` in that process; the router uses `LLM_FALLBACK` |
| `subscription_sharing_usage_unavailable`, `..._user_unavailable` (503), network error | This call goes to the fallback; the next call tries the plan again |
| `subscription_sharing_invalid_user` (401) | One forced refresh and retry, then the fallback |
| A terminal refresh error (`refresh_token_reused`, `invalid_grant`, ...) | The file is marked `needs_reauth`; sign in again (step 2) |
| `subscription_sharing_user_not_eligible`, scope or route errors (403) | The plan is disabled until restart; see Settings for the reason |

OpenAI never switches billing on its own, and its docs ask apps not to do it
silently. Here you choose it in advance by listing a paid provider in
`LLM_FALLBACK`. To stop instead of paying, list only free or local providers.

**Set `LLM_FALLBACK` explicitly.** With `LLM_PRIMARY=chatgpt_plan` and no valid
`LLM_FALLBACK`, there is no fallback at all: a usage limit stops answers until
the pause ends, rather than switching to a paid model you did not name.

**Signing in again** (after `needs_reauth`): read the saved registration on the
server (not secret, no tokens) and pass it to `login`, so the same registration
and the same account are kept:

```bash
python -c "import json;d=json.load(open('/path/to/data/chatgpt_plan.json'));print(d['client_id'],d['subject'])"
python scripts/chatgpt_signin.py login --host-id <server host ID> --client-id <client_id> --subject <subject> --out ~/rz-plan/chatgpt_plan.json
```

## Security

- `chatgpt_plan.json` holds live tokens. It is written with owner-only
  permissions and never logged. Never commit it, paste it into chat or put it in
  a URL.
- Refreshes take a lock file (`chatgpt_plan.lock`) so the API and the bots,
  which share `DATA_PATH`, never refresh at the same time.
- At sign-in the ID token is verified against OpenAI's published keys (issuer,
  audience = the issued client ID, expiry, nonce). On a re-sign-in the account
  must be the same one.

## Known gaps

- The monthly cap is a soft cap: every call already admitted when the total
  crosses it still finishes and is charged. A failed ledger write is logged as
  an error and that charge is missing from the total.
- The refresh lock is a file lock on Linux; on Windows it only covers threads of
  one process. Run one RealizeOS process per `DATA_PATH` on Windows.
- Pre-existing, outside this change: direct vision calls (`realize_core/media`)
  bypass the router's limits, and a paid model LiteLLM cannot price is counted
  as $0. Check that your fallback model has a price (`litellm.cost_per_token`).
