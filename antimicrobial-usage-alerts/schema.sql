-- Indication monitoring database schema
-- Part of the AEGIS Antimicrobial Stewardship module

-- Candidates: antibiotic orders that need indication review
CREATE TABLE IF NOT EXISTS indication_candidates (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    patient_mrn TEXT NOT NULL,
    medication_request_id TEXT NOT NULL UNIQUE,
    medication_name TEXT NOT NULL,
    order_date TIMESTAMP NOT NULL,

    -- ICD-10 track
    icd10_codes TEXT,  -- JSON array of codes
    icd10_classification TEXT NOT NULL,  -- A, S, N, P, FN, U
    icd10_primary_indication TEXT,

    -- LLM track
    llm_extracted_indication TEXT,
    llm_classification TEXT,  -- A, S, N (if upgraded/downgraded)
    llm_confidence REAL,  -- 0.0-1.0

    -- Final determination
    final_classification TEXT NOT NULL,  -- A, S, N, P, FN, U
    classification_source TEXT NOT NULL,  -- icd10, llm, manual

    -- Status tracking
    status TEXT DEFAULT 'pending',  -- pending, alerted, reviewed
    alert_id TEXT,  -- Links to common alert_store

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reviews: pharmacist review decisions for indication candidates
CREATE TABLE IF NOT EXISTS indication_reviews (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,

    -- Reviewer info
    reviewer TEXT NOT NULL,
    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Decision
    reviewer_decision TEXT NOT NULL,  -- confirmed_n, override_to_a, override_to_s, override_to_p
    llm_decision TEXT,  -- What LLM said (if applicable)

    -- Override tracking
    is_override BOOLEAN DEFAULT 0,  -- True if reviewer disagreed with system
    override_reason TEXT,  -- Free text reason for override

    -- Notes
    notes TEXT,

    FOREIGN KEY (candidate_id) REFERENCES indication_candidates(id)
);

-- Extractions: LLM extraction audit trail
CREATE TABLE IF NOT EXISTS indication_extractions (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,

    -- LLM details
    model_used TEXT,
    prompt_version TEXT,

    -- Extraction results
    extracted_indications TEXT,  -- JSON array of found indications
    supporting_quotes TEXT,  -- JSON array of quotes from notes
    confidence REAL,  -- 0.0-1.0

    -- Performance tracking
    tokens_used INTEGER,
    response_time_ms INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (candidate_id) REFERENCES indication_candidates(id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_candidates_patient ON indication_candidates(patient_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON indication_candidates(status);
CREATE INDEX IF NOT EXISTS idx_candidates_classification ON indication_candidates(final_classification);
CREATE INDEX IF NOT EXISTS idx_candidates_order_date ON indication_candidates(order_date);
CREATE INDEX IF NOT EXISTS idx_candidates_created ON indication_candidates(created_at);

CREATE INDEX IF NOT EXISTS idx_reviews_candidate ON indication_reviews(candidate_id);
CREATE INDEX IF NOT EXISTS idx_reviews_override ON indication_reviews(is_override);

CREATE INDEX IF NOT EXISTS idx_extractions_candidate ON indication_extractions(candidate_id);
