# Asana Setup Guide — PMO Intelligence Engine

Follow these steps in order before deploying the pipeline.

---

## Step 0: Create Asana MCP OAuth App (do this first)

1. Go to [app.asana.com/0/my-apps](https://app.asana.com/0/my-apps) → **Create new app**
2. App type: **MCP app**
3. Under **OAuth**: add the following redirect URL to the allowlist:

   ```
   http://localhost:8888/callback
   ```

   > ⚠️ **This step is required before running `mcp_auth_setup.py`.** If this URL is not in the allowlist, Asana will reject the OAuth redirect with an `invalid_request` error. The script opens a local server on port 8888 to receive the authorization callback — that exact URL must match what's registered in the app.

4. Under **Manage Distribution**: configure which workspaces can authorize this app.

   You have two options:

   - **Specific workspaces** — click **Add workspace** and add the workspace you'll use for the demo. Only users from that workspace will be able to authorize the app.
   - **Any workspace** — any Asana user with the authorization link can use the app. Fine for a demo/dev app you control.

   > ⚠️ **If you skip this step, the token exchange will fail** with the error: *"This app is not available to your Asana workspace or organization."* Your workspace must be explicitly allowed before the OAuth flow will complete.

5. Copy **Client ID** → `.env` as `ASANA_MCP_CLIENT_ID`
6. Copy **Client Secret** → `.env` as `ASANA_MCP_CLIENT_SECRET`
7. Run: `python3 asana/mcp_auth_setup.py` (after `infra/setup.sh`, with venv active)

---

## Step 1: Create the Asana Project

1. Create a new project named **"New Project Requests"**
2. Layout: **Board**
3. Add the following sections in order:
   - `Submitted`
   - `Under Review`
   - `Approved`
   - `Rejected`

---

## Step 2: Add All Custom Fields

### Input Fields (submitted via form)

| Field Name | Type | Options |
|---|---|---|
| Project Type | Single-select | Product Launch, Infrastructure, Compliance, Digital Transformation, Cost Reduction |
| Budget Range | Single-select | Under $100K, $100K–$500K, $500K–$2M, Over $2M |
| Timeline (weeks) | Number | — |
| Requestor Team | Single-select | Engineering, Marketing, Operations, Finance, HR |
| Priority | Single-select | High, Medium, Low |

### Output Fields (written by AI agents)

| Field Name | Type | Notes / Options |
|---|---|---|
| AI Risk Score | Number | Range: 1–10 |
| Resource Signal | Text | — |
| Strategic Fit | Text | — |
| Live Workspace Context | Text | — |
| AI Recommendation | Single-select | Approve, Flag for Review, Escalate |
| Analysis Status | Single-select | Pending, In Progress, Complete, Error |

---

## Step 3: Create the Intake Form

1. Go to **Project Settings → Forms → Add Form**
2. Title: **"New Project Request"**
3. Map each **Input Field** (from Step 2) to a form question with a clear, human-readable label
4. Set the form description to:

   > After submitting, our AI pipeline will analyze your request using historical project data and live workspace context. You'll see results in your task within 30 seconds.

---

## Step 4: Create a Task Template

1. Create a task template that displays all custom fields in the right panel
2. Set the **Analysis Status** field default value to `Pending`

---

## Step 5: Note Your Project GID

1. Open the project in Asana
2. Find the GID in the URL: `asana.com/0/{PROJECT_GID}/...`
3. Add to `.env` as:

   ```
   ASANA_PROJECT_GID=<your_project_gid>
   ```

---

## Step 6: Register the Webhook (run AFTER deploy.sh completes)

1. Verify the webhook receiver is running:

   ```bash
   curl $WEBHOOK_RECEIVER_URL/health
   ```

2. Register the webhook:

   ```bash
   python asana/webhook_register.py
   ```
