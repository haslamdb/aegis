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
7. Risk factor present (antibiotics, hospitalization, PPI, gastrostomy)
8. Symptoms persist >= 48 hours (if low-risk)
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import logging

from .base import ElementChecker, CheckResult

logger = logging.getLogger(__name__)


class TestAppropriateness(Enum):
    """C. diff test appropriateness classification."""
    APPROPRIATE = "appropriate"
    POTENTIALLY_INAPPROPRIATE = "potentially_inappropriate"
    INAPPROPRIATE = "inappropriate"
    UNABLE_TO_ASSESS = "unable_to_assess"


class CDiffTestingChecker(ElementChecker):
    """Check bundle elements for C. diff testing appropriateness.

    Implements diagnostic stewardship per CCHMC guidelines.
    """

    MIN_AGE_YEARS = 3
    LAXATIVE_WINDOW_HOURS = 48
    CONTRAST_WINDOW_HOURS = 48
    SYMPTOM_DURATION_HOURS = 48
    MIN_LIQUID_STOOLS = 3

    LAXATIVE_KEYWORDS = [
        "miralax", "polyethylene glycol", "peg", "lactulose",
        "bisacodyl", "dulcolax", "senna", "senokot", "docusate",
        "colace", "milk of magnesia", "magnesium citrate", "golytely",
        "enema", "fleet", "suppository",
    ]

    CONTRAST_KEYWORDS = [
        "contrast", "gastrografin", "barium", "oral contrast", "enteral contrast",
    ]

    def __init__(self, fhir_client=None, use_nlp=True):
        """Initialize with FHIR client."""
        super().__init__(fhir_client)
        self._patient_context = {}
        self._nlp_extractor = None

        if use_nlp:
            try:
                from apps.guideline_adherence.logic.nlp.gi_symptoms import GISymptomExtractor
                self._nlp_extractor = GISymptomExtractor()
                logger.info("GI symptom NLP extractor initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize GI NLP extractor: {e}")

    def check(self, element, patient_id: str, trigger_time: datetime, **kwargs) -> CheckResult:
        """Check if a C. diff testing element is met."""
        element_id = element.element_id
        age_years = kwargs.get('age_years')

        if patient_id not in self._patient_context:
            self._patient_context[patient_id] = self._build_patient_context(
                patient_id, trigger_time, age_years
            )

        context = self._patient_context[patient_id]

        checkers = {
            "cdiff_age_appropriate": self._check_age_appropriate,
            "cdiff_liquid_stools": self._check_liquid_stools,
            "cdiff_no_laxatives": self._check_no_laxatives,
            "cdiff_no_contrast": self._check_no_contrast,
            "cdiff_no_tube_feed_changes": self._check_no_tube_feed_changes,
            "cdiff_no_gi_bleed": self._check_no_gi_bleed,
            "cdiff_risk_factor_present": self._check_risk_factor_present,
            "cdiff_symptom_duration": self._check_symptom_duration,
        }

        checker = checkers.get(element_id)
        if checker:
            return checker(element, patient_id, trigger_time, context)

        logger.warning(f"Unknown C. diff testing element: {element_id}")
        return self._create_result(
            element=element, status='pending', trigger_time=trigger_time,
            notes=f"Unknown element type: {element_id}",
        )

    def _build_patient_context(self, patient_id, trigger_time, age_years=None):
        """Build patient context for element evaluation."""
        context = {
            "age_years": age_years,
            "laxative_given_48h": False,
            "contrast_given_48h": False,
            "gi_bleed_present": False,
            "risk_factors_present": [],
        }

        if not self.fhir_client:
            return context

        if age_years is None:
            patient = self.fhir_client.get_patient(patient_id)
            if patient and patient.get("birth_date"):
                birth_str = patient["birth_date"]
                if isinstance(birth_str, str):
                    birth_date = datetime.strptime(birth_str, "%Y-%m-%d").date()
                else:
                    birth_date = birth_str
                age_days = (trigger_time.date() - birth_date).days
                context["age_years"] = age_days / 365.25

        context["laxative_given_48h"] = self._check_laxative_given(patient_id, trigger_time)
        context["contrast_given_48h"] = self._check_contrast_given(patient_id, trigger_time)
        context["gi_bleed_present"] = self._check_gi_bleed(patient_id, trigger_time)
        context["risk_factors_present"] = self._check_risk_factors(patient_id, trigger_time)

        return context

    def _check_laxative_given(self, patient_id, trigger_time):
        """Check if laxative was given in past 48 hours."""
        if not self.fhir_client:
            return False

        window_start = trigger_time - timedelta(hours=self.LAXATIVE_WINDOW_HOURS)
        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id, since_time=window_start,
        )

        for admin in med_admins:
            admin_time = admin.get("admin_time")
            if admin_time and window_start <= admin_time <= trigger_time:
                med_name = admin.get("medication_name", "").lower()
                if any(lax in med_name for lax in self.LAXATIVE_KEYWORDS):
                    return True
        return False

    def _check_contrast_given(self, patient_id, trigger_time):
        """Check if enteral contrast was given in past 48 hours."""
        if not self.fhir_client:
            return False

        window_start = trigger_time - timedelta(hours=self.CONTRAST_WINDOW_HOURS)
        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id, since_time=window_start,
        )

        for admin in med_admins:
            admin_time = admin.get("admin_time")
            if admin_time and window_start <= admin_time <= trigger_time:
                med_name = admin.get("medication_name", "").lower()
                if any(c in med_name for c in self.CONTRAST_KEYWORDS):
                    return True
        return False

    def _check_gi_bleed(self, patient_id, trigger_time):
        """Check for active GI bleed."""
        if not self.fhir_client:
            return False

        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id, since_time=trigger_time - timedelta(hours=48),
        )

        gi_bleed_keywords = [
            "gi bleed", "gi bleeding", "gastrointestinal bleed",
            "melena", "hematochezia", "bloody stool", "blood in stool",
            "hematemesis",
        ]

        for note in notes:
            note_text = note.get("text", "").lower()
            if any(kw in note_text for kw in gi_bleed_keywords):
                return True
        return False

    def _check_risk_factors(self, patient_id, trigger_time):
        """Check for C. diff risk factors."""
        if not self.fhir_client:
            return ["hospitalization"]

        risk_factors = []

        # Recent antibiotics (90 day lookback)
        window_start = trigger_time - timedelta(days=90)
        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id, since_time=window_start,
        )

        abx_keywords = [
            "amoxicillin", "ampicillin", "penicillin", "cephalexin",
            "ceftriaxone", "cefdinir", "azithromycin", "ciprofloxacin",
            "clindamycin", "metronidazole", "vancomycin", "doxycycline",
            "sulfamethoxazole", "trimethoprim", "bactrim", "augmentin",
        ]

        ppi_keywords = [
            "omeprazole", "lansoprazole", "pantoprazole", "esomeprazole",
            "protonix", "prilosec", "prevacid", "nexium",
        ]

        for admin in med_admins:
            med_name = admin.get("medication_name", "").lower()
            if any(abx in med_name for abx in abx_keywords):
                if "recent_antibiotics" not in risk_factors:
                    risk_factors.append("recent_antibiotics")
            if any(ppi in med_name for ppi in ppi_keywords):
                if "ppi_use" not in risk_factors:
                    risk_factors.append("ppi_use")

        # Notes-based risk factors
        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id, since_time=trigger_time - timedelta(days=30),
        )

        for note in notes:
            text = note.get("text", "").lower()
            if ("gastrostomy" in text or "g-tube" in text) and "gastrostomy" not in risk_factors:
                risk_factors.append("gastrostomy")
            if ("immunocompromised" in text or "immune deficiency" in text) and "immunocompromised" not in risk_factors:
                risk_factors.append("immunocompromised")
            if ("inflammatory bowel" in text or "ibd" in text or "crohn" in text or "ulcerative colitis" in text) and "ibd" not in risk_factors:
                risk_factors.append("ibd")

        if not risk_factors:
            risk_factors.append("hospitalization")

        return risk_factors

    def _check_age_appropriate(self, element, patient_id, trigger_time, context):
        """Check if patient age >= 3 years (or exception documented)."""
        age_years = context.get("age_years")

        if age_years is None:
            return self._create_result(
                element=element, status='pending', trigger_time=trigger_time,
                notes="Patient age not available",
            )

        if age_years >= self.MIN_AGE_YEARS:
            return self._create_result(
                element=element, status='met', trigger_time=trigger_time,
                value=f"{age_years:.1f} years",
                notes=f"Age appropriate: {age_years:.1f} years >= {self.MIN_AGE_YEARS} years",
            )

        # Check for documented exception
        if self.fhir_client:
            notes = self.fhir_client.get_recent_notes(
                patient_id=patient_id, since_time=trigger_time - timedelta(hours=24),
            )
            exception_keywords = [
                "c. diff testing appropriate", "cdiff testing indicated",
                "young age exception", "clinical concern for c. diff",
            ]
            for note in notes:
                if any(kw in note.get("text", "").lower() for kw in exception_keywords):
                    return self._create_result(
                        element=element, status='met', trigger_time=trigger_time,
                        value=f"{age_years:.1f} years (exception documented)",
                        notes=f"Age < {self.MIN_AGE_YEARS} years but exception documented",
                    )

        return self._create_result(
            element=element, status='not_met', trigger_time=trigger_time,
            value=f"{age_years:.1f} years",
            notes=f"Patient age {age_years:.1f} years < {self.MIN_AGE_YEARS} years. Testing may be inappropriate.",
        )

    def _check_liquid_stools(self, element, patient_id, trigger_time, context):
        """Check if patient has >= 3 liquid stools in 24 hours."""
        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="No FHIR client")

        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id, since_time=trigger_time - timedelta(hours=24),
        )

        if not notes:
            return self._create_result(
                element=element, status='pending', trigger_time=trigger_time,
                notes="No nursing documentation available to assess stool output",
            )

        # Try NLP extraction first
        if self._nlp_extractor:
            try:
                note_texts = [n.get("text", "") for n in notes if n.get("text")]
                if note_texts:
                    gi_result = self._nlp_extractor.extract(note_texts)
                    if hasattr(gi_result, 'meets_cdiff_criteria') and gi_result.meets_cdiff_criteria():
                        return self._create_result(
                            element=element, status='met', trigger_time=trigger_time,
                            value=f"{gi_result.stool_count_24h} stools",
                            notes=f"NLP: {gi_result.stool_count_24h} liquid stools in 24h",
                        )
                    elif hasattr(gi_result, 'stool_count_24h') and gi_result.stool_count_24h is not None:
                        if gi_result.stool_count_24h < self.MIN_LIQUID_STOOLS:
                            return self._create_result(
                                element=element, status='not_met', trigger_time=trigger_time,
                                value=f"{gi_result.stool_count_24h} stools",
                                notes=f"Only {gi_result.stool_count_24h} stools (need >= {self.MIN_LIQUID_STOOLS})",
                            )
            except Exception as e:
                logger.warning(f"GI NLP extraction failed: {e}")

        # Keyword fallback
        stool_keywords = [
            "liquid stool", "watery stool", "diarrhea", "loose stool",
            "3 or more stools", "multiple loose stools", "frequent diarrhea",
        ]

        for note in notes:
            if any(kw in note.get("text", "").lower() for kw in stool_keywords):
                return self._create_result(
                    element=element, status='met', trigger_time=trigger_time,
                    notes="Liquid stools documented (>=3 in 24h likely) - keyword match",
                )

        return self._create_result(
            element=element, status='pending', trigger_time=trigger_time,
            notes="Unable to confirm >= 3 liquid stools in 24 hours from documentation",
        )

    def _check_no_laxatives(self, element, patient_id, trigger_time, context):
        """Check that no laxatives were given in past 48 hours."""
        if context.get("laxative_given_48h", False):
            return self._create_result(
                element=element, status='not_met', trigger_time=trigger_time,
                notes="Laxative given within 48 hours - C. diff testing may be inappropriate",
            )
        return self._create_result(
            element=element, status='met', trigger_time=trigger_time,
            notes="No laxatives documented in past 48 hours",
        )

    def _check_no_contrast(self, element, patient_id, trigger_time, context):
        """Check that no enteral contrast was given in past 48 hours."""
        if context.get("contrast_given_48h", False):
            return self._create_result(
                element=element, status='not_met', trigger_time=trigger_time,
                notes="Enteral contrast given within 48 hours - C. diff testing may be inappropriate",
            )
        return self._create_result(
            element=element, status='met', trigger_time=trigger_time,
            notes="No enteral contrast documented in past 48 hours",
        )

    def _check_no_tube_feed_changes(self, element, patient_id, trigger_time, context):
        """Check for no recent tube feed changes."""
        if not self.fhir_client:
            return self._create_result(element=element, status='met', trigger_time=trigger_time,
                                       notes="No tube feed changes documented")

        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id, since_time=trigger_time - timedelta(hours=48),
        )

        tube_keywords = [
            "tube feed change", "formula change", "feeds changed",
            "new formula", "switching feeds", "feed advancement",
        ]

        for note in notes:
            if any(kw in note.get("text", "").lower() for kw in tube_keywords):
                return self._create_result(
                    element=element, status='not_met', trigger_time=trigger_time,
                    notes="Tube feed changes documented within 48 hours",
                )

        return self._create_result(
            element=element, status='met', trigger_time=trigger_time,
            notes="No tube feed changes documented in past 48 hours",
        )

    def _check_no_gi_bleed(self, element, patient_id, trigger_time, context):
        """Check that there is no active GI bleed."""
        if context.get("gi_bleed_present", False):
            return self._create_result(
                element=element, status='not_met', trigger_time=trigger_time,
                notes="Active GI bleed documented - C. diff testing may yield false results",
            )
        return self._create_result(
            element=element, status='met', trigger_time=trigger_time,
            notes="No active GI bleed documented",
        )

    def _check_risk_factor_present(self, element, patient_id, trigger_time, context):
        """Check that at least one risk factor is present."""
        risk_factors = context.get("risk_factors_present", [])

        if risk_factors:
            return self._create_result(
                element=element, status='met', trigger_time=trigger_time,
                value=", ".join(risk_factors),
                notes=f"Risk factors present: {', '.join(risk_factors)}",
            )

        return self._create_result(
            element=element, status='not_met', trigger_time=trigger_time,
            notes="No C. diff risk factors documented - testing may be inappropriate",
        )

    def _check_symptom_duration(self, element, patient_id, trigger_time, context):
        """Check symptom duration (conditional: >= 48h if low risk)."""
        risk_factors = context.get("risk_factors_present", [])

        if len(risk_factors) >= 2 or "recent_antibiotics" in risk_factors:
            return self._create_result(
                element=element, status='na', trigger_time=trigger_time,
                notes="High-risk patient - symptom duration requirement not applicable",
            )

        if not self.fhir_client:
            return self._create_result(element=element, status='pending',
                                       trigger_time=trigger_time, notes="Unable to check symptom duration")

        notes = self.fhir_client.get_recent_notes(
            patient_id=patient_id, since_time=trigger_time - timedelta(hours=72),
        )

        onset_keywords = ["diarrhea started", "symptoms began", "onset", "duration", "for the past"]
        for note in notes:
            text = note.get("text", "").lower()
            if any(kw in text for kw in onset_keywords):
                if any(d in text for d in ["2 days", "3 days", "48 hours", "several days"]):
                    return self._create_result(
                        element=element, status='met', trigger_time=trigger_time,
                        notes="Symptoms documented for >= 48 hours",
                    )

        return self._create_result(
            element=element, status='pending', trigger_time=trigger_time,
            notes="Low-risk patient - confirm symptoms persist >= 48 hours before testing",
        )

    def get_test_appropriateness(self, patient_id):
        """Get overall test appropriateness assessment."""
        if patient_id not in self._patient_context:
            return TestAppropriateness.UNABLE_TO_ASSESS, ["Patient context not available"]

        context = self._patient_context[patient_id]
        concerns = []

        age_years = context.get("age_years")
        if age_years is not None and age_years < self.MIN_AGE_YEARS:
            concerns.append(f"Age < {self.MIN_AGE_YEARS} years (high carrier rate)")
        if context.get("laxative_given_48h"):
            concerns.append("Laxative given within 48h")
        if context.get("contrast_given_48h"):
            concerns.append("Enteral contrast given within 48h")
        if context.get("gi_bleed_present"):
            concerns.append("Active GI bleed")
        if not context.get("risk_factors_present"):
            concerns.append("No risk factors present")

        if not concerns:
            return TestAppropriateness.APPROPRIATE, []
        elif len(concerns) >= 3:
            return TestAppropriateness.INAPPROPRIATE, concerns
        else:
            return TestAppropriateness.POTENTIALLY_INAPPROPRIATE, concerns

    def clear_patient_cache(self, patient_id=None):
        """Clear cached patient context."""
        if patient_id:
            self._patient_context.pop(patient_id, None)
        else:
            self._patient_context.clear()
