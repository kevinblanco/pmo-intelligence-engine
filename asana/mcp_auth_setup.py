"""
Asana MCP OAuth Setup — one-time authorization script.
Run this ONCE after infra/setup.sh to authorize the Asana MCP server.
Stores tokens in Secret Manager for use by the asana_context agent.

Usage:
  python asana/mcp_auth_setup.py

Prerequisites:
  - ASANA_MCP_CLIENT_ID and ASANA_MCP_CLIENT_SECRET in environment or .env
  - GCP_PROJECT_ID in environment
  - infra/setup.sh must have been run (Secret Manager secrets must exist)

NOTE: httpx is intentionally used here instead of the Asana Python SDK.
This script performs an OAuth2 authorization code flow against the
`/-/oauth_authorize` and `/-/oauth_token` endpoints — these are OAuth2
infrastructure endpoints, not Asana REST API endpoints. The Asana Python SDK
manages REST resources (tasks, projects, etc.) and does not implement OAuth2
authorization flows for MCP credentials.

NOTE: No PKCE. Asana MCP apps are confidential clients (they have a
client_secret). Asana's token endpoint rejects requests that send both
client_secret and code_verifier — PKCE is for public clients only.
"""

import http.server
import os
import secrets
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from google.cloud import secretmanager

load_dotenv()

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
ASANA_MCP_CLIENT_ID = os.environ.get("ASANA_MCP_CLIENT_ID")
ASANA_MCP_CLIENT_SECRET = os.environ.get("ASANA_MCP_CLIENT_SECRET")

REDIRECT_URI = "http://localhost:8888/callback"
ASANA_AUTH_URL = "https://app.asana.com/-/oauth_authorize"
ASANA_TOKEN_URL = "https://app.asana.com/-/oauth_token"
CALLBACK_TIMEOUT = 120  # seconds

_sm_client = secretmanager.SecretManagerServiceClient()


def _store_secret(secret_id: str, value: str) -> None:
    parent = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}"
    _sm_client.add_secret_version(
        request={
            "parent": parent,
            "payload": {"data": value.encode("utf-8")},
        }
    )



class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    callback_result = {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.callback_result["code"] = params.get("code", [None])[0]
        _CallbackHandler.callback_result["state"] = params.get("state", [None])[0]
        _CallbackHandler.callback_result["error"] = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h2>Authorization complete. You can close this tab.</h2></body></html>")

    def log_message(self, format, *args):
        pass  # Suppress request logs


def main():
    if not GCP_PROJECT_ID:
        print("ERROR: GCP_PROJECT_ID is not set")
        raise SystemExit(1)
    if not ASANA_MCP_CLIENT_ID:
        print("ERROR: ASANA_MCP_CLIENT_ID is not set")
        raise SystemExit(1)
    if not ASANA_MCP_CLIENT_SECRET:
        print("ERROR: ASANA_MCP_CLIENT_SECRET is not set")
        raise SystemExit(1)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Asana MCP OAuth Authorization")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # NOTE: No PKCE — Asana MCP apps are confidential clients (they have a
    # client_secret). Asana's token endpoint rejects requests that send both
    # client_secret and code_verifier. Confidential clients authenticate via
    # the secret alone; PKCE is only for public clients without a secret.
    state = secrets.token_urlsafe(16)

    # Build authorization URL
    auth_params = {
        "client_id": ASANA_MCP_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "resource": "https://mcp.asana.com/v2",
        "state": state,
    }
    auth_url = ASANA_AUTH_URL + "?" + urllib.parse.urlencode(auth_params)

    print(f"\nOpening browser for Asana authorization...")
    print(f"If your browser doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    # Start local callback server
    server = http.server.HTTPServer(("localhost", 8888), _CallbackHandler)
    server.timeout = CALLBACK_TIMEOUT

    print(f"Waiting for callback on http://localhost:8888/callback (timeout: {CALLBACK_TIMEOUT}s)...")

    # Handle ONE request
    server.handle_request()
    server.server_close()

    result = _CallbackHandler.callback_result
    if result.get("error"):
        print(f"ERROR: Authorization denied — {result['error']}")
        raise SystemExit(1)

    code = result.get("code")
    returned_state = result.get("state")

    if not code:
        print("ERROR: No authorization code received")
        raise SystemExit(1)

    if returned_state != state:
        print("ERROR: State mismatch — possible CSRF attack")
        raise SystemExit(1)

    print("  ✓ Authorization code received")

    # Exchange code for tokens
    # resource must match the value sent in the authorization request (RFC 8707)
    print("\nExchanging code for tokens...")
    token_response = httpx.post(
        ASANA_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": ASANA_MCP_CLIENT_ID,
            "client_secret": ASANA_MCP_CLIENT_SECRET,
            "resource": "https://mcp.asana.com/v2",
        },
        timeout=15,
    )

    if not token_response.is_success:
        print(f"\n  ERROR: Token exchange failed (HTTP {token_response.status_code})")
        print(f"  Asana response: {token_response.text}")
        raise SystemExit(1)

    token_data = token_response.json()

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=3600)).isoformat()

    print("  ✓ Tokens received")

    # Store in Secret Manager
    print("\nStoring tokens in Secret Manager...")
    _store_secret("asana-mcp-access-token", access_token)
    print("  ✓ asana-mcp-access-token")

    if refresh_token:
        _store_secret("asana-mcp-refresh-token", refresh_token)
        print("  ✓ asana-mcp-refresh-token")

    _store_secret("asana-mcp-client-secret", ASANA_MCP_CLIENT_SECRET)
    print("  ✓ asana-mcp-client-secret")

    _store_secret("asana-mcp-token-expiry", expiry)
    print("  ✓ asana-mcp-token-expiry")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  ✓ Asana MCP tokens stored in Secret Manager")
    print(f"  → Access token expires in 1 hour (auto-refreshed by agent)")
    print(f"  → You can now deploy the asana_context agent")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
