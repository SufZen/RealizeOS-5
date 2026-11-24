# Using your ChatGPT plan as the LLM

RealizeOS can send text completions to OpenAI on your ChatGPT plan instead of an
API key, through OpenAI's token sharing for open-source and self-hosted apps.
Plan calls cost $0 against `COST_LIMIT_PER_MONTH_USD`; only the fallback
providers spend API money.

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

1. **On the server**, print the server's host ID (created once, kept in `DATA_PATH`):

   ```bash
   python scripts/chatgpt_signin.py host-id
   ```

2. **On your computer** (a RealizeOS checkout with its dependencies), sign in for
   that host. A browser opens; approve plan use.

   ```bash
   python scripts/chatgpt_signin.py login --host-id <the server's host ID> --out chatgpt_plan.json
   python scripts/chatgpt_signin.py models --creds chatgpt_plan.json
   python scripts/chatgpt_signin.py check --creds chatgpt_plan.json --model <a slug from the list>
   ```

3. **Copy the file to the server** into `DATA_PATH` as `chatgpt_plan.json`, readable
   by the RealizeOS user only, then delete your local copy. The server does every
   refresh from now on, and each refresh replaces the refresh token, so a second
   copy would stop working anyway.

   ```bash
   scp chatgpt_plan.json server:/path/to/data/chatgpt_plan.json
   ssh server chmod 600 /path/to/data/chatgpt_plan.json
   ```

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

## Security

- `chatgpt_plan.json` holds live tokens. It is written with owner-only
  permissions and never logged. Never commit it, paste it into chat or put it in
  a URL.
- Refreshes take a lock file (`chatgpt_plan.lock`) so the API and the bots,
  which share `DATA_PATH`, never refresh at the same time.
- ID-token claims (email, subject) are read for display only; the signature is
  not checked in this version. Plan access is decided by OpenAI on each request.
