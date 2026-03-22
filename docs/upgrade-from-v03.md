# Upgrade from V03 to V5

This guide walks you through upgrading an existing RealizeOS V03 installation to V5.

## What's Changed

### Breaking Changes

| Area | V03 | V5 | Action Required |
|------|-----|-----|-----------------|
| **Agent definitions** | V1 YAML format | V2 YAML with protocols | Migrate or keep V1 (auto-detected) |
| **Tool count** | 13 Google Workspace | 24 Google Workspace + Sheets | Add `spreadsheets` OAuth scope |
| **Plugins** | `plugins/` with `plugin.yaml` | `extensions/` with `extension.yaml` | Rename directory + manifests |
| **Config file** | `realize-os.yaml` | `realize-os.yaml` (expanded) | Add new feature flags |
| **Docker volumes** | Unnamed volumes | Named volumes | Re-create containers |

### New Features (No Action Required)

These work automatically once you upgrade:

- Multi-LLM routing (auto-discovers providers from API keys)
- Visual dashboard (served at the same port)
- Agent pipelines and handoffs
- Extension system with auto-discovery
- Cron scheduler
- Event hooks
- Activity logging
- Approval gates

## Step-by-Step Upgrade

### 1. Back Up Everything

```bash
# Back up your current installation
cp -r realize-os realize-os-backup
cp .env .env.backup
```

### 2. Update the Code

```bash
# If using git
git fetch origin
git checkout main
git pull

# If using a zip download
# Download the V5 package and replace the realize_core/ directory
```

### 3. Install New Dependencies

```bash
pip install -r requirements.txt
```

V5 adds `litellm` for unified multi-LLM routing. All other new dependencies are optional.

### 4. Update Configuration

Add the new V5 feature flags to your `realize-os.yaml`:

```yaml
features:
  # Existing flags (keep your current values)
  review_pipeline: true
  auto_memory: true
  proactive_mode: true
  cross_system: false

  # New V5 flags (add these)
  activity_log: true           # Activity event logging (recommended)
  agent_lifecycle: true        # Agent status tracking
  heartbeats: false            # Scheduled agent runs (enable when ready)
  approval_gates: false        # Human-in-the-loop approvals
```

### 5. Migrate Agent Definitions (Optional)

V5 supports **both** V1 and V2 agent definitions — the loader auto-detects the format. You don't need to migrate immediately.

#### V1 Format (still works)

```yaml
# A-agents/writer.md or A-agents/writer.yaml
# Simple key-value definitions
name: writer
role: Content creation specialist
scope: Blog posts, social media, email campaigns
```

#### V2 Format (new capabilities)

```yaml
# A-agents/writer.yaml
version: "2"
name: writer
scope: Content creation specialist
communication_style: friendly, professional
inputs:
  - content_brief
  - venture_voice
outputs:
  - draft_content
  - revision_notes
guardrails:
  require_approval_for:
    - publish
    - send_email
tools:
  - gmail_send
  - drive_create_doc
critical_rules:
  - Always match the venture voice
  - Include a call-to-action
success_metrics:
  - content_quality_score > 80
```

### 6. Migrate Plugins to Extensions (Optional)

If you have custom plugins in `plugins/`, they'll continue to work — the extension loader scans `plugins/` as a fallback. To fully migrate:

1. **Rename the directory**:
   ```bash
   mv plugins/my-plugin extensions/my-plugin
   ```

2. **Rename the manifest** (if needed):
   ```bash
   mv extensions/my-plugin/plugin.yaml extensions/my-plugin/extension.yaml
   ```

3. **Update the manifest format** (add `type` field if missing):
   ```yaml
   # extension.yaml
   name: my-plugin
   version: "1.0.0"
   type: tool              # tool | channel | integration | hook
   entry_point: "__init__"
   description: "What this plugin does"
   ```

### 7. Update Google OAuth Scopes (If Using Google Tools)

V5 adds Google Sheets tools, which require a new OAuth scope. You need to re-authorize:

1. Delete your existing tokens:
   ```bash
   rm .credentials/tokens.json
   ```

2. Re-run the OAuth flow:
   ```bash
   python cli.py setup-google
   ```

3. Authorize the new `spreadsheets` scope in the consent screen.

### 8. Update Docker (If Using Docker)

V5 uses named volumes for better data management:

```bash
# Stop the old containers
docker compose down

# Rebuild with the new config
docker compose build --no-cache

# Start with new named volumes
docker compose up -d
```

> **Important:** If you had data in unnamed volumes, copy it to the new named volumes:
> ```bash
> # Find old volume
> docker volume ls | grep realize
>
> # Copy data
> docker run --rm \
>   -v old_volume_name:/from \
>   -v realizeos-data:/to \
>   alpine sh -c "cp -a /from/. /to/"
> ```

### 9. Verify the Upgrade

```bash
# Check health
curl http://localhost:8080/health

# Check status (should show V5 features)
curl http://localhost:8080/status

# Run tests
python -m pytest tests/ -v --tb=short

# Check tool count (should show 24 Google Workspace tools)
python -c "from realize_core.tools.google_workspace import GOOGLE_TOOL_SCHEMAS; print(f'{len(GOOGLE_TOOL_SCHEMAS)} GWS tools')"
python -c "from realize_core.tools.google_sheets import SHEETS_TOOL_SCHEMAS; print(f'{len(SHEETS_TOOL_SCHEMAS)} Sheets tools')"
```

## Rollback

If you need to revert:

```bash
# Restore from backup
cp -r realize-os-backup/* realize-os/
cp .env.backup .env

# Or with git
git checkout v03-tag
pip install -r requirements.txt
```

## Migration Checklist

- [ ] Back up current installation
- [ ] Update code (git pull or zip replace)
- [ ] Install new dependencies (`pip install -r requirements.txt`)
- [ ] Add new feature flags to `realize-os.yaml`
- [ ] (Optional) Migrate V1 → V2 agent definitions
- [ ] (Optional) Migrate `plugins/` → `extensions/`
- [ ] (If using Google) Re-authorize with new Sheets scope
- [ ] (If using Docker) Rebuild with named volumes
- [ ] Verify: health check, status, tests
- [ ] Review new dashboard at `http://localhost:8080`

## FAQ

### Do I need to migrate my agents to V2 format?

No. V5 auto-detects V1 agent definitions and loads them unchanged. V2 is optional and adds new capabilities (pipelines, guardrails, handoffs).

### Will my existing skills still work?

Yes. The skill system is backward compatible. V5 adds a `BaseSkill` protocol for new skill types but doesn't change the existing YAML skill format.

### Will my existing plugins still work?

Yes. The extension loader scans `plugins/` as a fallback directory and supports `plugin.yaml` manifests. Migrating to `extensions/` with `extension.yaml` is optional.

### Do I need all the new API keys?

No. V5 auto-discovers available providers from your configured API keys. If you only have `ANTHROPIC_API_KEY`, it will use Claude for all tasks. Adding `GOOGLE_AI_API_KEY` enables the multi-LLM routing.

### How do I disable V5 features I don't want?

Set feature flags to `false` in `realize-os.yaml`. All new V5 features default to `false` when the flag is not present, so your existing config will run in "V03 compat mode" until you opt in.
