-- Antibiotic approval requests storage schema
-- SQLite database for tracking phone-based approval requests

-- Main approval requests table
CREATE TABLE IF NOT EXISTS abx_approval_requests (
    id TEXT PRIMARY KEY,

    -- Patient info (captured at time of request)
    patient_id TEXT NOT NULL,
    patient_mrn TEXT NOT NULL,
    patient_name TEXT,
    patient_location TEXT,

    -- Request details
    antibiotic_name TEXT NOT NULL,
    antibiotic_dose TEXT,
    antibiotic_route TEXT,
    indication TEXT,
    duration_requested_hours INTEGER,
    prescriber_name TEXT,
    prescriber_pager TEXT,

    -- Clinical context (JSON blob for cultures, current meds snapshot)
    clinical_context TEXT,

    -- Decision
    decision TEXT,  -- approved, changed_therapy, denied, deferred
    decision_by TEXT,
    decision_at TIMESTAMP,
    decision_notes TEXT,

    -- For changed_therapy decisions
    alternative_recommended TEXT,

    -- Workflow
    status TEXT DEFAULT 'pending',  -- pending, completed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_approval_patient_mrn ON abx_approval_requests(patient_mrn);
CREATE INDEX IF NOT EXISTS idx_approval_status ON abx_approval_requests(status);
CREATE INDEX IF NOT EXISTS idx_approval_created ON abx_approval_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_approval_decision ON abx_approval_requests(decision);
CREATE INDEX IF NOT EXISTS idx_approval_antibiotic ON abx_approval_requests(antibiotic_name);

-- Audit trail for compliance
CREATE TABLE IF NOT EXISTS abx_approval_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id TEXT NOT NULL,
    action TEXT NOT NULL,
    performed_by TEXT,
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT,

    FOREIGN KEY (approval_id) REFERENCES abx_approval_requests(id)
);

CREATE INDEX IF NOT EXISTS idx_approval_audit_id ON abx_approval_audit(approval_id);
CREATE INDEX IF NOT EXISTS idx_approval_audit_at ON abx_approval_audit(performed_at);
