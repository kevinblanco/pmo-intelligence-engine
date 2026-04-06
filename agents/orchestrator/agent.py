"""
PMO Orchestrator Agent — ADK agent that synthesizes specialist agent outputs.
Used to generate the final formatted Asana comment.
"""

import os

from google.adk.agents import LlmAgent

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

SYSTEM_INSTRUCTION = """You are the PMO Intelligence Orchestrator. You receive the outputs of four specialist agents and synthesize them into a final enrichment payload for an Asana task.

Given the four JSON objects from: bigquery_analyst, risk_scorer, resource_advisor, and asana_context, produce a final summary comment for the Asana task. The comment should:
- Start with the AI Recommendation (bold)
- Show the risk score and factors
- Show resource availability
- Show live workspace context (from Asana MCP)
- List the top 3 risk factors from historical data
- End with a confidence statement

Format for Asana rich text (markdown-like, with ** for bold)."""


def create_agent():
    return LlmAgent(
        name="pmo_orchestrator",
        model=GEMINI_MODEL,
        instruction=SYSTEM_INSTRUCTION,
        tools=[],
    )
