"""
AEGIS Febrile Infant Guideline (0-60 Days)
==========================================

Evidence-based guideline for evaluation and management of well-appearing
febrile infants 8-60 days of age, adapted from:

    AAP Clinical Practice Guideline: Evaluation and Management of 
    Well-Appearing Febrile Infants 8 to 60 Days Old. 
    Pediatrics. August 2021;148(2).

This module demonstrates how to convert a clinical flowsheet/algorithm
into a computable guideline for AEGIS adherence tracking.

Key Features:
- Age-stratified workup requirements (0-21d, 22-28d, 29-60d)
- Conditional logic based on inflammatory markers
- CSF-based decision branches
- Disposition appropriateness tracking
- Bundle compliance scoring

Usage:
    from febrile_infant_guideline import FebrileInfantEvaluator
    
    evaluator = FebrileInfantEvaluator()
    
    result = evaluator.assess_encounter(
        age_days=14,
        fever_temp_c=38.5,
        labs={
            'ua_wbc': 2,
            'ua_le': False,
            'blood_culture_obtained': True,
            'lp_performed': True,
            'csf_wbc': 3,
            'pct': 0.2,
            'anc': 3500,
            'crp': 1.0
        },
        disposition='admit',
        antibiotics_given=True,
        hsv_considered=True
    )
    
    print(result.bundle_compliance_score)  # 100.0
    print(result.disposition_appropriate)   # True

Author: AEGIS Development Team, Cincinnati Children's Hospital
Version: 1.0.0
Reference: AAP Febrile Infant Guidelines 2021
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from datetime import datetime, timedelta
import json


# =============================================================================
# DEFINITIONS (from Flowsheet 1)
# =============================================================================

class InfantAgeGroup(Enum):
    """Age stratification for febrile infant evaluation."""
    DAYS_0_7 = "0-7 days"      # Excluded from AAP guideline (higher risk)
    DAYS_8_21 = "8-21 days"    # Highest risk group in guideline
    DAYS_22_28 = "22-28 days"  # Intermediate risk
    DAYS_29_60 = "29-60 days"  # Lower risk, more options


class ClinicalAppearance(Enum):
    """Clinical appearance assessment."""
    WELL_APPEARING = "well_appearing"
    ILL_APPEARING = "ill_appearing"


class Disposition(Enum):
    """Disposition options."""
    ADMIT = "admit"
    HOME_WITH_FOLLOWUP = "home_with_followup"
    HOME_OBSERVATION = "home_observation"


class CSFResult(Enum):
    """CSF interpretation categories."""
    NOT_OBTAINED = "not_obtained"
    NORMAL = "normal"                    # No pleocytosis, not traumatic
    PLEOCYTOSIS = "pleocytosis"          # CSF WBC ≥ 15/μL
    TRAUMATIC = "traumatic"              # Bloody tap
    UNINTERPRETABLE = "uninterpretable"  # Unable to interpret


# =============================================================================
# THRESHOLDS AND CRITERIA
# =============================================================================

@dataclass
class InflammatoryMarkerThresholds:
    """
    Thresholds for abnormal inflammatory markers.
    From AAP 2021 guideline.
    """
    # Procalcitonin (ng/mL)
    pct_abnormal: float = 0.5
    
    # Absolute Neutrophil Count (/μL)
    anc_abnormal: int = 4000
    
    # C-Reactive Protein (mg/dL)
    crp_abnormal: float = 2.0
    
    # CSF WBC threshold for pleocytosis (/μL)
    csf_wbc_pleocytosis: int = 15


@dataclass
class UrinalysisThresholds:
    """
    Thresholds for abnormal urinalysis.
    """
    # WBC per high-power field
    wbc_abnormal: int = 5
    
    # Leukocyte esterase (boolean)
    le_positive: bool = True


THRESHOLDS = InflammatoryMarkerThresholds()
UA_THRESHOLDS = UrinalysisThresholds()


# =============================================================================
# LAB INTERPRETATION FUNCTIONS
# =============================================================================

def is_ua_abnormal(ua_wbc: Optional[int], ua_le: Optional[bool]) -> bool:
    """
    Determine if urinalysis is abnormal.
    
    Abnormal UA defined as:
    - WBC ≥ 5/HPF OR
    - Positive leukocyte esterase
    """
    if ua_wbc is not None and ua_wbc >= UA_THRESHOLDS.wbc_abnormal:
        return True
    if ua_le is True:
        return True
    return False


def are_inflammatory_markers_abnormal(
    pct: Optional[float] = None,
    anc: Optional[int] = None,
    crp: Optional[float] = None
) -> Tuple[bool, List[str]]:
    """
    Determine if any inflammatory markers are abnormal.
    
    Returns:
        Tuple of (is_abnormal, list_of_abnormal_markers)
    """
    abnormal_markers = []
    
    if pct is not None and pct > THRESHOLDS.pct_abnormal:
        abnormal_markers.append(f"PCT {pct} > {THRESHOLDS.pct_abnormal}")
    
    if anc is not None and anc > THRESHOLDS.anc_abnormal:
        abnormal_markers.append(f"ANC {anc} > {THRESHOLDS.anc_abnormal}")
    
    if crp is not None and crp > THRESHOLDS.crp_abnormal:
        abnormal_markers.append(f"CRP {crp} > {THRESHOLDS.crp_abnormal}")
    
    return (len(abnormal_markers) > 0, abnormal_markers)


def interpret_csf(
    csf_wbc: Optional[int],
    csf_rbc: Optional[int] = None,
    traumatic_threshold: int = 500
) -> CSFResult:
    """
    Interpret CSF results.
    
    Args:
        csf_wbc: CSF white blood cell count (/μL)
        csf_rbc: CSF red blood cell count (/μL)
        traumatic_threshold: RBC count above which tap is traumatic
        
    Returns:
        CSFResult enum
    """
    if csf_wbc is None:
        return CSFResult.NOT_OBTAINED
    
    # Check for traumatic tap first
    if csf_rbc is not None and csf_rbc > traumatic_threshold:
        return CSFResult.TRAUMATIC
    
    # Check for pleocytosis
    if csf_wbc >= THRESHOLDS.csf_wbc_pleocytosis:
        return CSFResult.PLEOCYTOSIS
    
    return CSFResult.NORMAL


def get_age_group(age_days: int) -> InfantAgeGroup:
    """Determine age group for guideline stratification."""
    if age_days < 8:
        return InfantAgeGroup.DAYS_0_7
    elif age_days <= 21:
        return InfantAgeGroup.DAYS_8_21
    elif age_days <= 28:
        return InfantAgeGroup.DAYS_22_28
    else:
        return InfantAgeGroup.DAYS_29_60


# =============================================================================
# GUIDELINE ELEMENT DEFINITIONS
# =============================================================================

@dataclass
class GuidelineElement:
    """Single element of the febrile infant guideline bundle."""
    element_id: str
    name: str
    description: str
    category: str  # 'workup', 'treatment', 'disposition', 'safety'
    
    # Which age groups require this element
    required_age_groups: List[InfantAgeGroup] = field(default_factory=list)
    
    # Conditions under which element is required
    # These are evaluated against the clinical context
    conditional_requirements: Optional[str] = None
    
    # Time window for completion (hours from presentation)
    time_window_hours: Optional[float] = None
    
    # Is this a "must do" vs "should consider"
    strength: str = "required"  # 'required', 'recommended', 'consider'
    
    # Reference to guideline section
    reference: str = ""


# Define all guideline elements
FEBRILE_INFANT_ELEMENTS = [
    # ==========================================================================
    # WORKUP ELEMENTS - Required for all age groups
    # ==========================================================================
    GuidelineElement(
        element_id='fi_ua',
        name='Urinalysis obtained',
        description='Urinalysis performed via catheter or suprapubic aspiration',
        category='workup',
        required_age_groups=[
            InfantAgeGroup.DAYS_8_21,
            InfantAgeGroup.DAYS_22_28,
            InfantAgeGroup.DAYS_29_60
        ],
        time_window_hours=2.0,
        strength='required',
        reference='AAP 2021: Action Statement 2'
    ),
    GuidelineElement(
        element_id='fi_blood_culture',
        name='Blood culture obtained',
        description='Blood culture obtained prior to antibiotics',
        category='workup',
        required_age_groups=[
            InfantAgeGroup.DAYS_8_21,
            InfantAgeGroup.DAYS_22_28,
            InfantAgeGroup.DAYS_29_60
        ],
        time_window_hours=2.0,
        strength='required',
        reference='AAP 2021: Action Statement 3'
    ),
    GuidelineElement(
        element_id='fi_inflammatory_markers',
        name='Inflammatory markers obtained',
        description='ANC and CRP obtained; procalcitonin recommended for 29-60 days',
        category='workup',
        required_age_groups=[
            InfantAgeGroup.DAYS_8_21,
            InfantAgeGroup.DAYS_22_28,
            InfantAgeGroup.DAYS_29_60
        ],
        time_window_hours=2.0,
        strength='required',
        reference='AAP 2021: Action Statements 4-5'
    ),
    GuidelineElement(
        element_id='fi_procalcitonin',
        name='Procalcitonin obtained (29-60 days)',
        description='Procalcitonin recommended for infants 29-60 days; most useful if fever onset >6 hours',
        category='workup',
        required_age_groups=[InfantAgeGroup.DAYS_29_60],
        time_window_hours=2.0,
        strength='recommended',
        reference='AAP 2021: Action Statement 5a'
    ),
    
    # ==========================================================================
    # LUMBAR PUNCTURE - Age-stratified requirements
    # ==========================================================================
    GuidelineElement(
        element_id='fi_lp_8_21d',
        name='LP performed (8-21 days)',
        description='Lumbar puncture required for all febrile infants 8-21 days',
        category='workup',
        required_age_groups=[InfantAgeGroup.DAYS_8_21],
        time_window_hours=2.0,
        strength='required',
        reference='AAP 2021: Action Statement 4a'
    ),
    GuidelineElement(
        element_id='fi_lp_22_28d_im_abnormal',
        name='LP performed (22-28 days, IMs abnormal)',
        description='LP required if inflammatory markers abnormal in 22-28 day old',
        category='workup',
        required_age_groups=[InfantAgeGroup.DAYS_22_28],
        conditional_requirements='inflammatory_markers_abnormal',
        time_window_hours=2.0,
        strength='required',
        reference='AAP 2021: Action Statement 4b'
    ),
    GuidelineElement(
        element_id='fi_lp_22_28d_im_normal',
        name='LP considered (22-28 days, IMs normal)',
        description='LP may be performed if inflammatory markers normal in 22-28 day old',
        category='workup',
        required_age_groups=[InfantAgeGroup.DAYS_22_28],
        conditional_requirements='inflammatory_markers_normal',
        time_window_hours=2.0,
        strength='consider',
        reference='AAP 2021: Action Statement 4b'
    ),
    GuidelineElement(
        element_id='fi_lp_29_60d_im_abnormal',
        name='LP considered (29-60 days, IMs abnormal)',
        description='LP may be performed if inflammatory markers abnormal in 29-60 day old',
        category='workup',
        required_age_groups=[InfantAgeGroup.DAYS_29_60],
        conditional_requirements='inflammatory_markers_abnormal',
        time_window_hours=4.0,
        strength='consider',
        reference='AAP 2021: Action Statement 5b'
    ),
    GuidelineElement(
        element_id='fi_lp_29_60d_im_normal',
        name='LP not required (29-60 days, IMs normal)',
        description='LP need not be performed if inflammatory markers normal in 29-60 day old',
        category='workup',
        required_age_groups=[InfantAgeGroup.DAYS_29_60],
        conditional_requirements='inflammatory_markers_normal',
        strength='not_required',
        reference='AAP 2021: Action Statement 5b'
    ),
    
    # ==========================================================================
    # URINE CULTURE
    # ==========================================================================
    GuidelineElement(
        element_id='fi_urine_culture_if_ua_abnormal',
        name='Urine culture if UA abnormal',
        description='Obtain urine culture if urinalysis is abnormal',
        category='workup',
        required_age_groups=[
            InfantAgeGroup.DAYS_8_21,
            InfantAgeGroup.DAYS_22_28,
            InfantAgeGroup.DAYS_29_60
        ],
        conditional_requirements='ua_abnormal',
        time_window_hours=2.0,
        strength='required',
        reference='AAP 2021'
    ),
    
    # ==========================================================================
    # CSF STUDIES - What to send when LP is performed
    # ==========================================================================
    GuidelineElement(
        element_id='fi_csf_studies',
        name='Complete CSF studies',
        description='CSF cell count, Gram stain, glucose, protein, bacterial culture; enterovirus PCR if pleocytosis or local prevalence',
        category='workup',
        required_age_groups=[
            InfantAgeGroup.DAYS_8_21,
            InfantAgeGroup.DAYS_22_28,
            InfantAgeGroup.DAYS_29_60
        ],
        conditional_requirements='lp_performed',
        strength='required',
        reference='AAP 2021'
    ),
    
    # ==========================================================================
    # TREATMENT ELEMENTS
    # ==========================================================================
    GuidelineElement(
        element_id='fi_abx_8_21d',
        name='Parenteral antibiotics (8-21 days)',
        description='Start parenteral antimicrobials for all febrile infants 8-21 days',
        category='treatment',
        required_age_groups=[InfantAgeGroup.DAYS_8_21],
        time_window_hours=1.0,
        strength='required',
        reference='AAP 2021: Action Statement 4a'
    ),
    GuidelineElement(
        element_id='fi_abx_22_28d_im_abnormal',
        name='Parenteral antibiotics (22-28 days, IMs abnormal)',
        description='Start empiric parenteral antimicrobials',
        category='treatment',
        required_age_groups=[InfantAgeGroup.DAYS_22_28],
        conditional_requirements='inflammatory_markers_abnormal',
        time_window_hours=1.0,
        strength='required',
        reference='AAP 2021: Action Statement 4b'
    ),
    GuidelineElement(
        element_id='fi_abx_29_60d_uti',
        name='Antibiotics for UTI (29-60 days)',
        description='Start oral or parenteral antibiotics if UA abnormal with normal IMs',
        category='treatment',
        required_age_groups=[InfantAgeGroup.DAYS_29_60],
        conditional_requirements='ua_abnormal AND inflammatory_markers_normal',
        time_window_hours=2.0,
        strength='required',
        reference='AAP 2021: Action Statement 5c'
    ),
    
    # ==========================================================================
    # HSV CONSIDERATION
    # ==========================================================================
    GuidelineElement(
        element_id='fi_hsv_risk_assessment',
        name='HSV risk assessment',
        description='Consider HSV risk factors and need for acyclovir',
        category='safety',
        required_age_groups=[
            InfantAgeGroup.DAYS_8_21,
            InfantAgeGroup.DAYS_22_28
        ],
        strength='required',
        reference='AAP 2021: HSV risk factors'
    ),
    
    # ==========================================================================
    # DISPOSITION ELEMENTS
    # ==========================================================================
    GuidelineElement(
        element_id='fi_admit_8_21d',
        name='Hospital admission (8-21 days)',
        description='Admit to hospital for all febrile infants 8-21 days',
        category='disposition',
        required_age_groups=[InfantAgeGroup.DAYS_8_21],
        strength='required',
        reference='AAP 2021: Action Statement 4a'
    ),
    GuidelineElement(
        element_id='fi_admit_22_28d_im_abnormal',
        name='Hospital admission (22-28 days, IMs abnormal)',
        description='Admit to hospital if inflammatory markers abnormal',
        category='disposition',
        required_age_groups=[InfantAgeGroup.DAYS_22_28],
        conditional_requirements='inflammatory_markers_abnormal',
        strength='required',
        reference='AAP 2021: Action Statement 4b'
    ),
    GuidelineElement(
        element_id='fi_safe_discharge_checklist',
        name='Safe discharge checklist',
        description='If discharging: documented follow-up within 24h, working phone number, reliable transportation',
        category='disposition',
        required_age_groups=[
            InfantAgeGroup.DAYS_22_28,
            InfantAgeGroup.DAYS_29_60
        ],
        conditional_requirements='disposition_home',
        strength='required',
        reference='Cincinnati Local Adaptation'
    ),
]


# =============================================================================
# BUNDLE COMPLIANCE RESULT
# =============================================================================

@dataclass
class ElementComplianceResult:
    """Result for a single guideline element."""
    element_id: str
    element_name: str
    applicable: bool
    compliant: bool
    strength: str
    details: str = ""


@dataclass
class FebrileInfantAssessment:
    """Complete assessment result for a febrile infant encounter."""
    # Encounter info
    encounter_id: str
    patient_mrn: str
    assessment_time: datetime
    
    # Patient characteristics
    age_days: int
    age_group: InfantAgeGroup
    fever_temp_c: float
    clinical_appearance: ClinicalAppearance
    
    # Lab interpretations
    ua_abnormal: bool
    inflammatory_markers_abnormal: bool
    abnormal_markers_list: List[str]
    csf_result: CSFResult
    
    # Element-level compliance
    element_results: List[ElementComplianceResult] = field(default_factory=list)
    
    # Summary scores
    required_elements_met: int = 0
    required_elements_total: int = 0
    bundle_compliance_score: float = 0.0
    
    # Disposition assessment
    disposition: str = ""
    disposition_appropriate: bool = True
    disposition_notes: str = ""
    
    # Flags and recommendations
    flags: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'encounter_id': self.encounter_id,
            'patient_mrn': self.patient_mrn,
            'assessment_time': self.assessment_time.isoformat(),
            'age_days': self.age_days,
            'age_group': self.age_group.value,
            'fever_temp_c': self.fever_temp_c,
            'clinical_appearance': self.clinical_appearance.value,
            'ua_abnormal': self.ua_abnormal,
            'inflammatory_markers_abnormal': self.inflammatory_markers_abnormal,
            'abnormal_markers': self.abnormal_markers_list,
            'csf_result': self.csf_result.value,
            'bundle_compliance_score': self.bundle_compliance_score,
            'required_met': self.required_elements_met,
            'required_total': self.required_elements_total,
            'disposition': self.disposition,
            'disposition_appropriate': self.disposition_appropriate,
            'flags': self.flags,
            'recommendations': self.recommendations,
            'element_details': [
                {
                    'element': r.element_name,
                    'applicable': r.applicable,
                    'compliant': r.compliant,
                    'strength': r.strength,
                    'details': r.details
                }
                for r in self.element_results
            ]
        }


# =============================================================================
# MAIN EVALUATOR CLASS
# =============================================================================

class FebrileInfantEvaluator:
    """
    Evaluates guideline compliance for febrile infant encounters.
    
    This class demonstrates how to convert a clinical flowsheet into
    computable guideline adherence tracking.
    """
    
    def __init__(self):
        """Initialize with guideline elements."""
        self.elements = FEBRILE_INFANT_ELEMENTS
        self.thresholds = THRESHOLDS
    
    def assess_encounter(
        self,
        # Required parameters
        age_days: int,
        fever_temp_c: float,
        
        # Lab results (dict for flexibility)
        labs: Dict[str, Any],
        
        # Clinical context
        clinical_appearance: str = "well_appearing",
        disposition: str = "admit",
        
        # Treatment given
        antibiotics_given: bool = False,
        antibiotics_route: str = "parenteral",
        hsv_considered: bool = False,
        acyclovir_given: bool = False,
        
        # For tracking
        encounter_id: str = "",
        patient_mrn: str = "",
        
        # Safe discharge elements
        followup_arranged: bool = False,
        phone_documented: bool = False,
        transport_confirmed: bool = False
    ) -> FebrileInfantAssessment:
        """
        Assess guideline compliance for a febrile infant encounter.
        
        Args:
            age_days: Age in days
            fever_temp_c: Maximum temperature in Celsius
            labs: Dictionary containing lab values:
                - ua_wbc: Urine WBC per HPF
                - ua_le: Leukocyte esterase positive (bool)
                - blood_culture_obtained: bool
                - urine_culture_obtained: bool
                - lp_performed: bool
                - csf_wbc: CSF WBC count (/μL)
                - csf_rbc: CSF RBC count (/μL)
                - csf_culture_sent: bool
                - csf_enterovirus_pcr_sent: bool
                - pct: Procalcitonin (ng/mL)
                - anc: Absolute neutrophil count
                - crp: C-reactive protein (mg/dL)
            clinical_appearance: "well_appearing" or "ill_appearing"
            disposition: "admit", "home_with_followup", "home_observation"
            antibiotics_given: Whether antibiotics were started
            antibiotics_route: "parenteral" or "oral"
            hsv_considered: Whether HSV risk was documented
            acyclovir_given: Whether acyclovir was started
            encounter_id: Encounter identifier
            patient_mrn: Patient MRN
            followup_arranged: For home disposition
            phone_documented: For home disposition
            transport_confirmed: For home disposition
            
        Returns:
            FebrileInfantAssessment with compliance results
        """
        # Determine age group
        age_group = get_age_group(age_days)
        
        # Parse clinical appearance
        appearance = (ClinicalAppearance.ILL_APPEARING 
                     if clinical_appearance == "ill_appearing" 
                     else ClinicalAppearance.WELL_APPEARING)
        
        # Interpret labs
        ua_abnormal = is_ua_abnormal(
            labs.get('ua_wbc'),
            labs.get('ua_le')
        )
        
        im_abnormal, abnormal_markers = are_inflammatory_markers_abnormal(
            labs.get('pct'),
            labs.get('anc'),
            labs.get('crp')
        )
        
        csf_result = interpret_csf(
            labs.get('csf_wbc'),
            labs.get('csf_rbc')
        )
        
        # Build context for element evaluation
        context = {
            'age_days': age_days,
            'age_group': age_group,
            'clinical_appearance': appearance,
            'ua_abnormal': ua_abnormal,
            'inflammatory_markers_abnormal': im_abnormal,
            'inflammatory_markers_normal': not im_abnormal,
            'csf_result': csf_result,
            'lp_performed': labs.get('lp_performed', False),
            'disposition': disposition,
            'disposition_home': disposition in ['home_with_followup', 'home_observation'],
            'labs': labs,
            'antibiotics_given': antibiotics_given,
            'antibiotics_route': antibiotics_route,
            'hsv_considered': hsv_considered,
            'followup_arranged': followup_arranged,
            'phone_documented': phone_documented,
            'transport_confirmed': transport_confirmed
        }
        
        # Evaluate each element
        element_results = []
        required_met = 0
        required_total = 0
        flags = []
        recommendations = []
        
        for element in self.elements:
            result = self._evaluate_element(element, context)
            element_results.append(result)
            
            if result.applicable and result.strength == 'required':
                required_total += 1
                if result.compliant:
                    required_met += 1
                else:
                    flags.append(f"MISSING: {element.name}")
                    recommendations.append(f"Obtain: {element.description}")
        
        # Calculate compliance score
        compliance_score = (required_met / required_total * 100) if required_total > 0 else 100.0
        
        # Assess disposition appropriateness
        disposition_appropriate, disposition_notes = self._assess_disposition(
            age_group, im_abnormal, ua_abnormal, csf_result, 
            disposition, appearance
        )
        
        if not disposition_appropriate:
            flags.append("DISPOSITION_REVIEW")
            recommendations.append(disposition_notes)
        
        # Build assessment
        return FebrileInfantAssessment(
            encounter_id=encounter_id,
            patient_mrn=patient_mrn,
            assessment_time=datetime.now(),
            age_days=age_days,
            age_group=age_group,
            fever_temp_c=fever_temp_c,
            clinical_appearance=appearance,
            ua_abnormal=ua_abnormal,
            inflammatory_markers_abnormal=im_abnormal,
            abnormal_markers_list=abnormal_markers,
            csf_result=csf_result,
            element_results=element_results,
            required_elements_met=required_met,
            required_elements_total=required_total,
            bundle_compliance_score=compliance_score,
            disposition=disposition,
            disposition_appropriate=disposition_appropriate,
            disposition_notes=disposition_notes,
            flags=flags,
            recommendations=recommendations
        )
    
    def _evaluate_element(
        self, 
        element: GuidelineElement, 
        context: Dict
    ) -> ElementComplianceResult:
        """
        Evaluate compliance with a single guideline element.
        """
        age_group = context['age_group']
        
        # Check if element applies to this age group
        if age_group not in element.required_age_groups:
            return ElementComplianceResult(
                element_id=element.element_id,
                element_name=element.name,
                applicable=False,
                compliant=True,  # N/A counts as compliant
                strength=element.strength,
                details="Not applicable for this age group"
            )
        
        # Check conditional requirements
        if element.conditional_requirements:
            condition_met = self._evaluate_condition(
                element.conditional_requirements, context
            )
            if not condition_met:
                return ElementComplianceResult(
                    element_id=element.element_id,
                    element_name=element.name,
                    applicable=False,
                    compliant=True,
                    strength=element.strength,
                    details=f"Condition not met: {element.conditional_requirements}"
                )
        
        # Evaluate compliance based on element type
        compliant, details = self._check_element_compliance(element, context)
        
        return ElementComplianceResult(
            element_id=element.element_id,
            element_name=element.name,
            applicable=True,
            compliant=compliant,
            strength=element.strength,
            details=details
        )
    
    def _evaluate_condition(self, condition: str, context: Dict) -> bool:
        """Evaluate a conditional requirement string."""
        # Simple condition evaluation
        conditions = {
            'inflammatory_markers_abnormal': context.get('inflammatory_markers_abnormal', False),
            'inflammatory_markers_normal': context.get('inflammatory_markers_normal', True),
            'ua_abnormal': context.get('ua_abnormal', False),
            'lp_performed': context.get('lp_performed', False),
            'disposition_home': context.get('disposition_home', False),
        }
        
        # Handle compound conditions
        if ' AND ' in condition:
            parts = condition.split(' AND ')
            return all(conditions.get(p.strip(), False) for p in parts)
        
        return conditions.get(condition, False)
    
    def _check_element_compliance(
        self, 
        element: GuidelineElement, 
        context: Dict
    ) -> Tuple[bool, str]:
        """
        Check if a specific element was completed.
        
        Returns:
            Tuple of (compliant: bool, details: str)
        """
        labs = context.get('labs', {})
        
        # Map element IDs to compliance checks
        checks = {
            # Workup elements
            'fi_ua': (
                labs.get('ua_wbc') is not None or labs.get('ua_le') is not None,
                "UA obtained" if labs.get('ua_wbc') is not None else "UA not documented"
            ),
            'fi_blood_culture': (
                labs.get('blood_culture_obtained', False),
                "Blood culture obtained" if labs.get('blood_culture_obtained') else "Blood culture not obtained"
            ),
            'fi_inflammatory_markers': (
                labs.get('anc') is not None or labs.get('crp') is not None,
                "IMs obtained" if labs.get('anc') is not None else "IMs not documented"
            ),
            'fi_procalcitonin': (
                labs.get('pct') is not None,
                f"PCT = {labs.get('pct')}" if labs.get('pct') is not None else "PCT not obtained"
            ),
            
            # LP elements
            'fi_lp_8_21d': (
                labs.get('lp_performed', False),
                "LP performed" if labs.get('lp_performed') else "LP not performed"
            ),
            'fi_lp_22_28d_im_abnormal': (
                labs.get('lp_performed', False),
                "LP performed" if labs.get('lp_performed') else "LP required but not performed"
            ),
            'fi_lp_22_28d_im_normal': (
                True,  # "May perform" - always compliant
                "LP optional when IMs normal"
            ),
            'fi_lp_29_60d_im_abnormal': (
                True,  # "May perform" - always compliant
                "LP optional"
            ),
            'fi_lp_29_60d_im_normal': (
                True,  # "Need not perform" - always compliant
                "LP not required when IMs normal"
            ),
            
            # Urine culture
            'fi_urine_culture_if_ua_abnormal': (
                labs.get('urine_culture_obtained', False),
                "Urine culture obtained" if labs.get('urine_culture_obtained') else "Urine culture needed for abnormal UA"
            ),
            
            # CSF studies
            'fi_csf_studies': (
                labs.get('csf_culture_sent', False),
                "CSF studies sent" if labs.get('csf_culture_sent') else "CSF studies not documented"
            ),
            
            # Treatment
            'fi_abx_8_21d': (
                context.get('antibiotics_given', False) and context.get('antibiotics_route') == 'parenteral',
                "Parenteral abx given" if context.get('antibiotics_given') else "Antibiotics not started"
            ),
            'fi_abx_22_28d_im_abnormal': (
                context.get('antibiotics_given', False),
                "Antibiotics given" if context.get('antibiotics_given') else "Antibiotics not started"
            ),
            'fi_abx_29_60d_uti': (
                context.get('antibiotics_given', False),
                "Antibiotics given for UTI" if context.get('antibiotics_given') else "Antibiotics not started"
            ),
            
            # HSV
            'fi_hsv_risk_assessment': (
                context.get('hsv_considered', False),
                "HSV risk documented" if context.get('hsv_considered') else "HSV risk not documented"
            ),
            
            # Disposition
            'fi_admit_8_21d': (
                context.get('disposition') == 'admit',
                "Admitted" if context.get('disposition') == 'admit' else "Not admitted"
            ),
            'fi_admit_22_28d_im_abnormal': (
                context.get('disposition') == 'admit',
                "Admitted" if context.get('disposition') == 'admit' else "Not admitted"
            ),
            'fi_safe_discharge_checklist': (
                (context.get('followup_arranged', False) and 
                 context.get('phone_documented', False) and 
                 context.get('transport_confirmed', False)),
                "Safe discharge checklist complete" if context.get('followup_arranged') else "Discharge checklist incomplete"
            ),
        }
        
        if element.element_id in checks:
            return checks[element.element_id]
        
        # Default: unable to assess
        return (False, "Unable to assess")
    
    def _assess_disposition(
        self,
        age_group: InfantAgeGroup,
        im_abnormal: bool,
        ua_abnormal: bool,
        csf_result: CSFResult,
        disposition: str,
        appearance: ClinicalAppearance
    ) -> Tuple[bool, str]:
        """
        Assess if disposition is appropriate per guidelines.
        
        Returns:
            Tuple of (appropriate: bool, notes: str)
        """
        # Ill-appearing: always admit
        if appearance == ClinicalAppearance.ILL_APPEARING:
            if disposition != 'admit':
                return (False, "Ill-appearing infants should be admitted")
            return (True, "Appropriate: ill-appearing infant admitted")
        
        # Age 8-21 days: always admit
        if age_group == InfantAgeGroup.DAYS_8_21:
            if disposition != 'admit':
                return (False, "Infants 8-21 days should be admitted per AAP guideline")
            return (True, "Appropriate: 8-21 day old admitted")
        
        # Age 22-28 days
        if age_group == InfantAgeGroup.DAYS_22_28:
            if im_abnormal:
                if disposition != 'admit':
                    return (False, "22-28 day old with abnormal IMs should be admitted")
                return (True, "Appropriate: abnormal IMs, admitted")
            else:
                # Normal IMs: home or hospital observation acceptable
                if csf_result == CSFResult.PLEOCYTOSIS:
                    if disposition != 'admit':
                        return (False, "CSF pleocytosis requires admission")
                return (True, "Disposition appropriate for risk level")
        
        # Age 29-60 days
        if age_group == InfantAgeGroup.DAYS_29_60:
            if im_abnormal:
                # Higher risk, but home observation may be acceptable per guideline
                if csf_result == CSFResult.PLEOCYTOSIS:
                    if disposition != 'admit':
                        return (False, "CSF pleocytosis requires admission")
                return (True, "Disposition appropriate per risk stratification")
            else:
                # Normal IMs: home observation acceptable
                return (True, "Low-risk: home observation appropriate")
        
        return (True, "Disposition acceptable")
    
    def get_guideline_summary(self, age_days: int) -> Dict:
        """
        Get a summary of guideline requirements for a given age.
        
        Useful for displaying expected workup to clinicians.
        """
        age_group = get_age_group(age_days)
        
        required = []
        recommended = []
        consider = []
        
        for element in self.elements:
            if age_group in element.required_age_groups:
                if element.strength == 'required':
                    required.append(element.name)
                elif element.strength == 'recommended':
                    recommended.append(element.name)
                elif element.strength == 'consider':
                    consider.append(element.name)
        
        return {
            'age_days': age_days,
            'age_group': age_group.value,
            'required': required,
            'recommended': recommended,
            'consider': consider
        }


# =============================================================================
# AGGREGATE METRICS FOR DASHBOARD
# =============================================================================

@dataclass
class FebrileInfantMetrics:
    """Aggregate compliance metrics for febrile infant guideline."""
    period_start: datetime
    period_end: datetime
    
    total_encounters: int
    
    # By age group
    encounters_8_21d: int = 0
    encounters_22_28d: int = 0
    encounters_29_60d: int = 0
    
    # Compliance rates
    overall_compliance_rate: float = 0.0
    compliance_8_21d: float = 0.0
    compliance_22_28d: float = 0.0
    compliance_29_60d: float = 0.0
    
    # Element-specific compliance
    blood_culture_rate: float = 0.0
    ua_rate: float = 0.0
    lp_rate_8_21d: float = 0.0
    inflammatory_markers_rate: float = 0.0
    procalcitonin_rate_29_60d: float = 0.0
    hsv_documentation_rate: float = 0.0
    
    # Disposition metrics
    admit_rate_8_21d: float = 0.0
    appropriate_disposition_rate: float = 0.0


def calculate_febrile_infant_metrics(
    assessments: List[FebrileInfantAssessment]
) -> FebrileInfantMetrics:
    """
    Calculate aggregate metrics from a list of assessments.
    """
    if not assessments:
        return FebrileInfantMetrics(
            period_start=datetime.now(),
            period_end=datetime.now(),
            total_encounters=0
        )
    
    total = len(assessments)
    
    # Filter by age group
    group_8_21 = [a for a in assessments if a.age_group == InfantAgeGroup.DAYS_8_21]
    group_22_28 = [a for a in assessments if a.age_group == InfantAgeGroup.DAYS_22_28]
    group_29_60 = [a for a in assessments if a.age_group == InfantAgeGroup.DAYS_29_60]
    
    # Calculate compliance rates
    def compliance_rate(group):
        if not group:
            return 0.0
        return sum(a.bundle_compliance_score for a in group) / len(group)
    
    # Element-specific rates
    def element_rate(assessments, element_id):
        applicable = [a for a in assessments 
                     for e in a.element_results 
                     if e.element_id == element_id and e.applicable]
        if not applicable:
            return 0.0
        compliant = sum(1 for a in assessments 
                       for e in a.element_results 
                       if e.element_id == element_id and e.applicable and e.compliant)
        return compliant / len(applicable) * 100
    
    return FebrileInfantMetrics(
        period_start=min(a.assessment_time for a in assessments),
        period_end=max(a.assessment_time for a in assessments),
        total_encounters=total,
        encounters_8_21d=len(group_8_21),
        encounters_22_28d=len(group_22_28),
        encounters_29_60d=len(group_29_60),
        overall_compliance_rate=compliance_rate(assessments),
        compliance_8_21d=compliance_rate(group_8_21),
        compliance_22_28d=compliance_rate(group_22_28),
        compliance_29_60d=compliance_rate(group_29_60),
        blood_culture_rate=element_rate(assessments, 'fi_blood_culture'),
        ua_rate=element_rate(assessments, 'fi_ua'),
        lp_rate_8_21d=element_rate(group_8_21, 'fi_lp_8_21d'),
        inflammatory_markers_rate=element_rate(assessments, 'fi_inflammatory_markers'),
        procalcitonin_rate_29_60d=element_rate(group_29_60, 'fi_procalcitonin'),
        hsv_documentation_rate=element_rate(group_8_21 + group_22_28, 'fi_hsv_risk_assessment'),
        admit_rate_8_21d=sum(1 for a in group_8_21 if a.disposition == 'admit') / len(group_8_21) * 100 if group_8_21 else 0,
        appropriate_disposition_rate=sum(1 for a in assessments if a.disposition_appropriate) / total * 100
    )


# =============================================================================
# EXAMPLE USAGE AND TESTS
# =============================================================================

if __name__ == '__main__':
    print("="*70)
    print("FEBRILE INFANT GUIDELINE EVALUATOR")
    print("="*70)
    
    evaluator = FebrileInfantEvaluator()
    
    # Show guideline summary by age
    print("\n--- GUIDELINE REQUIREMENTS BY AGE ---\n")
    
    for age in [14, 25, 45]:
        summary = evaluator.get_guideline_summary(age)
        print(f"Age: {age} days ({summary['age_group']})")
        print(f"  Required: {', '.join(summary['required'])}")
        print(f"  Recommended: {', '.join(summary['recommended'])}")
        print()
    
    # Test cases
    print("="*70)
    print("TEST CASES")
    print("="*70)
    
    # Case 1: 14-day-old, well-appearing, complete workup
    print("\n--- Case 1: 14-day-old, complete workup ---")
    result1 = evaluator.assess_encounter(
        age_days=14,
        fever_temp_c=38.5,
        labs={
            'ua_wbc': 2,
            'ua_le': False,
            'blood_culture_obtained': True,
            'lp_performed': True,
            'csf_wbc': 3,
            'csf_culture_sent': True,
            'anc': 3500,
            'crp': 1.0
        },
        disposition='admit',
        antibiotics_given=True,
        antibiotics_route='parenteral',
        hsv_considered=True
    )
    print(f"  Age group: {result1.age_group.value}")
    print(f"  Bundle compliance: {result1.bundle_compliance_score:.1f}%")
    print(f"  Disposition appropriate: {result1.disposition_appropriate}")
    print(f"  Flags: {result1.flags if result1.flags else 'None'}")
    
    # Case 2: 14-day-old, missing LP
    print("\n--- Case 2: 14-day-old, missing LP ---")
    result2 = evaluator.assess_encounter(
        age_days=14,
        fever_temp_c=38.3,
        labs={
            'ua_wbc': 1,
            'ua_le': False,
            'blood_culture_obtained': True,
            'lp_performed': False,  # Missing!
            'anc': 2500,
            'crp': 0.5
        },
        disposition='admit',
        antibiotics_given=True,
        antibiotics_route='parenteral',
        hsv_considered=True
    )
    print(f"  Bundle compliance: {result2.bundle_compliance_score:.1f}%")
    print(f"  Flags: {result2.flags}")
    
    # Case 3: 25-day-old, normal IMs, no LP (acceptable)
    print("\n--- Case 3: 25-day-old, normal IMs, no LP ---")
    result3 = evaluator.assess_encounter(
        age_days=25,
        fever_temp_c=38.2,
        labs={
            'ua_wbc': 0,
            'ua_le': False,
            'blood_culture_obtained': True,
            'lp_performed': False,
            'anc': 2000,
            'crp': 0.3,
            'pct': 0.1
        },
        disposition='home_with_followup',
        antibiotics_given=True,
        antibiotics_route='parenteral',
        hsv_considered=True,
        followup_arranged=True,
        phone_documented=True,
        transport_confirmed=True
    )
    print(f"  IMs abnormal: {result3.inflammatory_markers_abnormal}")
    print(f"  Bundle compliance: {result3.bundle_compliance_score:.1f}%")
    print(f"  Disposition appropriate: {result3.disposition_appropriate}")
    
    # Case 4: 45-day-old, normal IMs, UTI
    print("\n--- Case 4: 45-day-old, normal IMs, UTI ---")
    result4 = evaluator.assess_encounter(
        age_days=45,
        fever_temp_c=38.8,
        labs={
            'ua_wbc': 25,  # Abnormal
            'ua_le': True,
            'urine_culture_obtained': True,
            'blood_culture_obtained': True,
            'lp_performed': False,
            'anc': 3000,
            'crp': 1.5,
            'pct': 0.2
        },
        disposition='home_with_followup',
        antibiotics_given=True,
        antibiotics_route='oral',
        followup_arranged=True,
        phone_documented=True,
        transport_confirmed=True
    )
    print(f"  UA abnormal: {result4.ua_abnormal}")
    print(f"  IMs abnormal: {result4.inflammatory_markers_abnormal}")
    print(f"  Bundle compliance: {result4.bundle_compliance_score:.1f}%")
    print(f"  Disposition appropriate: {result4.disposition_appropriate}")
    
    # Case 5: 45-day-old, abnormal IMs, discharged (inappropriate)
    print("\n--- Case 5: 45-day-old, abnormal IMs, CSF pleocytosis, discharged ---")
    result5 = evaluator.assess_encounter(
        age_days=45,
        fever_temp_c=39.0,
        labs={
            'ua_wbc': 2,
            'ua_le': False,
            'blood_culture_obtained': True,
            'lp_performed': True,
            'csf_wbc': 25,  # Pleocytosis!
            'csf_culture_sent': True,
            'anc': 5500,  # Abnormal
            'crp': 3.5,   # Abnormal
            'pct': 0.8    # Abnormal
        },
        disposition='home_with_followup',  # Should be admitted!
        antibiotics_given=True,
        antibiotics_route='parenteral'
    )
    print(f"  IMs abnormal: {result5.inflammatory_markers_abnormal}")
    print(f"  CSF result: {result5.csf_result.value}")
    print(f"  Disposition appropriate: {result5.disposition_appropriate}")
    print(f"  Notes: {result5.disposition_notes}")
    print(f"  Flags: {result5.flags}")
    
    # Show JSON output
    print("\n" + "="*70)
    print("JSON OUTPUT EXAMPLE")
    print("="*70)
    print(json.dumps(result1.to_dict(), indent=2))
