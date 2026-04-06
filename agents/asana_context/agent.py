"""
Asana Context Agent — ADK agent with Asana MCP server
Queries the live Asana Work Graph via Asana's MCP server to find active similar projects,
team task load, and potential duplicate work.
"""

import os

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StreamableHTTPConnectionParams

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
ASANA_MCP_URL = "https://mcp.asana.com/v2/mcp"

SYSTEM_INSTRUCTION = """You are an Asana workspace intelligence agent for a PMO. Given a new project request with a project_type and requestor_team, use the Asana MCP tools to find live organizational context.

1. Search for active, incomplete projects in the workspace that match the project_type (search by keyword in project name or description)
2. Find incomplete tasks assigned to or in projects owned by the requestor_team that are due in the current quarter
3. Check if any project name strongly suggests this work already exists or is already approved

Be concise and factual. If tools return errors or empty results, note that and return what you could find.

Return ONLY valid JSON:
{
  "active_similar_projects": [
    {"name": "<str>", "status": "<str>"}
  ],
  "team_current_task_load": <int, count of incomplete tasks found>,
  "potential_duplicate": true | false,
  "potential_duplicate_reason": "<string or null>",
  "live_context_summary": "<2-3 sentences describing current Asana state relevant to this request>"
}

Return only the JSON, no preamble. If the MCP server returns no results, return zeros and note 'No matching data found in current workspace.'"""


def create_agent(access_token: str):
    mcp_toolset = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=ASANA_MCP_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    )
    return LlmAgent(
        name="asana_context_advisor",
        model=GEMINI_MODEL,
        instruction=SYSTEM_INSTRUCTION,
        tools=[mcp_toolset],
    )
