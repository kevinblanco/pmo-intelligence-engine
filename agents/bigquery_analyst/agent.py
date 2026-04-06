"""
BigQuery Analyst Agent — ADK agent with BigQueryToolset
Queries historical_projects table for patterns similar to the incoming request.
Returns structured JSON analysis.
"""

import json
import os

from google.adk.agents import LlmAgent
from google.adk.tools.bigquery import BigQueryToolset

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "pmo_intelligence")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

SYSTEM_INSTRUCTION = """You are a data analyst for a PMO intelligence system. Given a new project request, query the historical_projects table in BigQuery to find similar past projects. Similar means: same project_type OR same requestor_team OR similar budget_range (within 50%). Use get_table_info first to understand the schema, then execute_sql to query.

Find up to 20 similar projects and analyze their outcomes.

Return ONLY valid JSON with this exact structure:
{
  "similar_projects_count": <int>,
  "avg_budget_overrun_pct": <float, 0 if no overruns>,
  "avg_timeline_overrun_pct": <float, 0 if no overruns>,
  "pct_over_budget": <float, percentage of similar projects that went over budget>,
  "pct_delayed": <float, percentage that were delayed>,
  "pct_cancelled": <float>,
  "most_common_outcome": "<string>",
  "top_risk_patterns": ["<pattern1>", "<pattern2>"],
  "sample_projects": [
    {"name": "<str>", "outcome": "<str>", "budget_overrun_pct": <float>}
  ]
}
Return only the JSON object, no preamble or explanation."""


def create_agent():
    # BigQueryToolset uses Application Default Credentials to infer the project.
    # Do not pass project_id — the current ADK version does not accept it.
    bq_toolset = BigQueryToolset()
    return LlmAgent(
        name="bigquery_analyst",
        model=GEMINI_MODEL,
        instruction=SYSTEM_INSTRUCTION,
        tools=[bq_toolset],
    )
