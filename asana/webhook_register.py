"""
Asana Webhook Registration Script
Registers a webhook against the "New Project Requests" project.
Run AFTER deploy.sh and AFTER the webhook receiver is healthy.

Usage:
  python asana/webhook_register.py

Prerequisites:
  - ASANA_PAT, ASANA_PROJECT_GID, WEBHOOK_RECEIVER_URL in environment or .env
  - Webhook receiver must be deployed and healthy
"""

import os
import sys

import asana
import httpx  # used only for the health check against our own receiver (not Asana)
from asana.rest import ApiException
from dotenv import load_dotenv

load_dotenv()

ASANA_PAT = os.environ.get("ASANA_PAT")
ASANA_PROJECT_GID = os.environ.get("ASANA_PROJECT_GID")
WEBHOOK_RECEIVER_URL = os.environ.get("WEBHOOK_RECEIVER_URL")


def _build_webhooks_api() -> asana.WebhooksApi:
    configuration = asana.Configuration()
    configuration.access_token = ASANA_PAT
    configuration.timeout = 35  # Asana handshake can take up to ~30s
    return asana.WebhooksApi(asana.ApiClient(configuration))


def main():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Asana Webhook Registration")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Validate env vars
    missing = []
    if not ASANA_PAT:
        missing.append("ASANA_PAT")
    if not ASANA_PROJECT_GID:
        missing.append("ASANA_PROJECT_GID")
    if not WEBHOOK_RECEIVER_URL:
        missing.append("WEBHOOK_RECEIVER_URL")

    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("Set them in .env or export them before running this script.")
        sys.exit(1)

    # Verify receiver is up
    print(f"\nChecking webhook receiver health at {WEBHOOK_RECEIVER_URL}/health ...")
    try:
        health_resp = httpx.get(f"{WEBHOOK_RECEIVER_URL}/health", timeout=10)
        health_resp.raise_for_status()
        health_data = health_resp.json()
        print(f"  ✓ Receiver is healthy: {health_data}")
    except Exception as e:
        print(f"  ERROR: Receiver health check failed: {e}")
        print("  The webhook receiver must be deployed and running before registration.")
        sys.exit(1)

    # Register webhook
    webhook_target = WEBHOOK_RECEIVER_URL.rstrip("/") + "/webhook"
    print(f"\nRegistering webhook:")
    print(f"  Project GID: {ASANA_PROJECT_GID}")
    print(f"  Target URL:  {webhook_target}")
    print(f"\n  Waiting for Asana handshake (this call blocks up to 30s)...")

    try:
        webhooks_api = _build_webhooks_api()
        webhook_data = webhooks_api.create_webhook(
            {
                "data": {
                    "resource": ASANA_PROJECT_GID,
                    "target": webhook_target,
                    "filters": [{"resource_type": "task", "action": "added"}],
                }
            },
            {},
        )
    except ApiException as e:
        print(f"\n  ERROR: Webhook registration failed (HTTP {e.status})")
        print(f"  Response body: {e.body}")
        print("\n  Common issues:")
        print("  - ASANA_PAT does not have access to the project")
        print("  - WEBHOOK_RECEIVER_URL is not publicly accessible from the internet")
        print("  - ASANA_PROJECT_GID is incorrect")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        print("  The webhook receiver may not be publicly accessible or the request timed out.")
        sys.exit(1)

    webhook_gid = webhook_data.get("gid", "unknown") if isinstance(webhook_data, dict) else getattr(webhook_data, "gid", "unknown")
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  ✓ Webhook registered successfully!")
    print(f"  Webhook GID: {webhook_gid}")
    print(f"  ✓ X-Hook-Secret has been stored to Secret Manager")
    print(f"\n  → Test by submitting the Asana intake form now.")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
