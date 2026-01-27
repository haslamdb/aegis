-- Guideline Adherence Bundle Monitoring Schema
-- Tracks bundle episodes, element compliance, and alerts

-- ============================================================================
-- BUNDLE EPISODES
-- ============================================================================
-- A bundle episode represents an active period of monitoring a patient for
-- compliance with a specific guideline bundle (e.g., sepsis, febrile infant)

CREATE TABLE IF NOT EXISTS bundle_episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Patient/encounter identification
    patient_id TEXT NOT NULL,
    patient_mrn TEXT,
    encounter_id TEXT NOT NULL,

    -- Bundle information
    bundle_id TEXT NOT NULL,
    bundle_name TEXT NOT NULL,

    -- Trigger information
    trigger_type TEXT NOT NULL,  -- 'diagnosis', 'order', 'lab', 'manual'
    trigger_code TEXT,           -- ICD-10, order code, LOINC, etc.
    trigger_description TEXT,
    trigger_time TIMESTAMP NOT NULL,

    -- Patient context at trigger time
    patient_age_days INTEGER,
    patient_age_months REAL,
    patient_weight_kg REAL,
    patient_unit TEXT,

    -- Episode status
    status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'completed', 'closed', 'expired'

    -- Adherence tracking
    elements_total INTEGER DEFAULT 0,
    elements_applicable INTEGER DEFAULT 0,
    elements_met INTEGER DEFAULT 0,
    elements_not_met INTEGER DEFAULT 0,
    elements_pending INTEGER DEFAULT 0,
    adherence_percentage REAL,
    adherence_level TEXT,  -- 'full', 'partial', 'low'

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,

    -- Unique constraint to prevent duplicate episodes
    UNIQUE(patient_id, encounter_id, bundle_id, trigger_time)
);

CREATE INDEX IF NOT EXISTS idx_bundle_episodes_patient ON bundle_episodes(patient_id);
CREATE INDEX IF NOT EXISTS idx_bundle_episodes_encounter ON bundle_episodes(encounter_id);
CREATE INDEX IF NOT EXISTS idx_bundle_episodes_bundle ON bundle_episodes(bundle_id);
CREATE INDEX IF NOT EXISTS idx_bundle_episodes_status ON bundle_episodes(status);
CREATE INDEX IF NOT EXISTS idx_bundle_episodes_trigger_time ON bundle_episodes(trigger_time);


-- ============================================================================
-- BUNDLE ELEMENT RESULTS
-- ============================================================================
-- Tracks the status of each element within a bundle episode

CREATE TABLE IF NOT EXISTS bundle_element_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Link to episode
    episode_id INTEGER NOT NULL,

    -- Element identification
    element_id TEXT NOT NULL,
    element_name TEXT NOT NULL,
    element_description TEXT,

    -- Element requirements
    required BOOLEAN DEFAULT TRUE,
    time_window_hours REAL,
    deadline TIMESTAMP,

    -- Result
    status TEXT NOT NULL,  -- 'met', 'not_met', 'pending', 'na', 'unknown'

    -- Completion details
    completed_at TIMESTAMP,
    value TEXT,            -- The actual value found (lab result, med name, etc.)
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (episode_id) REFERENCES bundle_episodes(id) ON DELETE CASCADE,
    UNIQUE(episode_id, element_id)
);

CREATE INDEX IF NOT EXISTS idx_element_results_episode ON bundle_element_results(episode_id);
CREATE INDEX IF NOT EXISTS idx_element_results_status ON bundle_element_results(status);
CREATE INDEX IF NOT EXISTS idx_element_results_deadline ON bundle_element_results(deadline);


-- ============================================================================
-- BUNDLE ALERTS
-- ============================================================================
-- Alerts generated when bundle elements are not met within time windows

CREATE TABLE IF NOT EXISTS bundle_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Link to episode and element
    episode_id INTEGER NOT NULL,
    element_result_id INTEGER,

    -- Patient/encounter (denormalized for quick access)
    patient_id TEXT NOT NULL,
    patient_mrn TEXT,
    encounter_id TEXT NOT NULL,

    -- Bundle/element info
    bundle_id TEXT NOT NULL,
    bundle_name TEXT NOT NULL,
    element_id TEXT,
    element_name TEXT,

    -- Alert details
    alert_type TEXT NOT NULL,  -- 'element_overdue', 'element_not_met', 'low_adherence', 'bundle_incomplete'
    severity TEXT NOT NULL,     -- 'critical', 'warning', 'info'
    title TEXT NOT NULL,
    message TEXT NOT NULL,

    -- Alert status
    status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'acknowledged', 'resolved', 'dismissed'
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (episode_id) REFERENCES bundle_episodes(id) ON DELETE CASCADE,
    FOREIGN KEY (element_result_id) REFERENCES bundle_element_results(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_bundle_alerts_episode ON bundle_alerts(episode_id);
CREATE INDEX IF NOT EXISTS idx_bundle_alerts_patient ON bundle_alerts(patient_id);
CREATE INDEX IF NOT EXISTS idx_bundle_alerts_status ON bundle_alerts(status);
CREATE INDEX IF NOT EXISTS idx_bundle_alerts_severity ON bundle_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_bundle_alerts_created ON bundle_alerts(created_at);


-- ============================================================================
-- BUNDLE TRIGGERS
-- ============================================================================
-- Configuration table for what triggers each bundle

CREATE TABLE IF NOT EXISTS bundle_triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    bundle_id TEXT NOT NULL,

    -- Trigger type and pattern
    trigger_type TEXT NOT NULL,  -- 'diagnosis', 'order', 'lab', 'medication', 'vital'
    trigger_code TEXT,           -- ICD-10, LOINC, medication code, etc.
    trigger_pattern TEXT,        -- Regex pattern for matching
    trigger_description TEXT,

    -- Additional criteria
    age_min_days INTEGER,
    age_max_days INTEGER,
    additional_criteria TEXT,    -- JSON for complex criteria

    -- Status
    active BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(bundle_id, trigger_type, trigger_code)
);

CREATE INDEX IF NOT EXISTS idx_bundle_triggers_bundle ON bundle_triggers(bundle_id);
CREATE INDEX IF NOT EXISTS idx_bundle_triggers_type ON bundle_triggers(trigger_type);
CREATE INDEX IF NOT EXISTS idx_bundle_triggers_active ON bundle_triggers(active);


-- ============================================================================
-- MONITORING STATE
-- ============================================================================
-- Tracks the last poll time for each trigger type to enable incremental polling

CREATE TABLE IF NOT EXISTS monitor_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    monitor_type TEXT NOT NULL UNIQUE,  -- 'diagnosis', 'order', 'lab', etc.
    last_poll_time TIMESTAMP,
    last_poll_count INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================================
-- INSERT DEFAULT BUNDLE TRIGGERS
-- ============================================================================

-- Sepsis Bundle Triggers
INSERT OR IGNORE INTO bundle_triggers (bundle_id, trigger_type, trigger_code, trigger_description, age_min_days, age_max_days)
VALUES
    ('sepsis_peds_2024', 'diagnosis', 'A41%', 'Sepsis ICD-10 codes', NULL, NULL),
    ('sepsis_peds_2024', 'diagnosis', 'A40%', 'Streptococcal sepsis', NULL, NULL),
    ('sepsis_peds_2024', 'diagnosis', 'R65.2%', 'Severe sepsis', NULL, NULL),
    ('sepsis_peds_2024', 'diagnosis', 'P36%', 'Neonatal sepsis', 0, 28),
    ('sepsis_peds_2024', 'lab', '2524-7', 'Lactate ordered (LOINC)', NULL, NULL);

-- Febrile Infant Bundle Triggers
INSERT OR IGNORE INTO bundle_triggers (bundle_id, trigger_type, trigger_code, trigger_description, age_min_days, age_max_days)
VALUES
    ('febrile_infant_2024', 'diagnosis', 'R50%', 'Fever ICD-10 codes', 8, 60),
    ('febrile_infant_2024', 'diagnosis', 'P81.9', 'Temperature regulation disturbance of newborn', 8, 60),
    ('febrile_infant_2024', 'vital', 'TEMP>=38', 'Temperature >= 38°C', 8, 60);

-- Neonatal HSV Bundle Triggers
INSERT OR IGNORE INTO bundle_triggers (bundle_id, trigger_type, trigger_code, trigger_description, age_min_days, age_max_days)
VALUES
    ('neonatal_hsv_2024', 'diagnosis', 'P35.2', 'Congenital HSV infection', 0, 21),
    ('neonatal_hsv_2024', 'diagnosis', 'B00%', 'Herpesviral infection', 0, 21),
    ('neonatal_hsv_2024', 'medication', 'acyclovir', 'Acyclovir ordered', 0, 21),
    ('neonatal_hsv_2024', 'lab', '16955-7', 'HSV PCR CSF ordered', 0, 21),
    ('neonatal_hsv_2024', 'lab', '49986-3', 'HSV PCR blood ordered', 0, 21);

-- C. diff Testing Bundle Triggers
INSERT OR IGNORE INTO bundle_triggers (bundle_id, trigger_type, trigger_code, trigger_description, age_min_days, age_max_days)
VALUES
    ('cdiff_testing_2024', 'lab', '34713-8', 'C. diff toxin ordered', NULL, NULL),
    ('cdiff_testing_2024', 'lab', '54067-4', 'C. diff PCR ordered', NULL, NULL),
    ('cdiff_testing_2024', 'lab', '29484-9', 'C. diff GDH ordered', NULL, NULL);

-- CAP Bundle Triggers
INSERT OR IGNORE INTO bundle_triggers (bundle_id, trigger_type, trigger_code, trigger_description, age_min_days, age_max_days)
VALUES
    ('cap_peds_2024', 'diagnosis', 'J13', 'Pneumococcal pneumonia', 90, NULL),
    ('cap_peds_2024', 'diagnosis', 'J14', 'H. influenzae pneumonia', 90, NULL),
    ('cap_peds_2024', 'diagnosis', 'J15%', 'Bacterial pneumonia', 90, NULL),
    ('cap_peds_2024', 'diagnosis', 'J18%', 'Pneumonia, unspecified', 90, NULL);

-- UTI Bundle Triggers
INSERT OR IGNORE INTO bundle_triggers (bundle_id, trigger_type, trigger_code, trigger_description, age_min_days, age_max_days)
VALUES
    ('uti_peds_2024', 'diagnosis', 'N39.0', 'UTI, site not specified', NULL, NULL),
    ('uti_peds_2024', 'diagnosis', 'N10', 'Acute pyelonephritis', NULL, NULL),
    ('uti_peds_2024', 'diagnosis', 'N30%', 'Cystitis', NULL, NULL);

-- SSTI Bundle Triggers
INSERT OR IGNORE INTO bundle_triggers (bundle_id, trigger_type, trigger_code, trigger_description, age_min_days, age_max_days)
VALUES
    ('ssti_peds_2024', 'diagnosis', 'L03%', 'Cellulitis', NULL, NULL),
    ('ssti_peds_2024', 'diagnosis', 'L02%', 'Abscess', NULL, NULL);

-- Febrile Neutropenia Bundle Triggers
INSERT OR IGNORE INTO bundle_triggers (bundle_id, trigger_type, trigger_code, trigger_description, age_min_days, age_max_days)
VALUES
    ('fn_peds_2024', 'diagnosis', 'D70%', 'Neutropenia', NULL, NULL),
    ('fn_peds_2024', 'lab', '751-8', 'ANC < 500', NULL, NULL);


-- ============================================================================
-- VIEWS FOR DASHBOARD
-- ============================================================================

-- Active episodes with element summary
CREATE VIEW IF NOT EXISTS v_active_episodes AS
SELECT
    e.id,
    e.patient_id,
    e.patient_mrn,
    e.encounter_id,
    e.bundle_id,
    e.bundle_name,
    e.trigger_type,
    e.trigger_time,
    e.patient_age_days,
    e.patient_unit,
    e.status,
    e.elements_applicable,
    e.elements_met,
    e.adherence_percentage,
    e.adherence_level,
    e.created_at,
    e.updated_at,
    (SELECT COUNT(*) FROM bundle_alerts a WHERE a.episode_id = e.id AND a.status = 'active') as active_alerts
FROM bundle_episodes e
WHERE e.status = 'active'
ORDER BY e.trigger_time DESC;


-- Pending elements that need attention
CREATE VIEW IF NOT EXISTS v_pending_elements AS
SELECT
    r.id,
    r.episode_id,
    e.patient_id,
    e.patient_mrn,
    e.encounter_id,
    e.bundle_id,
    e.bundle_name,
    r.element_id,
    r.element_name,
    r.required,
    r.deadline,
    r.status,
    r.notes,
    CASE
        WHEN r.deadline IS NOT NULL AND r.deadline < CURRENT_TIMESTAMP THEN 'overdue'
        WHEN r.deadline IS NOT NULL AND r.deadline < datetime(CURRENT_TIMESTAMP, '+1 hour') THEN 'due_soon'
        ELSE 'pending'
    END as urgency
FROM bundle_element_results r
JOIN bundle_episodes e ON r.episode_id = e.id
WHERE r.status = 'pending' AND e.status = 'active'
ORDER BY r.deadline ASC NULLS LAST;


-- Active alerts for dashboard
CREATE VIEW IF NOT EXISTS v_active_alerts AS
SELECT
    a.id,
    a.patient_id,
    a.patient_mrn,
    a.encounter_id,
    a.bundle_id,
    a.bundle_name,
    a.element_id,
    a.element_name,
    a.alert_type,
    a.severity,
    a.title,
    a.message,
    a.status,
    a.created_at,
    e.patient_unit,
    e.trigger_time
FROM bundle_alerts a
JOIN bundle_episodes e ON a.episode_id = e.id
WHERE a.status = 'active'
ORDER BY
    CASE a.severity
        WHEN 'critical' THEN 1
        WHEN 'warning' THEN 2
        ELSE 3
    END,
    a.created_at DESC;


-- Adherence summary by bundle (last 30 days)
CREATE VIEW IF NOT EXISTS v_adherence_summary AS
SELECT
    bundle_id,
    bundle_name,
    COUNT(*) as total_episodes,
    SUM(CASE WHEN adherence_level = 'full' THEN 1 ELSE 0 END) as full_adherence,
    SUM(CASE WHEN adherence_level = 'partial' THEN 1 ELSE 0 END) as partial_adherence,
    SUM(CASE WHEN adherence_level = 'low' THEN 1 ELSE 0 END) as low_adherence,
    ROUND(AVG(adherence_percentage), 1) as avg_adherence_pct
FROM bundle_episodes
WHERE created_at >= datetime('now', '-30 days')
  AND status IN ('completed', 'closed')
GROUP BY bundle_id, bundle_name;
