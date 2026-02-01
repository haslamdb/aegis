-- Outbreak Detection Database Schema
-- General-purpose cluster detection for infection control

-- Outbreak clusters table
CREATE TABLE IF NOT EXISTS outbreak_clusters (
    id TEXT PRIMARY KEY,
    infection_type TEXT NOT NULL,  -- mdro type, hai type, cdi, etc.
    organism TEXT,
    unit TEXT NOT NULL,
    location TEXT,

    -- Cluster info
    case_count INTEGER DEFAULT 0,
    first_case_date TEXT,
    last_case_date TEXT,
    window_days INTEGER DEFAULT 14,

    -- Status
    status TEXT DEFAULT 'active',  -- active, investigating, resolved
    severity TEXT DEFAULT 'low',   -- low, medium, high, critical
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT,
    resolution_notes TEXT,

    -- Alerting
    alerted INTEGER DEFAULT 0,
    alerted_at TEXT
);

-- Cases within clusters
CREATE TABLE IF NOT EXISTS cluster_cases (
    id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL,
    source TEXT NOT NULL,  -- mdro, hai, cdi, etc.
    source_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    patient_mrn TEXT NOT NULL,
    event_date TEXT NOT NULL,
    organism TEXT,
    infection_type TEXT NOT NULL,
    unit TEXT NOT NULL,
    location TEXT,
    added_at TEXT NOT NULL,
    FOREIGN KEY (cluster_id) REFERENCES outbreak_clusters(id),
    UNIQUE (source, source_id)  -- Prevent duplicate source entries
);

-- Alerts table for IP notifications
CREATE TABLE IF NOT EXISTS outbreak_alerts (
    id TEXT PRIMARY KEY,
    alert_type TEXT NOT NULL,  -- cluster_formed, cluster_escalated, threshold_exceeded
    severity TEXT NOT NULL,    -- low, medium, high, critical
    title TEXT NOT NULL,
    message TEXT,

    -- Related entities
    cluster_id TEXT,

    -- Status
    acknowledged INTEGER DEFAULT 0,
    acknowledged_by TEXT,
    acknowledged_at TEXT,
    created_at TEXT NOT NULL,

    FOREIGN KEY (cluster_id) REFERENCES outbreak_clusters(id)
);

-- Processing log to track what we've analyzed
CREATE TABLE IF NOT EXISTS outbreak_processing_log (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    cluster_id TEXT,
    PRIMARY KEY (source, source_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_clusters_unit ON outbreak_clusters(unit);
CREATE INDEX IF NOT EXISTS idx_clusters_type ON outbreak_clusters(infection_type);
CREATE INDEX IF NOT EXISTS idx_clusters_status ON outbreak_clusters(status);
CREATE INDEX IF NOT EXISTS idx_clusters_severity ON outbreak_clusters(severity);

CREATE INDEX IF NOT EXISTS idx_cases_cluster ON cluster_cases(cluster_id);
CREATE INDEX IF NOT EXISTS idx_cases_source ON cluster_cases(source, source_id);
CREATE INDEX IF NOT EXISTS idx_cases_date ON cluster_cases(event_date);

CREATE INDEX IF NOT EXISTS idx_alerts_acked ON outbreak_alerts(acknowledged);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON outbreak_alerts(created_at);

-- Views
CREATE VIEW IF NOT EXISTS active_clusters AS
SELECT * FROM outbreak_clusters
WHERE status = 'active'
ORDER BY
    CASE severity
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        ELSE 4
    END,
    created_at DESC;

CREATE VIEW IF NOT EXISTS pending_alerts AS
SELECT * FROM outbreak_alerts
WHERE acknowledged = 0
ORDER BY
    CASE severity
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        ELSE 4
    END,
    created_at DESC;
