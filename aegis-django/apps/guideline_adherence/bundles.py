"""
Guideline bundle definitions for AEGIS.

9 evidence-based clinical guideline bundles for pediatric care.
Adapted from Flask guideline_adherence.py (~1365 lines).
"""

from dataclasses import dataclass, field
from django.conf import settings


@dataclass
class BundleElement:
    """Single element within a guideline bundle."""
    element_id: str
    name: str
    description: str
    required: bool = True
    time_window_hours: float | None = None
    data_source: str = 'fhir'      # fhir, notes, vitals, orders
    checker_type: str = 'lab'      # lab, medication, note, febrile_infant, hsv, cdiff


@dataclass
class TriggerCriteria:
    """Criteria for triggering a bundle."""
    trigger_type: str              # diagnosis, order, lab
    icd10_prefixes: list[str] = field(default_factory=list)
    loinc_codes: list[str] = field(default_factory=list)
    cpt_codes: list[str] = field(default_factory=list)
    min_age_days: int | None = None
    max_age_days: int | None = None
    description: str = ''


@dataclass
class GuidelineBundle:
    """Complete guideline bundle definition."""
    bundle_id: str
    name: str
    description: str
    version: str
    elements: list[BundleElement]
    trigger_criteria: list[TriggerCriteria] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


# ============================================================================
# BUNDLE DEFINITIONS
# ============================================================================

SEPSIS_BUNDLE = GuidelineBundle(
    bundle_id='sepsis_peds_2024',
    name='Pediatric Sepsis Bundle',
    description='Evidence-based sepsis management bundle for pediatric patients. '
                'Includes blood cultures, lactate, empiric antibiotics within 1 hour, '
                'fluid resuscitation, and 48-hour reassessment.',
    version='2024.1',
    trigger_criteria=[
        TriggerCriteria(
            trigger_type='diagnosis',
            icd10_prefixes=['A41', 'A40', 'R65.2', 'P36'],
            description='Sepsis or septic shock diagnosis',
        ),
    ],
    elements=[
        BundleElement(
            element_id='sepsis_blood_cx',
            name='Blood Culture',
            description='Blood culture obtained before antibiotics',
            time_window_hours=1.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='sepsis_lactate',
            name='Serum Lactate',
            description='Serum lactate level obtained',
            time_window_hours=3.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='sepsis_abx_1hr',
            name='Antibiotics Within 1 Hour',
            description='Broad-spectrum antibiotics administered within 1 hour of recognition',
            time_window_hours=1.0,
            checker_type='medication',
        ),
        BundleElement(
            element_id='sepsis_fluid_bolus',
            name='Fluid Bolus (if shock)',
            description='20 mL/kg crystalloid bolus if hypotension or hypoperfusion',
            required=False,
            time_window_hours=1.0,
            checker_type='medication',
        ),
        BundleElement(
            element_id='sepsis_repeat_lactate',
            name='Repeat Lactate (if elevated)',
            description='Repeat lactate within 6 hours if initial >2 mmol/L',
            required=False,
            time_window_hours=6.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='sepsis_reassess_48h',
            name='48-Hour Reassessment',
            description='Antibiotic reassessment with culture review at 48 hours',
            time_window_hours=72.0,
            checker_type='note',
        ),
    ],
    references=[
        'Surviving Sepsis Campaign International Guidelines 2021',
        'CCHMC Sepsis Pathway 2024',
    ],
)

CAP_BUNDLE = GuidelineBundle(
    bundle_id='cap_peds_2024',
    name='Community-Acquired Pneumonia',
    description='Evidence-based management of community-acquired pneumonia in children >3 months. '
                'Includes imaging, oxygen assessment, appropriate antibiotic selection, '
                'duration control, and follow-up planning.',
    version='2024.1',
    trigger_criteria=[
        TriggerCriteria(
            trigger_type='diagnosis',
            icd10_prefixes=['J13', 'J14', 'J15', 'J16', 'J17', 'J18'],
            min_age_days=90,
            description='Pneumonia diagnosis in children >3 months',
        ),
    ],
    elements=[
        BundleElement(
            element_id='cap_cxr',
            name='Chest X-ray',
            description='Chest radiograph obtained',
            time_window_hours=4.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='cap_spo2',
            name='Pulse Oximetry',
            description='Oxygen saturation assessed',
            time_window_hours=1.0,
            data_source='vitals',
            checker_type='lab',
        ),
        BundleElement(
            element_id='cap_abx',
            name='Appropriate Antibiotics',
            description='Guideline-concordant antibiotic initiated (amoxicillin or ampicillin first-line)',
            time_window_hours=4.0,
            checker_type='medication',
        ),
        BundleElement(
            element_id='cap_blood_cx_severe',
            name='Blood Culture (if severe)',
            description='Blood culture for severe or hospitalized pneumonia',
            required=False,
            time_window_hours=4.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='cap_duration',
            name='Duration Control',
            description='Antibiotic course planned for <=7 days for uncomplicated CAP',
            time_window_hours=None,
            checker_type='note',
        ),
        BundleElement(
            element_id='cap_followup',
            name='Follow-up Arranged',
            description='Follow-up visit arranged before discharge',
            time_window_hours=None,
            checker_type='note',
        ),
    ],
    references=[
        'IDSA/PIDS CAP Guidelines 2011 (updated 2019)',
        'CCHMC CAP Evidence-Based Care Guideline 2024',
    ],
)

UTI_BUNDLE = GuidelineBundle(
    bundle_id='uti_peds_2024',
    name='Pediatric UTI',
    description='Evidence-based management of urinary tract infections in children. '
                'Includes urine collection, culture, empiric therapy, culture-directed '
                'narrowing, and imaging assessment.',
    version='2024.1',
    trigger_criteria=[
        TriggerCriteria(
            trigger_type='diagnosis',
            icd10_prefixes=['N10', 'N11', 'N12', 'N30', 'N39.0'],
            description='UTI diagnosis',
        ),
    ],
    elements=[
        BundleElement(
            element_id='uti_ua',
            name='Urinalysis',
            description='Urinalysis obtained (catheterized specimen for infants)',
            time_window_hours=2.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='uti_urine_cx',
            name='Urine Culture',
            description='Urine culture obtained before antibiotics',
            time_window_hours=2.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='uti_culture_confirms',
            name='Culture Confirmation',
            description='Urine culture confirms diagnosis (>=50,000 CFU/mL catheterized)',
            time_window_hours=72.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='uti_empiric_abx',
            name='Empiric Antibiotics',
            description='Appropriate empiric antibiotic initiated',
            time_window_hours=4.0,
            checker_type='medication',
        ),
        BundleElement(
            element_id='uti_narrow_to_culture',
            name='Narrow to Culture',
            description='Antibiotics narrowed based on culture results',
            time_window_hours=72.0,
            checker_type='note',
        ),
        BundleElement(
            element_id='uti_rbus',
            name='Renal Ultrasound (if febrile <2y)',
            description='Renal/bladder ultrasound for febrile UTI in children <2 years',
            required=False,
            time_window_hours=48.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='uti_vcug',
            name='VCUG Consideration',
            description='VCUG consideration documented (for recurrent UTI or abnormal RBUS)',
            required=False,
            time_window_hours=None,
            checker_type='note',
        ),
    ],
    references=[
        'AAP UTI Guidelines 2011 (reaffirmed 2016)',
        'CCHMC UTI Evidence-Based Care Guideline 2024',
    ],
)

SSTI_BUNDLE = GuidelineBundle(
    bundle_id='ssti_peds_2024',
    name='SSTI (Skin & Soft Tissue Infection)',
    description='Evidence-based management of skin and soft tissue infections. '
                'Includes wound assessment, MRSA coverage decisions, I&D for abscess, '
                'and antibiotic stewardship for simple abscesses.',
    version='2024.1',
    trigger_criteria=[
        TriggerCriteria(
            trigger_type='diagnosis',
            icd10_prefixes=['L03', 'L02'],
            description='Cellulitis or abscess diagnosis',
        ),
    ],
    elements=[
        BundleElement(
            element_id='ssti_margins',
            name='Margins Marked',
            description='Cellulitis margins marked and documented in nursing assessment',
            time_window_hours=12.0,
            checker_type='note',
        ),
        BundleElement(
            element_id='ssti_mrsa_coverage',
            name='MRSA Coverage (if purulent)',
            description='MRSA-active antibiotic for purulent cellulitis or abscess',
            required=False,
            time_window_hours=4.0,
            checker_type='medication',
        ),
        BundleElement(
            element_id='ssti_id_if_abscess',
            name='I&D (if abscess)',
            description='Incision and drainage performed for drainable abscess',
            required=False,
            time_window_hours=24.0,
            checker_type='note',
        ),
        BundleElement(
            element_id='ssti_wound_cx',
            name='Wound Culture',
            description='Wound culture obtained from abscess drainage',
            required=False,
            time_window_hours=24.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='ssti_no_abx_simple',
            name='No Antibiotics for Simple Abscess',
            description='Simple abscess after I&D does not require antibiotics unless immunocompromised',
            required=False,
            time_window_hours=None,
            checker_type='note',
        ),
        BundleElement(
            element_id='ssti_reassess_48h',
            name='48-Hour Reassessment',
            description='Clinical reassessment at 48 hours (margins, response to therapy)',
            time_window_hours=72.0,
            checker_type='note',
        ),
    ],
    references=[
        'IDSA SSTI Guidelines 2014',
        'CCHMC SSTI Evidence-Based Care Guideline 2024',
    ],
)

SURGICAL_PROPHYLAXIS_BUNDLE = GuidelineBundle(
    bundle_id='surgical_prophy_2024',
    name='Surgical Antimicrobial Prophylaxis',
    description='Surgical prophylaxis bundle elements for compliance tracking. '
                'Note: Detailed real-time monitoring is handled by the dedicated '
                'surgical prophylaxis module.',
    version='2024.1',
    trigger_criteria=[
        TriggerCriteria(
            trigger_type='order',
            description='Surgical case scheduled',
        ),
    ],
    elements=[
        BundleElement(
            element_id='sp_selection',
            name='Appropriate Agent Selection',
            description='ASHP/IDSA guideline-concordant antibiotic selected',
            time_window_hours=None,
            checker_type='medication',
        ),
        BundleElement(
            element_id='sp_timing',
            name='Timing Within 60 Minutes',
            description='Antibiotic administered within 60 minutes before incision',
            time_window_hours=1.0,
            checker_type='medication',
        ),
        BundleElement(
            element_id='sp_weight_dose',
            name='Weight-Based Dosing',
            description='Dose calculated based on patient weight per guidelines',
            time_window_hours=None,
            checker_type='medication',
        ),
        BundleElement(
            element_id='sp_redosing',
            name='Intraoperative Redosing',
            description='Redosing administered for prolonged cases per drug half-life',
            required=False,
            time_window_hours=None,
            checker_type='medication',
        ),
        BundleElement(
            element_id='sp_discontinuation',
            name='Discontinuation Within 48 Hours',
            description='Prophylaxis discontinued within 48 hours of surgery end',
            time_window_hours=48.0,
            checker_type='medication',
        ),
    ],
    references=[
        'ASHP Clinical Practice Guidelines 2013',
        'CCHMC Surgical Prophylaxis Protocol 2024',
    ],
)

FEBRILE_NEUTROPENIA_BUNDLE = GuidelineBundle(
    bundle_id='fn_peds_2024',
    name='Febrile Neutropenia',
    description='Evidence-based management of febrile neutropenia in pediatric oncology patients. '
                'Includes rapid blood cultures, empiric antibiotics within 1 hour, '
                'risk stratification, and daily assessment.',
    version='2024.1',
    trigger_criteria=[
        TriggerCriteria(
            trigger_type='diagnosis',
            icd10_prefixes=['D70'],
            description='Neutropenia with fever',
        ),
    ],
    elements=[
        BundleElement(
            element_id='fn_blood_cx_peripheral',
            name='Blood Culture (Peripheral)',
            description='Peripheral blood culture obtained',
            time_window_hours=1.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='fn_blood_cx_central',
            name='Blood Culture (Central Line)',
            description='Central line blood culture if CVC present',
            required=False,
            time_window_hours=1.0,
            checker_type='lab',
        ),
        BundleElement(
            element_id='fn_abx_1hr',
            name='Antibiotics Within 1 Hour',
            description='Empiric broad-spectrum antibiotics within 1 hour of triage',
            time_window_hours=1.0,
            checker_type='medication',
        ),
        BundleElement(
            element_id='fn_appropriate_regimen',
            name='Appropriate Regimen',
            description='Anti-pseudomonal beta-lactam (cefepime, piperacillin-tazobactam, or meropenem)',
            time_window_hours=1.0,
            checker_type='medication',
        ),
        BundleElement(
            element_id='fn_risk_stratification',
            name='Risk Stratification',
            description='Risk stratification documented (high vs low risk)',
            time_window_hours=4.0,
            checker_type='note',
        ),
        BundleElement(
            element_id='fn_daily_assessment',
            name='Daily Assessment',
            description='Daily assessment with culture review and de-escalation consideration',
            time_window_hours=48.0,
            checker_type='note',
        ),
    ],
    references=[
        'IDSA Febrile Neutropenia Guidelines 2011 (updated 2018)',
        'COG Supportive Care Guidelines 2023',
        'CCHMC Febrile Neutropenia Pathway 2024',
    ],
)

FEBRILE_INFANT_BUNDLE = GuidelineBundle(
    bundle_id='febrile_infant_2024',
    name='Febrile Infant (8-60 days)',
    description='AAP 2021 clinical practice guideline for well-appearing febrile infants 8-60 days. '
                'Age-stratified workup with inflammatory marker-guided management. '
                'Includes HSV risk assessment for neonates.',
    version='2024.1',
    trigger_criteria=[
        TriggerCriteria(
            trigger_type='diagnosis',
            icd10_prefixes=['R50', 'P81.9'],
            min_age_days=8,
            max_age_days=60,
            description='Fever in infant 8-60 days old',
        ),
    ],
    elements=[
        BundleElement(
            element_id='fi_ua',
            name='Urinalysis',
            description='Urinalysis obtained (catheterized specimen)',
            time_window_hours=2.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_blood_cx',
            name='Blood Culture',
            description='Blood culture obtained',
            time_window_hours=2.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_inflammatory_markers',
            name='Inflammatory Markers',
            description='ANC and CRP obtained (all ages 8-60 days)',
            time_window_hours=2.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_procalcitonin',
            name='Procalcitonin',
            description='Procalcitonin obtained (recommended for 29-60 day infants)',
            required=False,
            time_window_hours=2.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_lp',
            name='Lumbar Puncture',
            description='LP performed (required 8-21 days; conditional 22-28 days if IMs abnormal)',
            required=False,
            time_window_hours=4.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_urine_cx',
            name='Urine Culture',
            description='Urine culture obtained',
            time_window_hours=2.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_parenteral_abx',
            name='Parenteral Antibiotics',
            description='Parenteral antibiotics if indicated by age/inflammatory markers',
            required=False,
            time_window_hours=4.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_hsv_risk',
            name='HSV Risk Assessment',
            description='HSV risk factors assessed (maternal history, vesicles, ill-appearing)',
            time_window_hours=4.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_acyclovir',
            name='Acyclovir (if HSV risk)',
            description='Acyclovir initiated if HSV risk factors present',
            required=False,
            time_window_hours=1.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_clinical_impression',
            name='Clinical Impression',
            description='Clinical appearance documented (well vs ill-appearing)',
            time_window_hours=2.0,
            checker_type='febrile_infant',
            data_source='notes',
        ),
        BundleElement(
            element_id='fi_admission',
            name='Admission Decision',
            description='Admission for 8-28 day infants; disposition per IMs for 29-60 days',
            time_window_hours=8.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_repeat_im',
            name='Repeat Inflammatory Markers',
            description='Repeat inflammatory markers before discharge if initially abnormal',
            required=False,
            time_window_hours=48.0,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_safe_discharge',
            name='Safe Discharge Checklist',
            description='5-item checklist: follow-up 24h, phone, transportation, parent education, return precautions',
            required=False,
            time_window_hours=None,
            checker_type='febrile_infant',
        ),
        BundleElement(
            element_id='fi_disposition',
            name='Disposition',
            description='Final disposition documented (admit/discharge with plan)',
            time_window_hours=24.0,
            checker_type='febrile_infant',
        ),
    ],
    references=[
        'AAP Clinical Practice Guideline: Febrile Infants 8-60 Days (2021)',
        'CCHMC Febrile Infant Evidence-Based Care Guideline 2024',
    ],
)

NEONATAL_HSV_BUNDLE = GuidelineBundle(
    bundle_id='neonatal_hsv_2024',
    name='Neonatal HSV',
    description='CCHMC 2024 algorithm for evaluation and management of suspected neonatal HSV '
                'in infants <=21 days. Includes comprehensive workup, classification-based '
                'treatment duration, and suppressive therapy planning.',
    version='2024.1',
    trigger_criteria=[
        TriggerCriteria(
            trigger_type='diagnosis',
            icd10_prefixes=['P35.2', 'B00', 'A60'],
            max_age_days=21,
            description='Suspected HSV in neonate <=21 days',
        ),
    ],
    elements=[
        BundleElement(
            element_id='hsv_csf_pcr',
            name='CSF HSV PCR',
            description='CSF sent for HSV PCR testing',
            time_window_hours=4.0,
            checker_type='hsv',
        ),
        BundleElement(
            element_id='hsv_surface_cultures',
            name='Surface Cultures (SEM)',
            description='Surface swabs (skin, eye, mouth) sent for HSV culture',
            time_window_hours=4.0,
            checker_type='hsv',
        ),
        BundleElement(
            element_id='hsv_blood_pcr',
            name='Blood HSV PCR',
            description='Blood sent for HSV PCR testing',
            time_window_hours=4.0,
            checker_type='hsv',
        ),
        BundleElement(
            element_id='hsv_lfts',
            name='Liver Function Tests',
            description='ALT and AST obtained (elevated in disseminated disease)',
            time_window_hours=4.0,
            checker_type='hsv',
        ),
        BundleElement(
            element_id='hsv_acyclovir_started',
            name='Acyclovir Started',
            description='IV acyclovir initiated within 1 hour of recognition',
            time_window_hours=1.0,
            checker_type='hsv',
        ),
        BundleElement(
            element_id='hsv_acyclovir_dose',
            name='Proper Acyclovir Dosing',
            description='Acyclovir 20 mg/kg IV Q8H (60 mg/kg/day)',
            time_window_hours=4.0,
            checker_type='hsv',
        ),
        BundleElement(
            element_id='hsv_id_consult',
            name='ID Consult',
            description='Infectious Disease consultation ordered',
            time_window_hours=24.0,
            checker_type='hsv',
        ),
        BundleElement(
            element_id='hsv_ophthalmology',
            name='Ophthalmology Consult',
            description='Ophthalmology consultation if ocular involvement',
            required=False,
            time_window_hours=48.0,
            checker_type='hsv',
        ),
        BundleElement(
            element_id='hsv_neuroimaging',
            name='Neuroimaging',
            description='Brain MRI if CNS involvement suspected',
            required=False,
            time_window_hours=72.0,
            checker_type='hsv',
        ),
        BundleElement(
            element_id='hsv_treatment_duration',
            name='Treatment Duration',
            description='SEM: 14 days, CNS/Disseminated: 21 days IV acyclovir',
            time_window_hours=None,
            checker_type='hsv',
        ),
        BundleElement(
            element_id='hsv_suppressive',
            name='Suppressive Therapy',
            description='Oral acyclovir suppressive therapy planned (6 months post-treatment)',
            required=False,
            time_window_hours=None,
            checker_type='hsv',
        ),
    ],
    references=[
        'AAP Red Book: Herpes Simplex Virus 2024',
        'CCHMC Neonatal HSV Algorithm 2024',
    ],
)

CDIFF_TESTING_BUNDLE = GuidelineBundle(
    bundle_id='cdiff_testing_2024',
    name='C. difficile Testing Stewardship',
    description='Diagnostic stewardship bundle for C. difficile testing in children. '
                'Ensures testing appropriateness by verifying pre-test criteria '
                'before resulting. Reduces unnecessary testing in low-risk patients.',
    version='2024.1',
    trigger_criteria=[
        TriggerCriteria(
            trigger_type='order',
            loinc_codes=['34713-8', '54067-4', '31585-3'],
            min_age_days=365 * 3,  # 3 years
            description='C. diff test ordered',
        ),
    ],
    elements=[
        BundleElement(
            element_id='cdiff_age_appropriate',
            name='Age Appropriate',
            description='Patient age >= 3 years (or exception documented)',
            time_window_hours=None,
            checker_type='cdiff',
        ),
        BundleElement(
            element_id='cdiff_liquid_stools',
            name='Liquid Stools (>=3 in 24h)',
            description='>= 3 liquid/watery stools in past 24 hours documented',
            time_window_hours=None,
            checker_type='cdiff',
        ),
        BundleElement(
            element_id='cdiff_no_laxatives',
            name='No Laxatives (48h)',
            description='No laxatives administered in past 48 hours',
            time_window_hours=None,
            checker_type='cdiff',
        ),
        BundleElement(
            element_id='cdiff_no_contrast',
            name='No Enteral Contrast (48h)',
            description='No enteral contrast given in past 48 hours',
            time_window_hours=None,
            checker_type='cdiff',
        ),
        BundleElement(
            element_id='cdiff_no_tube_feed',
            name='No Tube Feed Changes (48h)',
            description='No tube feeding changes in past 48 hours',
            time_window_hours=None,
            checker_type='cdiff',
        ),
        BundleElement(
            element_id='cdiff_no_gi_bleed',
            name='No Active GI Bleed',
            description='No active gastrointestinal bleeding',
            time_window_hours=None,
            checker_type='cdiff',
        ),
        BundleElement(
            element_id='cdiff_risk_factor',
            name='Risk Factor Present',
            description='At least one C. diff risk factor documented (antibiotics, hospitalization, PPI, etc.)',
            time_window_hours=None,
            checker_type='cdiff',
        ),
        BundleElement(
            element_id='cdiff_symptom_duration',
            name='Symptom Duration (if low risk)',
            description='Symptoms persist >= 48 hours for low-risk patients',
            required=False,
            time_window_hours=None,
            checker_type='cdiff',
        ),
    ],
    references=[
        'IDSA/SHEA C. difficile Guidelines 2018',
        'CCHMC C. difficile Testing Stewardship Protocol 2024',
    ],
)


# ============================================================================
# BUNDLE REGISTRY
# ============================================================================

GUIDELINE_BUNDLES: dict[str, GuidelineBundle] = {
    'sepsis_peds_2024': SEPSIS_BUNDLE,
    'cap_peds_2024': CAP_BUNDLE,
    'uti_peds_2024': UTI_BUNDLE,
    'ssti_peds_2024': SSTI_BUNDLE,
    'surgical_prophy_2024': SURGICAL_PROPHYLAXIS_BUNDLE,
    'fn_peds_2024': FEBRILE_NEUTROPENIA_BUNDLE,
    'febrile_infant_2024': FEBRILE_INFANT_BUNDLE,
    'neonatal_hsv_2024': NEONATAL_HSV_BUNDLE,
    'cdiff_testing_2024': CDIFF_TESTING_BUNDLE,
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_bundle(bundle_id: str) -> GuidelineBundle | None:
    """Get a bundle by ID."""
    return GUIDELINE_BUNDLES.get(bundle_id)


def get_enabled_bundles() -> list[GuidelineBundle]:
    """Get list of enabled bundles from settings."""
    enabled_ids = getattr(settings, 'GUIDELINE_ADHERENCE', {}).get('ENABLED_BUNDLES', [])
    if not enabled_ids:
        return list(GUIDELINE_BUNDLES.values())
    return [
        GUIDELINE_BUNDLES[bid]
        for bid in enabled_ids
        if bid in GUIDELINE_BUNDLES
    ]


def identify_applicable_bundles(
    icd10_codes: list[str],
    patient_age_days: int | None = None,
) -> list[GuidelineBundle]:
    """Identify which bundles apply to a patient based on diagnoses and age.

    Args:
        icd10_codes: Patient's active ICD-10 codes.
        patient_age_days: Patient age in days (for age-filtered bundles).

    Returns:
        List of applicable GuidelineBundle objects.
    """
    applicable = []

    for bundle in get_enabled_bundles():
        for trigger in bundle.trigger_criteria:
            if trigger.trigger_type != 'diagnosis':
                continue

            # Check ICD-10 match
            matched = False
            for code in icd10_codes:
                for prefix in trigger.icd10_prefixes:
                    if code.startswith(prefix):
                        matched = True
                        break
                if matched:
                    break

            if not matched:
                continue

            # Check age criteria
            if patient_age_days is not None:
                if trigger.min_age_days is not None and patient_age_days < trigger.min_age_days:
                    continue
                if trigger.max_age_days is not None and patient_age_days > trigger.max_age_days:
                    continue

            applicable.append(bundle)
            break  # Don't add same bundle twice

    return applicable
