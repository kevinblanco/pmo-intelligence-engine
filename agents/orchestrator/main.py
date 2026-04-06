"""
PMO Intelligence Engine — Orchestrator
FastAPI service that coordinates 4 specialist agents in parallel/sequential pattern
and writes enriched intelligence back to the Asana task.
"""

import asyncio
import json
import logging
import os
import time
import uuid

import google.cloud.logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from a2a_client import send_a2a_task
from asana_updater import set_analysis_status, update_task_with_enrichment

# ─── Logging ─────────────────────────────────────────────────────────────────

try:
    log_client = google.cloud.logging.Client()
    log_client.setup_logging()
except Exception:
    pass

logger = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ─── Config ───────────────────────────────────────────────────────────────────

BQ_ANALYST_URL = os.environ["BQ_ANALYST_URL"]
RISK_SCORER_URL = os.environ["RISK_SCORER_URL"]
RESOURCE_ADVISOR_URL = os.environ["RESOURCE_ADVISOR_URL"]
ASANA_CONTEXT_URL = os.environ["ASANA_CONTEXT_URL"]

app = FastAPI(title="PMO Orchestrator")


# ─── Request model ────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    task_gid: str
    project_name: str
    project_type: str | None = None
    budget_range: str | None = None
    timeline_weeks: float | None = None
    requestor_team: str | None = None
    priority: str | None = None
    notes: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _log_step(event: str, task_gid: str, agent: str = "", duration_ms: int = 0, success: bool = True, detail: str = ""):
    logger.info(json.dumps({
        "event": event,
        "task_gid": task_gid,
        "agent": agent,
        "duration_ms": duration_ms,
        "success": success,
        "detail": detail,
        "service": "orchestrator",
    }))


def _assemble_payload(
    req: AnalyzeRequest,
    bq_result: dict,
    risk_result: dict,
    resource_result: dict,
    asana_result: dict,
) -> dict:
    """Merges all specialist outputs into a single enrichment payload."""
    return {
        # From risk_scorer
        "risk_score": risk_result.get("risk_score", 5),
        "risk_level": risk_result.get("risk_level", "Medium"),
        "confidence": risk_result.get("confidence", "Low"),
        "risk_factors": risk_result.get("risk_factors", []),
        "strategic_fit": risk_result.get("strategic_fit", "Unknown"),
        "strategic_fit_reason": risk_result.get("strategic_fit_reason", ""),
        "recommendation": risk_result.get("recommendation", "Flag for Review"),

        # From resource_advisor
        "resource_signal": resource_result.get("resource_signal", "Unknown"),
        "resource_recommendation": resource_result.get("resource_recommendation", ""),
        "okr_alignment": resource_result.get("okr_alignment", "Unknown"),

        # From asana_context
        "live_context_summary": asana_result.get("live_context_summary", ""),
        "potential_duplicate": asana_result.get("potential_duplicate", False),
        "potential_duplicate_reason": asana_result.get("potential_duplicate_reason", ""),
        "active_similar_projects": asana_result.get("active_similar_projects", []),

        # From bigquery_analyst (for comment context)
        "similar_projects_count": bq_result.get("similar_projects_count", 0),
        "avg_budget_overrun_pct": bq_result.get("avg_budget_overrun_pct", 0),
        "pct_over_budget": bq_result.get("pct_over_budget", 0),
        "most_common_outcome": bq_result.get("most_common_outcome", ""),
    }


# ─── Main route ───────────────────────────────────────────────────────────────

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    task_gid = req.task_gid
    run_id = str(uuid.uuid4())[:8]

    _log_step("analysis_started", task_gid, detail=f"run_id={run_id}")

    # Step 1: Set Analysis Status → In Progress
    try:
        set_analysis_status(task_gid, "In Progress")
        _log_step("status_set_in_progress", task_gid)
    except Exception as e:
        _log_step("status_set_failed", task_gid, success=False, detail=str(e))
        # Non-fatal — continue with analysis

    # Step 2: Build content strings
    bq_content = (
        f"Project: {req.project_name}. "
        f"Type: {req.project_type}. "
        f"Team: {req.requestor_team}. "
        f"Budget: {req.budget_range}. "
        f"Timeline: {req.timeline_weeks} weeks. "
        f"Priority: {req.priority}."
    )
    resource_content = (
        f"Requestor team: {req.requestor_team}. "
        f"Project type: {req.project_type}. "
        f"Budget range: {req.budget_range}."
    )
    asana_content = (
        f"Project type: {req.project_type}. "
        f"Requestor team: {req.requestor_team}. "
        f"Project name: {req.project_name}."
    )

    # Step 3: Run BQ Analyst, Resource Advisor, Asana Context in PARALLEL
    t0 = time.monotonic()
    bq_task_id = f"{run_id}-bq"
    resource_task_id = f"{run_id}-resource"
    asana_task_id = f"{run_id}-asana"

    bq_result, resource_result, asana_result = await asyncio.gather(
        send_a2a_task(BQ_ANALYST_URL, bq_content, bq_task_id),
        send_a2a_task(RESOURCE_ADVISOR_URL, resource_content, resource_task_id),
        send_a2a_task(ASANA_CONTEXT_URL, asana_content, asana_task_id),
    )

    parallel_ms = int((time.monotonic() - t0) * 1000)
    _log_step("parallel_agents_complete", task_gid, duration_ms=parallel_ms,
              success="error" not in bq_result)

    _log_step("bq_analyst_result", task_gid, agent="bigquery_analyst",
              success="error" not in bq_result,
              detail=f"similar_projects={bq_result.get('similar_projects_count', 'error')}")
    _log_step("resource_advisor_result", task_gid, agent="resource_advisor",
              success="error" not in resource_result,
              detail=f"signal={resource_result.get('resource_signal', 'error')}")
    _log_step("asana_context_result", task_gid, agent="asana_context",
              success="error" not in asana_result,
              detail=f"duplicate={asana_result.get('potential_duplicate', 'error')}")

    # Step 4: Risk Scorer runs AFTER BQ (needs historical data)
    risk_content = (
        f"Historical analysis data: {json.dumps(bq_result)}. "
        f"Project type: {req.project_type}. "
        f"Budget range: {req.budget_range}. "
        f"Team: {req.requestor_team}. "
        f"Priority: {req.priority}."
    )

    t1 = time.monotonic()
    risk_result = await send_a2a_task(RISK_SCORER_URL, risk_content, f"{run_id}-risk")
    risk_ms = int((time.monotonic() - t1) * 1000)

    _log_step("risk_scorer_result", task_gid, agent="risk_scorer",
              duration_ms=risk_ms,
              success="error" not in risk_result,
              detail=f"score={risk_result.get('risk_score', 'error')}, recommendation={risk_result.get('recommendation', 'error')}")

    # Step 5: Assemble payload
    payload = _assemble_payload(req, bq_result, risk_result, resource_result, asana_result)

    # Step 6: Write back to Asana
    try:
        t2 = time.monotonic()
        update_task_with_enrichment(task_gid, payload)
        asana_ms = int((time.monotonic() - t2) * 1000)
        _log_step("asana_update_complete", task_gid, duration_ms=asana_ms)
    except Exception as e:
        _log_step("asana_update_failed", task_gid, success=False, detail=str(e))
        return JSONResponse(status_code=500, content={"error": f"Asana update failed: {e}"})

    total_ms = int((time.monotonic() - t0) * 1000)
    _log_step("analysis_complete", task_gid,
              duration_ms=total_ms,
              detail=f"recommendation={payload['recommendation']}, risk_score={payload['risk_score']}")

    return JSONResponse(content={
        "status": "complete",
        "task_gid": task_gid,
        "recommendation": payload["recommendation"],
        "risk_score": payload["risk_score"],
        "duration_ms": total_ms,
    })


@app.get("/health")
async def health():
    return {"status": "ok"}
