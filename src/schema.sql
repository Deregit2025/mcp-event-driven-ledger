-- =============================================================================
-- APEX LEDGER — PostgreSQL Schema
-- =============================================================================
-- Run once against your database:
--   psql -U ledger -d apex_ledger -f src/schema.sql
--
-- Idempotent — safe to re-run (IF NOT EXISTS everywhere).
-- =============================================================================

-- ── EVENTS ───────────────────────────────────────────────────────────────────
-- The append-only event log. Core of the event store.
-- Every agent action, every compliance check, every decision is one row here.
-- Rows are NEVER updated or deleted.

CREATE TABLE IF NOT EXISTS events (
    -- Identity
    event_id         UUID            NOT NULL DEFAULT gen_random_uuid(),
    stream_id        TEXT            NOT NULL,
    stream_position  INTEGER         NOT NULL,   -- position within stream (0-based)
    global_position  BIGSERIAL,                  -- global ordering across all streams

    -- Event data
    event_type       TEXT            NOT NULL,
    event_version    INTEGER         NOT NULL DEFAULT 1,
    payload          JSONB           NOT NULL DEFAULT '{}',
    metadata         JSONB           NOT NULL DEFAULT '{}',

    -- Timestamps
    recorded_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Constraints
    PRIMARY KEY (event_id),
    UNIQUE (stream_id, stream_position)   -- OCC enforcement at DB level
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_events_stream_id
    ON events (stream_id, stream_position ASC);

CREATE INDEX IF NOT EXISTS idx_events_global_position
    ON events (global_position ASC);

CREATE INDEX IF NOT EXISTS idx_events_event_type
    ON events (event_type);

CREATE INDEX IF NOT EXISTS idx_events_recorded_at
    ON events (recorded_at DESC);

-- ── EVENT STREAMS ─────────────────────────────────────────────────────────────
-- One row per stream. Tracks current version for OCC.
-- Locked with SELECT FOR UPDATE during appends.

CREATE TABLE IF NOT EXISTS event_streams (
    stream_id        TEXT            NOT NULL,
    aggregate_type   TEXT            NOT NULL,   -- e.g. "loan", "agent", "compliance"
    current_version  INTEGER         NOT NULL DEFAULT -1,
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    PRIMARY KEY (stream_id)
);

CREATE INDEX IF NOT EXISTS idx_event_streams_aggregate_type
    ON event_streams (aggregate_type);

-- ── OUTBOX ────────────────────────────────────────────────────────────────────
-- Transactional outbox for guaranteed event delivery.
-- Written in the same transaction as events — never lost.
-- A background worker reads this and publishes to external systems.

CREATE TABLE IF NOT EXISTS outbox (
    id               BIGSERIAL       PRIMARY KEY,
    stream_id        TEXT            NOT NULL,
    stream_position  INTEGER         NOT NULL,
    event_type       TEXT            NOT NULL,
    payload          JSONB           NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    processed_at     TIMESTAMPTZ     NULL,
    published_at     TIMESTAMPTZ     NULL,
    delivery_attempts INTEGER        NOT NULL DEFAULT 0,
    last_error       TEXT            NULL,

    UNIQUE (stream_id, stream_position),
    CONSTRAINT fk_outbox_events
        FOREIGN KEY (stream_id, stream_position)
        REFERENCES events (stream_id, stream_position)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_outbox_unprocessed
    ON outbox (created_at ASC)
    WHERE processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON outbox (created_at ASC)
    WHERE published_at IS NULL AND processed_at IS NOT NULL;

-- ── PROJECTION CHECKPOINTS ────────────────────────────────────────────────────
-- One row per projection. Stores the last global_position processed.
-- The ProjectionDaemon reads this to resume after restart.

CREATE TABLE IF NOT EXISTS projection_checkpoints (
    projection_name  TEXT            NOT NULL,
    last_position    BIGINT          NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    PRIMARY KEY (projection_name)
);

-- ── APPLICATION SUMMARY PROJECTION ───────────────────────────────────────────
-- One row per loan application. Current state for fast queries.
-- Rebuilt by the ProjectionDaemon from the event stream.

CREATE TABLE IF NOT EXISTS application_summary (
    application_id       TEXT            NOT NULL,
    state                TEXT            NOT NULL DEFAULT 'SUBMITTED',
    applicant_id         TEXT,
    requested_amount_usd NUMERIC(15,2),
    loan_purpose         TEXT,
    submission_channel   TEXT,

    -- Analysis results
    credit_risk_tier     TEXT,
    credit_confidence    FLOAT,
    fraud_score          FLOAT,
    compliance_verdict   TEXT,

    -- Decision
    final_decision       TEXT,
    approved_amount_usd  NUMERIC(15,2),

    -- Timestamps
    submitted_at         TIMESTAMPTZ,
    decided_at           TIMESTAMPTZ,
    last_event_type      TEXT,
    last_event_at        TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    PRIMARY KEY (application_id)
);

CREATE INDEX IF NOT EXISTS idx_application_summary_state
    ON application_summary (state);

CREATE INDEX IF NOT EXISTS idx_application_summary_applicant
    ON application_summary (applicant_id);

-- ── AGENT PERFORMANCE LEDGER PROJECTION ──────────────────────────────────────
-- Metrics per agent type per model version.
-- Used to detect model drift and performance degradation.

CREATE TABLE IF NOT EXISTS agent_performance_ledger (
    agent_type           TEXT            NOT NULL,
    model_version        TEXT            NOT NULL,

    -- Counters
    total_sessions       INTEGER         NOT NULL DEFAULT 0,
    successful_sessions  INTEGER         NOT NULL DEFAULT 0,
    failed_sessions      INTEGER         NOT NULL DEFAULT 0,

    -- Credit analysis metrics
    approve_count        INTEGER         NOT NULL DEFAULT 0,
    decline_count        INTEGER         NOT NULL DEFAULT 0,
    refer_count          INTEGER         NOT NULL DEFAULT 0,
    avg_confidence       FLOAT,

    -- Cost metrics
    total_llm_cost_usd   FLOAT           NOT NULL DEFAULT 0.0,
    total_tokens_used    BIGINT          NOT NULL DEFAULT 0,
    avg_cost_per_session FLOAT,

    -- Timing
    avg_duration_ms      FLOAT,
    last_session_at      TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    PRIMARY KEY (agent_type, model_version)
);

-- ── COMPLIANCE AUDIT VIEW PROJECTION ─────────────────────────────────────────
-- Current compliance status per application.
-- Supports temporal queries via snapshots.

CREATE TABLE IF NOT EXISTS compliance_audit_view (
    application_id       TEXT            NOT NULL,
    regulation_set       TEXT,

    -- Rule results
    rules_evaluated      INTEGER         NOT NULL DEFAULT 0,
    rules_passed         INTEGER         NOT NULL DEFAULT 0,
    rules_failed         INTEGER         NOT NULL DEFAULT 0,
    rules_noted          INTEGER         NOT NULL DEFAULT 0,
    has_hard_block       BOOLEAN         NOT NULL DEFAULT FALSE,
    overall_verdict      TEXT,
    block_rule_id        TEXT,

    -- Timestamps
    initiated_at         TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    last_event_at        TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    PRIMARY KEY (application_id)
);

-- Snapshots for temporal queries: "what was the compliance state at time T?"
CREATE TABLE IF NOT EXISTS compliance_audit_snapshots (
    id                   BIGSERIAL       PRIMARY KEY,
    application_id       TEXT            NOT NULL,
    snapshot_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    global_position      BIGINT          NOT NULL,
    state                JSONB           NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_compliance_snapshots_app_time
    ON compliance_audit_snapshots (application_id, snapshot_at DESC);

-- ── APPLICANT REGISTRY (read-only external schema) ───────────────────────────
-- Created by datagen/generate_all.py — never written by the event store.
-- Agents query this; they never write to it.

CREATE SCHEMA IF NOT EXISTS applicant_registry;

CREATE TABLE IF NOT EXISTS applicant_registry.companies (
    company_id           TEXT            NOT NULL,
    name                 TEXT            NOT NULL,
    industry             TEXT,
    naics                TEXT,
    jurisdiction         TEXT,
    legal_type           TEXT,
    founded_year         INTEGER,
    employee_count       INTEGER,
    risk_segment         TEXT,
    trajectory           TEXT,
    submission_channel   TEXT,
    ip_region            TEXT,
    PRIMARY KEY (company_id)
);

CREATE TABLE IF NOT EXISTS applicant_registry.financial_history (
    company_id           TEXT            NOT NULL,
    fiscal_year          INTEGER         NOT NULL,
    total_revenue        NUMERIC(15,2),
    gross_profit         NUMERIC(15,2),
    operating_income     NUMERIC(15,2),
    ebitda               NUMERIC(15,2),
    net_income           NUMERIC(15,2),
    total_assets         NUMERIC(15,2),
    total_liabilities    NUMERIC(15,2),
    total_equity         NUMERIC(15,2),
    long_term_debt       NUMERIC(15,2),
    cash_and_equivalents NUMERIC(15,2),
    current_assets       NUMERIC(15,2),
    current_liabilities  NUMERIC(15,2),
    accounts_receivable  NUMERIC(15,2),
    inventory            NUMERIC(15,2),
    debt_to_equity       FLOAT,
    current_ratio        FLOAT,
    debt_to_ebitda       FLOAT,
    interest_coverage_ratio FLOAT,
    gross_margin         FLOAT,
    ebitda_margin        FLOAT,
    net_margin           FLOAT,
    PRIMARY KEY (company_id, fiscal_year)
);

CREATE TABLE IF NOT EXISTS applicant_registry.compliance_flags (
    id                   BIGSERIAL       PRIMARY KEY,
    company_id           TEXT            NOT NULL,
    flag_type            TEXT            NOT NULL,
    severity             TEXT            NOT NULL,
    is_active            BOOLEAN         NOT NULL DEFAULT TRUE,
    added_date           DATE,
    note                 TEXT
);

CREATE INDEX IF NOT EXISTS idx_compliance_flags_company
    ON applicant_registry.compliance_flags (company_id, is_active);

CREATE TABLE IF NOT EXISTS applicant_registry.loan_relationships (
    id                   BIGSERIAL       PRIMARY KEY,
    company_id           TEXT            NOT NULL,
    loan_id              TEXT,
    origination_date     DATE,
    maturity_date        DATE,
    original_amount      NUMERIC(15,2),
    outstanding_balance  NUMERIC(15,2),
    loan_type            TEXT,
    status               TEXT,
    default_occurred     BOOLEAN         NOT NULL DEFAULT FALSE,
    default_date         DATE
);

CREATE INDEX IF NOT EXISTS idx_loan_relationships_company
    ON applicant_registry.loan_relationships (company_id);