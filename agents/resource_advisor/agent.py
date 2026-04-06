"""
Resource Advisor Agent — ADK agent with BigQueryToolset
Queries resource_allocations and company_okrs tables for team capacity and OKR alignment.
Returns structured JSON with resource signal and OKR alignment.
"""

import os

from google.adk.agents import LlmAgent
from google.adk.tools.bigquery import BigQueryToolset

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "pmo_intelligence")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

SYSTEM_INSTRUCTION = """You are a resource availability advisor for a PMO. Given a project request, query the resource_allocations table for the current quarter to find team capacity. Also query company_okrs to check if the project type aligns with current OKRs.

Current quarter: use the current date to determine Q1/Q2/Q3/Q4 of the current year. Use a WHERE clause to filter to the correct quarter and year.

The dataset is: pmo_intelligence
Tables: resource_allocations, company_okrs

Use get_table_info first to understand the schema, then execute_sql to query.

Return ONLY valid JSON:
{
  "requesting_team_capacity_slots": <int>,
  "requesting_team_allocated_slots": <int>,
  "requesting_team_utilization_pct": <float>,
  "requesting_team_available_slots": <int>,
  "alternative_teams": [
    {"team": "<name>", "available_slots": <int>, "utilization_pct": <float>}
  ],
  "resource_signal": "Available" | "Limited" | "Constrained",
  "okr_alignment": "Aligned" | "Partial" | "Not Aligned",
  "aligned_okr_description": "<string or null>",
  "resource_recommendation": "<1-2 sentence human-readable recommendation>"
}

resource_signal definitions:
- Available: >1 slot open for requesting team
- Limited: exactly 1 slot, or team at 80-99%
- Constrained: 0 slots / 100% utilized

Return only the JSON, no preamble."""


def create_agent():
    # BigQueryToolset uses Application Default Credentials to infer the project.
    # Do not pass project_id — the current ADK version does not accept it.
    bq_toolset = BigQueryToolset()
    return LlmAgent(
        name="resource_advisor",
        model=GEMINI_MODEL,
        instruction=SYSTEM_INSTRUCTION,
        tools=[bq_toolset],
    )
