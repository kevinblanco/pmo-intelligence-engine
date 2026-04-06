#!/usr/bin/env bash
set -euo pipefail

# Source .env if present (so ASANA_MCP_CLIENT_ID and other vars are available)
if [[ -f ".env" ]]; then
  set -o allexport
  # shellcheck source=.env
  source .env
  set +o allexport
fi

# ─── Variables ────────────────────────────────────────────────────────────────

if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID is not set"
  exit 1
fi
if [[ -z "${GCP_REGION:-}" ]]; then
  echo "ERROR: GCP_REGION is not set"
  exit 1
fi

PROJECT_ID="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"
SA_EMAIL="pmo-intelligence-sa@${PROJECT_ID}.iam.gserviceaccount.com"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.0-flash}"
BIGQUERY_DATASET="${BIGQUERY_DATASET:-pmo_intelligence}"

# Vertex AI env vars required by Google ADK.
# Without these the ADK defaults to the Gemini API and fails with "No API key".
VERTEX_ENV="GOOGLE_GENAI_USE_VERTEXAI=1,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PMO Intelligence Engine — Cloud Run Deployment"
echo "  Project: ${PROJECT_ID}"
echo "  Region:  ${REGION}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

gcloud config set project "${PROJECT_ID}"

# ─── 1. Deploy webhook-receiver (FIRST — must be running before orchestrator) ──

echo ""
echo "▶ [1/5] Deploying webhook-receiver..."

gcloud run deploy webhook-receiver \
  --source ./webhook_receiver \
  --region "${REGION}" \
  --allow-unauthenticated \
  --min-instances 1 \
  --memory 512Mi \
  --timeout 300 \
  --concurrency 80 \
  --service-account "${SA_EMAIL}" \
  --set-secrets "ASANA_PAT=asana-pat:latest,ASANA_WEBHOOK_SECRET=asana-webhook-secret:latest" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
  --quiet

WEBHOOK_RECEIVER_URL=$(gcloud run services describe webhook-receiver \
  --region "${REGION}" \
  --format "value(status.url)")

echo "  ✓ webhook-receiver: ${WEBHOOK_RECEIVER_URL}"

# ─── 2. Deploy bigquery-analyst ────────────────────────────────────────────────

echo ""
echo "▶ [2/5] Deploying bigquery-analyst..."

gcloud run deploy bigquery-analyst \
  --source ./agents/bigquery_analyst \
  --region "${REGION}" \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --memory 1Gi \
  --timeout 300 \
  --service-account "${SA_EMAIL}" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},BIGQUERY_DATASET=${BIGQUERY_DATASET},GEMINI_MODEL=${GEMINI_MODEL},${VERTEX_ENV}" \
  --quiet

BQ_ANALYST_URL=$(gcloud run services describe bigquery-analyst \
  --region "${REGION}" \
  --format "value(status.url)")

echo "  ✓ bigquery-analyst: ${BQ_ANALYST_URL}"

# Allow orchestrator SA to invoke
gcloud run services add-iam-policy-binding bigquery-analyst \
  --region "${REGION}" \
  --member "serviceAccount:${SA_EMAIL}" \
  --role "roles/run.invoker" \
  --quiet

# ─── 3. Deploy risk-scorer ─────────────────────────────────────────────────────

echo ""
echo "▶ [3/5] Deploying risk-scorer..."

gcloud run deploy risk-scorer \
  --source ./agents/risk_scorer \
  --region "${REGION}" \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --memory 1Gi \
  --timeout 300 \
  --service-account "${SA_EMAIL}" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},GEMINI_MODEL=${GEMINI_MODEL},${VERTEX_ENV}" \
  --quiet

RISK_SCORER_URL=$(gcloud run services describe risk-scorer \
  --region "${REGION}" \
  --format "value(status.url)")

echo "  ✓ risk-scorer: ${RISK_SCORER_URL}"

gcloud run services add-iam-policy-binding risk-scorer \
  --region "${REGION}" \
  --member "serviceAccount:${SA_EMAIL}" \
  --role "roles/run.invoker" \
  --quiet

# ─── 4. Deploy resource-advisor ────────────────────────────────────────────────

echo ""
echo "▶ [4/5] Deploying resource-advisor..."

gcloud run deploy resource-advisor \
  --source ./agents/resource_advisor \
  --region "${REGION}" \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --memory 1Gi \
  --timeout 300 \
  --service-account "${SA_EMAIL}" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},BIGQUERY_DATASET=${BIGQUERY_DATASET},GEMINI_MODEL=${GEMINI_MODEL},${VERTEX_ENV}" \
  --quiet

RESOURCE_ADVISOR_URL=$(gcloud run services describe resource-advisor \
  --region "${REGION}" \
  --format "value(status.url)")

echo "  ✓ resource-advisor: ${RESOURCE_ADVISOR_URL}"

gcloud run services add-iam-policy-binding resource-advisor \
  --region "${REGION}" \
  --member "serviceAccount:${SA_EMAIL}" \
  --role "roles/run.invoker" \
  --quiet

# ─── 5. Deploy asana-context ───────────────────────────────────────────────────

echo ""
echo "▶ [5/6] Deploying asana-context..."

ASANA_MCP_CLIENT_ID="${ASANA_MCP_CLIENT_ID:-}"
if [[ -z "${ASANA_MCP_CLIENT_ID}" ]]; then
  echo "  WARNING: ASANA_MCP_CLIENT_ID not set — asana-context will fail to refresh tokens"
fi

gcloud run deploy asana-context \
  --source ./agents/asana_context \
  --region "${REGION}" \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --memory 1Gi \
  --timeout 300 \
  --service-account "${SA_EMAIL}" \
  --set-secrets "ASANA_MCP_ACCESS_TOKEN=asana-mcp-access-token:latest,ASANA_MCP_REFRESH_TOKEN=asana-mcp-refresh-token:latest,ASANA_MCP_CLIENT_SECRET=asana-mcp-client-secret:latest" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},GEMINI_MODEL=${GEMINI_MODEL},ASANA_MCP_CLIENT_ID=${ASANA_MCP_CLIENT_ID},${VERTEX_ENV}" \
  --quiet

ASANA_CONTEXT_URL=$(gcloud run services describe asana-context \
  --region "${REGION}" \
  --format "value(status.url)")

echo "  ✓ asana-context: ${ASANA_CONTEXT_URL}"

gcloud run services add-iam-policy-binding asana-context \
  --region "${REGION}" \
  --member "serviceAccount:${SA_EMAIL}" \
  --role "roles/run.invoker" \
  --quiet

# ─── 6. Deploy orchestrator (last — needs all agent URLs) ─────────────────────

echo ""
echo "▶ [6/6] Deploying orchestrator..."

gcloud run deploy orchestrator \
  --source ./agents/orchestrator \
  --region "${REGION}" \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --memory 1Gi \
  --timeout 300 \
  --service-account "${SA_EMAIL}" \
  --set-secrets "ASANA_PAT=asana-pat:latest" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},GEMINI_MODEL=${GEMINI_MODEL},BQ_ANALYST_URL=${BQ_ANALYST_URL},RISK_SCORER_URL=${RISK_SCORER_URL},RESOURCE_ADVISOR_URL=${RESOURCE_ADVISOR_URL},ASANA_CONTEXT_URL=${ASANA_CONTEXT_URL},${VERTEX_ENV}" \
  --quiet

ORCHESTRATOR_URL=$(gcloud run services describe orchestrator \
  --region "${REGION}" \
  --format "value(status.url)")

echo "  ✓ orchestrator: ${ORCHESTRATOR_URL}"

gcloud run services add-iam-policy-binding orchestrator \
  --region "${REGION}" \
  --member "serviceAccount:${SA_EMAIL}" \
  --role "roles/run.invoker" \
  --quiet

# ─── 7. Update webhook-receiver with ORCHESTRATOR_URL ─────────────────────────

echo ""
echo "▶ Updating webhook-receiver with ORCHESTRATOR_URL..."

gcloud run services update webhook-receiver \
  --region "${REGION}" \
  --update-env-vars "ORCHESTRATOR_URL=${ORCHESTRATOR_URL}" \
  --quiet

echo "  ✓ webhook-receiver updated"

# ─── 8. Health check ──────────────────────────────────────────────────────────

echo ""
echo "▶ Running health check..."
HEALTH_RESPONSE=$(curl -sf "${WEBHOOK_RECEIVER_URL}/health" || echo '{"status":"unreachable"}')
echo "  ${WEBHOOK_RECEIVER_URL}/health → ${HEALTH_RESPONSE}"

# ─── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Deployment complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
printf "  %-25s %s\n" "Service" "URL"
printf "  %-25s %s\n" "───────────────────────" "───────────────────────────────────────────"
printf "  %-25s %s\n" "webhook-receiver"  "${WEBHOOK_RECEIVER_URL}"
printf "  %-25s %s\n" "bigquery-analyst"  "${BQ_ANALYST_URL}"
printf "  %-25s %s\n" "risk-scorer"       "${RISK_SCORER_URL}"
printf "  %-25s %s\n" "resource-advisor"  "${RESOURCE_ADVISOR_URL}"
printf "  %-25s %s\n" "asana-context"     "${ASANA_CONTEXT_URL}"
printf "  %-25s %s\n" "orchestrator"      "${ORCHESTRATOR_URL}"
echo ""
echo "  → Add these to your .env file:"
echo "    WEBHOOK_RECEIVER_URL=${WEBHOOK_RECEIVER_URL}"
echo "    ORCHESTRATOR_URL=${ORCHESTRATOR_URL}"
echo "    BQ_ANALYST_URL=${BQ_ANALYST_URL}"
echo "    RISK_SCORER_URL=${RISK_SCORER_URL}"
echo "    RESOURCE_ADVISOR_URL=${RESOURCE_ADVISOR_URL}"
echo "    ASANA_CONTEXT_URL=${ASANA_CONTEXT_URL}"
echo ""
echo "  → Now run: python asana/webhook_register.py"
echo ""
