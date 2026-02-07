-- Unified metrics and activity tracking schema for ASP/IP monitoring
-- SQLite database for cross-module activity aggregation

-- Provider activity log - tracks every human action across all modules
CREATE TABLE IF NOT EXISTS provider_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Provider information
    provider_id TEXT,              -- Badge ID or user identifier
    provider_name TEXT,            -- Display name
    provider_role TEXT,            -- pharmacist, physician, nurse, etc.

    -- Activity details
    activity_type TEXT NOT NULL,   -- review, acknowledgment, intervention, education
    module TEXT NOT NULL,          -- hai, asp_alerts, guideline_adherence, abx_indications
    entity_id TEXT,                -- ID of the record being acted upon
    entity_type TEXT,              -- alert, candidate, episode, etc.
    action_taken TEXT,             -- specific action (e.g., approved, escalated, therapy_changed)
    outcome TEXT,                  -- result of the action

    -- Patient/location context
    patient_mrn TEXT,
    location_code TEXT,            -- unit/ward code
    service TEXT,                  -- medical service

    -- Effort tracking
    duration_minutes INTEGER,      -- optional time spent

    -- Timestamps
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Additional context as JSON
    details TEXT                   -- JSON blob for module-specific data
);

CREATE INDEX IF NOT EXISTS idx_activity_provider ON provider_activity(provider_id);
CREATE INDEX IF NOT EXISTS idx_activity_module ON provider_activity(module);
CREATE INDEX IF NOT EXISTS idx_activity_type ON provider_activity(activity_type);
CREATE INDEX IF NOT EXISTS idx_activity_location ON provider_activity(location_code);
CREATE INDEX IF NOT EXISTS idx_activity_performed_at ON provider_activity(performed_at);
CREATE INDEX IF NOT EXISTS idx_activity_patient ON provider_activity(patient_mrn);

-- Intervention sessions - tracks education/outreach activities
CREATE TABLE IF NOT EXISTS intervention_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Session details
    session_type TEXT NOT NULL,    -- unit_rounding, service_education, individual_feedback, committee
    session_date DATE NOT NULL,

    -- Target of intervention
    target_type TEXT NOT NULL,     -- unit, service, provider, department
    target_id TEXT,                -- location code, service name, or provider ID
    target_name TEXT,              -- human-readable name

    -- Content
    topic TEXT,                    -- main topic discussed
    attendees TEXT,                -- JSON array of attendee names/roles
    notes TEXT,                    -- session notes

    -- Related alerts/issues that prompted this intervention
    related_alerts TEXT,           -- JSON array of alert IDs
    related_targets TEXT,          -- JSON array of intervention_target IDs

    -- Conducted by
    conducted_by TEXT,             -- provider who led the session

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_type ON intervention_sessions(session_type);
CREATE INDEX IF NOT EXISTS idx_session_date ON intervention_sessions(session_date);
CREATE INDEX IF NOT EXISTS idx_session_target ON intervention_sessions(target_type, target_id);

-- Daily metrics snapshot - aggregated metrics for trending
CREATE TABLE IF NOT EXISTS metrics_daily_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date DATE NOT NULL UNIQUE,

    -- Alert metrics
    alerts_created INTEGER DEFAULT 0,
    alerts_resolved INTEGER DEFAULT 0,
    alerts_acknowledged INTEGER DEFAULT 0,
    avg_time_to_ack_minutes REAL,
    avg_time_to_resolve_minutes REAL,

    -- HAI metrics
    hai_candidates_created INTEGER DEFAULT 0,
    hai_candidates_reviewed INTEGER DEFAULT 0,
    hai_confirmed INTEGER DEFAULT 0,
    hai_override_count INTEGER DEFAULT 0,

    -- Guideline adherence metrics
    bundle_episodes_active INTEGER DEFAULT 0,
    bundle_alerts_created INTEGER DEFAULT 0,
    bundle_adherence_rate REAL,

    -- ABX indication metrics
    indication_reviews INTEGER DEFAULT 0,
    appropriate_count INTEGER DEFAULT 0,
    inappropriate_count INTEGER DEFAULT 0,
    inappropriate_rate REAL,

    -- Drug-Bug mismatch metrics
    drug_bug_alerts_created INTEGER DEFAULT 0,
    drug_bug_alerts_resolved INTEGER DEFAULT 0,
    drug_bug_therapy_changed_count INTEGER DEFAULT 0,

    -- MDRO surveillance metrics
    mdro_cases_identified INTEGER DEFAULT 0,
    mdro_cases_reviewed INTEGER DEFAULT 0,
    mdro_confirmed INTEGER DEFAULT 0,

    -- Outbreak detection metrics
    outbreak_clusters_active INTEGER DEFAULT 0,
    outbreak_alerts_triggered INTEGER DEFAULT 0,

    -- Surgical prophylaxis metrics
    surgical_prophylaxis_cases INTEGER DEFAULT 0,
    surgical_prophylaxis_compliant INTEGER DEFAULT 0,
    surgical_prophylaxis_compliance_rate REAL,

    -- Human activity metrics
    total_reviews INTEGER DEFAULT 0,
    unique_reviewers INTEGER DEFAULT 0,
    total_interventions INTEGER DEFAULT 0,

    -- Breakdown by location (JSON)
    by_location TEXT,              -- JSON object with location-level metrics

    -- Breakdown by service (JSON)
    by_service TEXT,               -- JSON object with service-level metrics

    -- Created timestamp
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_snapshot_date ON metrics_daily_snapshot(snapshot_date);

-- Intervention targets - identifies units/services needing attention
CREATE TABLE IF NOT EXISTS intervention_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Target identification
    target_type TEXT NOT NULL,     -- unit, service, provider
    target_id TEXT NOT NULL,       -- location code, service name, or provider ID
    target_name TEXT,              -- human-readable name

    -- Issue details
    issue_type TEXT NOT NULL,      -- high_inappropriate_abx, low_bundle_adherence, etc.
    issue_description TEXT,        -- detailed description of the issue

    -- Priority scoring
    priority_score REAL,           -- calculated priority (higher = more urgent)
    priority_reason TEXT,          -- explanation of priority calculation

    -- Metric values
    baseline_value REAL,           -- value at time of identification
    target_value REAL,             -- goal value
    current_value REAL,            -- latest value

    -- Measurement details
    metric_name TEXT,              -- which metric is being tracked
    metric_unit TEXT,              -- percentage, rate, count, etc.

    -- Status workflow
    status TEXT NOT NULL DEFAULT 'identified',  -- identified, planned, in_progress, completed, dismissed

    -- Assignment
    assigned_to TEXT,              -- provider responsible for intervention

    -- Dates
    identified_date DATE NOT NULL,
    planned_date DATE,
    started_date DATE,
    completed_date DATE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(target_type, target_id, issue_type, identified_date)
);

CREATE INDEX IF NOT EXISTS idx_target_status ON intervention_targets(status);
CREATE INDEX IF NOT EXISTS idx_target_type ON intervention_targets(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_target_issue ON intervention_targets(issue_type);
CREATE INDEX IF NOT EXISTS idx_target_priority ON intervention_targets(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_target_identified ON intervention_targets(identified_date);

-- Intervention outcomes - pre/post comparison data
CREATE TABLE IF NOT EXISTS intervention_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Links to related records
    target_id INTEGER NOT NULL,    -- FK to intervention_targets
    session_id INTEGER,            -- FK to intervention_sessions (optional)

    -- Pre-intervention period
    pre_period_start DATE NOT NULL,
    pre_period_end DATE NOT NULL,
    pre_value REAL NOT NULL,
    pre_sample_size INTEGER,       -- number of observations in pre period

    -- Post-intervention period
    post_period_start DATE,
    post_period_end DATE,
    post_value REAL,
    post_sample_size INTEGER,

    -- Calculated outcomes
    absolute_change REAL,          -- post_value - pre_value
    percent_change REAL,           -- (post - pre) / pre * 100
    is_improvement INTEGER,        -- 1 if change is in desired direction

    -- Follow-up measurements
    day_30_value REAL,
    day_60_value REAL,
    day_90_value REAL,
    sustained_improvement INTEGER, -- 1 if improvement maintained at 90 days

    -- Statistical significance (optional)
    p_value REAL,
    confidence_interval TEXT,      -- JSON: {"lower": x, "upper": y}

    -- Notes
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (target_id) REFERENCES intervention_targets(id),
    FOREIGN KEY (session_id) REFERENCES intervention_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_outcome_target ON intervention_outcomes(target_id);
CREATE INDEX IF NOT EXISTS idx_outcome_session ON intervention_outcomes(session_id);
CREATE INDEX IF NOT EXISTS idx_outcome_improvement ON intervention_outcomes(is_improvement);
