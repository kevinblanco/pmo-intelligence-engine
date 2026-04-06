"""
PMO Intelligence Engine — Webhook Receiver
Handles Asana webhook handshake, heartbeats, HMAC validation, and event dispatch.

CRITICAL DEPLOYMENT NOTE:
  Deploy with --min-instances 1. Asana requires a 200 response within 10 seconds.
  Cold starts on serverless containers can exceed this window.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os

import asana
import google.cloud.logging
import httpx  # used only for orchestrator dispatch (non-Asana HTTP call)
from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from google.cloud import secretmanager

# ─── Logging ─────────────────────────────────────────────────────────────────

try:
    log_client = google.cloud.logging.Client()
    log_client.setup_logging()
except Exception:
    pass  # Fall back to standard logging outside GCP

logger = logging.getLogger("webhook-receiver")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ─── Config ───────────────────────────────────────────────────────────────────

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "")
ASANA_PAT = os.getenv("ASANA_PAT", "")

app = FastAPI(title="PMO Webhook Receiver")

# ─── Secret Manager helpers ───────────────────────────────────────────────────

_sm_client = secretmanager.SecretManagerServiceClient()


def get_secret(secret_id: str) -> str:
    name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}/versions/latest"
    response = _sm_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


def store_secret(secret_id: str, value: str) -> None:
    parent = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}"
    _sm_client.add_secret_version(
        request={
            "parent": parent,
            "payload": {"data": value.encode("utf-8")},
        }
    )


# ─── Asana task fetcher (Asana Python SDK) ───────────────────────────────────

OPT_FIELDS = ",".join([
    "gid",
    "name",
    "custom_fields",
    "custom_fields.gid",
    "custom_fields.display_name",
    "custom_fields.type",
    "custom_fields.text_value",
    "custom_fields.number_value",
    "custom_fields.enum_value",
    "custom_fields.enum_value.name",
    "notes",
    "assignee",
    "assignee.name",
])


def _build_tasks_api() -> asana.TasksApi:
    configuration = asana.Configuration()
    configuration.access_token = ASANA_PAT
    return asana.TasksApi(asana.ApiClient(configuration))


def _fetch_asana_task_sync(task_gid: str) -> dict:
    """Synchronous SDK call — run via asyncio.to_thread() to avoid blocking."""
    tasks_api = _build_tasks_api()
    # SDK unwraps the {"data": ...} envelope automatically
    return tasks_api.get_task(task_gid, {"opt_fields": OPT_FIELDS})


async def fetch_asana_task(task_gid: str) -> dict:
    """Fetches an Asana task using the Python SDK in a thread pool."""
    return await asyncio.to_thread(_fetch_asana_task_sync, task_gid)


def extract_custom_fields(task: dict) -> dict:
    fields = {}
    for cf in task.get("custom_fields", []):
        name = cf.get("display_name", "")
        cf_type = cf.get("type", "")
        if cf_type == "text":
            fields[name] = cf.get("text_value")
        elif cf_type == "number":
            fields[name] = cf.get("number_value")
        elif cf_type == "enum":
            enum_val = cf.get("enum_value")
            fields[name] = enum_val.get("name") if enum_val else None
        else:
            fields[name] = None
    return fields


# ─── Cloud Run identity token helper ─────────────────────────────────────────

async def _get_id_token(audience: str) -> str:
    """Fetch a Google-signed OIDC ID token from the GCE metadata server.

    Cloud Run services deployed with --no-allow-unauthenticated require an
    Authorization: Bearer <id_token> header on every inbound request.
    The metadata server issues tokens scoped to the given audience URL.
    """
    metadata_url = (
        "http://metadata.google.internal/computeMetadata/v1/instance/"
        f"service-accounts/default/identity?audience={audience}&format=full"
    )
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(
            metadata_url,
            headers={"Metadata-Flavor": "Google"},
        )
        resp.raise_for_status()
        return resp.text.strip()


# ─── Background event processor ──────────────────────────────────────────────

async def process_events(events: list) -> None:
    for event in events:
        if event.get("action") != "added" or event.get("resource", {}).get("resource_type") != "task":
            continue

        task_gid = event.get("resource", {}).get("gid", "")
        # Validate GID — Asana GIDs are numeric strings up to 19 digits
        if not task_gid or not isinstance(task_gid, str) or not task_gid.isdigit() or len(task_gid) > 19:
            logger.warning(json.dumps({
                "event": "invalid_task_gid_skipped",
                "task_gid": str(task_gid)[:50],
                "service": "webhook-receiver",
            }))
            continue

        logger.info(json.dumps({
            "event": "task_added",
            "task_gid": task_gid,
            "service": "webhook-receiver",
        }))

        try:
            task = await fetch_asana_task(task_gid)
        except Exception as e:
            # Use type name only — str(e) may include full API response bodies
            logger.error(json.dumps({
                "event": "task_fetch_failed",
                "task_gid": task_gid,
                "error": type(e).__name__,
                "service": "webhook-receiver",
            }))
            continue

        custom_fields = extract_custom_fields(task)

        payload = {
            "task_gid": task_gid,
            "project_name": task.get("name", ""),
            "notes": task.get("notes", ""),
            "project_type": custom_fields.get("Project Type"),
            "budget_range": custom_fields.get("Budget Range"),
            "timeline_weeks": custom_fields.get("Timeline (weeks)"),
            "requestor_team": custom_fields.get("Requestor Team"),
            "priority": custom_fields.get("Priority"),
        }

        if not ORCHESTRATOR_URL:
            logger.warning("ORCHESTRATOR_URL not set — skipping dispatch")
            continue

        try:
            # Fetch a Google-signed OIDC token from the metadata server.
            # The orchestrator runs with --no-allow-unauthenticated, so every
            # Cloud Run-to-Cloud Run call must carry an identity token whose
            # audience matches the target service URL.
            id_token = await _get_id_token(ORCHESTRATOR_URL)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{ORCHESTRATOR_URL}/analyze",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {id_token}",
                    },
                )
                resp.raise_for_status()
            logger.info(json.dumps({
                "event": "dispatched_to_orchestrator",
                "task_gid": task_gid,
                "status": resp.status_code,
                "service": "webhook-receiver",
            }))
        except Exception as e:
            # Use type name only — str(e) from httpx may include response bodies
            logger.error(json.dumps({
                "event": "orchestrator_dispatch_failed",
                "task_gid": task_gid,
                "error": type(e).__name__,
                "service": "webhook-receiver",
            }))


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    hook_secret_header = request.headers.get("X-Hook-Secret")

    # ── HANDSHAKE ─────────────────────────────────────────────────────────────
    if hook_secret_header:
        logger.info(json.dumps({
            "event": "handshake_received",
            "service": "webhook-receiver",
        }))
        try:
            store_secret("asana-webhook-secret", hook_secret_header)
        except Exception as e:
            logger.error(f"Failed to store webhook secret: {e}")
            # Still echo the header — Asana handshake must succeed
        return Response(
            status_code=200,
            headers={"X-Hook-Secret": hook_secret_header},
        )

    # ── Parse body ────────────────────────────────────────────────────────────
    raw_body = await request.body()

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.error("Received non-JSON webhook body")
        return Response(status_code=400)

    events = body.get("events", [])

    # ── HEARTBEAT ─────────────────────────────────────────────────────────────
    if not events:
        logger.info(json.dumps({
            "event": "heartbeat_received",
            "service": "webhook-receiver",
        }))
        return Response(status_code=200)

    # ── EVENT — HMAC validation ───────────────────────────────────────────────
    received_sig = request.headers.get("X-Hook-Signature", "")

    try:
        stored_secret = get_secret("asana-webhook-secret")
    except Exception as e:
        logger.error(f"Failed to read webhook secret from Secret Manager: {e}")
        return Response(status_code=500)

    computed_sig = hmac.new(
        stored_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_sig, received_sig):
        logger.warning(json.dumps({
            "event": "hmac_validation_failed",
            "service": "webhook-receiver",
        }))
        return Response(status_code=403)

    # ── Return 200 IMMEDIATELY, process in background ─────────────────────────
    background_tasks.add_task(process_events, events)
    return Response(status_code=200)


@app.get("/health")
async def health():
    secret_configured = False
    try:
        secret = get_secret("asana-webhook-secret")
        secret_configured = bool(secret and secret != "placeholder")
    except Exception:
        pass

    return JSONResponse(content={
        "status": "ok",
        "webhook_secret_configured": secret_configured,
        "orchestrator_url_set": bool(ORCHESTRATOR_URL),
    })
