"""
PMO Intelligence Engine — BigQuery Seed Data
Generates synthetic but realistic PMO project history for demo purposes.

Usage:
  pip install google-cloud-bigquery
  python bigquery/seed_data.py

Requirements:
  - Application Default Credentials: gcloud auth application-default login
  - GCP_PROJECT_ID environment variable set
"""

import os
import random
import uuid
from datetime import datetime

import google.auth
from google.cloud import bigquery
from google.cloud.exceptions import Conflict

DATASET_ID = os.getenv("BIGQUERY_DATASET", "pmo_intelligence")
PROJECT_ID = os.getenv("GCP_PROJECT_ID")

if not PROJECT_ID:
    raise EnvironmentError("GCP_PROJECT_ID environment variable is not set.")

random.seed(42)  # Reproducible results for demo reliability


# ─── BigQuery client ──────────────────────────────────────────────────────────

credentials, project = google.auth.default()
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)


# ─── Dataset ──────────────────────────────────────────────────────────────────

def ensure_dataset():
    dataset_ref = bigquery.Dataset(f"{PROJECT_ID}.{DATASET_ID}")
    dataset_ref.location = "US"
    try:
        client.create_dataset(dataset_ref)
        print(f"  ✓ Created dataset: {DATASET_ID}")
    except Conflict:
        print(f"  ↷ Dataset already exists: {DATASET_ID}")


# ─── Table schemas ────────────────────────────────────────────────────────────

HISTORICAL_SCHEMA = [
    bigquery.SchemaField("project_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("project_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("project_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("requestor_team", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("budget_requested", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("budget_actual", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("timeline_weeks_planned", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("timeline_weeks_actual", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("priority", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("outcome", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("year", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("quarter", "STRING", mode="REQUIRED"),
]

RESOURCE_SCHEMA = [
    bigquery.SchemaField("team_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("capacity_slots", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("allocated_slots", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("quarter", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("year", "INT64", mode="REQUIRED"),
]

OKR_SCHEMA = [
    bigquery.SchemaField("okr_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("okr_description", "STRING", mode="REQUIRED"),
    bigquery.SchemaField(
        "aligned_project_types", "STRING", mode="REPEATED"
    ),
    bigquery.SchemaField("quarter", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("year", "INT64", mode="REQUIRED"),
]


def ensure_table(table_id, schema):
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{table_id}"
    table = bigquery.Table(table_ref, schema=schema)
    try:
        client.create_table(table)
        print(f"  ✓ Created table: {table_id}")
    except Conflict:
        print(f"  ↷ Table already exists: {table_id}")


# ─── Seed: historical_projects ────────────────────────────────────────────────

PROJECT_TYPES = {
    "infrastructure": 0.30,
    "product_launch": 0.25,
    "digital_transformation": 0.20,
    "compliance": 0.15,
    "cost_reduction": 0.10,
}

TEAMS = {
    "engineering": 0.35,
    "marketing": 0.20,
    "operations": 0.20,
    "finance": 0.15,
    "hr": 0.10,
}

PRIORITIES = ["high", "medium", "low"]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]
YEARS = [2022, 2023, 2024]

# Budget ranges (USD) by project type
BUDGET_RANGES = {
    "infrastructure": (200_000, 3_000_000),
    "product_launch": (100_000, 1_500_000),
    "digital_transformation": (300_000, 2_500_000),
    "compliance": (50_000, 500_000),
    "cost_reduction": (50_000, 400_000),
}

PROJECT_NAME_TEMPLATES = {
    "infrastructure": [
        "Cloud Infrastructure Modernization",
        "Data Center Migration",
        "Network Security Upgrade",
        "Kubernetes Platform Rollout",
        "ML Platform Migration",
        "CI/CD Pipeline Overhaul",
        "Observability Stack Implementation",
        "Disaster Recovery Hardening",
        "Edge Computing Deployment",
        "Data Warehouse Consolidation",
    ],
    "product_launch": [
        "Mobile App v3 Launch",
        "Enterprise Dashboard Release",
        "API Gateway Productization",
        "Self-Serve Onboarding Flow",
        "Reporting Suite Launch",
        "SSO Integration Release",
        "Marketplace Feature Launch",
        "Webhook Platform GA",
        "AI Recommendations Feature",
        "Developer Portal Launch",
    ],
    "digital_transformation": [
        "ERP System Migration",
        "Customer 360 Platform",
        "Workflow Automation Initiative",
        "Digital Customer Experience Overhaul",
        "RPA Implementation",
        "Data-Driven Decision Platform",
        "Omnichannel Integration",
        "Smart Procurement System",
        "Intelligent Document Processing",
        "Digital Twin Deployment",
    ],
    "compliance": [
        "SOC2 Type II Certification",
        "GDPR Remediation Program",
        "ISO 27001 Implementation",
        "PCI DSS Compliance Uplift",
        "HIPAA Gap Closure",
        "Data Residency Enforcement",
        "Audit Trail System",
        "Privacy Policy Enforcement Engine",
    ],
    "cost_reduction": [
        "Cloud Cost Optimization",
        "SaaS Rationalization",
        "Vendor Consolidation Program",
        "Infrastructure Right-Sizing",
        "License Audit and Reduction",
        "Automated Cost Tagging",
    ],
}


def weighted_choice(options_dict):
    items = list(options_dict.keys())
    weights = list(options_dict.values())
    return random.choices(items, weights=weights, k=1)[0]


def generate_historical_projects():
    rows = []
    name_counters = {pt: 0 for pt in PROJECT_TYPES}

    # First: seed the DEMO-CRITICAL records
    # infrastructure + budget > $500K → over_budget or delayed (at least 8 records)
    demo_critical = [
        {
            "project_type": "infrastructure",
            "requestor_team": "engineering",
            "budget_requested": random.uniform(600_000, 2_500_000),
            "outcome": random.choice(["over_budget", "over_budget", "delayed"]),
            "year": random.choice(YEARS),
            "quarter": random.choice(QUARTERS),
            "priority": "high",
        }
        for _ in range(10)  # 10 guaranteed records for demo reliability
    ]

    for dc in demo_critical:
        budget = dc["budget_requested"]
        overrun_multiplier = random.uniform(1.15, 1.45)
        budget_actual = budget * overrun_multiplier
        timeline_planned = random.randint(12, 24)
        timeline_actual = int(timeline_planned * random.uniform(1.10, 1.40))
        pt = dc["project_type"]
        names = PROJECT_NAME_TEMPLATES[pt]
        idx = name_counters[pt] % len(names)
        name_counters[pt] += 1
        rows.append({
            "project_id": str(uuid.uuid4()),
            "project_name": f"{names[idx]} ({dc['year']} {dc['quarter']})",
            "project_type": pt,
            "requestor_team": dc["requestor_team"],
            "budget_requested": round(budget, 2),
            "budget_actual": round(budget_actual, 2),
            "timeline_weeks_planned": timeline_planned,
            "timeline_weeks_actual": timeline_actual,
            "priority": dc["priority"],
            "outcome": dc["outcome"],
            "year": dc["year"],
            "quarter": dc["quarter"],
        })

    # Fill remaining 140 rows with realistic distribution
    while len(rows) < 150:
        pt = weighted_choice(PROJECT_TYPES)
        team = weighted_choice(TEAMS)
        year = random.choice(YEARS)
        quarter = random.choice(QUARTERS)
        priority = random.choices(PRIORITIES, weights=[0.30, 0.50, 0.20])[0]

        budget_min, budget_max = BUDGET_RANGES[pt]
        budget = random.uniform(budget_min, budget_max)

        # Outcome distribution: 35% on_time, 30% delayed, 25% over_budget, 10% cancelled
        outcome = random.choices(
            ["on_time", "delayed", "over_budget", "cancelled"],
            weights=[0.35, 0.30, 0.25, 0.10],
        )[0]

        if outcome == "on_time":
            budget_actual = budget * random.uniform(0.90, 1.05)
            timeline_planned = random.randint(4, 26)
            timeline_actual = int(timeline_planned * random.uniform(0.95, 1.05))
        elif outcome == "delayed":
            budget_actual = budget * random.uniform(0.95, 1.15)
            timeline_planned = random.randint(6, 24)
            timeline_actual = int(timeline_planned * random.uniform(1.15, 1.40))
        elif outcome == "over_budget":
            budget_actual = budget * random.uniform(1.20, 1.60)
            timeline_planned = random.randint(8, 26)
            timeline_actual = int(timeline_planned * random.uniform(1.00, 1.25))
        else:  # cancelled
            budget_actual = budget * random.uniform(0.30, 0.70)
            timeline_planned = random.randint(10, 30)
            timeline_actual = int(timeline_planned * random.uniform(0.20, 0.60))

        names = PROJECT_NAME_TEMPLATES[pt]
        idx = name_counters[pt] % len(names)
        name_counters[pt] += 1

        rows.append({
            "project_id": str(uuid.uuid4()),
            "project_name": f"{names[idx]} ({year} {quarter})",
            "project_type": pt,
            "requestor_team": team,
            "budget_requested": round(budget, 2),
            "budget_actual": round(budget_actual, 2),
            "timeline_weeks_planned": timeline_planned,
            "timeline_weeks_actual": timeline_actual,
            "priority": priority,
            "outcome": outcome,
            "year": year,
            "quarter": quarter,
        })

    return rows


# ─── Seed: resource_allocations ───────────────────────────────────────────────

TEAM_CONFIGS = {
    "team_alpha":   {"capacity": 6, "label": "Engineering",  "base_alloc": (5, 6)},
    "team_beta":    {"capacity": 4, "label": "Marketing",    "base_alloc": (2, 3)},
    "team_gamma":   {"capacity": 8, "label": "Operations",   "base_alloc": (7, 8)},
    "team_delta":   {"capacity": 5, "label": "Finance",      "base_alloc": (3, 4)},
    "team_epsilon": {"capacity": 4, "label": "HR",           "base_alloc": (2, 3)},
}

RESOURCE_QUARTERS = [
    (2023, "Q1"), (2023, "Q2"), (2023, "Q3"), (2023, "Q4"),
    (2024, "Q1"), (2024, "Q2"), (2024, "Q3"), (2024, "Q4"),
    (2025, "Q1"), (2025, "Q2"),
]


def generate_resource_allocations():
    rows = []
    for year, quarter in RESOURCE_QUARTERS:
        for team_name, cfg in TEAM_CONFIGS.items():
            # Q2 2025: Engineering (team_alpha) locked at 5/6 = 83%
            if year == 2025 and quarter == "Q2" and team_name == "team_alpha":
                allocated = 5
            else:
                lo, hi = cfg["base_alloc"]
                allocated = random.randint(lo, hi)

            rows.append({
                "team_name": team_name,
                "capacity_slots": cfg["capacity"],
                "allocated_slots": allocated,
                "quarter": quarter,
                "year": year,
            })
    return rows


# ─── Seed: company_okrs ───────────────────────────────────────────────────────

def generate_company_okrs():
    return [
        # Q1 2025
        {
            "okr_id": "okr-2025-q1-001",
            "okr_description": "Accelerate cloud infrastructure modernization to reduce ops overhead by 30%",
            "aligned_project_types": ["infrastructure", "digital_transformation"],
            "quarter": "Q1",
            "year": 2025,
        },
        {
            "okr_id": "okr-2025-q1-002",
            "okr_description": "Expand revenue through three new product lines in H1",
            "aligned_project_types": ["product_launch"],
            "quarter": "Q1",
            "year": 2025,
        },
        {
            "okr_id": "okr-2025-q1-003",
            "okr_description": "Achieve SOC2 Type II certification by end of Q2",
            "aligned_project_types": ["compliance"],
            "quarter": "Q1",
            "year": 2025,
        },
        {
            "okr_id": "okr-2025-q1-004",
            "okr_description": "Reduce SaaS and cloud spend by 15% through consolidation",
            "aligned_project_types": ["cost_reduction"],
            "quarter": "Q1",
            "year": 2025,
        },
        # Q2 2025 — DEMO CRITICAL: infrastructure aligns here for "High" strategic fit
        {
            "okr_id": "okr-2025-q2-001",
            "okr_description": "Complete ML and data platform migration to managed cloud services",
            "aligned_project_types": ["infrastructure", "digital_transformation"],
            "quarter": "Q2",
            "year": 2025,
        },
        {
            "okr_id": "okr-2025-q2-002",
            "okr_description": "Launch developer platform to accelerate internal tooling velocity",
            "aligned_project_types": ["product_launch", "infrastructure"],
            "quarter": "Q2",
            "year": 2025,
        },
        {
            "okr_id": "okr-2025-q2-003",
            "okr_description": "Complete GDPR and data residency remediation across all products",
            "aligned_project_types": ["compliance"],
            "quarter": "Q2",
            "year": 2025,
        },
        {
            "okr_id": "okr-2025-q2-004",
            "okr_description": "Automate 40% of manual finance and HR workflows",
            "aligned_project_types": ["digital_transformation", "cost_reduction"],
            "quarter": "Q2",
            "year": 2025,
        },
        # Q3 2025
        {
            "okr_id": "okr-2025-q3-001",
            "okr_description": "Scale platform to support 10x traffic growth by end of year",
            "aligned_project_types": ["infrastructure"],
            "quarter": "Q3",
            "year": 2025,
        },
        {
            "okr_id": "okr-2025-q3-002",
            "okr_description": "Launch AI-powered features across core product surfaces",
            "aligned_project_types": ["product_launch", "digital_transformation"],
            "quarter": "Q3",
            "year": 2025,
        },
        # Q4 2025
        {
            "okr_id": "okr-2025-q4-001",
            "okr_description": "Achieve ISO 27001 certification before end of fiscal year",
            "aligned_project_types": ["compliance"],
            "quarter": "Q4",
            "year": 2025,
        },
        {
            "okr_id": "okr-2025-q4-002",
            "okr_description": "Consolidate vendor ecosystem from 120 to under 80 tools",
            "aligned_project_types": ["cost_reduction", "digital_transformation"],
            "quarter": "Q4",
            "year": 2025,
        },
    ]


# ─── Insert helpers ───────────────────────────────────────────────────────────

def insert_rows(table_id, rows):
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{table_id}"
    errors = client.insert_rows_json(table_ref, rows)
    if errors:
        raise RuntimeError(f"BigQuery insert errors for {table_id}: {errors}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("PMO Intelligence Engine — BigQuery Seed Data")
    print("=" * 50)

    ensure_dataset()

    print("\nCreating tables...")
    ensure_table("historical_projects", HISTORICAL_SCHEMA)
    ensure_table("resource_allocations", RESOURCE_SCHEMA)
    ensure_table("company_okrs", OKR_SCHEMA)

    print("\nInserting data...")

    projects = generate_historical_projects()
    insert_rows("historical_projects", projects)
    print(f"  ✓ Inserted {len(projects)} historical projects")

    resources = generate_resource_allocations()
    insert_rows("resource_allocations", resources)
    print(f"  ✓ Inserted {len(resources)} resource allocation records")

    okrs = generate_company_okrs()
    insert_rows("company_okrs", okrs)
    print(f"  ✓ Inserted {len(okrs)} company OKRs")

    print("\n" + "=" * 50)
    print("Seed data complete.")
    print("\nDemo-critical verification:")
    infra_high_budget = [
        p for p in projects
        if p["project_type"] == "infrastructure"
        and p["budget_requested"] > 500_000
        and p["outcome"] in ("over_budget", "delayed")
    ]
    print(f"  Infrastructure + >$500K + over_budget/delayed: {len(infra_high_budget)} records")
    print("  (Need ≥8 for reliable 'Flag for Review' demo result)")
    if len(infra_high_budget) < 8:
        print("  ⚠ WARNING: fewer than 8 records — demo result may not be reliable")
    else:
        print("  ✓ Demo-critical threshold met")


if __name__ == "__main__":
    main()
