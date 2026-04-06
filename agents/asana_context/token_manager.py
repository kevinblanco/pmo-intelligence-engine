"""
Asana MCP OAuth Token Manager
Reads/refreshes Asana OAuth tokens from Secret Manager.
Tokens expire after 1 hour; this module auto-refreshes when expiry is within 5 minutes.

NOTE: httpx is intentionally used here instead of the Asana Python SDK.
The `/-/oauth_token` endpoint is an OAuth2 token endpoint — not part of the
Asana REST API. The Asana Python SDK handles REST resources (tasks, projects, etc.)
but does not manage OAuth2 token refresh flows for MCP credentials.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from google.cloud import secretmanager

logger = logging.getLogger("asana-context.token-manager")

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
ASANA_MCP_CLIENT_ID = os.getenv("ASANA_MCP_CLIENT_ID", "")
ASANA_TOKEN_URL = "https://app.asana.com/-/oauth_token"

_sm_client = secretmanager.SecretManagerServiceClient()


def _get_secret(secret_id: str) -> str:
    name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}/versions/latest"
    response = _sm_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


def _store_secret(secret_id: str, value: str) -> None:
    parent = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}"
    _sm_client.add_secret_version(
        request={
            "parent": parent,
            "payload": {"data": value.encode("utf-8")},
        }
    )


def _is_token_expiring(expiry_iso: str) -> bool:
    try:
        expiry = datetime.fromisoformat(expiry_iso)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= (expiry - timedelta(minutes=5))
    except Exception:
        return True  # If we can't parse, refresh


def _refresh_token() -> str:
    logger.info("Refreshing Asana MCP access token")
    refresh_token = _get_secret("asana-mcp-refresh-token")
    client_secret = _get_secret("asana-mcp-client-secret")

    response = httpx.post(
        ASANA_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": ASANA_MCP_CLIENT_ID,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    response.raise_for_status()
    token_data = response.json()

    new_access_token = token_data["access_token"]
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=3600)).isoformat()

    _store_secret("asana-mcp-access-token", new_access_token)
    _store_secret("asana-mcp-token-expiry", expiry)

    if "refresh_token" in token_data:
        _store_secret("asana-mcp-refresh-token", token_data["refresh_token"])

    logger.info("Asana MCP access token refreshed successfully")
    return new_access_token


def get_valid_access_token() -> str:
    """
    Returns a valid Asana MCP access token.
    Refreshes automatically if expiring within 5 minutes.
    Raises RuntimeError if a valid token cannot be obtained.
    """
    try:
        expiry_iso = _get_secret("asana-mcp-token-expiry")
        if _is_token_expiring(expiry_iso):
            token = _refresh_token()
        else:
            token = _get_secret("asana-mcp-access-token")
    except Exception as e:
        logger.warning(f"Token read failed, attempting refresh: {type(e).__name__}")
        token = _refresh_token()

    if not token or len(token) < 10:
        raise RuntimeError("Failed to obtain a valid Asana MCP access token — check Secret Manager and OAuth credentials")

    return token
