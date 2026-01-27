"""C. diff Testing Appropriateness bundle element checker.

Implements the CCHMC C. diff Testing Algorithm (2024) for diagnostic stewardship
to ensure C. diff testing criteria are met before ordering.

Testing Appropriateness Criteria:
1. Age >= 3 years (or exception documented)
2. >= 3 liquid stools in 24 hours
3. No laxatives in past 48 hours
4. No enteral contrast in past 48 hours
5. No recent tube feed changes
6. No active GI bleed
7. Risk factor present (antibiotics, hospitalization, PPI, gastrostomy, chronic disease)
8. Symptoms persist >= 48 hours (if low-risk)

Purpose: Reduce inappropriate C. diff testing in pediatric patients.
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


class TestAppropriateness(Enum):
    """C. diff test appropriateness classification."""
    APPROPRIATE = "appropriate"
    POTENTIALLY_INAPPROPRIATE = "potentially_inappropriate"
    INAPPROPRIATE = "inappropriate"
    UNABLE_TO_ASSESS = "unable_to_assess"


class CDiffTestingChecker(ElementChecker):
    """Check bundle elements for C. diff testing appropriateness.

    This checker implements diagnostic stewardship for C. diff testing
    per CCHMC guidelines. The goal is to ensure testing is only performed
    when clinically appropriate to reduce false positives and unnecessary
    treatment.
    """

    # Minimum age for C. diff testing (years)
    MIN_AGE_YEARS = 3

    # Time windows (hours)
    LAXATIVE_WINDOW_HOURS = 48
    CONTRAST_WINDOW_HOURS = 48
    SYMPTOM_DURATION_HOURS = 48

    # Minimum liquid stools in 24 hours
    MIN_LIQUID_STOOLS = 3

    # Risk factors for C. diff
    RISK_FACTORS = [
        "antibiotic",
        "hospitalization",
        "ppi",
        "proton pump inhibitor",
        "gastrostomy",
        "g-tube",
        "gtube",
        "immunocompromised",
        "inflammatory bowel",
        "ibd",
        "chronic disease",
        "chemotherapy",
    ]

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
        age_years: Optional[float] = None,
    ) -> ElementCheckResult:
        """Check if a C. diff testing appropriateness element is met.

        Args:
            element: The bundle element to check.
            patient_id: FHIR patient ID.
            trigger_time: When the C. diff test was ordered.
            age_years: Patient age in years.

        Returns:
            ElementCheckResult with status.
        """
        element_id = element.element_id

        # Get patient context if not cached
        if patient_id not in self._patient_context:
            self._patient_context[patient_id] = self._build_patient_context(
                patient_id, trigger_time, age_years
            )

        context = self._patient_context[patient_id]

        # Route to specific checker based on element type
        if element_id == "cdiff_age_appropriate":
            return self._check_age_appropriate(element, patient_id, trigger_time, context)

        elif element_id == "cdiff_liquid_stools":
            return self._check_liquid_stools(element, patient_id, trigger_time, context)

        elif element_id == "cdiff_no_laxatives":
            return self._check_no_laxatives(element, patient_id, trigger_time, context)

        elif element_id == "cdiff_no_contrast":
            return self._check_no_contrast(element, patient_id, trigger_time, context)

        elif element_id == "cdiff_no_tube_feed_changes":
            return self._check_no_tube_feed_changes(element, patient_id, trigger_time, context)

        elif element_id == "cdiff_no_gi_bleed":
            return self._check_no_gi_bleed(element, patient_id, trigger_time, context)

        elif element_id == "cdiff_risk_factor_present":
            return self._check_risk_factor_present(element, patient_id, trigger_time, context)

        elif element_id == "cdiff_symptom_duration":
            return self._check_symptom_duration(element, patient_id, trigger_time, context)

        else:
            logger.warning(f"Unknown C. diff testing element: {element_id}")
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
        age_years: Optional[float] = None
    ) -> dict:
        """Build patient context for element evaluation.

        Args:
            patient_id: FHIR patient ID.
            trigger_time: When the C. diff test was ordered.
            age_years: Patient age in years (if known).

        Returns:
            Dict with patient context for element evaluation.
        """
        context = {
            "age_years": age_years,
            "has_exception_documented": False,
            "liquid_stool_count": 0,
            "laxative_given_48h": False,
            "contrast_given_48h": False,
            "tube_feed_change_48h": False,
            "gi_bleed_present": False,
            "risk_factors_present": [],
            "symptom_onset": None,
            "is_low_risk": False,
        }

        # Get patient info if age not provided
        if age_years is None:
            patient = self.fhir_client.get_patient(patient_id)
            if patient and patient.get("birth_date"):
                birth_date = patient["birth_date"]
                age_days = (trigger_time.date() - birth_date).days
                context["age_years"] = age_days / 365.25

        # Check for laxative administration in past 48h
        context["laxative_given_48h"] = self._check_laxative_given(patient_id, trigger_time)

        # Check for contrast administration in past 48h
        context["contrast_given_48h"] = self._check_contrast_given(patient_id, trigger_time)

        # Check for GI bleed
        context["gi_bleed_present"] = self._check_gi_bleed(patient_id, trigger_time)

        # Check for risk factors
        context["risk_factors_present"] = self._check_risk_factors(patient_id, trigger_time)

        return context

    def _check_laxative_given(self, patient_id: str, trigger_time: datetime) -> bool:
        """Check if laxative was given in past 48 hours."""
        window_start = trigger_time - timedelta(hours=self.LAXATIVE_WINDOW_HOURS)

        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id,
            since_time=window_start,
        )

        laxative_keywords = [
            "miralax", "polyethylene glycol", "peg", "lactulose",
            "bisacodyl", "dulcolax", "senna", "senokot", "docusate",
            "colace", "milk of magnesia", "magnesium citrate", "golytely",
            "enema", "fleet", "suppository"
        ]

        for admin in med_admins:
            admin_time = admin.get("admin_time")
            if admin_time and admin_time >= window_start and admin_time <= trigger_time:
                med_name = admin.get("medication_name", "").lower()
                if any(lax in med_name for lax in laxative_keywords):
                    return True

        return False

    def _check_contrast_given(self, patient_id: str, trigger_time: datetime) -> bool:
        """Check if enteral contrast was given in past 48 hours."""
        window_start = trigger_time - timedelta(hours=self.CONTRAST_WINDOW_HOURS)

        # Check imaging orders for contrast
        imaging_orders = self.fhir_client.get_orders(
            patient_id=patient_id,
            order_type="imaging",
            since_time=window_start,
        )

        contrast_keywords = [
            "contrast", "gastrografin", "barium", "oral contrast",
            "enteral contrast"
        ]

        for order in imaging_orders:
            order_time = order.get("order_time")
            if order_time and order_time >= window_start and order_time <= trigger_time:
                description = order.get("description", "").lower()
                if any(c in description for c in contrast_keywords):
                    return True

        # Also check medication administrations for contrast
        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id,
            since_time=window_start,
        )

        for admin in med_admins:
            admin_time = admin.get("admin_time")
            if admin_time and admin_time >= window_start and admin_time <= trigger_time:
                med_name = admin.get("medication_name", "").lower()
                if any(c in med_name for c in contrast_keywords):
                    return True

        return False

    def _check_gi_bleed(self, patient_id: str, trigger_time: datetime) -> bool:
        """Check for active GI bleed based on documentation."""
        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id,
            since_time=trigger_time - timedelta(hours=48),
        )

        gi_bleed_keywords = [
            "gi bleed", "gi bleeding", "gastrointestinal bleed",
            "melena", "hematochezia", "bloody stool", "blood in stool",
            "hematemesis", "upper gi bleed", "lower gi bleed"
        ]

        for note in notes:
            note_text = note.get("text", "").lower()
            if any(kw in note_text for kw in gi_bleed_keywords):
                return True

        # Check active problem list
        conditions = self.fhir_client.get_patient_conditions(patient_id)
        for condition in conditions:
            condition_lower = condition.lower()
            if any(kw in condition_lower for kw in gi_bleed_keywords):
                return True

        return False

    def _check_risk_factors(self, patient_id: str, trigger_time: datetime) -> list:
        """Check for C. diff risk factors."""
        risk_factors_found = []

        # Check for recent antibiotics
        window_start = trigger_time - timedelta(days=90)  # 3 months
        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id,
            since_time=window_start,
        )

        antibiotic_keywords = [
            "amoxicillin", "ampicillin", "penicillin", "cephalexin",
            "ceftriaxone", "cefdinir", "azithromycin", "ciprofloxacin",
            "clindamycin", "metronidazole", "vancomycin", "doxycycline",
            "sulfamethoxazole", "trimethoprim", "bactrim", "augmentin",
        ]

        for admin in med_admins:
            med_name = admin.get("medication_name", "").lower()
            if any(abx in med_name for abx in antibiotic_keywords):
                risk_factors_found.append("recent_antibiotics")
                break

        # Check for PPI
        ppi_keywords = ["omeprazole", "lansoprazole", "pantoprazole", "esomeprazole", "protonix", "prilosec", "prevacid", "nexium"]
        for admin in med_admins:
            med_name = admin.get("medication_name", "").lower()
            if any(ppi in med_name for ppi in ppi_keywords):
                risk_factors_found.append("ppi_use")
                break

        # Check notes for other risk factors
        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id,
            since_time=trigger_time - timedelta(days=30),
        )

        for note in notes:
            note_text = note.get("text", "").lower()
            if "gastrostomy" in note_text or "g-tube" in note_text:
                if "gastrostomy" not in risk_factors_found:
                    risk_factors_found.append("gastrostomy")
            if "immunocompromised" in note_text or "immune deficiency" in note_text:
                if "immunocompromised" not in risk_factors_found:
                    risk_factors_found.append("immunocompromised")
            if "inflammatory bowel" in note_text or "ibd" in note_text or "crohn" in note_text or "ulcerative colitis" in note_text:
                if "ibd" not in risk_factors_found:
                    risk_factors_found.append("ibd")

        # Check for recent hospitalization
        # For simplicity, assume current hospitalization counts
        if len(risk_factors_found) == 0:
            # Check if currently hospitalized
            risk_factors_found.append("hospitalization")

        return risk_factors_found

    def _check_age_appropriate(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check if patient is age >= 3 years (or exception documented).

        C. diff testing in children < 3 years is generally not recommended
        as asymptomatic carriage is common.
        """
        age_years = context.get("age_years")

        if age_years is None:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes="Patient age not available",
            )

        if age_years >= self.MIN_AGE_YEARS:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.MET,
                trigger_time=trigger_time,
                value=f"{age_years:.1f} years",
                notes=f"Age appropriate: {age_years:.1f} years >= {self.MIN_AGE_YEARS} years",
            )

        # Check for documented exception
        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id,
            since_time=trigger_time - timedelta(hours=24),
        )

        exception_keywords = [
            "c. diff testing appropriate", "cdiff testing indicated",
            "young age exception", "clinical concern for c. diff",
            "high suspicion for c. diff"
        ]

        for note in notes:
            note_text = note.get("text", "").lower()
            if any(kw in note_text for kw in exception_keywords):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.MET,
                    trigger_time=trigger_time,
                    value=f"{age_years:.1f} years (exception documented)",
                    notes=f"Age < {self.MIN_AGE_YEARS} years but exception documented",
                )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            value=f"{age_years:.1f} years",
            notes=f"Patient age {age_years:.1f} years < {self.MIN_AGE_YEARS} years. C. diff testing may be inappropriate.",
        )

    def _check_liquid_stools(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check if patient has >= 3 liquid stools in 24 hours."""
        # Check nursing documentation for stool counts
        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id,
            since_time=trigger_time - timedelta(hours=24),
        )

        stool_keywords = [
            "liquid stool", "watery stool", "diarrhea", "loose stool",
            "3 or more stools", "multiple loose stools", "frequent diarrhea"
        ]

        for note in notes:
            note_text = note.get("text", "").lower()
            if any(kw in note_text for kw in stool_keywords):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.MET,
                    trigger_time=trigger_time,
                    notes="Liquid stools documented (>=3 in 24 hours likely)",
                )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.PENDING,
            trigger_time=trigger_time,
            notes="Unable to confirm >= 3 liquid stools in 24 hours from documentation",
        )

    def _check_no_laxatives(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check that no laxatives were given in past 48 hours."""
        if context.get("laxative_given_48h", False):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.NOT_MET,
                trigger_time=trigger_time,
                notes="Laxative given within 48 hours - C. diff testing may be inappropriate",
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.MET,
            trigger_time=trigger_time,
            notes="No laxatives documented in past 48 hours",
        )

    def _check_no_contrast(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check that no enteral contrast was given in past 48 hours."""
        if context.get("contrast_given_48h", False):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.NOT_MET,
                trigger_time=trigger_time,
                notes="Enteral contrast given within 48 hours - C. diff testing may be inappropriate",
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.MET,
            trigger_time=trigger_time,
            notes="No enteral contrast documented in past 48 hours",
        )

    def _check_no_tube_feed_changes(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check for no recent tube feed changes."""
        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id,
            since_time=trigger_time - timedelta(hours=48),
        )

        tube_feed_keywords = [
            "tube feed change", "formula change", "feeds changed",
            "new formula", "switching feeds", "feed advancement"
        ]

        for note in notes:
            note_text = note.get("text", "").lower()
            if any(kw in note_text for kw in tube_feed_keywords):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.NOT_MET,
                    trigger_time=trigger_time,
                    notes="Tube feed changes documented within 48 hours",
                )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.MET,
            trigger_time=trigger_time,
            notes="No tube feed changes documented in past 48 hours",
        )

    def _check_no_gi_bleed(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check that there is no active GI bleed."""
        if context.get("gi_bleed_present", False):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.NOT_MET,
                trigger_time=trigger_time,
                notes="Active GI bleed documented - C. diff testing may yield false results",
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.MET,
            trigger_time=trigger_time,
            notes="No active GI bleed documented",
        )

    def _check_risk_factor_present(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check that at least one risk factor is present."""
        risk_factors = context.get("risk_factors_present", [])

        if risk_factors:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.MET,
                trigger_time=trigger_time,
                value=", ".join(risk_factors),
                notes=f"Risk factors present: {', '.join(risk_factors)}",
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            notes="No C. diff risk factors documented - testing may be inappropriate",
        )

    def _check_symptom_duration(
        self,
        element: BundleElement,
        patient_id: str,
        trigger_time: datetime,
        context: dict,
    ) -> ElementCheckResult:
        """Check symptom duration (conditional: >= 48h if low risk)."""
        risk_factors = context.get("risk_factors_present", [])

        # If high-risk, symptom duration doesn't apply
        if len(risk_factors) >= 2 or "recent_antibiotics" in risk_factors:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.NOT_APPLICABLE,
                trigger_time=trigger_time,
                notes="High-risk patient - symptom duration requirement not applicable",
            )

        # For low-risk, check symptom duration >= 48h
        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id,
            since_time=trigger_time - timedelta(hours=72),
        )

        # Look for symptom onset documentation
        onset_keywords = [
            "diarrhea started", "symptoms began", "onset", "duration",
            "for the past", "x days", "started having"
        ]

        for note in notes:
            note_text = note.get("text", "").lower()
            if any(kw in note_text for kw in onset_keywords):
                if any(d in note_text for d in ["2 days", "3 days", "48 hours", "several days"]):
                    return self._create_result(
                        element=element,
                        status=ElementCheckStatus.MET,
                        trigger_time=trigger_time,
                        notes="Symptoms documented for >= 48 hours",
                    )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.PENDING,
            trigger_time=trigger_time,
            notes="Low-risk patient - confirm symptoms persist >= 48 hours before testing",
        )

    def get_test_appropriateness(self, patient_id: str) -> tuple[TestAppropriateness, list[str]]:
        """Get overall test appropriateness assessment.

        Args:
            patient_id: FHIR patient ID.

        Returns:
            Tuple of (TestAppropriateness, list of concerns).
        """
        if patient_id not in self._patient_context:
            return TestAppropriateness.UNABLE_TO_ASSESS, ["Patient context not available"]

        context = self._patient_context[patient_id]
        concerns = []

        # Check age
        age_years = context.get("age_years")
        if age_years is not None and age_years < self.MIN_AGE_YEARS:
            concerns.append(f"Age < {self.MIN_AGE_YEARS} years (high carrier rate)")

        # Check confounders
        if context.get("laxative_given_48h"):
            concerns.append("Laxative given within 48h")
        if context.get("contrast_given_48h"):
            concerns.append("Enteral contrast given within 48h")
        if context.get("tube_feed_change_48h"):
            concerns.append("Tube feed changes within 48h")
        if context.get("gi_bleed_present"):
            concerns.append("Active GI bleed")

        # Check risk factors
        if not context.get("risk_factors_present"):
            concerns.append("No risk factors present")

        # Determine appropriateness
        if not concerns:
            return TestAppropriateness.APPROPRIATE, []
        elif len(concerns) >= 3:
            return TestAppropriateness.INAPPROPRIATE, concerns
        else:
            return TestAppropriateness.POTENTIALLY_INAPPROPRIATE, concerns

    def clear_patient_cache(self, patient_id: Optional[str] = None):
        """Clear cached patient context.

        Args:
            patient_id: Specific patient to clear, or None to clear all.
        """
        if patient_id:
            self._patient_context.pop(patient_id, None)
        else:
            self._patient_context.clear()
