"""
BigQuery Analyst Agent — FastAPI A2A server
Exposes POST /a2a (JSON-RPC 2.0 message/send) and GET /.well-known/agent.json
"""

import json
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from agent import create_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bigquery-analyst")

app = FastAPI(title="BigQuery Analyst Agent")

AGENT_CARD_PATH = os.path.join(os.path.dirname(__file__), "agent_card.json")
ASANA_CONTEXT_URL = os.getenv("ASANA_CONTEXT_URL", "${ASANA_CONTEXT_URL}")

with open(AGENT_CARD_PATH) as f:
    _agent_card = json.load(f)


async def run_agent(content: str) -> str:
    agent = create_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name="bigquery_analyst",
        session_service=session_service,
    )
    session = await session_service.create_session(
        app_name="bigquery_analyst",
        user_id="a2a",
    )
    response_text = ""
    async for event in runner.run_async(
        user_id="a2a",
        session_id=session.id,
        new_message=genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=content)],
        ),
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts:
                if part.text:
                    response_text += part.text
    return response_text


_MAX_CONTENT_BYTES = 10_000


@app.post("/a2a")
async def a2a_endpoint(request: Request):
    body = await request.json()
    rpc_id = body.get("id", "unknown")
    try:
        content = body["params"]["message"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        return JSONResponse(status_code=400, content={"error": f"Invalid A2A payload: {e}"})

    # Input validation — reject oversized or non-string payloads
    if not isinstance(content, str):
        return JSONResponse(status_code=400, content={"error": "Invalid payload: text must be a string"})
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        return JSONResponse(status_code=400, content={"error": "Payload too large"})

    logger.info(f"[bigquery-analyst] Received request id={rpc_id}")

    try:
        result_text = await run_agent(content)
    except Exception as e:
        # Log full exception server-side; return generic message to caller
        logger.exception(f"Agent execution failed: {e}")
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "status": "error",
                    "message": {
                        "role": "agent",
                        "parts": [{"type": "text", "text": json.dumps({"error": "Agent processing failed. Check service logs."})}],
                    },
                },
            }
        )

    logger.info(f"[bigquery-analyst] Completed request id={rpc_id}")
    return JSONResponse(
        content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "status": "completed",
                "message": {
                    "role": "agent",
                    "parts": [{"type": "text", "text": result_text}],
                },
            },
        }
    )


@app.get("/.well-known/agent.json")
async def agent_card():
    return JSONResponse(content=_agent_card)


@app.get("/health")
async def health():
    return {"status": "ok"}
