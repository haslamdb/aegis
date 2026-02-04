-- ============================================================================
-- AEGIS Gold Standard Case Extraction Queries
-- Target: Epic Clarity/Caboodle at Cincinnati Children's Hospital
-- Purpose: Pull structured data for CLABSI gold standard case library
-- 
-- IMPORTANT: These queries use standard Clarity table/column names.
-- Your local Clarity schema may have custom columns or different naming.
-- Work with your Clarity analysts to verify table names before running.
-- 
-- Usage: Replace @START_DATE, @END_DATE, and @PATIENT_LIST as needed.
-- Recommended: Pull 12-18 months of data while Vigilanz is still available.
-- ============================================================================

-- Set your date range (recommend: last 12-18 months)
-- DECLARE @START_DATE DATE = '2024-08-01';
-- DECLARE @END_DATE DATE = '2026-02-01';


-- ============================================================================
-- QUERY 1: BSI CANDIDATE IDENTIFICATION
-- Start here. This identifies all patients with positive blood cultures
-- during the date range, which is your universe of potential CLABSI cases.
-- ============================================================================

SELECT DISTINCT
    pat.PAT_MRN_ID                          AS mrn,
    pat.PAT_ID                              AS pat_id,
    enc.PAT_ENC_CSN_ID                      AS csn,
    enc.HOSP_ADMSN_TIME                     AS admission_datetime,
    enc.HOSP_DISCH_TIME                     AS discharge_datetime,
    dep.DEPARTMENT_NAME                     AS unit_at_culture,
    op.ORDER_PROC_ID                        AS culture_order_id,
    op.ORDER_INST                           AS culture_order_datetime,
    op.SPECIMN_TAKEN_TIME                   AS culture_collection_datetime,
    op.RESULT_TIME                          AS culture_result_datetime,
    orc.COMPONENT_NAME                      AS result_component,
    orr.ORD_VALUE                           AS organism,
    orr.RESULT_TIME                         AS result_finalized_datetime
FROM 
    PATIENT pat
    INNER JOIN PAT_ENC_HSP enc ON pat.PAT_ID = enc.PAT_ID
    INNER JOIN ORDER_PROC op ON enc.PAT_ENC_CSN_ID = op.PAT_ENC_CSN_ID
    INNER JOIN ORDER_RESULTS orr ON op.ORDER_PROC_ID = orr.ORDER_PROC_ID
    INNER JOIN CLARITY_COMPONENT orc ON orr.COMPONENT_ID = orc.COMPONENT_ID
    LEFT JOIN CLARITY_DEP dep ON enc.DEPARTMENT_ID = dep.DEPARTMENT_ID
WHERE
    op.PROC_CODE IN ('BLDCX', 'BCXAER', 'BCXAN')  -- Blood culture procedure codes
    -- NOTE: Verify your local proc codes for blood cultures. 
    -- Common alternatives: 'LAB123', 'BLOOD CULTURE', etc.
    -- Check with your Beaker/micro lab for exact codes.
    AND orr.ORD_VALUE IS NOT NULL                     -- Has an organism result
    AND orr.ORD_VALUE NOT LIKE '%No growth%'          -- Exclude negatives
    AND orr.ORD_VALUE NOT LIKE '%No organism%'
    AND op.SPECIMN_TAKEN_TIME >= @START_DATE
    AND op.SPECIMN_TAKEN_TIME < @END_DATE
ORDER BY
    pat.PAT_MRN_ID, op.SPECIMN_TAKEN_TIME;


-- ============================================================================
-- QUERY 2: CENTRAL LINE DEVICE DATA
-- For each BSI candidate, pull central line placement and removal.
-- This uses flowsheet data, which is where nursing documents devices.
-- 
-- NOTE: Flowsheet row IDs are institution-specific. You MUST verify these
-- with your Epic build team or flowsheet dictionary.
-- Common CCHMC flowsheet rows for CL documentation may differ.
-- ============================================================================

SELECT
    pat.PAT_MRN_ID                          AS mrn,
    enc.PAT_ENC_CSN_ID                      AS csn,
    fsd.FSD_ID                              AS flowsheet_id,
    flt.FLO_MEAS_NAME                       AS flowsheet_measure,
    fsd.RECORDED_TIME                       AS recorded_datetime,
    fsd.MEAS_VALUE                          AS value,
    dep.DEPARTMENT_NAME                     AS unit
FROM
    IP_FLWSHT_REC fsr
    INNER JOIN IP_FLWSHT_MEAS fsd ON fsr.FSD_ID = fsd.FSD_ID
    INNER JOIN IP_FLO_GP_DATA flt ON fsd.FLO_MEAS_ID = flt.FLO_MEAS_ID
    INNER JOIN PAT_ENC_HSP enc ON fsr.INPATIENT_DATA_ID = enc.INPATIENT_DATA_ID
    INNER JOIN PATIENT pat ON enc.PAT_ID = pat.PAT_ID
    LEFT JOIN CLARITY_DEP dep ON fsr.ADT_DEPARTMENT_ID = dep.DEPARTMENT_ID
WHERE
    -- IMPORTANT: Replace these FLO_MEAS_IDs with your local flowsheet row IDs
    -- for central line documentation. These are EXAMPLES ONLY.
    fsd.FLO_MEAS_ID IN (
        '30410',    -- Example: Central line type
        '30411',    -- Example: Central line insertion date  
        '30412',    -- Example: Central line removal date
        '30413',    -- Example: Central line site
        '30414',    -- Example: Central line lumen count
        '30420',    -- Example: PICC line insertion
        '30421'     -- Example: Umbilical line
        -- Also look for:
        -- IP LDA (Lines/Drains/Airways) data if your build uses that
        -- Infection Prevention device tracking flowsheets
    )
    AND enc.PAT_ENC_CSN_ID IN (/* INSERT CSNs FROM QUERY 1 */)
ORDER BY
    pat.PAT_MRN_ID, fsd.RECORDED_TIME;


-- ============================================================================
-- QUERY 2B: ALTERNATIVE - LDA (Lines/Drains/Airways) DATA
-- Many Epic builds use the LDA model for device tracking rather than 
-- flowsheets. Check which your build uses. LDA is more structured.
-- ============================================================================

SELECT
    pat.PAT_MRN_ID                          AS mrn,
    enc.PAT_ENC_CSN_ID                      AS csn,
    lda.DESCRIPTION                         AS device_description,
    lda.PLACEMENT_INSTANT                   AS placement_datetime,
    lda.REMOVAL_INSTANT                     AS removal_datetime,
    dep.DEPARTMENT_NAME                     AS placement_unit,
    lda.LDA_STATUS_C                        AS device_status  -- Active vs. removed
FROM
    IP_LDA_NOADD lda   -- or IP_LDA depending on your Clarity version
    INNER JOIN PAT_ENC_HSP enc ON lda.PAT_ENC_CSN_ID = enc.PAT_ENC_CSN_ID
    INNER JOIN PATIENT pat ON enc.PAT_ID = pat.PAT_ID
    LEFT JOIN CLARITY_DEP dep ON lda.DEPT_ID = dep.DEPARTMENT_ID
WHERE
    lda.DESCRIPTION LIKE '%central%'
    OR lda.DESCRIPTION LIKE '%PICC%'
    OR lda.DESCRIPTION LIKE '%Broviac%'
    OR lda.DESCRIPTION LIKE '%Hickman%'
    OR lda.DESCRIPTION LIKE '%port%'
    OR lda.DESCRIPTION LIKE '%umbilical%'
    OR lda.DESCRIPTION LIKE '%UVC%'
    OR lda.DESCRIPTION LIKE '%UAC%'
    -- Add other CL types per your institution's LDA naming
    AND enc.PAT_ENC_CSN_ID IN (/* INSERT CSNs FROM QUERY 1 */)
ORDER BY
    pat.PAT_MRN_ID, lda.PLACEMENT_INSTANT;


-- ============================================================================
-- QUERY 3: MICROBIOLOGY DETAILS
-- Full culture and susceptibility data for each BSI candidate.
-- Includes specimen source, all organisms, and susceptibility results.
-- ============================================================================

SELECT
    pat.PAT_MRN_ID                          AS mrn,
    enc.PAT_ENC_CSN_ID                      AS csn,
    op.ORDER_PROC_ID                        AS order_id,
    op.DESCRIPTION                          AS order_description,
    op.SPECIMN_TAKEN_TIME                   AS collection_datetime,
    op.RESULT_TIME                          AS result_datetime,
    orc.COMPONENT_NAME                      AS component,
    orr.ORD_VALUE                           AS value,
    orr.REFERENCE_LOW                       AS ref_low,
    orr.REFERENCE_HIGH                      AS ref_high,
    orr.RESULT_FLAG_C                       AS abnormal_flag,
    -- Susceptibility results often in separate components
    sens.COMPONENT_NAME                     AS susceptibility_antibiotic,
    sens_r.ORD_VALUE                        AS susceptibility_result,  -- S/I/R
    sens_r.REFERENCE_LOW                    AS mic_value
FROM
    PATIENT pat
    INNER JOIN PAT_ENC_HSP enc ON pat.PAT_ID = enc.PAT_ID
    INNER JOIN ORDER_PROC op ON enc.PAT_ENC_CSN_ID = op.PAT_ENC_CSN_ID
    INNER JOIN ORDER_RESULTS orr ON op.ORDER_PROC_ID = orr.ORDER_PROC_ID
    INNER JOIN CLARITY_COMPONENT orc ON orr.COMPONENT_ID = orc.COMPONENT_ID
    -- Self-join for susceptibility components linked to same order
    LEFT JOIN ORDER_RESULTS sens_r ON op.ORDER_PROC_ID = sens_r.ORDER_PROC_ID
        AND sens_r.COMPONENT_ID != orr.COMPONENT_ID
    LEFT JOIN CLARITY_COMPONENT sens ON sens_r.COMPONENT_ID = sens.COMPONENT_ID
        AND sens.COMPONENT_NAME LIKE '%suscept%'
WHERE
    op.PROC_CODE IN ('BLDCX', 'BCXAER', 'BCXAN')  -- Verify local codes
    AND enc.PAT_ENC_CSN_ID IN (/* INSERT CSNs FROM QUERY 1 */)
ORDER BY
    pat.PAT_MRN_ID, op.SPECIMN_TAKEN_TIME, orc.COMPONENT_NAME;


-- ============================================================================
-- QUERY 4: VITAL SIGNS (Temperature focus)
-- Pull temperature readings around the BSI event window.
-- NHSN requires: fever >38.0°C or hypothermia <36.0°C
-- Pull a window of -2 to +2 days around culture collection.
-- ============================================================================

SELECT
    pat.PAT_MRN_ID                          AS mrn,
    enc.PAT_ENC_CSN_ID                      AS csn,
    fsd.RECORDED_TIME                       AS vital_datetime,
    flt.FLO_MEAS_NAME                       AS vital_type,
    fsd.MEAS_VALUE                          AS vital_value
FROM
    IP_FLWSHT_REC fsr
    INNER JOIN IP_FLWSHT_MEAS fsd ON fsr.FSD_ID = fsd.FSD_ID
    INNER JOIN IP_FLO_GP_DATA flt ON fsd.FLO_MEAS_ID = flt.FLO_MEAS_ID
    INNER JOIN PAT_ENC_HSP enc ON fsr.INPATIENT_DATA_ID = enc.INPATIENT_DATA_ID
    INNER JOIN PATIENT pat ON enc.PAT_ID = pat.PAT_ID
WHERE
    flt.FLO_MEAS_NAME IN (
        'TEMPERATURE',          -- Verify local names
        'TEMP',
        'R TEMPERATURE',
        'HEART RATE',           -- For tachycardia criterion
        'RESPIRATORY RATE',     -- For tachypnea criterion  
        'BLOOD PRESSURE SYSTOLIC',  -- For hypotension criterion
        'BLOOD PRESSURE DIASTOLIC'
    )
    AND enc.PAT_ENC_CSN_ID IN (/* INSERT CSNs FROM QUERY 1 */)
    -- Optionally restrict to window around culture date:
    -- AND fsd.RECORDED_TIME BETWEEN DATEADD(DAY, -2, @CULTURE_DATE) 
    --     AND DATEADD(DAY, 2, @CULTURE_DATE)
ORDER BY
    pat.PAT_MRN_ID, fsd.RECORDED_TIME;


-- ============================================================================
-- QUERY 5: LAB RESULTS
-- WBC, bands, ANC (for MBI-LCBI criteria), CRP, procalcitonin
-- ============================================================================

SELECT
    pat.PAT_MRN_ID                          AS mrn,
    enc.PAT_ENC_CSN_ID                      AS csn,
    op.ORDER_PROC_ID                        AS order_id,
    op.SPECIMN_TAKEN_TIME                   AS collection_datetime,
    op.RESULT_TIME                          AS result_datetime,
    orc.COMPONENT_NAME                      AS lab_component,
    orr.ORD_VALUE                           AS lab_value,
    orr.REFERENCE_LOW                       AS ref_low,
    orr.REFERENCE_HIGH                      AS ref_high,
    orr.RESULT_FLAG_C                       AS abnormal_flag
FROM
    PATIENT pat
    INNER JOIN PAT_ENC_HSP enc ON pat.PAT_ID = enc.PAT_ID
    INNER JOIN ORDER_PROC op ON enc.PAT_ENC_CSN_ID = op.PAT_ENC_CSN_ID
    INNER JOIN ORDER_RESULTS orr ON op.ORDER_PROC_ID = orr.ORDER_PROC_ID
    INNER JOIN CLARITY_COMPONENT orc ON orr.COMPONENT_ID = orc.COMPONENT_ID
WHERE
    orc.COMPONENT_NAME IN (
        'WBC',                  -- White blood cell count
        'WHITE BLOOD CELL COUNT',
        'BAND NEUTROPHILS',     -- Bands / immature granulocytes
        'BANDS',
        'IMMATURE GRANULOCYTES',
        'ANC',                  -- Absolute neutrophil count (for MBI-LCBI)
        'ABSOLUTE NEUTROPHIL COUNT',
        'ANC CALCULATED',
        'PLATELET COUNT',       -- Thrombocytopenia criterion
        'CRP',                  -- C-reactive protein
        'C-REACTIVE PROTEIN',
        'PROCALCITONIN',
        'LACTIC ACID',          -- Lactate
        'LACTATE'
        -- Verify component names against your Clarity component dictionary
    )
    AND enc.PAT_ENC_CSN_ID IN (/* INSERT CSNs FROM QUERY 1 */)
ORDER BY
    pat.PAT_MRN_ID, op.SPECIMN_TAKEN_TIME, orc.COMPONENT_NAME;


-- ============================================================================
-- QUERY 6: ANTIMICROBIAL ORDERS AND ADMINISTRATION
-- For assessing empiric therapy, de-escalation, and treatment decisions.
-- MAR (Medication Administration Record) gives you what was actually given.
-- ============================================================================

SELECT
    pat.PAT_MRN_ID                          AS mrn,
    enc.PAT_ENC_CSN_ID                      AS csn,
    om.ORDER_MED_ID                         AS order_id,
    om.ORDERING_DATE                        AS order_datetime,
    om.DESCRIPTION                          AS medication_name,
    om.HV_GENERIC_NAME                      AS generic_name,
    om.MED_ROUTE_C                          AS route,       -- IV vs PO
    om.HV_DOSE_UNIT                         AS dose_unit,
    om.MED_DIS_DISP_QTY                     AS dose_quantity,
    om.FREQ_NAME                            AS frequency,
    om.START_DATE                            AS start_datetime,
    om.END_DATE                             AS end_datetime,
    om.ORDER_STATUS_C                       AS order_status, -- Active, completed, discontinued
    -- MAR administration data
    mar.TAKEN_TIME                          AS admin_datetime,
    mar.MAR_ACTION_C                        AS admin_action,  -- Given, held, refused
    mar.DOSE                                AS admin_dose,
    mar.DOSE_UNIT_C                         AS admin_dose_unit
FROM
    PATIENT pat
    INNER JOIN PAT_ENC_HSP enc ON pat.PAT_ID = enc.PAT_ID
    INNER JOIN ORDER_MED om ON enc.PAT_ENC_CSN_ID = om.PAT_ENC_CSN_ID
    LEFT JOIN MAR_ADMIN_INFO mar ON om.ORDER_MED_ID = mar.ORDER_MED_ID
WHERE
    -- Filter for antimicrobials using therapeutic class or pharm class
    -- NOTE: The exact column and values depend on your pharmacy build
    (
        om.PHARM_CLASS_NAME LIKE '%antibiotic%'
        OR om.PHARM_CLASS_NAME LIKE '%antifungal%'
        OR om.PHARM_CLASS_NAME LIKE '%antiviral%'
        OR om.THERA_CLASS_NAME LIKE '%anti-infect%'
        -- Or use specific medication names if pharm class isn't reliable:
        -- OR om.HV_GENERIC_NAME IN ('vancomycin', 'meropenem', 'cefepime', ...)
    )
    AND enc.PAT_ENC_CSN_ID IN (/* INSERT CSNs FROM QUERY 1 */)
ORDER BY
    pat.PAT_MRN_ID, om.ORDERING_DATE;


-- ============================================================================
-- QUERY 7: CLINICAL NOTES
-- Pull progress notes, ID consult notes, microbiology comments.
-- These are what the LLM will process. 
--
-- WARNING: Note text can be very large. Consider pulling only notes 
-- within a window around the BSI event (e.g., -3 to +3 days).
-- ============================================================================

SELECT
    pat.PAT_MRN_ID                          AS mrn,
    enc.PAT_ENC_CSN_ID                      AS csn,
    hno.NOTE_ID                             AS note_id,
    hno.IP_NOTE_TYPE_C                      AS note_type_code,
    znt.NAME                                AS note_type_name,
    hno.NOTE_STATUS_C                       AS note_status,
    hno.ENTRY_INSTANT_DTTM                  AS note_datetime,
    hno.AUTHOR_PROV_ID                      AS author_id,
    ser.PROV_NAME                           AS author_name,
    ser.SPECIALTY                            AS author_specialty,
    -- Note text - may be in HNO_NOTE_TEXT or NOTE_ENC_INFO depending on version
    nt.NOTE_TEXT                             AS note_text,
    nt.LINE                                 AS text_line_number
FROM
    HNO_INFO hno
    INNER JOIN PAT_ENC_HSP enc ON hno.PAT_ENC_CSN_ID = enc.PAT_ENC_CSN_ID
    INNER JOIN PATIENT pat ON enc.PAT_ID = pat.PAT_ID
    LEFT JOIN HNO_NOTE_TEXT nt ON hno.NOTE_ID = nt.NOTE_ID
    LEFT JOIN ZC_IP_NOTE_TYPE znt ON hno.IP_NOTE_TYPE_C = znt.IP_NOTE_TYPE_C
    LEFT JOIN CLARITY_SER ser ON hno.AUTHOR_PROV_ID = ser.PROV_ID
WHERE
    -- Focus on note types most relevant to BSI evaluation
    znt.NAME IN (
        'Progress Notes',
        'H&P',
        'Consult Note',           -- ID consult notes
        'Infectious Disease',
        'Critical Care',
        'Neonatology',
        'Discharge Summary',
        'Procedure Note',         -- For line insertion documentation
        'Nursing Note',
        'Pharmacy Note'
        -- Your note type names may differ - check ZC_IP_NOTE_TYPE
    )
    AND hno.NOTE_STATUS_C = 2     -- Signed/finalized notes only (verify code)
    AND enc.PAT_ENC_CSN_ID IN (/* INSERT CSNs FROM QUERY 1 */)
ORDER BY
    pat.PAT_MRN_ID, hno.ENTRY_INSTANT_DTTM, nt.LINE;


-- ============================================================================
-- QUERY 8: PATIENT DEMOGRAPHICS AND ENCOUNTER DETAILS
-- ============================================================================

SELECT
    pat.PAT_MRN_ID                          AS mrn,
    pat.PAT_ID                              AS pat_id,
    enc.PAT_ENC_CSN_ID                      AS csn,
    -- Demographics
    pat.BIRTH_DATE                          AS dob,
    DATEDIFF(MONTH, pat.BIRTH_DATE, enc.HOSP_ADMSN_TIME) AS age_months_at_admit,
    pat.SEX_C                               AS sex,
    -- Encounter details
    enc.HOSP_ADMSN_TIME                     AS admission_datetime,
    enc.HOSP_DISCH_TIME                     AS discharge_datetime,
    dep.DEPARTMENT_NAME                     AS admitting_unit,
    enc.ADT_PAT_CLASS_C                     AS patient_class,
    -- Service / attending
    enc.ATTEND_PROV_ID                      AS attending_id,
    ser.PROV_NAME                           AS attending_name,
    ser.SPECIALTY                            AS attending_specialty,
    -- Diagnosis context (for identifying oncology, transplant, etc.)
    edg.CURRENT_ICD10_LIST                  AS diagnosis_codes
FROM
    PATIENT pat
    INNER JOIN PAT_ENC_HSP enc ON pat.PAT_ID = enc.PAT_ID
    LEFT JOIN CLARITY_DEP dep ON enc.DEPARTMENT_ID = dep.DEPARTMENT_ID
    LEFT JOIN CLARITY_SER ser ON enc.ATTEND_PROV_ID = ser.PROV_ID
    LEFT JOIN PAT_ENC_DX edx ON enc.PAT_ENC_CSN_ID = edx.PAT_ENC_CSN_ID
    LEFT JOIN CLARITY_EDG edg ON edx.DX_ID = edg.DX_ID
WHERE
    enc.PAT_ENC_CSN_ID IN (/* INSERT CSNs FROM QUERY 1 */)
ORDER BY
    pat.PAT_MRN_ID;


-- ============================================================================
-- QUERY 9: CONCURRENT INFECTIONS (for secondary BSI determination)
-- Pull other positive cultures (urine, respiratory, wound) to identify
-- potential primary infection sources that would make a BSI "secondary"
-- rather than primary/CLABSI.
-- ============================================================================

SELECT
    pat.PAT_MRN_ID                          AS mrn,
    enc.PAT_ENC_CSN_ID                      AS csn,
    op.ORDER_PROC_ID                        AS order_id,
    op.DESCRIPTION                          AS culture_type,
    op.SPECIMN_TAKEN_TIME                   AS collection_datetime,
    orc.COMPONENT_NAME                      AS component,
    orr.ORD_VALUE                           AS result_value
FROM
    PATIENT pat
    INNER JOIN PAT_ENC_HSP enc ON pat.PAT_ID = enc.PAT_ID
    INNER JOIN ORDER_PROC op ON enc.PAT_ENC_CSN_ID = op.PAT_ENC_CSN_ID
    INNER JOIN ORDER_RESULTS orr ON op.ORDER_PROC_ID = orr.ORDER_PROC_ID
    INNER JOIN CLARITY_COMPONENT orc ON orr.COMPONENT_ID = orc.COMPONENT_ID
WHERE
    -- Non-blood culture micro orders
    op.PROC_CODE IN (
        'URNCX',    -- Urine culture (verify local code)
        'RSPCX',    -- Respiratory culture
        'WNDCX',    -- Wound culture
        'CSFCX',    -- CSF culture
        'PRFLCX',   -- Peritoneal fluid
        'STLCX'     -- Stool culture (for C. diff context)
        -- Verify all proc codes with your micro lab
    )
    AND orr.ORD_VALUE IS NOT NULL
    AND orr.ORD_VALUE NOT LIKE '%No growth%'
    AND orr.ORD_VALUE NOT LIKE '%Normal flora%'
    AND enc.PAT_ENC_CSN_ID IN (/* INSERT CSNs FROM QUERY 1 */)
ORDER BY
    pat.PAT_MRN_ID, op.SPECIMN_TAKEN_TIME;


-- ============================================================================
-- QUERY 10: MUCOSITIS / ANC DATA FOR MBI-LCBI DETERMINATION
-- For oncology patients - pull mucositis documentation and ANC trends
-- ============================================================================

SELECT
    pat.PAT_MRN_ID                          AS mrn,
    enc.PAT_ENC_CSN_ID                      AS csn,
    -- Mucositis from flowsheets (institution-specific)
    fsd.RECORDED_TIME                       AS assessment_datetime,
    flt.FLO_MEAS_NAME                       AS assessment_type,
    fsd.MEAS_VALUE                          AS assessment_value
FROM
    IP_FLWSHT_REC fsr
    INNER JOIN IP_FLWSHT_MEAS fsd ON fsr.FSD_ID = fsd.FSD_ID
    INNER JOIN IP_FLO_GP_DATA flt ON fsd.FLO_MEAS_ID = flt.FLO_MEAS_ID
    INNER JOIN PAT_ENC_HSP enc ON fsr.INPATIENT_DATA_ID = enc.INPATIENT_DATA_ID
    INNER JOIN PATIENT pat ON enc.PAT_ID = pat.PAT_ID
WHERE
    (
        flt.FLO_MEAS_NAME LIKE '%mucositis%'
        OR flt.FLO_MEAS_NAME LIKE '%oral assessment%'
        OR flt.FLO_MEAS_NAME LIKE '%mouth care%'
        OR flt.FLO_MEAS_NAME LIKE '%GI assessment%'
        -- Check your oncology-specific flowsheets
    )
    AND enc.PAT_ENC_CSN_ID IN (/* INSERT CSNs FROM QUERY 1 */)
ORDER BY
    pat.PAT_MRN_ID, fsd.RECORDED_TIME;


-- ============================================================================
-- CROSS-VALIDATION QUERY: COMPARE AGAINST VIGILANZ
-- If you can export your Vigilanz case list, use this to map Vigilanz
-- cases to Clarity encounters for side-by-side comparison.
-- 
-- You'll need to join on MRN + date range since Vigilanz and Epic
-- use different internal IDs.
-- ============================================================================

-- Step 1: Export from Vigilanz (CSV or similar):
--   MRN, EventDate, Classification, Organism, CentralLineType
-- 
-- Step 2: Load into a temp table in Clarity:
--   CREATE TABLE #VIGILANZ_CASES (
--       MRN VARCHAR(20),
--       EVENT_DATE DATE,
--       CLASSIFICATION VARCHAR(50),
--       ORGANISM VARCHAR(200),
--       CL_TYPE VARCHAR(100)
--   );
--   -- BULK INSERT or manual load from CSV
-- 
-- Step 3: Map to Clarity encounters:
-- SELECT
--     vc.*,
--     enc.PAT_ENC_CSN_ID,
--     enc.HOSP_ADMSN_TIME,
--     enc.HOSP_DISCH_TIME
-- FROM
--     #VIGILANZ_CASES vc
--     INNER JOIN PATIENT pat ON vc.MRN = pat.PAT_MRN_ID
--     INNER JOIN PAT_ENC_HSP enc ON pat.PAT_ID = enc.PAT_ID
--         AND vc.EVENT_DATE BETWEEN CAST(enc.HOSP_ADMSN_TIME AS DATE) 
--             AND ISNULL(CAST(enc.HOSP_DISCH_TIME AS DATE), GETDATE())
-- ORDER BY vc.MRN, vc.EVENT_DATE;
