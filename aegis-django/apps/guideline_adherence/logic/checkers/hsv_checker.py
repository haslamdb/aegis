"""Neonatal HSV bundle element checker.

Implements the CCHMC Neonatal HSV Algorithm (2024) for evaluation and
treatment of suspected HSV in neonates <=21 days.

HSV Classification:
- SEM (Skin, Eye, Mouth): 14 days treatment
- CNS (CNS involvement): 21 days treatment
- Disseminated: 21 days treatment
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import logging

from apps.guideline_adherence.logic import config as cfg
from .base import ElementChecker, CheckResult

logger = logging.getLogger(__name__)


class HSVClassification(Enum):
    """HSV disease classification for treatment duration."""
    SEM = "SEM"                    # Skin, Eye, Mouth - 14 days
    CNS = "CNS"                    # CNS involvement - 21 days
    DISSEMINATED = "Disseminated"  # Disseminated - 21 days
    UNKNOWN = "Unknown"


class HSVChecker(ElementChecker):
    """Check bundle elements for neonatal HSV guideline.

    Implements the CCHMC Neonatal HSV Algorithm.
    """

    # Treatment durations by classification
    TREATMENT_DURATION = {
        HSVClassification.SEM: 14,
        HSVClassification.CNS: 21,
        HSVClassification.DISSEMINATED: 21,
        HSVClassification.UNKNOWN: 21,
    }

    def __init__(self, fhir_client=None):
        """Initialize with FHIR client."""
        super().__init__(fhir_client)
        self._patient_context = {}

    def check(self, element, patient_id: str, trigger_time: datetime, **kwargs) -> CheckResult:
        """Check if a neonatal HSV bundle element has been completed."""
        element_id = element.element_id
        age_days = kwargs.get('age_days')

        if patient_id not in self._patient_context:
            self._patient_context[patient_id] = self._build_patient_context(
                patient_id, trigger_time, age_days
            )

        context = self._patient_context[patient_id]

        # Age check
        if context.get("age_days") is not None and context["age_days"] > 21:
            return self._create_result(
                element=element, status='na', trigger_time=trigger_time,
                notes="HSV bundle only applies to neonates <=21 days",
            )

        checkers = {
            "hsv_csf_pcr": lambda: self._check_lab(element, patient_id, trigger_time,
                                                    [cfg.LOINC_HSV_CSF_PCR], "CSF HSV PCR"),
            "hsv_surface_cultures": lambda: self._check_lab(element, patient_id, trigger_time,
                                                             [cfg.LOINC_HSV_CULTURE], "HSV surface cultures"),
            "hsv_blood_pcr": lambda: self._check_lab(element, patient_id, trigger_time,
                                                      [cfg.LOINC_HSV_BLOOD_PCR], "Blood HSV PCR"),
            "hsv_lfts": lambda: self._check_lab(element, patient_id, trigger_time,
                                                 [cfg.LOINC_ALT, cfg.LOINC_AST], "LFTs (ALT/AST)"),
            "hsv_acyclovir_started": lambda: self._check_acyclovir_started(element, patient_id, trigger_time, context),
            "hsv_acyclovir_dose": lambda: self._check_acyclovir_dose(element, patient_id, trigger_time, context),
            "hsv_id_consult": lambda: self._check_consult(element, patient_id, trigger_time,
                                                           ["infectious disease", "id consult", "infection"],
                                                           "ID consult"),
            "hsv_ophthalmology": lambda: self._check_ophthalmology(element, patient_id, trigger_time, context),
            "hsv_neuroimaging": lambda: self._check_neuroimaging(element, patient_id, trigger_time, context),
            "hsv_treatment_duration": lambda: self._check_treatment_duration(element, patient_id, trigger_time, context),
            "hsv_suppressive_therapy": lambda: self._check_suppressive_therapy(element, patient_id, trigger_time, context),
        }

        checker = checkers.get(element_id)
        if checker:
            return checker()

        logger.warning(f"Unknown HSV element: {element_id}")
        return self._create_result(
            element=element, status='pending', trigger_time=trigger_time,
            notes=f"Unknown element type: {element_id}",
        )

    def _build_patient_context(self, patient_id, trigger_time, age_days=None):
        """Build patient context for conditional element evaluation."""
        context = {
            "age_days": age_days,
            "hsv_classification": HSVClassification.UNKNOWN,
            "csf_positive": False,
            "acyclovir_start_time": None,
        }

        if not self.fhir_client:
            return context

        if age_days is None:
            patient = self.fhir_client.get_patient(patient_id)
            if patient and patient.get("birth_date"):
                birth_str = patient["birth_date"]
                if isinstance(birth_str, str):
                    birth_date = datetime.strptime(birth_str, "%Y-%m-%d").date()
                else:
                    birth_date = birth_str
                context["age_days"] = (trigger_time.date() - birth_date).days

        context["hsv_classification"] = self._determine_hsv_classification(patient_id, trigger_time)
        return context

    def _determine_hsv_classification(self, patient_id, trigger_time):
        """Determine HSV classification based on clinical findings."""
        if not self.fhir_client:
            return HSVClassification.UNKNOWN

        # CNS: CSF HSV PCR positive or CSF pleocytosis
        csf_hsv = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_HSV_CSF_PCR],
            since_time=trigger_time,
        )
        for result in csf_hsv:
            value = str(result.get("value", "")).lower()
            if value in ["positive", "detected", "pos", "+"]:
                return HSVClassification.CNS

        csf_wbc = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_CSF_WBC],
            since_time=trigger_time,
        )
        for result in csf_wbc:
            try:
                if float(result.get("value", 0)) > cfg.FI_CSF_WBC_PLEOCYTOSIS:
                    return HSVClassification.CNS
            except (ValueError, TypeError):
                pass

        # Disseminated: elevated LFTs + blood PCR positive
        lft_results = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[cfg.LOINC_ALT, cfg.LOINC_AST],
            since_time=trigger_time,
        )
        elevated_lfts = False
        for result in lft_results:
            try:
                if float(result.get("value", 0)) > cfg.HSV_LFT_ELEVATED:
                    elevated_lfts = True
                    break
            except (ValueError, TypeError):
                pass

        if elevated_lfts:
            blood_hsv = self.fhir_client.get_lab_results(
                patient_id=patient_id,
                loinc_codes=[cfg.LOINC_HSV_BLOOD_PCR],
                since_time=trigger_time,
            )
            for result in blood_hsv:
                value = str(result.get("value", "")).lower()
                if value in ["positive", "detected", "pos", "+"]:
                    return HSVClassification.DISSEMINATED

        return HSVClassification.SEM

    def _check_lab(self, element, patient_id, trigger_time, loinc_codes, lab_name):
        """Generic lab element check."""
        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes=f"Awaiting {lab_name}")

        labs = self.fhir_client.get_lab_results(
            patient_id=patient_id, loinc_codes=loinc_codes, since_time=trigger_time,
        )

        if not labs:
            status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
            notes = f"Awaiting {lab_name}" if status == 'pending' else f"{lab_name} not obtained within time window"
            return self._create_result(element=element, status=status, trigger_time=trigger_time, notes=notes)

        deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
        for lab in sorted(labs, key=lambda x: x.get("effective_time", datetime.max)):
            effective_time = lab.get("effective_time")
            if effective_time and (deadline is None or effective_time <= deadline):
                value = lab.get("value")
                return self._create_result(
                    element=element, status='met', trigger_time=trigger_time,
                    completed_at=effective_time, value=value,
                    notes=f"{lab_name}: {value}" if value else f"{lab_name} obtained",
                )

        status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
        return self._create_result(element=element, status=status, trigger_time=trigger_time,
                                   notes=f"{lab_name} found but not within required window")

    def _check_acyclovir_started(self, element, patient_id, trigger_time, context):
        """Check if acyclovir was started within 1 hour."""
        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="Acyclovir not yet administered")

        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id, since_time=trigger_time,
        )
        acyclovir = [ma for ma in med_admins if "acyclovir" in ma.get("medication_name", "").lower()]

        if not acyclovir:
            status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
            notes = "Acyclovir not yet administered" if status == 'pending' else "Acyclovir not started within 1 hour"
            return self._create_result(element=element, status=status, trigger_time=trigger_time, notes=notes)

        deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
        for admin in sorted(acyclovir, key=lambda x: x.get("admin_time", datetime.max)):
            admin_time = admin.get("admin_time")
            if admin_time and (deadline is None or admin_time <= deadline):
                context["acyclovir_start_time"] = admin_time
                return self._create_result(
                    element=element, status='met', trigger_time=trigger_time,
                    completed_at=admin_time, notes="Acyclovir started within required window",
                )

        status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
        return self._create_result(element=element, status=status, trigger_time=trigger_time,
                                   notes="Acyclovir not started within required timeframe")

    def _check_acyclovir_dose(self, element, patient_id, trigger_time, context):
        """Check if acyclovir dose is 20 mg/kg Q8H (60 mg/kg/day)."""
        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="No acyclovir orders found")

        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id, since_time=trigger_time,
        )
        acyclovir = [ma for ma in med_admins if "acyclovir" in ma.get("medication_name", "").lower()]

        if not acyclovir:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="No acyclovir orders found")

        for order in acyclovir:
            dose_text = str(order.get("dose", "")).lower()
            # Check for 20 mg/kg dosing
            if "20" in dose_text and "mg" in dose_text:
                return self._create_result(
                    element=element, status='met', trigger_time=trigger_time,
                    completed_at=order.get("admin_time"), value=dose_text,
                    notes="Acyclovir 20 mg/kg Q8H ordered correctly",
                )

        return self._create_result(
            element=element, status='not_met', trigger_time=trigger_time,
            notes="Acyclovir dose may not be optimal (expected 20 mg/kg Q8H)",
        )

    def _check_consult(self, element, patient_id, trigger_time, keywords, consult_name):
        """Check if a consult was ordered."""
        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes=f"{consult_name} not yet ordered")

        # Check notes for consult documentation
        notes = self.fhir_client.get_recent_notes(patient_id=patient_id, since_time=trigger_time)
        for note in notes:
            note_text = note.get("text", "").lower()
            if any(kw in note_text for kw in keywords):
                return self._create_result(
                    element=element, status='met', trigger_time=trigger_time,
                    completed_at=note.get("date"), notes=f"{consult_name} documented",
                )

        status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
        notes_str = f"{consult_name} not yet ordered" if status == 'pending' else f"{consult_name} not ordered within required timeframe"
        return self._create_result(element=element, status=status, trigger_time=trigger_time, notes=notes_str)

    def _check_ophthalmology(self, element, patient_id, trigger_time, context):
        """Check ophthalmology consult (conditional if ocular involvement)."""
        if not self.fhir_client:
            return self._create_result(element=element, status='na',
                                       trigger_time=trigger_time, notes="Ophthalmology consult conditional")

        notes = self.fhir_client.get_recent_notes(patient_id=patient_id, since_time=trigger_time)
        ocular_keywords = ["eye", "ocular", "conjunctiv", "keratitis", "chorioretinitis"]

        has_ocular = False
        for note in notes:
            if any(kw in note.get("text", "").lower() for kw in ocular_keywords):
                has_ocular = True
                break

        if not has_ocular:
            return self._create_result(
                element=element, status='na', trigger_time=trigger_time,
                notes="Ophthalmology consult conditional on ocular involvement (not documented)",
            )

        return self._check_consult(element, patient_id, trigger_time,
                                   ["ophthalmology", "eye", "ophtho"], "Ophthalmology consult")

    def _check_neuroimaging(self, element, patient_id, trigger_time, context):
        """Check neuroimaging (conditional if CNS involvement)."""
        classification = context.get("hsv_classification", HSVClassification.UNKNOWN)

        if classification not in [HSVClassification.CNS, HSVClassification.DISSEMINATED]:
            return self._create_result(
                element=element, status='na', trigger_time=trigger_time,
                notes="Neuroimaging conditional on CNS involvement",
            )

        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="Neuroimaging needed for CNS involvement")

        notes = self.fhir_client.get_recent_notes(patient_id=patient_id, since_time=trigger_time)
        imaging_keywords = ["mri brain", "head mri", "brain mri", "ct head", "head ct", "neuroimaging"]

        for note in notes:
            if any(kw in note.get("text", "").lower() for kw in imaging_keywords):
                return self._create_result(
                    element=element, status='met', trigger_time=trigger_time,
                    completed_at=note.get("date"), notes="Neuroimaging ordered for CNS involvement",
                )

        status = 'pending' if self._is_within_window(trigger_time, element.time_window_hours) else 'not_met'
        notes_str = "Neuroimaging needed for CNS involvement" if status == 'pending' else "Neuroimaging not ordered despite CNS involvement"
        return self._create_result(element=element, status=status, trigger_time=trigger_time, notes=notes_str)

    def _check_treatment_duration(self, element, patient_id, trigger_time, context):
        """Check treatment duration based on classification."""
        classification = context.get("hsv_classification", HSVClassification.UNKNOWN)
        required_days = self.TREATMENT_DURATION.get(classification, 21)

        return self._create_result(
            element=element, status='pending', trigger_time=trigger_time,
            notes=f"Treatment duration tracking: {classification.value} = {required_days} days required",
            value=str(required_days),
        )

    def _check_suppressive_therapy(self, element, patient_id, trigger_time, context):
        """Check suppressive therapy follow-up documentation."""
        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="Suppressive therapy follow-up needed")

        notes = self.fhir_client.get_recent_notes(patient_id=patient_id, since_time=trigger_time)
        suppressive_keywords = [
            "suppressive therapy", "suppressive acyclovir",
            "oral acyclovir", "prophylaxis", "suppress"
        ]

        for note in notes:
            if any(kw in note.get("text", "").lower() for kw in suppressive_keywords):
                return self._create_result(
                    element=element, status='met', trigger_time=trigger_time,
                    completed_at=note.get("date"), notes="Suppressive therapy follow-up documented",
                )

        return self._create_result(
            element=element, status='pending', trigger_time=trigger_time,
            notes="Suppressive therapy follow-up needed at discharge",
        )

    def get_hsv_classification(self, patient_id):
        """Get HSV classification for a patient."""
        if patient_id in self._patient_context:
            return self._patient_context[patient_id].get(
                "hsv_classification", HSVClassification.UNKNOWN
            )
        return HSVClassification.UNKNOWN

    def clear_patient_cache(self, patient_id=None):
        """Clear cached patient context."""
        if patient_id:
            self._patient_context.pop(patient_id, None)
        else:
            self._patient_context.clear()
