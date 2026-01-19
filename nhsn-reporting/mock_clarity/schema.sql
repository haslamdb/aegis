-- Mock Clarity Database Schema for NHSN Reporting Development
-- SQLite schema matching Epic Clarity table structures for hybrid FHIR/Clarity testing
--
-- Purpose:
-- - Enable denominator data aggregation (device-days, patient-days)
-- - Support bulk historical queries without FHIR pagination overhead
-- - Test Clarity-based data retrieval logic before production deployment

-- ============================================================================
-- Core Patient/Encounter Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS PATIENT (
    PAT_ID INTEGER PRIMARY KEY,
    PAT_MRN_ID TEXT UNIQUE NOT NULL,
    PAT_NAME TEXT,
    BIRTH_DATE DATE
);

CREATE TABLE IF NOT EXISTS PAT_ENC (
    PAT_ENC_CSN_ID INTEGER PRIMARY KEY,
    PAT_ID INTEGER REFERENCES PATIENT(PAT_ID),
    INPATIENT_DATA_ID INTEGER UNIQUE,
    HOSP_ADMIT_DTTM DATETIME,
    HOSP_DISCH_DTTM DATETIME,
    DEPARTMENT_ID INTEGER
);

-- ============================================================================
-- Clinical Notes Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS HNO_INFO (
    NOTE_ID INTEGER PRIMARY KEY,
    PAT_ENC_CSN_ID INTEGER REFERENCES PAT_ENC(PAT_ENC_CSN_ID),
    ENTRY_INSTANT_DTTM DATETIME,
    ENTRY_USER_ID INTEGER,
    NOTE_TEXT TEXT
);

CREATE TABLE IF NOT EXISTS IP_NOTE_TYPE (
    NOTE_ID INTEGER REFERENCES HNO_INFO(NOTE_ID),
    NOTE_TYPE_C INTEGER,
    PRIMARY KEY (NOTE_ID, NOTE_TYPE_C)
);

CREATE TABLE IF NOT EXISTS ZC_NOTE_TYPE_IP (
    NOTE_TYPE_C INTEGER PRIMARY KEY,
    NAME TEXT
);

CREATE TABLE IF NOT EXISTS CLARITY_EMP (
    PROV_ID INTEGER PRIMARY KEY,
    PROV_NAME TEXT
);

-- ============================================================================
-- Flowsheet Data (Device Presence)
-- ============================================================================

CREATE TABLE IF NOT EXISTS IP_FLWSHT_REC (
    FSD_ID INTEGER PRIMARY KEY,
    INPATIENT_DATA_ID INTEGER
);

CREATE TABLE IF NOT EXISTS IP_FLWSHT_MEAS (
    FLO_MEAS_ID INTEGER,
    FSD_ID INTEGER REFERENCES IP_FLWSHT_REC(FSD_ID),
    RECORDED_TIME DATETIME,
    MEAS_VALUE TEXT,
    PRIMARY KEY (FLO_MEAS_ID, FSD_ID, RECORDED_TIME)
);

CREATE TABLE IF NOT EXISTS IP_FLO_GP_DATA (
    FLO_MEAS_ID INTEGER PRIMARY KEY,
    DISP_NAME TEXT
);

-- ============================================================================
-- Lab/Culture Results
-- ============================================================================

CREATE TABLE IF NOT EXISTS ORDER_PROC (
    ORDER_PROC_ID INTEGER PRIMARY KEY,
    PAT_ID INTEGER REFERENCES PATIENT(PAT_ID),
    PROC_NAME TEXT
);

CREATE TABLE IF NOT EXISTS ORDER_RESULTS (
    ORDER_ID INTEGER PRIMARY KEY,
    ORDER_PROC_ID INTEGER REFERENCES ORDER_PROC(ORDER_PROC_ID),
    SPECIMN_TAKEN_TIME DATETIME,
    RESULT_TIME DATETIME,
    COMPONENT_ID INTEGER,
    ORD_VALUE TEXT
);

CREATE TABLE IF NOT EXISTS CLARITY_COMPONENT (
    COMPONENT_ID INTEGER PRIMARY KEY,
    NAME TEXT
);

-- ============================================================================
-- NHSN Location Mapping (Custom Table for Denominators)
-- ============================================================================

CREATE TABLE IF NOT EXISTS NHSN_LOCATION_MAP (
    EPIC_DEPT_ID INTEGER PRIMARY KEY,
    NHSN_LOCATION_CODE TEXT NOT NULL,
    LOCATION_DESCRIPTION TEXT,
    UNIT_TYPE TEXT  -- ICU, Ward, NICU, etc.
);

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_pat_mrn ON PATIENT(PAT_MRN_ID);
CREATE INDEX IF NOT EXISTS idx_pat_enc_pat ON PAT_ENC(PAT_ID);
CREATE INDEX IF NOT EXISTS idx_pat_enc_admit ON PAT_ENC(HOSP_ADMIT_DTTM);
CREATE INDEX IF NOT EXISTS idx_pat_enc_dept ON PAT_ENC(DEPARTMENT_ID);
CREATE INDEX IF NOT EXISTS idx_pat_enc_inpatient ON PAT_ENC(INPATIENT_DATA_ID);
CREATE INDEX IF NOT EXISTS idx_hno_enc ON HNO_INFO(PAT_ENC_CSN_ID);
CREATE INDEX IF NOT EXISTS idx_hno_date ON HNO_INFO(ENTRY_INSTANT_DTTM);
CREATE INDEX IF NOT EXISTS idx_flwsht_rec_inpatient ON IP_FLWSHT_REC(INPATIENT_DATA_ID);
CREATE INDEX IF NOT EXISTS idx_flwsht_time ON IP_FLWSHT_MEAS(RECORDED_TIME);
CREATE INDEX IF NOT EXISTS idx_flwsht_fsd ON IP_FLWSHT_MEAS(FSD_ID);
CREATE INDEX IF NOT EXISTS idx_order_pat ON ORDER_PROC(PAT_ID);
CREATE INDEX IF NOT EXISTS idx_order_time ON ORDER_RESULTS(SPECIMN_TAKEN_TIME);
CREATE INDEX IF NOT EXISTS idx_nhsn_loc_code ON NHSN_LOCATION_MAP(NHSN_LOCATION_CODE);

-- ============================================================================
-- Reference Data Inserts
-- ============================================================================

-- Note type reference values (matching typical Epic configuration)
INSERT OR REPLACE INTO ZC_NOTE_TYPE_IP (NOTE_TYPE_C, NAME) VALUES
    (1, 'Progress Notes'),
    (2, 'Daily Progress Note'),
    (3, 'Discharge Summary'),
    (4, 'History and Physical'),
    (5, 'Consultation'),
    (10, 'Infectious Disease Consult'),
    (11, 'ID Consult Note'),
    (20, 'Procedure Note'),
    (30, 'Nursing Note');

-- Flowsheet item reference values (central line tracking)
INSERT OR REPLACE INTO IP_FLO_GP_DATA (FLO_MEAS_ID, DISP_NAME) VALUES
    (1001, 'Central Line Present'),
    (1002, 'Central Line Site'),
    (1003, 'Central Line Type'),
    (1004, 'Central Line Dressing Change'),
    (1005, 'Central Line Insertion Date'),
    (1006, 'PICC Line Present'),
    (1007, 'Tunneled Catheter Present');

-- Flowsheet item reference values (urinary catheter tracking for CAUTI)
INSERT OR REPLACE INTO IP_FLO_GP_DATA (FLO_MEAS_ID, DISP_NAME) VALUES
    (2101, 'Foley Catheter Present'),
    (2102, 'Foley Catheter Site'),
    (2103, 'Foley Catheter Size'),
    (2104, 'Indwelling Urinary Catheter'),
    (2105, 'Urinary Catheter Insertion Date'),
    (2106, 'Urinary Catheter Care'),
    (2107, 'Urinary Catheter Output');

-- Flowsheet item reference values (ventilator tracking for VAE/VAP)
INSERT OR REPLACE INTO IP_FLO_GP_DATA (FLO_MEAS_ID, DISP_NAME) VALUES
    (3101, 'Ventilator Mode'),
    (3102, 'Mechanical Ventilation'),
    (3103, 'Ventilator Settings'),
    (3104, 'Intubation Status'),
    (3105, 'ETT Size'),
    (3106, 'Ventilator FiO2'),
    (3107, 'Ventilator PEEP'),
    (3108, 'Ventilator Rate');

-- Lab component reference values
INSERT OR REPLACE INTO CLARITY_COMPONENT (COMPONENT_ID, NAME) VALUES
    (2001, 'Blood Culture Result'),
    (2002, 'Blood Culture Organism'),
    (2003, 'Blood Culture Gram Stain'),
    (2004, 'Susceptibility Result');

-- CCHMC-specific NHSN location mappings
INSERT OR REPLACE INTO NHSN_LOCATION_MAP (EPIC_DEPT_ID, NHSN_LOCATION_CODE, LOCATION_DESCRIPTION, UNIT_TYPE) VALUES
    (100, 'T5A', 'Pediatric ICU', 'ICU'),
    (101, 'T5B', 'Cardiac ICU', 'ICU'),
    (102, 'T4', 'Neonatal ICU', 'NICU'),
    (103, 'G5S', 'Oncology', 'Oncology'),
    (104, 'G6N', 'Bone Marrow Transplant', 'BMT'),
    (105, 'A6N', 'Hospital Medicine', 'Ward'),
    (106, 'A5N', 'Hospital Medicine 2', 'Ward'),
    (107, 'T6A', 'Surgical Unit', 'Ward'),
    (108, 'T6B', 'Transplant Unit', 'Ward');
