"""
Guideline Adherence configuration.

Reads from django.conf.settings.GUIDELINE_ADHERENCE.
Contains LOINC code mappings and clinical thresholds.
"""

from django.conf import settings

_config = getattr(settings, 'GUIDELINE_ADHERENCE', {})

# FHIR
FHIR_BASE_URL = _config.get('FHIR_BASE_URL', 'http://localhost:8081/fhir')

# LLM
LLM_BACKEND = _config.get('LLM_BACKEND', 'ollama')
OLLAMA_BASE_URL = _config.get('OLLAMA_BASE_URL', 'http://localhost:11434')
FULL_MODEL = _config.get('FULL_MODEL', 'llama3.3:70b')
TRIAGE_MODEL = _config.get('TRIAGE_MODEL', 'qwen2.5:7b')

# Monitoring
CHECK_INTERVAL_MINUTES = _config.get('CHECK_INTERVAL_MINUTES', 15)
POLL_INTERVAL_SECONDS = _config.get('POLL_INTERVAL_SECONDS', 300)
ENABLED_BUNDLES = _config.get('ENABLED_BUNDLES', [])

# ============================================================================
# LOINC CODE MAPPINGS
# ============================================================================

# Common labs
LOINC_LACTATE = '2524-7'
LOINC_BLOOD_CULTURE = '600-7'
LOINC_TEMPERATURE = '8310-5'
LOINC_HEART_RATE = '8867-4'
LOINC_RESP_RATE = '9279-1'
LOINC_SPO2 = '2708-6'
LOINC_SBP = '8480-6'
LOINC_DBP = '8462-4'
LOINC_MAP = '8478-0'

# Febrile infant labs
LOINC_PROCALCITONIN = '33959-8'
LOINC_CRP = '1988-5'
LOINC_ANC = '26499-4'
LOINC_WBC = '6690-2'
LOINC_UA = '5767-9'
LOINC_URINE_CULTURE = '630-4'
LOINC_CSF_WBC = '10366-0'
LOINC_CSF_RBC = '10367-8'
LOINC_CSF_GLUCOSE = '2342-4'
LOINC_CSF_PROTEIN = '2880-3'

# HSV labs
LOINC_HSV_CSF_PCR = '16960-8'
LOINC_HSV_BLOOD_PCR = '16964-0'
LOINC_HSV_CULTURE = '5861-0'
LOINC_ALT = '1742-6'
LOINC_AST = '1920-8'

# C.diff labs
LOINC_CDIFF_TOXIN = '34713-8'
LOINC_CDIFF_PCR = '54067-4'
LOINC_CDIFF_GDH = '31585-3'

# UTI labs
LOINC_UA_WBC = '5821-4'
LOINC_RBUS = 'RBUS'  # Not a real LOINC - procedure code

# Chest X-ray
LOINC_CXR = '36643-5'

# ============================================================================
# CLINICAL THRESHOLDS (AAP 2021 Febrile Infant)
# ============================================================================

FI_PCT_ABNORMAL = 0.5        # ng/mL - procalcitonin
FI_ANC_ABNORMAL = 4000       # cells/μL
FI_CRP_ABNORMAL = 2.0        # mg/dL
FI_CSF_WBC_PLEOCYTOSIS = 15  # cells/μL
FI_UA_WBC_ABNORMAL = 5       # per HPF

# HSV thresholds
HSV_LFT_ELEVATED = 100       # U/L (elevated in neonates)

# ============================================================================
# ICD-10 CODE MAPPINGS
# ============================================================================

ICD10_SEPSIS = ['A41', 'A40', 'R65.2', 'P36']
ICD10_CAP = ['J13', 'J14', 'J15', 'J16', 'J17', 'J18']
ICD10_UTI = ['N10', 'N11', 'N12', 'N30', 'N39.0']
ICD10_SSTI = ['L03', 'L02']
ICD10_FEBRILE_INFANT = ['R50', 'P81.9']
ICD10_HSV = ['P35.2', 'B00', 'A60']
ICD10_CDIFF = ['A04.7']
ICD10_FEBRILE_NEUTROPENIA = ['D70']
