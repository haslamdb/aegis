"""Febrile Infant bundle element checker.

Implements the AAP 2021 guideline for evaluation of well-appearing
febrile infants 8-60 days old. Handles:
- Age-stratified workup requirements (8-21d, 22-28d, 29-60d)
- Conditional logic based on inflammatory markers
- CSF-based decision branches
- NLP-based clinical impression assessment (ill-appearing vs well-appearing)
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import logging

from apps.guideline_adherence.logic import config as cfg
from .base import ElementChecker, CheckResult

logger = logging.getLogger(__name__)


# HSV risk factors for febrile infants (AAP 2021 / CCHMC guidelines)
HSV_RISK_FACTORS = [
    "maternal hsv",
    "maternal herpes",
    "genital lesion",
    "scalp electrode",
    "scalp monitor",
    "fetal scalp",
    "prolonged rupture",
    "rom >",
    "prom",
    "vesicles",
    "vesicular rash",
    "ill-appearing",
    "ill appearing",
    "seizure",
    "csf pleocytosis",
    "elevated lfts",
    "elevated transaminases",
]


class InfantAgeGroup(Enum):
    """Age stratification for febrile infant evaluation (AAP 2021)."""
    DAYS_0_7 = "0-7 days"      # Excluded from AAP guideline (higher risk)
    DAYS_8_21 = "8-21 days"    # Highest risk group in guideline
    DAYS_22_28 = "22-28 days"  # Intermediate risk
    DAYS_29_60 = "29-60 days"  # Lower risk, more options


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


class FebrileInfantChecker(ElementChecker):
    """Check bundle elements for febrile infant guideline.

    This checker implements age-stratified and conditional logic per AAP 2021.
    """

    # Map element IDs to LOINC codes
    ELEMENT_LOINC_MAP = {
        "fi_ua": [cfg.LOINC_UA, cfg.LOINC_UA_WBC],
        "fi_blood_culture": [cfg.LOINC_BLOOD_CULTURE],
        "fi_inflammatory_markers": [cfg.LOINC_ANC, cfg.LOINC_CRP],
        "fi_procalcitonin": [cfg.LOINC_PROCALCITONIN],
        "fi_csf_studies": [cfg.LOINC_CSF_WBC, cfg.LOINC_CSF_RBC],
        "fi_urine_culture": [cfg.LOINC_URINE_CULTURE],
    }

    def __init__(self, fhir_client=None, use_nlp=True, use_triage=True):
        """Initialize with FHIR client.

        Args:
            fhir_client: FHIR client for data retrieval.
            use_nlp: Whether to use NLP for clinical impression extraction.
            use_triage: Whether to use fast triage model before full model.
        """
        super().__init__(fhir_client)
        self._patient_context = {}
        self._nlp_extractor = None
        self._use_triage = use_triage

        if use_nlp:
            try:
                from apps.guideline_adherence.logic.nlp.clinical_impression import (
                    ClinicalImpressionExtractor,
                )
                self._nlp_extractor = ClinicalImpressionExtractor()
                logger.info("Clinical impression extractor initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize NLP extractor: {e}")

    def check(self, element, patient_id: str, trigger_time: datetime, **kwargs) -> CheckResult:
        """Check if a febrile infant bundle element has been completed."""
        element_id = element.element_id
        age_days = kwargs.get('age_days')
        episode_id = kwargs.get('episode_id')

        # Build patient context if not cached
        if patient_id not in self._patient_context:
            self._patient_context[patient_id] = self._build_patient_context(
                patient_id, trigger_time, age_days, episode_id
            )

        context = self._patient_context[patient_id]
        age_group = context.get("age_group")

        # Check applicability
        applicability = self._check_element_applicability(element_id, context)
        if applicability == "not_applicable":
            return self._create_result(
                element=element,
                status='na',
                trigger_time=trigger_time,
                notes=f"Not applicable for age group {age_group.value if age_group else 'unknown'}",
            )
        elif applicability == "conditional_not_met":
            return self._create_result(
                element=element,
                status='na',
                trigger_time=trigger_time,
                notes="Conditional requirement not met",
            )

        # Route to specific checker
        if element_id in self.ELEMENT_LOINC_MAP:
            return self._check_lab_element(element, patient_id, trigger_time, context)
        elif element_id.startswith("fi_lp"):
            return self._check_lp_element(element, patient_id, trigger_time, context)
        elif element_id.startswith("fi_abx"):
            return self._check_antibiotic_element(element, patient_id, trigger_time, context)
        elif element_id == "fi_hsv_risk_assessment":
            return self._check_hsv_assessment(element, patient_id, trigger_time, context)
        elif element_id == "fi_hsv_acyclovir_if_risk":
            return self._check_hsv_acyclovir(element, patient_id, trigger_time, context)
        elif element_id == "fi_repeat_ims_before_discharge":
            return self._check_repeat_inflammatory_markers(element, patient_id, trigger_time, context)
        elif element_id.startswith("fi_admit"):
            return self._check_admission_element(element, patient_id, trigger_time, context)
        elif element_id == "fi_safe_discharge_checklist":
            return self._check_discharge_checklist(element, patient_id, trigger_time, context)
        else:
            logger.warning(f"Unknown febrile infant element: {element_id}")
            return self._create_result(
                element=element,
                status='pending',
                trigger_time=trigger_time,
                notes=f"Unknown element type: {element_id}",
            )

    def _build_patient_context(self, patient_id, trigger_time, age_days=None, episode_id=None):
        """Build patient context for conditional element evaluation."""
        context = {
            "age_days": age_days,
            "age_group": get_age_group(age_days) if age_days is not None else None,
            "inflammatory_markers_abnormal": False,
            "ua_abnormal": False,
            "lp_performed": False,
            "csf_pleocytosis": False,
            "disposition_home": False,
            "hsv_risk_factors": [],
            "hsv_risk_present": False,
            "acyclovir_ordered": False,
            "clinical_impression": None,
            "is_ill_appearing": False,
            "clinical_impression_confidence": "LOW",
            "clinical_impression_source": "keyword",
        }

        if not self.fhir_client:
            return context

        # Get patient info if age not provided
        if age_days is None:
            patient = self.fhir_client.get_patient(patient_id)
            if patient and patient.get("birth_date"):
                from datetime import date
                birth_str = patient["birth_date"]
                if isinstance(birth_str, str):
                    birth_date = datetime.strptime(birth_str, "%Y-%m-%d").date()
                else:
                    birth_date = birth_str
                context["age_days"] = (trigger_time.date() - birth_date).days
                context["age_group"] = get_age_group(context["age_days"])

        # Check inflammatory markers
        context["inflammatory_markers_abnormal"] = self._are_inflammatory_markers_abnormal(
            patient_id, trigger_time
        )

        # Check UA
        context["ua_abnormal"] = self._is_ua_abnormal(patient_id, trigger_time)

        # Check LP status
        context["lp_performed"] = self._is_lp_performed(patient_id, trigger_time)

        # Check for CSF pleocytosis
        context["csf_pleocytosis"] = self._has_csf_pleocytosis(patient_id, trigger_time)

        # Check HSV risk factors (8-28d)
        if context["age_group"] in [InfantAgeGroup.DAYS_8_21, InfantAgeGroup.DAYS_22_28]:
            context["hsv_risk_factors"] = self._check_hsv_risk_factors(patient_id, trigger_time)
            context["hsv_risk_present"] = len(context["hsv_risk_factors"]) > 0

        # Clinical impression
        context.update(self._assess_clinical_impression(patient_id, trigger_time, episode_id))

        return context

    def _assess_clinical_impression(self, patient_id, trigger_time, episode_id=None):
        """Assess clinical impression using NLP or keyword matching."""
        result = {
            "clinical_impression": None,
            "is_ill_appearing": False,
            "clinical_impression_confidence": "LOW",
            "clinical_impression_source": "keyword",
        }

        if not self.fhir_client:
            return result

        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id,
            since_time=trigger_time - timedelta(hours=24),
        )

        if not notes:
            return result

        # Try NLP-based extraction first
        if self._nlp_extractor:
            try:
                note_texts = [n.get("text", "") for n in notes if n.get("text")]
                if note_texts:
                    impression = self._nlp_extractor.extract(note_texts)
                    result["clinical_impression"] = impression
                    result["is_ill_appearing"] = impression.get("is_high_risk", False)
                    result["clinical_impression_confidence"] = impression.get("confidence", "LOW")
                    result["clinical_impression_source"] = "nlp"
                    return result
            except Exception as e:
                logger.warning(f"NLP extraction failed, falling back to keywords: {e}")

        # Fallback to keyword-based matching
        ill_keywords = [
            "toxic", "toxic-appearing", "toxic appearing",
            "septic", "ill-appearing", "ill appearing",
            "lethargic", "listless", "limp", "floppy",
            "irritable", "inconsolable", "high-pitched cry",
            "poor feeding", "not feeding", "poor suck",
            "mottled", "mottling", "pale", "cyanotic",
            "delayed cap refill", "poor perfusion",
            "grunting", "nasal flaring", "retractions",
        ]

        well_keywords = [
            "well-appearing", "well appearing", "non-toxic",
            "alert", "playful", "active", "interactive",
            "feeding well", "good suck", "taking feeds",
            "good eye contact", "consolable",
            "pink", "well-perfused", "good perfusion",
        ]

        ill_count = 0
        well_count = 0
        for note in notes:
            note_text = note.get("text", "").lower()
            for kw in ill_keywords:
                if kw in note_text:
                    ill_count += 1
            for kw in well_keywords:
                if kw in note_text:
                    well_count += 1

        if ill_count > 0:
            result["is_ill_appearing"] = True
            result["clinical_impression_confidence"] = "MEDIUM" if ill_count >= 2 else "LOW"
        elif well_count > 0:
            result["is_ill_appearing"] = False
            result["clinical_impression_confidence"] = "MEDIUM" if well_count >= 2 else "LOW"

        return result

    def _check_element_applicability(self, element_id, context):
        """Check if element applies given patient context.

        Returns 'applicable', 'not_applicable', or 'conditional_not_met'.
        """
        age_group = context.get("age_group")
        im_abnormal = context.get("inflammatory_markers_abnormal", False)

        age_requirements = {
            "fi_lp_8_21d": [InfantAgeGroup.DAYS_8_21],
            "fi_lp_22_28d_im_abnormal": [InfantAgeGroup.DAYS_22_28],
            "fi_abx_8_21d": [InfantAgeGroup.DAYS_8_21],
            "fi_abx_22_28d_im_abnormal": [InfantAgeGroup.DAYS_22_28],
            "fi_admit_8_21d": [InfantAgeGroup.DAYS_8_21],
            "fi_admit_22_28d_im_abnormal": [InfantAgeGroup.DAYS_22_28],
            "fi_hsv_risk_assessment": [InfantAgeGroup.DAYS_8_21, InfantAgeGroup.DAYS_22_28],
            "fi_hsv_acyclovir_if_risk": [InfantAgeGroup.DAYS_8_21, InfantAgeGroup.DAYS_22_28],
            "fi_procalcitonin": [InfantAgeGroup.DAYS_29_60],
            "fi_repeat_ims_before_discharge": [InfantAgeGroup.DAYS_22_28, InfantAgeGroup.DAYS_29_60],
        }

        if element_id in age_requirements:
            if age_group not in age_requirements[element_id]:
                return "not_applicable"

        conditional_requirements = {
            "fi_lp_22_28d_im_abnormal": lambda: im_abnormal,
            "fi_abx_22_28d_im_abnormal": lambda: im_abnormal,
            "fi_admit_22_28d_im_abnormal": lambda: im_abnormal,
            "fi_urine_culture": lambda: context.get("ua_abnormal", False),
            "fi_safe_discharge_checklist": lambda: context.get("disposition_home", False),
            "fi_hsv_acyclovir_if_risk": lambda: context.get("hsv_risk_present", False),
            "fi_repeat_ims_before_discharge": lambda: im_abnormal,
        }

        if element_id in conditional_requirements:
            if not conditional_requirements[element_id]():
                return "conditional_not_met"

        return "applicable"

    def _are_inflammatory_markers_abnormal(self, patient_id, trigger_time):
        """Check if any inflammatory markers are abnormal (AAP 2021 thresholds)."""
        if not self.fhir_client:
            return False

        # PCT > 0.5 ng/mL
        pct_labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_PROCALCITONIN],
            since_time=trigger_time,
        )
        for lab in pct_labs:
            try:
                if float(lab.get("value", 0)) > cfg.FI_PCT_ABNORMAL:
                    return True
            except (ValueError, TypeError):
                pass

        # ANC > 4000
        anc_labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_ANC],
            since_time=trigger_time,
        )
        for lab in anc_labs:
            try:
                if float(lab.get("value", 0)) > cfg.FI_ANC_ABNORMAL:
                    return True
            except (ValueError, TypeError):
                pass

        # CRP > 2.0
        crp_labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_CRP],
            since_time=trigger_time,
        )
        for lab in crp_labs:
            try:
                if float(lab.get("value", 0)) > cfg.FI_CRP_ABNORMAL:
                    return True
            except (ValueError, TypeError):
                pass

        return False

    def _is_ua_abnormal(self, patient_id, trigger_time):
        """Check if UA is abnormal (WBC >= 5/HPF)."""
        if not self.fhir_client:
            return False

        ua_wbc_labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_UA_WBC],
            since_time=trigger_time,
        )
        for lab in ua_wbc_labs:
            try:
                if float(lab.get("value", 0)) >= cfg.FI_UA_WBC_ABNORMAL:
                    return True
            except (ValueError, TypeError):
                pass

        return False

    def _is_lp_performed(self, patient_id, trigger_time):
        """Check if LP was performed (CSF results available)."""
        if not self.fhir_client:
            return False

        csf_labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_CSF_WBC],
            since_time=trigger_time,
        )
        return len(csf_labs) > 0

    def _has_csf_pleocytosis(self, patient_id, trigger_time):
        """Check if CSF WBC is elevated (>15 cells/uL)."""
        if not self.fhir_client:
            return False

        csf_wbc_labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_CSF_WBC],
            since_time=trigger_time,
        )
        for lab in csf_wbc_labs:
            try:
                if float(lab.get("value", 0)) > cfg.FI_CSF_WBC_PLEOCYTOSIS:
                    return True
            except (ValueError, TypeError):
                pass

        return False

    def _check_hsv_risk_factors(self, patient_id, trigger_time):
        """Check clinical documentation for HSV risk factors."""
        if not self.fhir_client:
            return []

        risk_factors_found = []
        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id,
            since_time=trigger_time,
        )

        for note in notes:
            note_text = note.get("text", "").lower()
            for rf in HSV_RISK_FACTORS:
                if rf in note_text and rf not in risk_factors_found:
                    risk_factors_found.append(rf)

        if self._has_csf_pleocytosis(patient_id, trigger_time):
            if "csf pleocytosis" not in risk_factors_found:
                risk_factors_found.append("csf pleocytosis")

        # Elevated LFTs
        lft_labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_ALT, cfg.LOINC_AST],
            since_time=trigger_time,
        )
        for lab in lft_labs:
            try:
                if float(lab.get("value", 0)) > cfg.HSV_LFT_ELEVATED:
                    if "elevated lfts" not in risk_factors_found:
                        risk_factors_found.append("elevated lfts")
                    break
            except (ValueError, TypeError):
                pass

        return risk_factors_found

    def _check_lab_element(self, element, patient_id, trigger_time, context):
        """Check lab-based febrile infant elements."""
        loinc_codes = self.ELEMENT_LOINC_MAP.get(element.element_id, [])

        if not loinc_codes or not self.fhir_client:
            return self._create_result(
                element=element, status='pending',
                trigger_time=trigger_time, notes="No LOINC codes configured or no FHIR client",
            )

        labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=loinc_codes,
            since_time=trigger_time,
        )

        if not labs:
            status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
            notes = "Awaiting lab results" if status == 'pending' else "Time window expired without lab result"
            return self._create_result(element=element, status=status, trigger_time=trigger_time, notes=notes)

        deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
        for lab in sorted(labs, key=lambda x: x.get("effective_time", datetime.max)):
            effective_time = lab.get("effective_time")
            if effective_time and (deadline is None or effective_time <= deadline):
                value = lab.get("value")
                return self._create_result(
                    element=element, status='met', trigger_time=trigger_time,
                    completed_at=effective_time, value=value,
                    notes=f"Result: {value}" if value else "Result obtained",
                )

        status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
        return self._create_result(element=element, status=status, trigger_time=trigger_time,
                                   notes="Results found but not within required window")

    def _check_lp_element(self, element, patient_id, trigger_time, context):
        """Check LP-related elements."""
        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="No FHIR client")

        csf_labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_CSF_WBC, cfg.LOINC_CSF_RBC],
            since_time=trigger_time,
        )

        if csf_labs:
            deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
            for lab in sorted(csf_labs, key=lambda x: x.get("effective_time", datetime.max)):
                effective_time = lab.get("effective_time")
                if effective_time and (deadline is None or effective_time <= deadline):
                    return self._create_result(
                        element=element, status='met', trigger_time=trigger_time,
                        completed_at=effective_time, notes="LP performed - CSF results available",
                    )

        status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
        notes = "LP not yet performed" if status == 'pending' else "LP required but not performed within time window"
        return self._create_result(element=element, status=status, trigger_time=trigger_time, notes=notes)

    def _check_antibiotic_element(self, element, patient_id, trigger_time, context):
        """Check antibiotic administration elements."""
        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="No FHIR client")

        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id, since_time=trigger_time,
        )

        iv_antibiotics = [
            ma for ma in med_admins
            if ma.get("route", "").lower() in ["iv", "intravenous", "parenteral"]
            and self._is_antibiotic(ma.get("medication_name", ""))
        ]

        if not iv_antibiotics:
            status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
            notes = "IV antibiotics not yet administered" if status == 'pending' else "IV antibiotics not administered within time window"
            return self._create_result(element=element, status=status, trigger_time=trigger_time, notes=notes)

        deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
        for admin in sorted(iv_antibiotics, key=lambda x: x.get("admin_time", datetime.max)):
            admin_time = admin.get("admin_time")
            if admin_time and (deadline is None or admin_time <= deadline):
                med_name = admin.get("medication_name", "antibiotic")
                return self._create_result(
                    element=element, status='met', trigger_time=trigger_time,
                    completed_at=admin_time, value=med_name, notes=f"IV {med_name} administered",
                )

        status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
        return self._create_result(element=element, status=status, trigger_time=trigger_time,
                                   notes="IV antibiotics found but not within required window")

    def _check_hsv_assessment(self, element, patient_id, trigger_time, context):
        """Check HSV risk assessment documentation."""
        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="No FHIR client")

        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id, since_time=trigger_time,
        )
        if any("acyclovir" in ma.get("medication_name", "").lower() for ma in med_admins):
            return self._create_result(
                element=element, status='met', trigger_time=trigger_time,
                notes="Acyclovir administered - HSV considered",
            )

        notes = self.fhir_client.get_recent_notes(patient_id=patient_id, since_time=trigger_time)
        hsv_keywords = ["hsv", "herpes", "acyclovir", "hsv risk", "vesicles"]
        for note in notes:
            note_text = note.get("text", "").lower()
            if any(kw in note_text for kw in hsv_keywords):
                return self._create_result(
                    element=element, status='met', trigger_time=trigger_time,
                    completed_at=note.get("date"), notes="HSV risk documented in notes",
                )

        status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
        notes_str = "HSV risk assessment not yet documented" if status == 'pending' else "HSV risk assessment not documented"
        return self._create_result(element=element, status=status, trigger_time=trigger_time, notes=notes_str)

    def _check_hsv_acyclovir(self, element, patient_id, trigger_time, context):
        """Check if acyclovir is started for infants with HSV risk factors."""
        if not context.get("hsv_risk_present", False):
            return self._create_result(
                element=element, status='na', trigger_time=trigger_time,
                notes="No HSV risk factors identified",
            )

        risk_factors = context.get("hsv_risk_factors", [])

        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="No FHIR client")

        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id, since_time=trigger_time,
        )
        acyclovir_admins = [
            ma for ma in med_admins if "acyclovir" in ma.get("medication_name", "").lower()
        ]

        if acyclovir_admins:
            admin = acyclovir_admins[0]
            return self._create_result(
                element=element, status='met', trigger_time=trigger_time,
                completed_at=admin.get("admin_time"), value=", ".join(risk_factors),
                notes=f"Acyclovir started for HSV risk factors: {', '.join(risk_factors)}",
            )

        status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
        notes = (f"HSV risk factors present ({', '.join(risk_factors)}) - acyclovir recommended"
                 if status == 'pending'
                 else f"Acyclovir not started despite HSV risk factors: {', '.join(risk_factors)}")
        return self._create_result(element=element, status=status, trigger_time=trigger_time,
                                   value=", ".join(risk_factors), notes=notes)

    def _check_repeat_inflammatory_markers(self, element, patient_id, trigger_time, context):
        """Check if inflammatory markers were repeated before discharge."""
        if not context.get("inflammatory_markers_abnormal", False):
            return self._create_result(
                element=element, status='na', trigger_time=trigger_time,
                notes="Initial inflammatory markers normal - repeat not required",
            )

        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="No FHIR client")

        window_start = trigger_time + timedelta(hours=24)
        repeat_labs = []
        for loinc in [cfg.LOINC_PROCALCITONIN, cfg.LOINC_ANC, cfg.LOINC_CRP]:
            repeat_labs.extend(self.fhir_client.get_lab_results(
                patient_id=patient_id, loinc_codes=[loinc], since_time=window_start,
            ))

        if repeat_labs:
            lab = repeat_labs[0]
            return self._create_result(
                element=element, status='met', trigger_time=trigger_time,
                completed_at=lab.get("effective_time"),
                notes="Inflammatory markers repeated before discharge",
            )

        return self._create_result(
            element=element, status='pending', trigger_time=trigger_time,
            notes="Initially abnormal IMs - repeat recommended before discharge",
        )

    def _check_admission_element(self, element, patient_id, trigger_time, context):
        """Check hospital admission elements."""
        return self._create_result(
            element=element, status='pending', trigger_time=trigger_time,
            notes="Admission status check requires encounter data",
        )

    def _check_discharge_checklist(self, element, patient_id, trigger_time, context):
        """Check safe discharge checklist (5 items)."""
        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="No FHIR client")

        notes = self.fhir_client.get_recent_notes(patient_id=patient_id, since_time=trigger_time)

        checklist = {"followup_24h": False, "phone_number": False,
                     "transportation": False, "parent_education": False, "return_precautions": False}

        followup_kw = ["follow-up", "followup", "f/u", "pmd", "pediatrician", "appointment", "within 24"]
        phone_kw = ["phone", "telephone", "contact number", "callback", "working phone"]
        transport_kw = ["transportation", "transport", "ride", "car seat", "reliable transport"]
        education_kw = ["education", "educated", "teaching", "taught", "instructions", "counseled"]
        precaution_kw = ["return precautions", "warning signs", "when to return", "seek care if", "return if"]

        for note in notes:
            text = note.get("text", "").lower()
            if any(k in text for k in followup_kw): checklist["followup_24h"] = True
            if any(k in text for k in phone_kw): checklist["phone_number"] = True
            if any(k in text for k in transport_kw): checklist["transportation"] = True
            if any(k in text for k in education_kw): checklist["parent_education"] = True
            if any(k in text for k in precaution_kw): checklist["return_precautions"] = True

        documented = sum(checklist.values())
        missing = [k for k, v in checklist.items() if not v]

        if documented >= 4:
            return self._create_result(
                element=element, status='met', trigger_time=trigger_time,
                value=f"{documented}/5 items",
                notes=f"Safe discharge checklist complete ({documented}/5 items documented)",
            )

        if documented >= 2:
            return self._create_result(
                element=element, status='pending', trigger_time=trigger_time,
                value=f"{documented}/5 items",
                notes=f"Safe discharge checklist partially complete. Missing: {', '.join(missing)}",
            )

        return self._create_result(
            element=element, status='not_met', trigger_time=trigger_time,
            value=f"{documented}/5 items",
            notes=f"Safe discharge checklist incomplete ({documented}/5). Missing: {', '.join(missing)}",
        )

    def _is_antibiotic(self, medication_name):
        """Check if medication is an antibiotic."""
        abx_keywords = [
            "ampicillin", "gentamicin", "cefotaxime", "ceftriaxone",
            "vancomycin", "acyclovir", "penicillin", "cephalosporin",
            "amoxicillin", "cefazolin", "azithromycin", "metronidazole",
        ]
        return any(abx in medication_name.lower() for abx in abx_keywords)

    def clear_patient_cache(self, patient_id=None):
        """Clear cached patient context."""
        if patient_id:
            self._patient_context.pop(patient_id, None)
        else:
            self._patient_context.clear()
