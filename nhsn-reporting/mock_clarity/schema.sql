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

-- ============================================================================
-- Medication Administration (MAR) Tables for AU Reporting
-- ============================================================================

CREATE TABLE IF NOT EXISTS RX_MED_ONE (
    MEDICATION_ID INTEGER PRIMARY KEY,
    GENERIC_NAME TEXT,
    BRAND_NAME TEXT,
    PHARM_CLASS TEXT,         -- e.g., 'Antibacterial', 'Antifungal', 'Antiviral'
    PHARM_SUBCLASS TEXT       -- e.g., 'Penicillin', 'Fluoroquinolone', 'Carbapenem'
);

CREATE TABLE IF NOT EXISTS ORDER_MED (
    ORDER_MED_ID INTEGER PRIMARY KEY,
    PAT_ENC_CSN_ID INTEGER REFERENCES PAT_ENC(PAT_ENC_CSN_ID),
    MEDICATION_ID INTEGER REFERENCES RX_MED_ONE(MEDICATION_ID),
    ORDERING_DATE DATETIME,
    ADMIN_ROUTE TEXT,           -- 'IV', 'PO', 'IM', 'SC', etc.
    DOSE REAL,
    DOSE_UNIT TEXT,             -- 'mg', 'g', 'mcg', etc.
    FREQUENCY TEXT              -- 'Q8H', 'Q12H', 'DAILY', etc.
);

CREATE TABLE IF NOT EXISTS MAR_ADMIN_INFO (
    MAR_ADMIN_ID INTEGER PRIMARY KEY,
    ORDER_MED_ID INTEGER REFERENCES ORDER_MED(ORDER_MED_ID),
    TAKEN_TIME DATETIME,
    ACTION_NAME TEXT,           -- 'Given', 'Held', 'Refused', 'Not Given'
    DOSE_GIVEN REAL,
    DOSE_UNIT TEXT
);

-- NHSN Antimicrobial Code Mapping
CREATE TABLE IF NOT EXISTS NHSN_ANTIMICROBIAL_MAP (
    MEDICATION_ID INTEGER REFERENCES RX_MED_ONE(MEDICATION_ID),
    NHSN_CODE TEXT NOT NULL,          -- NHSN antimicrobial code (e.g., 'AMK' for amikacin)
    NHSN_CATEGORY TEXT NOT NULL,      -- NHSN category (e.g., 'Aminoglycosides')
    ATC_CODE TEXT,                    -- WHO ATC code (e.g., 'J01GB06')
    DDD REAL,                         -- Defined Daily Dose (for DDD calculations)
    DDD_UNIT TEXT,                    -- DDD unit (e.g., 'g', 'mg')
    PRIMARY KEY (MEDICATION_ID)
);

-- ============================================================================
-- Susceptibility Tables for AR Reporting
-- ============================================================================

CREATE TABLE IF NOT EXISTS CULTURE_RESULTS (
    CULTURE_ID INTEGER PRIMARY KEY,
    ORDER_PROC_ID INTEGER REFERENCES ORDER_PROC(ORDER_PROC_ID),
    PAT_ID INTEGER REFERENCES PATIENT(PAT_ID),
    PAT_ENC_CSN_ID INTEGER REFERENCES PAT_ENC(PAT_ENC_CSN_ID),
    SPECIMEN_TAKEN_TIME DATETIME,
    RESULT_TIME DATETIME,
    SPECIMEN_TYPE TEXT,               -- 'Blood', 'Urine', 'Respiratory', 'CSF', 'Wound'
    SPECIMEN_SOURCE TEXT,             -- More specific source (e.g., 'Central Line', 'Midstream')
    CULTURE_STATUS TEXT               -- 'Positive', 'Negative', 'Pending', 'No Growth'
);

CREATE TABLE IF NOT EXISTS CULTURE_ORGANISM (
    CULTURE_ORGANISM_ID INTEGER PRIMARY KEY,
    CULTURE_ID INTEGER REFERENCES CULTURE_RESULTS(CULTURE_ID),
    ORGANISM_ID INTEGER,
    ORGANISM_NAME TEXT,               -- e.g., 'Staphylococcus aureus'
    ORGANISM_GROUP TEXT,              -- e.g., 'Gram-positive cocci'
    CFU_COUNT INTEGER,                -- Colony forming units (for urine)
    IS_PRIMARY INTEGER DEFAULT 1      -- Primary pathogen vs colonizer
);

CREATE TABLE IF NOT EXISTS SUSCEPTIBILITY_RESULTS (
    SUSCEPTIBILITY_ID INTEGER PRIMARY KEY,
    CULTURE_ORGANISM_ID INTEGER REFERENCES CULTURE_ORGANISM(CULTURE_ORGANISM_ID),
    ANTIBIOTIC TEXT NOT NULL,         -- e.g., 'Vancomycin'
    ANTIBIOTIC_CODE TEXT,             -- e.g., 'VAN'
    MIC REAL,                         -- Minimum Inhibitory Concentration
    MIC_UNITS TEXT,                   -- 'mcg/mL', 'ug/mL'
    INTERPRETATION TEXT,              -- 'S' (Susceptible), 'I' (Intermediate), 'R' (Resistant)
    METHOD TEXT                       -- 'Disk Diffusion', 'MIC', 'E-test'
);

-- NHSN Organism Phenotype Map (for AR reporting)
CREATE TABLE IF NOT EXISTS NHSN_PHENOTYPE_MAP (
    PHENOTYPE_ID INTEGER PRIMARY KEY,
    PHENOTYPE_CODE TEXT NOT NULL,     -- 'MRSA', 'VRE', 'ESBL', 'CRE', 'MDRO'
    PHENOTYPE_NAME TEXT NOT NULL,
    ORGANISM_PATTERN TEXT,            -- Regex pattern for matching organisms
    RESISTANCE_PATTERN TEXT           -- Required resistance pattern (e.g., 'OXA:R' for MRSA)
);

-- ============================================================================
-- Additional Indexes for AU/AR Queries
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_mar_time ON MAR_ADMIN_INFO(TAKEN_TIME);
CREATE INDEX IF NOT EXISTS idx_mar_order ON MAR_ADMIN_INFO(ORDER_MED_ID);
CREATE INDEX IF NOT EXISTS idx_order_med_enc ON ORDER_MED(PAT_ENC_CSN_ID);
CREATE INDEX IF NOT EXISTS idx_order_med_date ON ORDER_MED(ORDERING_DATE);
CREATE INDEX IF NOT EXISTS idx_culture_time ON CULTURE_RESULTS(SPECIMEN_TAKEN_TIME);
CREATE INDEX IF NOT EXISTS idx_culture_pat ON CULTURE_RESULTS(PAT_ID);
CREATE INDEX IF NOT EXISTS idx_culture_type ON CULTURE_RESULTS(SPECIMEN_TYPE);
CREATE INDEX IF NOT EXISTS idx_suscept_org ON SUSCEPTIBILITY_RESULTS(CULTURE_ORGANISM_ID);

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

-- ============================================================================
-- Antimicrobial Reference Data for AU Reporting
-- ============================================================================

-- Common antimicrobials (subset of NHSN list)
INSERT OR REPLACE INTO RX_MED_ONE (MEDICATION_ID, GENERIC_NAME, BRAND_NAME, PHARM_CLASS, PHARM_SUBCLASS) VALUES
    (5001, 'amikacin', 'Amikin', 'Antibacterial', 'Aminoglycoside'),
    (5002, 'ampicillin', 'Principen', 'Antibacterial', 'Penicillin'),
    (5003, 'ampicillin/sulbactam', 'Unasyn', 'Antibacterial', 'Beta-lactam/Inhibitor'),
    (5004, 'azithromycin', 'Zithromax', 'Antibacterial', 'Macrolide'),
    (5005, 'aztreonam', 'Azactam', 'Antibacterial', 'Monobactam'),
    (5006, 'cefazolin', 'Ancef', 'Antibacterial', 'Cephalosporin 1st Gen'),
    (5007, 'cefepime', 'Maxipime', 'Antibacterial', 'Cephalosporin 4th Gen'),
    (5008, 'ceftazidime', 'Fortaz', 'Antibacterial', 'Cephalosporin 3rd Gen'),
    (5009, 'ceftriaxone', 'Rocephin', 'Antibacterial', 'Cephalosporin 3rd Gen'),
    (5010, 'ciprofloxacin', 'Cipro', 'Antibacterial', 'Fluoroquinolone'),
    (5011, 'clindamycin', 'Cleocin', 'Antibacterial', 'Lincosamide'),
    (5012, 'daptomycin', 'Cubicin', 'Antibacterial', 'Lipopeptide'),
    (5013, 'ertapenem', 'Invanz', 'Antibacterial', 'Carbapenem'),
    (5014, 'gentamicin', 'Garamycin', 'Antibacterial', 'Aminoglycoside'),
    (5015, 'levofloxacin', 'Levaquin', 'Antibacterial', 'Fluoroquinolone'),
    (5016, 'linezolid', 'Zyvox', 'Antibacterial', 'Oxazolidinone'),
    (5017, 'meropenem', 'Merrem', 'Antibacterial', 'Carbapenem'),
    (5018, 'metronidazole', 'Flagyl', 'Antibacterial', 'Nitroimidazole'),
    (5019, 'piperacillin/tazobactam', 'Zosyn', 'Antibacterial', 'Beta-lactam/Inhibitor'),
    (5020, 'tobramycin', 'Tobrex', 'Antibacterial', 'Aminoglycoside'),
    (5021, 'vancomycin', 'Vancocin', 'Antibacterial', 'Glycopeptide'),
    (5022, 'fluconazole', 'Diflucan', 'Antifungal', 'Azole'),
    (5023, 'micafungin', 'Mycamine', 'Antifungal', 'Echinocandin'),
    (5024, 'amphotericin B', 'Fungizone', 'Antifungal', 'Polyene'),
    (5025, 'voriconazole', 'Vfend', 'Antifungal', 'Azole'),
    -- Additional antimicrobials for MDRO phenotype detection
    (5026, 'oxacillin', 'Bactocill', 'Antibacterial', 'Penicillin'),
    (5027, 'nafcillin', 'Nallpen', 'Antibacterial', 'Penicillin'),
    (5028, 'cefoxitin', 'Mefoxin', 'Antibacterial', 'Cephalosporin 2nd Gen'),
    (5029, 'cefotaxime', 'Claforan', 'Antibacterial', 'Cephalosporin 3rd Gen'),
    (5030, 'imipenem', 'Primaxin', 'Antibacterial', 'Carbapenem'),
    (5031, 'doripenem', 'Doribax', 'Antibacterial', 'Carbapenem');

-- NHSN antimicrobial code mappings
INSERT OR REPLACE INTO NHSN_ANTIMICROBIAL_MAP (MEDICATION_ID, NHSN_CODE, NHSN_CATEGORY, ATC_CODE, DDD, DDD_UNIT) VALUES
    (5001, 'AMK', 'Aminoglycosides', 'J01GB06', 1.0, 'g'),
    (5002, 'AMP', 'Penicillins', 'J01CA01', 2.0, 'g'),
    (5003, 'SAM', 'Beta-lactam/Inhibitor', 'J01CR01', 6.0, 'g'),
    (5004, 'AZM', 'Macrolides', 'J01FA10', 0.3, 'g'),
    (5005, 'ATM', 'Monobactams', 'J01DF01', 4.0, 'g'),
    (5006, 'CFZ', 'Cephalosporins 1st Gen', 'J01DB04', 3.0, 'g'),
    (5007, 'FEP', 'Cephalosporins 4th Gen', 'J01DE01', 2.0, 'g'),
    (5008, 'CAZ', 'Cephalosporins 3rd Gen', 'J01DD02', 4.0, 'g'),
    (5009, 'CRO', 'Cephalosporins 3rd Gen', 'J01DD04', 2.0, 'g'),
    (5010, 'CIP', 'Fluoroquinolones', 'J01MA02', 1.0, 'g'),
    (5011, 'CLI', 'Lincosamides', 'J01FF01', 1.2, 'g'),
    (5012, 'DAP', 'Lipopeptides', 'J01XX09', 0.28, 'g'),
    (5013, 'ETP', 'Carbapenems', 'J01DH03', 1.0, 'g'),
    (5014, 'GEN', 'Aminoglycosides', 'J01GB03', 0.24, 'g'),
    (5015, 'LVX', 'Fluoroquinolones', 'J01MA12', 0.5, 'g'),
    (5016, 'LZD', 'Oxazolidinones', 'J01XX08', 1.2, 'g'),
    (5017, 'MEM', 'Carbapenems', 'J01DH02', 2.0, 'g'),
    (5018, 'MTR', 'Nitroimidazoles', 'J01XD01', 1.5, 'g'),
    (5019, 'TZP', 'Beta-lactam/Inhibitor', 'J01CR05', 14.0, 'g'),
    (5020, 'TOB', 'Aminoglycosides', 'J01GB01', 0.24, 'g'),
    (5021, 'VAN', 'Glycopeptides', 'J01XA01', 2.0, 'g'),
    (5022, 'FLU', 'Antifungals - Azoles', 'J02AC01', 0.2, 'g'),
    (5023, 'MCF', 'Antifungals - Echinocandins', 'J02AX05', 0.1, 'g'),
    (5024, 'AMB', 'Antifungals - Polyenes', 'J02AA01', 0.035, 'g'),
    (5025, 'VRC', 'Antifungals - Azoles', 'J02AC03', 0.4, 'g'),
    -- Additional antimicrobials for MDRO phenotype detection
    (5026, 'OXA', 'Penicillins', 'J01CF04', 2.0, 'g'),
    (5027, 'NAF', 'Penicillins', 'J01CF06', 2.0, 'g'),
    (5028, 'FOX', 'Cephalosporins 2nd Gen', 'J01DC01', 6.0, 'g'),
    (5029, 'CTX', 'Cephalosporins 3rd Gen', 'J01DD01', 4.0, 'g'),
    (5030, 'IPM', 'Carbapenems', 'J01DH51', 2.0, 'g'),
    (5031, 'DOR', 'Carbapenems', 'J01DH04', 1.5, 'g');

-- NHSN Phenotype definitions for AR reporting
-- Aligned with CDC/NHSN definitions for consistency with MDRO Surveillance module
-- Reference: CDC NHSN Antimicrobial Use and Resistance Module Protocol
INSERT OR REPLACE INTO NHSN_PHENOTYPE_MAP (PHENOTYPE_ID, PHENOTYPE_CODE, PHENOTYPE_NAME, ORGANISM_PATTERN, RESISTANCE_PATTERN) VALUES
    -- MRSA: Staph aureus resistant to oxacillin (or methicillin/nafcillin/cefoxitin)
    (1, 'MRSA', 'Methicillin-resistant Staphylococcus aureus', 'Staphylococcus aureus', 'OXA:R|METH:R|NAF:R|FOX:R'),
    -- VRE: Enterococcus (faecalis or faecium) resistant to vancomycin
    (2, 'VRE', 'Vancomycin-resistant Enterococcus', 'Enterococcus%', 'VAN:R'),
    -- ESBL: Enterobacterales with extended-spectrum cephalosporin resistance
    -- Requires resistance to >=1 of: ceftriaxone, ceftazidime, cefotaxime, or aztreonam
    (3, 'ESBL', 'Extended-spectrum beta-lactamase', 'Escherichia coli|Klebsiella%|Proteus mirabilis', 'CRO:R|CAZ:R|CTX:R|ATM:R'),
    -- CRE: Enterobacterales resistant to at least one carbapenem
    -- Specific organism list matches CDC Enterobacterales definition
    (4, 'CRE', 'Carbapenem-resistant Enterobacterales', 'Escherichia coli|Klebsiella%|Enterobacter%|Citrobacter%|Serratia%|Proteus%|Morganella%|Providencia%|Salmonella%|Shigella%', 'MEM:R|IPM:R|ETP:R|DOR:R'),
    -- CRPA: Pseudomonas aeruginosa resistant to carbapenems
    (5, 'CRPA', 'Carbapenem-resistant Pseudomonas aeruginosa', 'Pseudomonas aeruginosa|Pseudomonas%', 'MEM:R|IPM:R|DOR:R'),
    -- CRAB: Acinetobacter baumannii resistant to carbapenems
    (6, 'CRAB', 'Carbapenem-resistant Acinetobacter baumannii', 'Acinetobacter baumannii|Acinetobacter%', 'MEM:R|IPM:R|DOR:R');
