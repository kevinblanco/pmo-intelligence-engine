# PMO Intelligence Engine

> **A2A + MCP (Google & Asana) + Vertex AI + BigQuery + Asana**
>
> Live demo for [Google Cloud Next](https://cloud.withgoogle.com/next)

**Author:** Kevin Blanco | Senior Developer Advocate, Asana | Google Developer Expert (Cloud & AI/ML)

---

## What it does

Enterprise have years of historical project data and PMOs are not taking advatage of it when evaluating a new project request. This **PMO Intelligence Engine** closes that gap.

When a PMO analyst submits a project request through an Asana intake form, a multi-agent AI pipeline activates within seconds:

1. A **webhook** fires the moment the task is created in Asana
2. An **ADK orchestrator** on Cloud Run dispatches to four specialist agents via **A2A** (Agent-to-Agent protocol)
3. Two agents query **BigQuery** through Google's managed **MCP** server for historical patterns and resource data
4. One agent queries the live **Asana Work Graph** through Asana's **MCP** server
5. A risk scorer synthesizes everything using **Gemini 2.0 Flash** on **Vertex AI**
6. The orchestrator writes enriched intelligence back to the Asana task via REST API

The PMO reviewer opens the task and has everything they need to make a data-driven decision — no spreadsheets, no BigQuery queries, no Slack threads.

![PMO Intelligence Engine Architecture](pmo_intelligence_engine.png)

---

## Tech stack

| Technology | Role |
|---|---|
| **Google ADK** | Agent runtime for all 5 Cloud Run services |
| **A2A (Agent-to-Agent)** | Protocol for orchestrator ↔ specialist agent communication |
| **MCP — Google-managed** | BigQuery data access for BQ Analyst + Resource Advisor |
| **MCP — Asana-managed** | Live Work Graph access for Asana Context agent |
| **Vertex AI / Gemini 2.0 Flash** | LLM for all agent reasoning |
| **BigQuery** | Historical project outcomes, resource capacity, company OKRs |
| **Cloud Run** | Hosts all 5 services (serverless containers) |
| **Asana Python SDK** | All Asana REST API calls (task fetch, field updates, comments, webhook registration) |
| **Asana** | Human interface (intake form → task) + live data source (MCP) |
| **Secret Manager** | Credentials at runtime — no secrets in source |

---

## Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth application-default login`)
- Python 3.12+
- Asana account with admin access to a workspace

**Desired, but not needed"**
- Docker (for local builds)
- `brew install graphviz` (macOS) — for diagram generation

---

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/kevinblanco/pmo-intelligence-engine
cd pmo-intelligence-engine
cp .env.example .env
# Fill in GCP_PROJECT_ID, ASANA_PAT, ASANA_PROJECT_GID, ASANA_MCP_CLIENT_ID/SECRET
```

### 2. Provision GCP infrastructure

```bash
export GCP_PROJECT_ID=your-project-id
export GCP_REGION=us-central1
bash infra/setup.sh
```

This enables APIs, creates the Artifact Registry repo, service account, IAM bindings, and Secret Manager placeholder secrets.

### 2b. Populate Secret Manager secrets

`infra/setup.sh` creates placeholder secrets. You must replace them with real values **before deploying**. Run each command below, substituting your actual credentials:

```bash
# Your Asana Personal Access Token
# → Asana profile → My Settings → Apps → Manage Developer Apps → Personal access token
echo -n "your-asana-pat" | gcloud secrets versions add asana-pat --data-file=-

# Your Asana MCP OAuth client credentials (from Step 4 / asana/setup_guide.md Step 0)
echo -n "your-mcp-client-id" | gcloud secrets versions add asana-mcp-client-id --data-file=-
echo -n "your-mcp-client-secret" | gcloud secrets versions add asana-mcp-client-secret --data-file=-
```

> **`asana-webhook-secret`** is written automatically during the webhook handshake (`webhook_register.py`) — do not set it manually.
>
> **`asana-mcp-access-token`, `asana-mcp-refresh-token`, `asana-mcp-token-expiry`** are written automatically by `asana/mcp_auth_setup.py` — do not set them manually.

Verify any secret was stored correctly:

```bash
gcloud secrets versions access latest --secret=asana-pat
```

### 3. Seed BigQuery data

Create a virtual environment first — this avoids macOS system Python namespace package conflicts that affect the `google.*` libraries:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install google-cloud-bigquery asana google-cloud-secret-manager httpx python-dotenv
python3 bigquery/seed_data.py
```

Creates the `pmo_intelligence` dataset with 150 historical projects, 40 resource allocation records, and 12 company OKRs.

> **Keep the venv active** for all subsequent local script steps (`mcp_auth_setup.py`, `webhook_register.py`). To reactivate in a new terminal: `source .venv/bin/activate`

### 4. Configure Asana

Follow the step-by-step guide in [`asana/setup_guide.md`](asana/setup_guide.md):
- Create the "New Project Requests" project with custom fields
- Create the MCP OAuth app with two required settings before running the auth script:
  - **OAuth:** add `http://localhost:8888/callback` to the redirect URL allowlist
  - **Manage Distribution:** add your workspace (or set to "Any workspace") — without this the token exchange fails with *"This app is not available to your Asana workspace or organization"*
- Run `python3 asana/mcp_auth_setup.py` to authorize the Asana MCP server

### 5. Deploy to Cloud Run

```bash
bash deploy.sh
```

Deploys all 5 services in the correct order, captures service URLs, and injects them as environment variables.

### 6. Register the Asana webhook

```bash
python3 asana/webhook_register.py
```

Registers the webhook against the "New Project Requests" project using the Asana Python SDK. The SDK call blocks synchronously while Asana completes the handshake with the webhook receiver (up to ~30 seconds), then returns the webhook GID on success.

### 7. Test the pipeline

Submit the Asana intake form with:
- **Project Type:** Infrastructure
- **Budget Range:** $500K–$2M
- **Requestor Team:** Engineering

Watch Cloud Logging stream real-time agent activity. The task enriches within ~30 seconds with a **Risk Score: 7** and **Recommendation: Flag for Review**.

---

## Architecture diagram

The architecture diagram is version-controlled as Python code:

```bash
python3 -m pip install -r diagrams/requirements.txt
python3 diagrams/architecture.py
# Output: pmo_intelligence_engine.png
```

---

## Repository structure

```
pmo-intelligence-engine/
├── diagrams/           # Architecture-as-code (diagrams library)
├── infra/              # GCP provisioning script
├── bigquery/           # Schema DDL + synthetic seed data
├── asana/              # Setup guide, webhook registration, MCP OAuth
├── agents/
│   ├── orchestrator/   # ADK orchestrator + A2A client + Asana REST write-back
│   ├── bigquery_analyst/   # ADK + BigQuery MCP (historical patterns)
│   ├── risk_scorer/    # ADK + Gemini (risk 1–10, recommendation)
│   ├── resource_advisor/   # ADK + BigQuery MCP (capacity + OKR alignment)
│   └── asana_context/  # ADK + Asana MCP (live Work Graph)
├── webhook_receiver/   # FastAPI: handshake + HMAC + heartbeat + dispatch
├── deploy.sh           # Cloud Run deployment (all 5 services, ordered)
└── demo/               # 10-minute recording studio script
```

---

## Troubleshooting

### 401 Unauthorized — task fetch fails after webhook fires

The webhook-receiver can reach Asana but the PAT is rejected. Two causes:

**1. Secret Manager still has the placeholder value.**
`infra/setup.sh` creates secrets with the value `"placeholder"`. You must update them before deploying (see Step 2b above). To check:

```bash
gcloud secrets versions access latest --secret=asana-pat
```

If it prints `placeholder`, update it:

```bash
echo -n "your-real-asana-pat" | gcloud secrets versions add asana-pat --data-file=-
```

**2. The running container didn't pick up the new secret.**
Cloud Run injects `--set-secrets` as environment variables at container start time, not on every request. If you updated the secret _after_ the container started, it still has the old value in memory. Force a new revision:

```bash
gcloud run services update webhook-receiver \
  --region us-central1 \
  --update-env-vars "GCP_PROJECT_ID=$(gcloud config get-value project)"
```

> ⚠️ Use `--update-env-vars` (not `--set-env-vars`) — `--set-env-vars` **replaces all environment variables**, which will wipe `ORCHESTRATOR_URL` and break dispatch to the orchestrator.

---

### 403 Forbidden — `orchestrator_dispatch_failed` in webhook-receiver logs

The webhook-receiver is reaching the orchestrator but the request is rejected because it has no authentication token. Cloud Run services deployed with `--no-allow-unauthenticated` require every caller to present a Google-signed OIDC identity token.

This is handled automatically in code — the webhook-receiver fetches an ID token from the GCE metadata server before each orchestrator call. If you see this error it usually means you're running an older container image that predates this fix. Redeploy the webhook-receiver:

```bash
gcloud run deploy webhook-receiver \
  --source ./webhook_receiver \
  --region us-central1 \
  --quiet
```

If `ORCHESTRATOR_URL` gets wiped during the redeploy, re-inject it without touching other vars:

```bash
ORCHESTRATOR_URL=$(gcloud run services describe orchestrator \
  --region us-central1 --format "value(status.url)")

gcloud run services update webhook-receiver \
  --region us-central1 \
  --update-env-vars "ORCHESTRATOR_URL=${ORCHESTRATOR_URL}"
```

---

### 400 Bad Request — Asana MCP token exchange fails

Two known causes:

- **Redirect URI mismatch:** `http://localhost:8888/callback` must be in your app's OAuth allowlist. Go to [app.asana.com/0/my-apps](https://app.asana.com/0/my-apps) → your app → OAuth → add the redirect URL.
- **Workspace not authorized:** Under **Manage Distribution**, add your workspace or set to "Any workspace." Without this, Asana returns *"This app is not available to your Asana workspace or organization."*

---

### `ModuleNotFoundError: No module named 'google'` — seed_data.py

macOS system Python 3.9 has a namespace package bug with `google.*` libraries when the script directory is on `sys.path`. Fix: use a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install google-cloud-bigquery asana google-cloud-secret-manager httpx python-dotenv
python3 bigquery/seed_data.py
```

---

### `DefaultCredentialsError` — seed_data.py or other GCP scripts

Application Default Credentials are not configured. Run:

```bash
gcloud auth application-default login
```

---

### Webhook registration times out or returns an error

- Verify the webhook-receiver is running: `curl $WEBHOOK_RECEIVER_URL/health`
- The health response must show `"webhook_secret_configured": false` (expected before first registration). If it shows `"status": "unreachable"`, the service isn't deployed.
- Re-run: `python3 asana/webhook_register.py`

---

## License

Apache 2.0 — see [LICENSE](LICENSE)
