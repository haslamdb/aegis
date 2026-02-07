-- Unified LLM decision tracking schema
-- SQLite database for cross-module LLM extraction tracking

CREATE TABLE IF NOT EXISTS llm_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Module and context
    module TEXT NOT NULL,              -- abx_indications, guideline_adherence, hai_detection, etc.
    entity_id TEXT NOT NULL,           -- ID of the record being reviewed
    entity_type TEXT,                  -- order, episode, candidate, etc.

    -- Patient context
    patient_mrn TEXT,
    encounter_id TEXT,

    -- LLM extraction details
    llm_model TEXT,                    -- Model identifier
    llm_confidence REAL,              -- Confidence score 0.0-1.0
    llm_recommendation TEXT,          -- What the LLM recommended
    llm_reasoning TEXT,               -- LLM reasoning/explanation
    llm_extracted_data TEXT,          -- Full extraction as JSON

    -- Human review
    outcome TEXT NOT NULL DEFAULT 'pending',  -- accepted, modified, overridden, pending
    human_decision TEXT,              -- What the human chose
    override_reason TEXT,             -- Standardized override reason
    override_notes TEXT,              -- Free-text notes
    reviewer_id TEXT,
    reviewer_name TEXT,

    -- Timing
    extracted_at TIMESTAMP,
    reviewed_at TIMESTAMP,
    review_duration_seconds INTEGER,

    -- Created
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_llm_module ON llm_decisions(module);
CREATE INDEX IF NOT EXISTS idx_llm_entity ON llm_decisions(entity_id);
CREATE INDEX IF NOT EXISTS idx_llm_outcome ON llm_decisions(outcome);
CREATE INDEX IF NOT EXISTS idx_llm_override ON llm_decisions(override_reason);
CREATE INDEX IF NOT EXISTS idx_llm_confidence ON llm_decisions(llm_confidence);
CREATE INDEX IF NOT EXISTS idx_llm_reviewed_at ON llm_decisions(reviewed_at);
CREATE INDEX IF NOT EXISTS idx_llm_patient ON llm_decisions(patient_mrn);
CREATE INDEX IF NOT EXISTS idx_llm_module_outcome ON llm_decisions(module, outcome);
