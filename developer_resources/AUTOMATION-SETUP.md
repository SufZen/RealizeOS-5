# RealizeOS — Post-Purchase Automation Setup

All automations run on self-hosted **n8n** at `https://<YOUR_N8N_DOMAIN>`.
Importable workflow JSON files are in your n8n-automations repository.

---

## 1. Google Drive Setup

### Upload files for direct download

1. Go to Google Drive
2. Upload the **Lite Edition** Obsidian vault ZIP
3. Upload the **Full Edition** package ZIP
4. For each file: right-click → **Share** → "Anyone with the link" (Viewer)
5. Copy each file's ID from its URL: `drive.google.com/file/d/FILE_ID_HERE/view`

### Update the download links

File IDs are already wired into both `docs/thank-you.html` and the `realizeos-welcome-flow.json` workflow in your n8n-automations repo:

```javascript
const driveLinks = {
  lite: 'https://drive.google.com/uc?export=download&id=<LITE_FILE_ID>',
  full: 'https://drive.google.com/uc?export=download&id=<FULL_FILE_ID>',
  setup: 'https://drive.google.com/uc?export=download&id=<SETUP_FILE_ID>'
};
```

---

## 2. Stripe Configuration

### Payment links (already configured via API)
- **Lite:** `https://buy.stripe.com/<LITE_LINK_ID>` → redirects to `https://<YOUR_DOMAIN>/thank-you.html?tier=lite`
- **Full:** `https://buy.stripe.com/<FULL_LINK_ID>` → redirects to `https://<YOUR_DOMAIN>/thank-you.html?tier=full`
- **Setup:** `https://buy.stripe.com/<SETUP_LINK_ID>` → redirects to `https://<YOUR_DOMAIN>/thank-you.html?tier=setup`

### Webhook (already configured via API)

- **Endpoint ID:** see Stripe Dashboard → Developers → Webhooks
- **URL:** `https://<YOUR_N8N_DOMAIN>/webhook/realizeos-stripe-webhook`
- **Events:** `checkout.session.completed`
- **Signing secret:** stored in `.env` file — never commit to git

---

## 3. TidyCal Setup (already configured via API)

Booking type created: **RealizeOS Setup Assistance**
- URL: `https://tidycal.com/realization/realizeos-setup`
- Duration: 1 hour, 15 min padding, 24-hour minimum notice
- Already wired into `docs/thank-you.html`

---

## 4. n8n Workflows

### 4.1 Deploy n8n on VPS
```bash
# n8n should be running on your VPS
ssh root@<YOUR_VPS_IP>
cd /opt/n8n
docker compose up -d
```

### 4.2 Import workflows
In n8n admin (`https://<YOUR_N8N_DOMAIN>`):

1. Go to **Workflows** → **Import from File**
2. Import these 3 workflow files from your n8n-automations repo:

| Workflow | File | What it does |
|----------|------|-------------|
| Welcome Flow | `realizeos-welcome-flow.json` | Stripe webhook → parse tier → Google Sheets + Welcome email + Setup call email |
| Email Capture | `realizeos-email-capture.json` | Landing page form → Google Sheets + Lead email |
| Drip Emails | `realizeos-drip-emails.json` | Daily schedule → Day 3/7/14 emails based on purchase date |

### 4.3 Configure credentials in n8n
After importing, you need to set up these credentials:

1. **Google OAuth** (for Gmail + Google Sheets):
   - Go to n8n Settings → Credentials → Add Credential → Google OAuth2
   - Use your Google Workspace account
   - Scopes needed: Gmail send, Google Sheets read/write
   - Connect to all Gmail and Google Sheets nodes

2. **Google Sheets** — Single spreadsheet with 2 tabs (already created):
   - **Spreadsheet ID:** `<YOUR_SPREADSHEET_ID>`
   - **Sheet1** (Leads) — Columns: `Name`, `Email`, `Challenge`, `Source`, `Timestamp`
   - **Customers** tab — Columns: `Date`, `Name`, `Email`, `Tier`, `Amount`, `Stripe ID`
   - Already wired into all 3 workflow JSON files

### 4.4 Update landing page webhook URL
After the Email Capture workflow is active, copy the n8n webhook URL and update `docs/js/main.js` line 185:
```javascript
// Old webhook URL (replaced):
// const WEBHOOK_URL = 'https://<OLD_WEBHOOK_URL>';
// Current n8n URL:
const WEBHOOK_URL = 'https://<YOUR_N8N_DOMAIN>/webhook/lead-capture';
```

### 4.5 Activate all workflows
In n8n, toggle each workflow to **Active**.

---

## 5. Workflow Details

### Welcome Flow
```
Stripe Webhook (POST /webhook/realizeos-stripe-webhook)
  → Parse: email, name, tier (from amount: 7900=lite, 24900=full, 49900=setup)
  → Google Sheets: Add row to "RealizeOS Customers"
  → Gmail: Send welcome email (styled HTML with Drive link, setup steps, community)
  → IF tier = setup:
      → Gmail: Send setup call email (TidyCal booking link + prep checklist)
```

### Email Capture
```
Webhook (POST /webhook/lead-capture)
  → Respond 200 OK (for the frontend fetch)
  → Google Sheets: Add row to "RealizeOS Leads"
  → Gmail: Send lead nurture email (Venture Worksheet link + pricing)
```

### Drip Emails
```
Schedule: Daily at 9:00 AM (Europe/Lisbon)
  → Read "RealizeOS Customers" sheet
  → For each customer, calculate days since purchase
  → Day 3: "3 tips to make your AI sound like you"
  → Day 7: "Your first week — what's next"
  → Day 14: "How's it going?" (feedback request + testimonial ask)
```

---

## Quick Checklist

- [x] Stripe success URLs set for all 3 payment links (via API)
- [x] TidyCal booking type created (via API)
- [x] TidyCal link added to thank-you page
- [x] n8n workflow JSON files created (with spreadsheet ID + correct sheet names)
- [x] n8n deployed on VPS (docker compose up)
- [x] Google OAuth credentials configured in n8n
- [x] Google Sheets created (single file, 2 tabs: Sheet1=Leads, Customers)
- [x] Stripe webhook endpoint added via API (`<YOUR_WEBHOOK_ENDPOINT_ID>`)
- [x] Landing page webhook URL updated to n8n (`lead-capture`)
- [x] Google Drive files uploaded (`<LITE_FILE_ID>` / `<FULL_FILE_ID>`)
- [x] FILE_IDs wired into thank-you page + welcome flow email
- [x] All 3 n8n workflows imported and activated
- [x] Test purchase completed end-to-end (all 3 tiers verified, 7 bugs fixed)

---

## Note: Stepper Hash Routing (March 2026)

`guide.html`, `setup.html`, and `venture-worksheet.html` now use a **stepper wizard** (multi-step navigation). URLs use `#step-N` format instead of section anchor IDs.

**Legacy anchors still work** via alias mapping in `js/stepper.js` — e.g., `guide.html#lite` → step 4, `guide.html#troubleshooting` → step 9.

**Updated links in this repo:**
- `thank-you.html` now uses `#step-4` / `#step-5` / `#step-6` for guide links

**n8n email templates (external repo):** If any drip/welcome emails link to `guide.html#lite`, `guide.html#full`, etc., those still work via anchor aliases. Optionally update them to `#step-N` format when next editing the n8n workflows.
