"""Neonatal HSV bundle element checker.

Implements the CCHMC Neonatal HSV Algorithm (2024) for evaluation and
treatment of suspected HSV in neonates <=21 days.

HSV Classification:
- SEM (Skin, Eye, Mouth): 14 days treatment
- CNS (CNS involvement): 21 days treatment
- Disseminated: 21 days treatment

Risk factors for HSV:
- Maternal HSV history or active lesions
- Scalp monitor during delivery
- Prolonged rupture of membranes
- Ill-appearing neonate
- CSF pleocytosis
- Seizures
- Vesicular rash
- Elevated LFTs
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import logging
import sys
from pathlib import Path

# Add parent paths for imports
GUIDELINE_ADHERENCE_PATH = Path(__file__).parent.parent.parent
if str(GUIDELINE_ADHERENCE_PATH) not in sys.path:
    sys.path.insert(0, str(GUIDELINE_ADHERENCE_PATH))

from guideline_adherence import BundleElement

from ..models import ElementCheckResult, ElementCheckStatus
from ..config import config
from .base import ElementChecker

logger = logging.getLogger(__name__)


class HSVClassification(Enum):
    """HSV disease classification for treatment duration."""
    SEM = "SEM"                    # Skin, Eye, Mouth - 14 days
    CNS = "CNS"                    # CNS involvement - 21 days
    DISSEMINATED = "Disseminated" # Disseminated - 21 days
    UNKNOWN = "Unknown"


class HSVChecker(ElementChecker):
    """Check bundle elements for neonatal HSV guideline.

    This checker implements the CCHMC Neonatal HSV Algorithm.
    """

    # Map element IDs to LOINC codes
    ELEMENT_LOINC_MAP = {
        "hsv_csf_pcr": [config.LOINC_HSV_PCR_CSF],
        "hsv_surface_cultures": [config.LOINC_HSV_CULTURE],
        "hsv_blood_pcr": [config.LOINC_HSV_PCR_BLOOD],
        "hsv_lfts": [config.LOINC_ALT, config.LOINC_AST],
        "hsv_csf_studies": [config.LOINC_CSF_WBC, config.LOINC_CSF_RBC],
    }

    # Treatment durations by classification
    TREATMENT_DURATION = {
        HSVClassification.SEM: 14,
        HSVClassification.CNS: 21,
        HSVClassification.DISSEMINATED: 21,
        HSVClassification.UNKNOWN: 21,  # Default to longer if unknown
    }

    def __init__(self, fhir_client):
        """Initialize with FHIR client."""
        super().__init__(fhir_client)
        # Cache for patient context
        self._patient_context = {}

    def check(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        age_days: Optional[int] = None,
    ) -> ElementCheckResult:
        """Check if a neonatal HSV bundle element has been completed.

        Args:
            element: The bundle element to check.
            patient_id: FHIR patient ID.
            trigger_time: When the bundle was triggered.
            age_days: Patient age in days (must be <=21 for this bundle).

        Returns:
            ElementCheckResult with status.
        """
        element_id = element.element_id

        # Get patient context if not cached
        if patient_id not in self._patient_context:
            self._patient_context[patient_id] = self._build_patient_context(
                patient_id, trigger_time, age_days
            )

        context = self._patient_context[patient_id]

        # Check age applicability (HSV bundle for <=21 days)
        if context.get("age_days") is not None and context["age_days"] > 21:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.NOT_APPLICABLE,
                trigger_time=trigger_time,
                notes="HSV bundle only applies to neonates <=21 days",
            )

        # Route to specific checker based on element type
        if element_id == "hsv_csf_pcr":
            return self._check_csf_hsv_pcr(element, patient_id, trigger_time, context)

        elif element_id == "hsv_surface_cultures":
            return self._check_surface_cultures(element, patient_id, trigger_time, context)

        elif element_id == "hsv_blood_pcr":
            return self._check_blood_hsv_pcr(element, patient_id, trigger_time, context)

        elif element_id == "hsv_lfts":
            return self._check_lfts(element, patient_id, trigger_time, context)

        elif element_id == "hsv_acyclovir_started":
            return self._check_acyclovir_started(element, patient_id, trigger_time, context)

        elif element_id == "hsv_acyclovir_dose":
            return self._check_acyclovir_dose(element, patient_id, trigger_time, context)

        elif element_id == "hsv_id_consult":
            return self._check_id_consult(element, patient_id, trigger_time, context)

        elif element_id == "hsv_ophthalmology":
            return self._check_ophthalmology(element, patient_id, trigger_time, context)

        elif element_id == "hsv_neuroimaging":
            return self._check_neuroimaging(element, patient_id, trigger_time, context)

        elif element_id == "hsv_treatment_duration":
            return self._check_treatment_duration(element, patient_id, trigger_time, context)

        elif element_id == "hsv_suppressive_therapy":
            return self._check_suppressive_therapy(element, patient_id, trigger_time, context)

        else:
            logger.warning(f"Unknown HSV element: {element_id}")
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes=f"Unknown element type: {element_id}",
            )

    def _build_patient_context(
        self,
        patient_id: str,
        trigger_time: datetime,
        age_days: Optional[int] = None
    ) -> dict:
        """Build patient context for conditional element evaluation.

        Args:
            patient_id: FHIR patient ID.
            trigger_time: When the bundle was triggered.
            age_days: Patient age in days (if known).

        Returns:
            Dict with patient context for element evaluation.
        """
        context = {
            "age_days": age_days,
            "hsv_classification": HSVClassification.UNKNOWN,
            "csf_positive": False,
            "ocular_involvement": False,
            "cns_involvement": False,
            "disseminated": False,
            "acyclovir_start_time": None,
        }

        # Get patient info if age not provided
        if age_days is None:
            patient = self.fhir_client.get_patient(patient_id)
            if patient and patient.get("birth_date"):
                birth_date = patient["birth_date"]
                context["age_days"] = (trigger_time.date() - birth_date).days

        # Determine HSV classification based on findings
        context["hsv_classification"] = self._determine_hsv_classification(
            patient_id, trigger_time
        )

        return context

    def _determine_hsv_classification(
        self,
        patient_id: str,
        trigger_time: datetime
    ) -> HSVClassification:
        """Determine HSV classification based on clinical findings.

        Args:
            patient_id: FHIR patient ID.
            trigger_time: When evaluation started.

        Returns:
            HSVClassification (SEM, CNS, or Disseminated).
        """
        # Check for CNS involvement (CSF HSV positive or abnormal)
        csf_hsv_results = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[config.LOINC_HSV_PCR_CSF],
            since_time=trigger_time,
        )

        for result in csf_hsv_results:
            value = str(result.get("value", "")).lower()
            if value in ["positive", "detected", "pos", "+"]:
                return HSVClassification.CNS

        # Check CSF pleocytosis
        csf_wbc_results = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[config.LOINC_CSF_WBC],
            since_time=trigger_time,
        )

        for result in csf_wbc_results:
            try:
                value = float(result.get("value", 0))
                if value > config.FI_CSF_WBC_PLEOCYTOSIS:
                    return HSVClassification.CNS
            except (ValueError, TypeError):
                pass

        # Check for disseminated disease (elevated LFTs, multi-organ involvement)
        lft_results = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[config.LOINC_ALT, config.LOINC_AST],
            since_time=trigger_time,
        )

        elevated_lfts = False
        for result in lft_results:
            try:
                value = float(result.get("value", 0))
                # Elevated if >3x upper limit of normal (roughly >100 U/L in neonates)
                if value > 100:
                    elevated_lfts = True
                    break
            except (ValueError, TypeError):
                pass

        if elevated_lfts:
            # Check blood HSV PCR for disseminated
            blood_hsv_results = self.fhir_client.get_lab_results(
                patient_id=patient_id,
                loinc_codes=[config.LOINC_HSV_PCR_BLOOD],
                since_time=trigger_time,
            )

            for result in blood_hsv_results:
                value = str(result.get("value", "")).lower()
                if value in ["positive", "detected", "pos", "+"]:
                    return HSVClassification.DISSEMINATED

        # Default to SEM if no CNS or disseminated findings
        return HSVClassification.SEM

    def _check_csf_hsv_pcr(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check CSF HSV PCR element."""
        return self._check_lab_element(
            element, patient_id, trigger_time, context,
            loinc_codes=[config.LOINC_HSV_PCR_CSF],
            lab_name="CSF HSV PCR"
        )

    def _check_surface_cultures(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check surface cultures (SEM) element.

        Surface cultures include: conjunctiva, oropharynx, nasopharynx, rectum.
        """
        return self._check_lab_element(
            element, patient_id, trigger_time, context,
            loinc_codes=[config.LOINC_HSV_CULTURE],
            lab_name="HSV surface cultures (SEM)"
        )

    def _check_blood_hsv_pcr(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check blood HSV PCR element."""
        return self._check_lab_element(
            element, patient_id, trigger_time, context,
            loinc_codes=[config.LOINC_HSV_PCR_BLOOD],
            lab_name="Blood HSV PCR"
        )

    def _check_lfts(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check LFTs (ALT/AST) element."""
        return self._check_lab_element(
            element, patient_id, trigger_time, context,
            loinc_codes=[config.LOINC_ALT, config.LOINC_AST],
            lab_name="LFTs (ALT/AST)"
        )

    def _check_lab_element(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
        loinc_codes: list,
        lab_name: str,
    ) -> ElementCheckResult:
        """Generic lab element check."""
        labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=loinc_codes,
            since_time=trigger_time,
        )

        if not labs:
            if self._is_within_window(trigger_time, element.time_window_hours):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.PENDING,
                    trigger_time=trigger_time,
                    notes=f"Awaiting {lab_name}",
                )
            else:
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.NOT_MET,
                    trigger_time=trigger_time,
                    notes=f"{lab_name} not obtained within time window",
                )

        # Check if result within window
        deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
        for lab in sorted(labs, key=lambda x: x.get("effective_time", datetime.max)):
            effective_time = lab.get("effective_time")
            if effective_time and (deadline is None or effective_time <= deadline):
                value = lab.get("value")
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.MET,
                    trigger_time=trigger_time,
                    completed_at=effective_time,
                    value=value,
                    notes=f"{lab_name}: {value}" if value else f"{lab_name} obtained",
                )

        if self._is_within_window(trigger_time, element.time_window_hours):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes=f"{lab_name} found but not within required window",
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            notes=f"{lab_name} not obtained within required timeframe",
        )

    def _check_acyclovir_started(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check if acyclovir was started within 1 hour."""
        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id,
            since_time=trigger_time,
        )

        acyclovir_admins = [
            ma for ma in med_admins
            if "acyclovir" in ma.get("medication_name", "").lower()
        ]

        if not acyclovir_admins:
            if self._is_within_window(trigger_time, element.time_window_hours):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.PENDING,
                    trigger_time=trigger_time,
                    notes="Acyclovir not yet administered",
                )
            else:
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.NOT_MET,
                    trigger_time=trigger_time,
                    notes="Acyclovir not started within 1 hour",
                )

        # Check timing
        deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
        for admin in sorted(acyclovir_admins, key=lambda x: x.get("admin_time", datetime.max)):
            admin_time = admin.get("admin_time")
            if admin_time and (deadline is None or admin_time <= deadline):
                # Save start time for context
                context["acyclovir_start_time"] = admin_time
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.MET,
                    trigger_time=trigger_time,
                    completed_at=admin_time,
                    notes="Acyclovir started within required window",
                )

        if self._is_within_window(trigger_time, element.time_window_hours):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes="Acyclovir found but timing check pending",
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            notes="Acyclovir not started within required timeframe",
        )

    def _check_acyclovir_dose(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check if acyclovir dose is 60 mg/kg/day divided Q8H.

        Expected: 20 mg/kg Q8H = 60 mg/kg/day.
        """
        med_orders = self.fhir_client.get_medication_orders(
            patient_id=patient_id,
            since_time=trigger_time,
        )

        acyclovir_orders = [
            mo for mo in med_orders
            if "acyclovir" in mo.get("medication_name", "").lower()
        ]

        if not acyclovir_orders:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes="No acyclovir orders found",
            )

        # Check for appropriate dosing (20 mg/kg Q8H)
        for order in acyclovir_orders:
            dose_text = str(order.get("dose", "")).lower()
            frequency = str(order.get("frequency", "")).lower()

            # Check for 20 mg/kg and Q8H
            has_correct_dose = "20" in dose_text and "mg/kg" in dose_text
            has_correct_freq = "q8" in frequency or "every 8" in frequency

            if has_correct_dose and has_correct_freq:
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.MET,
                    trigger_time=trigger_time,
                    completed_at=order.get("order_time"),
                    value=f"{dose_text} {frequency}",
                    notes="Acyclovir 60 mg/kg/day Q8H ordered correctly",
                )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            notes="Acyclovir dose may not be optimal (expected 20 mg/kg Q8H)",
        )

    def _check_id_consult(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check if ID consult was ordered."""
        orders = self.fhir_client.get_orders(
            patient_id=patient_id,
            order_type="consult",
            since_time=trigger_time,
        )

        id_consults = [
            o for o in orders
            if any(kw in o.get("description", "").lower()
                   for kw in ["infectious disease", "id consult", "infection"])
        ]

        if id_consults:
            consult = id_consults[0]
            return self._create_result(
                element=element,
                status=ElementCheckStatus.MET,
                trigger_time=trigger_time,
                completed_at=consult.get("order_time"),
                notes="ID consult ordered",
            )

        if self._is_within_window(trigger_time, element.time_window_hours):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes="ID consult not yet ordered",
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            notes="ID consult not ordered within required timeframe",
        )

    def _check_ophthalmology(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check ophthalmology consult (conditional if ocular involvement)."""
        # Check for ocular involvement in notes or findings
        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id,
            since_time=trigger_time,
        )

        ocular_keywords = ["eye", "ocular", "conjunctiv", "keratitis", "chorioretinitis"]
        has_ocular_involvement = False

        for note in notes:
            note_text = note.get("text", "").lower()
            if any(kw in note_text for kw in ocular_keywords):
                has_ocular_involvement = True
                break

        if not has_ocular_involvement:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.NOT_APPLICABLE,
                trigger_time=trigger_time,
                notes="Ophthalmology consult conditional on ocular involvement (not documented)",
            )

        # Check for ophthalmology consult
        orders = self.fhir_client.get_orders(
            patient_id=patient_id,
            order_type="consult",
            since_time=trigger_time,
        )

        ophtho_consults = [
            o for o in orders
            if any(kw in o.get("description", "").lower()
                   for kw in ["ophthalmology", "eye", "ophtho"])
        ]

        if ophtho_consults:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.MET,
                trigger_time=trigger_time,
                completed_at=ophtho_consults[0].get("order_time"),
                notes="Ophthalmology consult ordered for ocular involvement",
            )

        if self._is_within_window(trigger_time, element.time_window_hours):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes="Ophthalmology consult needed for ocular involvement",
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            notes="Ophthalmology consult not ordered despite ocular involvement",
        )

    def _check_neuroimaging(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check neuroimaging (conditional if CNS involvement)."""
        classification = context.get("hsv_classification", HSVClassification.UNKNOWN)

        if classification not in [HSVClassification.CNS, HSVClassification.DISSEMINATED]:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.NOT_APPLICABLE,
                trigger_time=trigger_time,
                notes="Neuroimaging conditional on CNS involvement",
            )

        # Check for neuroimaging orders
        imaging_orders = self.fhir_client.get_orders(
            patient_id=patient_id,
            order_type="imaging",
            since_time=trigger_time,
        )

        neuro_imaging = [
            o for o in imaging_orders
            if any(kw in o.get("description", "").lower()
                   for kw in ["mri brain", "head mri", "brain mri", "ct head", "head ct"])
        ]

        if neuro_imaging:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.MET,
                trigger_time=trigger_time,
                completed_at=neuro_imaging[0].get("order_time"),
                notes="Neuroimaging ordered for CNS involvement",
            )

        if self._is_within_window(trigger_time, element.time_window_hours):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes="Neuroimaging needed for CNS involvement",
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            notes="Neuroimaging not ordered despite CNS involvement",
        )

    def _check_treatment_duration(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check treatment duration based on classification.

        - SEM: 14 days
        - CNS: 21 days
        - Disseminated: 21 days
        """
        classification = context.get("hsv_classification", HSVClassification.UNKNOWN)
        required_days = self.TREATMENT_DURATION.get(classification, 21)

        # This is typically assessed at end of therapy
        # For now, track expected duration
        return self._create_result(
            element=element,
            status=ElementCheckStatus.PENDING,
            trigger_time=trigger_time,
            notes=f"Treatment duration tracking: {classification.value} = {required_days} days required",
            value=required_days,
        )

    def _check_suppressive_therapy(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check suppressive therapy follow-up documentation.

        All HSV cases need suppressive oral acyclovir until 6 months after treatment.
        """
        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id,
            since_time=trigger_time,
        )

        suppressive_keywords = [
            "suppressive therapy", "suppressive acyclovir",
            "oral acyclovir", "prophylaxis", "suppress"
        ]

        for note in notes:
            note_text = note.get("text", "").lower()
            if any(kw in note_text for kw in suppressive_keywords):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.MET,
                    trigger_time=trigger_time,
                    completed_at=note.get("date"),
                    notes="Suppressive therapy follow-up documented",
                )

        # Check for discharge medication order
        med_orders = self.fhir_client.get_medication_orders(
            patient_id=patient_id,
            since_time=trigger_time,
        )

        oral_acyclovir = [
            mo for mo in med_orders
            if "acyclovir" in mo.get("medication_name", "").lower()
            and mo.get("route", "").lower() in ["oral", "po"]
        ]

        if oral_acyclovir:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.MET,
                trigger_time=trigger_time,
                completed_at=oral_acyclovir[0].get("order_time"),
                notes="Oral acyclovir ordered for suppressive therapy",
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.PENDING,
            trigger_time=trigger_time,
            notes="Suppressive therapy follow-up needed at discharge",
        )

    def get_hsv_classification(self, patient_id: str) -> HSVClassification:
        """Get the HSV classification for a patient.

        Args:
            patient_id: FHIR patient ID.

        Returns:
            HSVClassification for the patient.
        """
        if patient_id in self._patient_context:
            return self._patient_context[patient_id].get(
                "hsv_classification", HSVClassification.UNKNOWN
            )
        return HSVClassification.UNKNOWN

    def clear_patient_cache(self, patient_id: Optional[str] = None):
        """Clear cached patient context.

        Args:
            patient_id: Specific patient to clear, or None to clear all.
        """
        if patient_id:
            self._patient_context.pop(patient_id, None)
        else:
            self._patient_context.clear()
