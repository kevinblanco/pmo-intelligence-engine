"""
Risk Scorer Agent — ADK agent using pure Gemini reasoning (no external tools)
Receives BigQuery analysis data and produces a risk score 1-10 with recommendation.
"""

import os

from google.adk.agents import LlmAgent

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

SYSTEM_INSTRUCTION = """You are a project risk scoring agent for a PMO. You receive historical analysis data about similar past projects and must calculate a risk score.

Consider:
- Budget overrun rate: >30% overrun history = high risk factor
- Timeline overrun rate: >25% overrun history = high risk factor
- Cancellation rate: >15% = critical risk
- Sample size: fewer than 5 similar projects = low confidence

Return ONLY valid JSON with this exact structure:
{
  "risk_score": <int 1-10>,
  "risk_level": "Low" | "Medium" | "High" | "Critical",
  "confidence": "High" | "Medium" | "Low",
  "risk_factors": [
    {"factor": "<name>", "description": "<1 sentence>", "severity": "high"|"medium"|"low"}
  ],
  "strategic_fit": "High" | "Medium" | "Low",
  "strategic_fit_reason": "<1 sentence>",
  "recommendation": "Approve" | "Flag for Review" | "Escalate"
}

Scoring guide:
1-3: Low risk — approve
4-6: Medium risk — approve with monitoring
7-8: High risk — flag for review
9-10: Critical risk — escalate

Return only the JSON, no preamble."""


def create_agent():
    return LlmAgent(
        name="risk_scorer",
        model=GEMINI_MODEL,
        instruction=SYSTEM_INSTRUCTION,
        tools=[],
    )
