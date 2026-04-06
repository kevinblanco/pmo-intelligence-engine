"""
PMO Intelligence Engine — Architecture Diagram
Generated with: pip install diagrams
Requires: brew install graphviz (macOS) or apt-get install graphviz (Linux)
Run with: python diagrams/architecture.py
Output: pmo_intelligence_engine.png (run from repo root)

Prerequisites:
  - diagrams/asana_icon.png must exist (committed to the repo)
  - Download once with:
      curl -L -A "Mozilla/5.0" \
        "https://upload.wikimedia.org/wikipedia/commons/3/3b/Asana_logo.png" \
        -o diagrams/asana_icon.png

Nodes used:
  diagrams.gcp.compute.Run              → Cloud Run services
  diagrams.gcp.analytics.BigQuery       → BigQuery data warehouse
  diagrams.gcp.ml.VertexAI              → Vertex AI / Gemini models
  diagrams.gcp.security.SecretManager   → Secret Manager
  diagrams.gcp.operations.Logging       → Cloud Logging
  diagrams.gcp.devtools.ContainerRegistry → Artifact Registry
  diagrams.custom.Custom                → Asana (custom icon, no built-in node)
"""

import os
from diagrams import Cluster, Diagram, Edge
from diagrams.gcp.compute import Run
from diagrams.gcp.analytics import BigQuery
from diagrams.gcp.ml import VertexAI
from diagrams.gcp.security import SecretManager
from diagrams.gcp.operations import Logging
from diagrams.gcp.devtools import ContainerRegistry
from diagrams.custom import Custom

asana_icon = os.path.join(os.path.dirname(__file__), "asana_icon.png")

graph_attr = {
    "fontsize": "22",
    "bgcolor": "white",
    "pad": "1.5",
    "splines": "ortho",
    "nodesep": "0.9",
    "ranksep": "2.2",
    "size": "44,24",
    "ratio": "fill",
    "rankdir": "LR",
    "dpi": "300",
}

with Diagram(
    "PMO Intelligence Engine",
    filename="pmo_intelligence_engine",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):

    # ── FAR LEFT: Asana Intake ───────────────────────────────────────
    # Defining intake first pins it to the left rank in LR layout
    with Cluster("Asana — Intake"):
        asana_form    = Custom("Intake Form", asana_icon)
        asana_project = Custom("New Project Requests", asana_icon)

    # ── MIDDLE: Google Cloud Platform ────────────────────────────────
    with Cluster("Google Cloud Platform"):

        with Cluster("Shared Services"):
            secrets  = SecretManager("Secret Manager\nPAT · MCP tokens · Webhook")
            logs     = Logging("Cloud Logging\nObservability")
            vertex   = VertexAI("Vertex AI\nGemini 2.0 Flash")
            registry = ContainerRegistry("Artifact Registry")

        with Cluster("Agent Layer — Cloud Run"):

            with Cluster("Ingress"):
                webhook_receiver = Run("Webhook Receiver\nHandshake · HMAC · Heartbeat\n--min-instances 1")

            with Cluster("Orchestration"):
                orchestrator = Run("Orchestrator\nADK · A2A Client\nAssembles payload")

            with Cluster("Specialist Agents"):
                asana_context    = Run("Asana Context\nADK · Asana MCP\nLive Work Graph")
                resource_advisor = Run("Resource Advisor\nADK · BigQuery MCP\nTeam capacity")
                risk_scorer      = Run("Risk Scorer\nADK · Gemini\nRisk score 1–10")
                bq_analyst       = Run("BQ Analyst\nADK · BigQuery MCP\nHistorical patterns")

        with Cluster("Data Layer"):
            with Cluster("Google-Managed MCP"):
                bq_mcp = BigQuery("BigQuery MCP Server\n(Google-managed)")
            bq = BigQuery("BigQuery\npmo_intelligence\nhistorical_projects\nresource_allocations\ncompany_okrs")

    # ── FAR RIGHT: Asana Output ──────────────────────────────────────
    # Defining output last pins it to the right rank in LR layout
    with Cluster("Asana — Output"):
        asana_mcp_srv = Custom("Asana MCP Server\nmcp.asana.com/v2", asana_icon)
        asana_task    = Custom("Enriched Task", asana_icon)

    # ── Edges ─────────────────────────────────────────────────────────

    # Human intake flow (left → middle)
    asana_form    >> Edge(label="submit")                                 >> asana_project
    asana_project >> Edge(label="task.added webhook", color="darkorange") >> webhook_receiver

    # Webhook → orchestrator
    webhook_receiver >> Edge(label="POST /analyze\n(BackgroundTask)", color="darkorange") >> orchestrator

    # A2A: orchestrator → specialist agents
    orchestrator >> Edge(label="A2A", color="royalblue", style="dashed") >> asana_context
    orchestrator >> Edge(label="A2A", color="royalblue", style="dashed") >> resource_advisor
    orchestrator >> Edge(label="A2A", color="royalblue", style="dashed") >> risk_scorer
    orchestrator >> Edge(label="A2A", color="royalblue", style="dashed") >> bq_analyst

    # MCP: Google-managed (middle → data layer)
    bq_analyst       >> Edge(label="MCP (Google)", color="darkgreen", style="dotted") >> bq_mcp
    resource_advisor >> Edge(label="MCP (Google)", color="darkgreen", style="dotted") >> bq_mcp
    bq_mcp           >> Edge(color="darkgreen", style="dotted")                        >> bq

    # MCP: Asana-managed (middle → far right)
    asana_context >> Edge(label="MCP (Asana)", color="purple", style="dotted") >> asana_mcp_srv

    # REST write-back (middle → far right)
    orchestrator >> Edge(label="REST API\nupdate task", color="firebrick") >> asana_task

    # Shared infra
    webhook_receiver >> Edge(style="dotted", color="gray") >> secrets
    asana_context    >> Edge(style="dotted", color="gray") >> secrets

    # Logging
    for svc in [orchestrator, bq_analyst, risk_scorer, resource_advisor, asana_context]:
        svc >> Edge(style="dotted", color="gray") >> logs

    # Vertex AI powers all agents
    for agent in [orchestrator, bq_analyst, risk_scorer, resource_advisor, asana_context]:
        vertex >> Edge(style="dotted", color="lightgray") >> agent
