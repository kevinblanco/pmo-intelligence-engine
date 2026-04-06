#!/usr/bin/env bash
set -euo pipefail

# ─── SECTION 1: Variables ─────────────────────────────────────────────────────

if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID is not set. Run: export GCP_PROJECT_ID=your-project-id"
  exit 1
fi

if [[ -z "${GCP_REGION:-}" ]]; then
  echo "ERROR: GCP_REGION is not set. Run: export GCP_REGION=us-central1"
  exit 1
fi

SA_NAME="pmo-intelligence-sa"
SA_EMAIL="${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PMO Intelligence Engine — GCP Setup"
echo "  Project: ${GCP_PROJECT_ID}"
echo "  Region:  ${GCP_REGION}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

gcloud config set project "${GCP_PROJECT_ID}"

# ─── SECTION 2: Enable APIs ───────────────────────────────────────────────────

echo ""
echo "▶ Enabling GCP APIs..."

gcloud services enable \
  run.googleapis.com \
  bigquery.googleapis.com \
  bigquerymigration.googleapis.com \
  bigquerystorage.googleapis.com \
  aiplatform.googleapis.com \
  cloudapiregistry.googleapis.com \
  apihub.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com

echo "  ✓ Core APIs enabled"

# Enable BigQuery MCP server (beta)
echo "  Enabling BigQuery MCP server (beta)..."
gcloud beta services mcp enable bigquery.googleapis.com || \
  echo "  ⚠ BigQuery MCP beta enable may require allowlisting — contact your Google rep if this fails"

echo "  ✓ APIs ready"

# ─── SECTION 3: Artifact Registry ────────────────────────────────────────────

echo ""
echo "▶ Creating Artifact Registry repository..."

gcloud artifacts repositories create pmo-intelligence \
  --repository-format=docker \
  --location="${GCP_REGION}" \
  --description="PMO Intelligence Engine Docker images" \
  --quiet || echo "  (repository may already exist — skipping)"

echo "  ✓ Artifact Registry: pmo-intelligence in ${GCP_REGION}"

# ─── SECTION 4: Service Account ───────────────────────────────────────────────

echo ""
echo "▶ Creating service account..."

gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="PMO Intelligence Engine SA" \
  --quiet || echo "  (service account may already exist — skipping)"

echo "  ✓ Service account: ${SA_EMAIL}"

echo "  Assigning IAM roles..."

ROLES=(
  "roles/bigquery.dataViewer"
  "roles/bigquery.jobUser"
  "roles/run.invoker"
  "roles/secretmanager.secretAccessor"
  "roles/secretmanager.secretVersionAdder"
  "roles/aiplatform.user"
  "roles/logging.logWriter"
)

for ROLE in "${ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --quiet > /dev/null
  echo "    ✓ ${ROLE}"
done

# ─── SECTION 5: Secret Manager — Placeholder Secrets ─────────────────────────

echo ""
echo "▶ Creating Secret Manager placeholder secrets..."

SECRETS=(
  "asana-pat"
  "asana-webhook-secret"
  "asana-mcp-access-token"
  "asana-mcp-refresh-token"
  "asana-mcp-client-id"
  "asana-mcp-client-secret"
  "asana-mcp-token-expiry"
)

for SECRET in "${SECRETS[@]}"; do
  # Create secret if it doesn't already exist
  if ! gcloud secrets describe "${SECRET}" --quiet > /dev/null 2>&1; then
    echo -n "placeholder" | gcloud secrets create "${SECRET}" \
      --data-file=- \
      --replication-policy=automatic \
      --quiet
    echo "    ✓ Created: ${SECRET}"
  else
    echo "    ↷ Already exists: ${SECRET}"
  fi
done

# ─── SECTION 6: Summary ───────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  ✓ APIs enabled"
echo "  ✓ Artifact Registry created (pmo-intelligence, ${GCP_REGION})"
echo "  ✓ Service account created (${SA_EMAIL})"
echo "  ✓ IAM roles assigned (7 roles)"
echo "  ✓ Secret Manager placeholders created (fill in via GCP Console)"
echo ""
echo "  Next steps:"
echo "  → Fill in Secret Manager secrets at:"
echo "    https://console.cloud.google.com/security/secret-manager?project=${GCP_PROJECT_ID}"
echo ""
echo "  → Run: python bigquery/seed_data.py"
echo "  → Configure Asana: see asana/setup_guide.md"
echo "  → Run: python asana/mcp_auth_setup.py"
echo "  → Run: bash deploy.sh"
echo "  → Run: python asana/webhook_register.py"
echo ""
