-- Migration script to add duration tracking and re-approval fields
-- Run this on existing databases to update schema

-- Add new columns to abx_approval_requests table
ALTER TABLE abx_approval_requests ADD COLUMN approval_duration_hours INTEGER;
ALTER TABLE abx_approval_requests ADD COLUMN planned_end_date TIMESTAMP;
ALTER TABLE abx_approval_requests ADD COLUMN is_reapproval BOOLEAN DEFAULT 0;
ALTER TABLE abx_approval_requests ADD COLUMN parent_approval_id TEXT;
ALTER TABLE abx_approval_requests ADD COLUMN approval_chain_count INTEGER DEFAULT 0;
ALTER TABLE abx_approval_requests ADD COLUMN recheck_status TEXT;
ALTER TABLE abx_approval_requests ADD COLUMN last_recheck_date TIMESTAMP;

-- Create new indexes
CREATE INDEX IF NOT EXISTS idx_approval_planned_end ON abx_approval_requests(planned_end_date);
CREATE INDEX IF NOT EXISTS idx_approval_recheck_status ON abx_approval_requests(recheck_status);
CREATE INDEX IF NOT EXISTS idx_approval_parent ON abx_approval_requests(parent_approval_id);
CREATE INDEX IF NOT EXISTS idx_approval_is_reapproval ON abx_approval_requests(is_reapproval);
