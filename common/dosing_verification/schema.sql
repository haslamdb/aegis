-- Dosing verification alerts storage schema
-- SQLite database for tracking dosing alerts and resolutions

CREATE TABLE IF NOT EXISTS dose_alerts (
    id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL,
    patient_id TEXT,
    patient_mrn TEXT,
    patient_name TEXT,
    encounter_id TEXT,

    -- Alert content
    drug TEXT NOT NULL,
    indication TEXT,
    flag_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'moderate',
    message TEXT NOT NULL,
    expected_dose TEXT,
    actual_dose TEXT,
    rule_source TEXT,

    -- Clinical context (JSON blobs)
    patient_factors TEXT,        -- JSON: {age, weight, scr, gfr, dialysis, gest_age}
    assessment_details TEXT,     -- JSON: full assessment with all flags

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    sent_at TEXT,
    acknowledged_at TEXT,
    acknowledged_by TEXT,
    resolved_at TEXT,
    resolved_by TEXT,
    resolution TEXT,
    resolution_notes TEXT,
    notes TEXT

    -- Deduplication: one active alert per drug per patient per flag type
    -- UNIQUE(patient_mrn, drug, flag_type) WHERE status != 'resolved'
);

CREATE INDEX IF NOT EXISTS idx_dose_alerts_status ON dose_alerts(status);
CREATE INDEX IF NOT EXISTS idx_dose_alerts_severity ON dose_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_dose_alerts_patient ON dose_alerts(patient_mrn);
CREATE INDEX IF NOT EXISTS idx_dose_alerts_drug ON dose_alerts(drug);
CREATE INDEX IF NOT EXISTS idx_dose_alerts_created ON dose_alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_dose_alerts_flag_type ON dose_alerts(flag_type);

CREATE TABLE IF NOT EXISTS dose_alert_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL,
    action TEXT NOT NULL,
    performed_by TEXT,
    performed_at TEXT NOT NULL DEFAULT (datetime('now')),
    details TEXT,
    FOREIGN KEY (alert_id) REFERENCES dose_alerts(id)
);

CREATE INDEX IF NOT EXISTS idx_dose_audit_alert ON dose_alert_audit(alert_id);
CREATE INDEX IF NOT EXISTS idx_dose_audit_at ON dose_alert_audit(performed_at);
