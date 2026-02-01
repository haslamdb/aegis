-- MDRO Surveillance Database Schema
-- Tracks multi-drug resistant organism cases

-- Main MDRO cases table
CREATE TABLE IF NOT EXISTS mdro_cases (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    patient_mrn TEXT NOT NULL,
    patient_name TEXT,

    -- Culture info
    culture_id TEXT NOT NULL UNIQUE,
    culture_date TEXT NOT NULL,
    specimen_type TEXT,
    organism TEXT NOT NULL,

    -- MDRO classification
    mdro_type TEXT NOT NULL,  -- mrsa, vre, cre, esbl, crpa, crab
    resistant_antibiotics TEXT,  -- JSON array
    classification_reason TEXT,

    -- Location/timing
    location TEXT,
    unit TEXT,
    admission_date TEXT,
    days_since_admission INTEGER,

    -- Transmission classification
    transmission_status TEXT DEFAULT 'pending',  -- pending, community, healthcare

    -- Status
    is_new INTEGER DEFAULT 1,
    prior_history INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by TEXT,
    notes TEXT
);

-- Reviews table for IP tracking
CREATE TABLE IF NOT EXISTS mdro_reviews (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    decision TEXT NOT NULL,  -- confirmed, rejected, needs_info
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES mdro_cases(id)
);

-- Processing log to track what we've seen
CREATE TABLE IF NOT EXISTS mdro_processing_log (
    culture_id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL,
    is_mdro INTEGER NOT NULL,
    mdro_type TEXT,
    case_id TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_cases_patient ON mdro_cases(patient_id);
CREATE INDEX IF NOT EXISTS idx_cases_mrn ON mdro_cases(patient_mrn);
CREATE INDEX IF NOT EXISTS idx_cases_mdro_type ON mdro_cases(mdro_type);
CREATE INDEX IF NOT EXISTS idx_cases_unit ON mdro_cases(unit);
CREATE INDEX IF NOT EXISTS idx_cases_date ON mdro_cases(culture_date);
CREATE INDEX IF NOT EXISTS idx_cases_status ON mdro_cases(transmission_status);
CREATE INDEX IF NOT EXISTS idx_processing_log_date ON mdro_processing_log(processed_at);

-- Views for common queries
CREATE VIEW IF NOT EXISTS recent_mdro_by_type AS
SELECT
    mdro_type,
    COUNT(*) as count,
    COUNT(DISTINCT patient_id) as unique_patients,
    COUNT(DISTINCT unit) as affected_units
FROM mdro_cases
WHERE date(culture_date) >= date('now', '-30 days')
GROUP BY mdro_type;
