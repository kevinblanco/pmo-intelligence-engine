"""
A2A Client — JSON-RPC 2.0 helper for agent-to-agent communication.
Sends tasks to specialist agents via POST /a2a with retry + exponential backoff.

All specialist agents run with --no-allow-unauthenticated on Cloud Run.
Every outbound call must include a Google-signed OIDC identity token in the
Authorization header. The token is fetched from the GCE metadata server with
the target service URL as the audience.
"""

import asyncio
import json
import logging

import httpx

logger = logging.getLogger("orchestrator.a2a-client")

RETRY_DELAYS = [2, 4, 8]  # seconds


async def _get_id_token(audience: str) -> str:
    """Fetch a Google-signed OIDC ID token for the given audience URL."""
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


async def send_a2a_task(agent_url: str, content: str, task_id: str) -> dict:
    """
    Sends a task to a specialist agent via A2A JSON-RPC 2.0.

    Args:
        agent_url: Base URL of the specialist agent (without /a2a path)
        content:   Text content to send as the user message
        task_id:   Unique ID for this RPC call (used as jsonrpc id)

    Returns:
        Parsed JSON dict from the agent's response, or {"error": "<msg>"} on failure.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": task_id,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": content}],
            }
        },
    }

    url = agent_url.rstrip("/") + "/a2a"
    # Use the base service URL (without /a2a) as the OIDC audience
    audience = agent_url.rstrip("/")
    last_error = None

    for attempt, delay in enumerate([0] + RETRY_DELAYS, start=1):
        if delay > 0:
            logger.info(f"[a2a-client] Retry {attempt-1}/{len(RETRY_DELAYS)} for {url} in {delay}s")
            await asyncio.sleep(delay)

        try:
            id_token = await _get_id_token(audience)
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {id_token}",
                    },
                )
                response.raise_for_status()

            rpc_response = response.json()
            result = rpc_response.get("result", {})
            message_parts = result.get("message", {}).get("parts", [])

            if not message_parts:
                return {"error": "Agent returned empty response"}

            text = message_parts[0].get("text", "")

            # Strip markdown code fences if present
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            return json.loads(text)

        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e} — raw: {text[:200]}"
            logger.warning(f"[a2a-client] {last_error}")
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            logger.warning(f"[a2a-client] {last_error}")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[a2a-client] Request failed: {e}")

    logger.error(f"[a2a-client] All retries exhausted for {url}: {last_error}")
    return {"error": last_error}
