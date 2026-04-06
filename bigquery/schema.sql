-- PMO Intelligence Engine — BigQuery Schema
-- Dataset: pmo_intelligence
-- Run: python bigquery/seed_data.py (creates dataset, tables, and inserts data)

-- ─── Table 1: Historical project outcomes ────────────────────────────────────
-- 150 rows covering 2022–2024
-- Used by: BigQuery Analyst Agent, Risk Scorer Agent

CREATE TABLE IF NOT EXISTS pmo_intelligence.historical_projects (
  project_id               STRING    NOT NULL,
  project_name             STRING    NOT NULL,
  project_type             STRING    NOT NULL,  -- product_launch | infrastructure | compliance |
                                                 -- digital_transformation | cost_reduction
  requestor_team           STRING    NOT NULL,  -- engineering | marketing | operations | finance | hr
  budget_requested         FLOAT64   NOT NULL,  -- USD
  budget_actual            FLOAT64   NOT NULL,  -- USD
  timeline_weeks_planned   INT64     NOT NULL,
  timeline_weeks_actual    INT64     NOT NULL,
  priority                 STRING    NOT NULL,  -- high | medium | low
  outcome                  STRING    NOT NULL,  -- on_time | delayed | cancelled | over_budget
  year                     INT64     NOT NULL,
  quarter                  STRING    NOT NULL   -- Q1 | Q2 | Q3 | Q4
);

-- ─── Table 2: Team resource capacity ─────────────────────────────────────────
-- 40 rows: 5 teams × 8 quarters (2023 Q1 – 2024 Q4 + 2025 Q1/Q2)
-- Used by: Resource Advisor Agent

CREATE TABLE IF NOT EXISTS pmo_intelligence.resource_allocations (
  team_name        STRING  NOT NULL,
  capacity_slots   INT64   NOT NULL,
  allocated_slots  INT64   NOT NULL,
  quarter          STRING  NOT NULL,  -- Q1 | Q2 | Q3 | Q4
  year             INT64   NOT NULL
);

-- ─── Table 3: Company OKRs ────────────────────────────────────────────────────
-- 12 rows: 4 OKRs per quarter for 2025
-- Used by: Resource Advisor Agent (OKR alignment check)

CREATE TABLE IF NOT EXISTS pmo_intelligence.company_okrs (
  okr_id                  STRING         NOT NULL,
  okr_description         STRING         NOT NULL,
  aligned_project_types   ARRAY<STRING>  NOT NULL,
  quarter                 STRING         NOT NULL,
  year                    INT64          NOT NULL
);
