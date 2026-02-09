"""Tests for Drug-Bug Mismatch module."""

from django.test import TestCase

from .antibiotic_map import ANTIBIOTIC_SUSCEPTIBILITY_MAP, SUSCEPTIBILITY_TO_RXNORM
from .data_models import (
    AlertSeverity,
    Antibiotic,
    CultureWithSusceptibilities,
    DrugBugMismatch,
    MismatchAssessment,
    MismatchType,
    Patient,
    Susceptibility,
)
from .matcher import (
    assess_mismatch,
    check_coverage,
    find_matching_susceptibility,
    get_recommendation,
    has_any_effective_coverage,
    normalize_antibiotic_name,
    should_alert,
)


class MatcherTests(TestCase):
    """Test the drug-bug matcher logic."""

    def setUp(self):
        self.patient = Patient(
            fhir_id="P-123",
            mrn="MRN-100234",
            name="Test Patient",
        )

    def _make_culture(self, organism, susceptibilities):
        return CultureWithSusceptibilities(
            fhir_id="C-123",
            patient_id="P-123",
            organism=organism,
            specimen_type="Blood",
            susceptibilities=susceptibilities,
        )

    def test_resistant_detected(self):
        """Resistant antibiotic should produce RESISTANT mismatch."""
        culture = self._make_culture("MRSA", [
            Susceptibility(organism="MRSA", antibiotic="ceftriaxone", interpretation="R"),
            Susceptibility(organism="MRSA", antibiotic="vancomycin", interpretation="S"),
        ])
        antibiotics = [
            Antibiotic(fhir_id="A-1", medication_name="ceftriaxone", rxnorm_code="2193"),
        ]
        mismatches = check_coverage(culture, antibiotics)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0].mismatch_type, MismatchType.RESISTANT)

    def test_intermediate_detected(self):
        """Intermediate susceptibility should produce INTERMEDIATE mismatch."""
        culture = self._make_culture("Pseudomonas", [
            Susceptibility(organism="Pseudomonas", antibiotic="meropenem", interpretation="I"),
        ])
        antibiotics = [
            Antibiotic(fhir_id="A-1", medication_name="meropenem", rxnorm_code="29561"),
        ]
        mismatches = check_coverage(culture, antibiotics)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0].mismatch_type, MismatchType.INTERMEDIATE)

    def test_susceptible_no_mismatch(self):
        """Susceptible antibiotic should not produce a mismatch."""
        culture = self._make_culture("E. coli", [
            Susceptibility(organism="E. coli", antibiotic="meropenem", interpretation="S"),
        ])
        antibiotics = [
            Antibiotic(fhir_id="A-1", medication_name="meropenem", rxnorm_code="29561"),
        ]
        mismatches = check_coverage(culture, antibiotics)
        self.assertEqual(len(mismatches), 0)

    def test_no_antibiotics_with_susceptible_options(self):
        """No antibiotics when susceptible options exist -> NO_COVERAGE."""
        culture = self._make_culture("E. coli", [
            Susceptibility(organism="E. coli", antibiotic="meropenem", interpretation="S"),
        ])
        mismatches = check_coverage(culture, [])
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0].mismatch_type, MismatchType.NO_COVERAGE)

    def test_no_susceptibility_data(self):
        """No susceptibility data should return no mismatches."""
        culture = self._make_culture("E. coli", [])
        antibiotics = [
            Antibiotic(fhir_id="A-1", medication_name="meropenem", rxnorm_code="29561"),
        ]
        mismatches = check_coverage(culture, antibiotics)
        self.assertEqual(len(mismatches), 0)

    def test_has_effective_coverage(self):
        """Should detect when at least one antibiotic is effective."""
        culture = self._make_culture("E. coli", [
            Susceptibility(organism="E. coli", antibiotic="ceftriaxone", interpretation="R"),
            Susceptibility(organism="E. coli", antibiotic="meropenem", interpretation="S"),
        ])
        antibiotics = [
            Antibiotic(fhir_id="A-1", medication_name="ceftriaxone", rxnorm_code="2193"),
            Antibiotic(fhir_id="A-2", medication_name="meropenem", rxnorm_code="29561"),
        ]
        self.assertTrue(has_any_effective_coverage(culture, antibiotics))

    def test_assess_mismatch_generates_alert(self):
        """Full assessment should generate alert for resistant organism."""
        culture = self._make_culture("MRSA", [
            Susceptibility(organism="MRSA", antibiotic="ceftriaxone", interpretation="R"),
            Susceptibility(organism="MRSA", antibiotic="vancomycin", interpretation="S"),
        ])
        antibiotics = [
            Antibiotic(fhir_id="A-1", medication_name="ceftriaxone", rxnorm_code="2193"),
        ]
        assessment = assess_mismatch(self.patient, culture, antibiotics)
        self.assertTrue(should_alert(assessment))
        self.assertTrue(assessment.has_mismatches())
        self.assertIn("vancomycin", assessment.recommendation)


# ===========================================================================
# Additional tests - expand beyond existing 7
# ===========================================================================

class SusceptibilityDataModelTests(TestCase):
    """Test Susceptibility dataclass methods."""

    def test_is_susceptible(self):
        s = Susceptibility(organism="E. coli", antibiotic="meropenem", interpretation="S")
        self.assertTrue(s.is_susceptible())
        self.assertFalse(s.is_resistant())
        self.assertFalse(s.is_intermediate())

    def test_is_resistant(self):
        s = Susceptibility(organism="E. coli", antibiotic="ampicillin", interpretation="R")
        self.assertTrue(s.is_resistant())
        self.assertFalse(s.is_susceptible())

    def test_is_intermediate(self):
        s = Susceptibility(organism="Pseudomonas", antibiotic="meropenem", interpretation="I")
        self.assertTrue(s.is_intermediate())


class CultureMethodTests(TestCase):
    """Test CultureWithSusceptibilities methods."""

    def test_get_susceptibility_for_found(self):
        culture = CultureWithSusceptibilities(
            fhir_id="C-1", patient_id="P-1", organism="E. coli",
            susceptibilities=[
                Susceptibility(organism="E. coli", antibiotic="meropenem", interpretation="S"),
                Susceptibility(organism="E. coli", antibiotic="ampicillin", interpretation="R"),
            ],
        )
        susc = culture.get_susceptibility_for("meropenem")
        self.assertIsNotNone(susc)
        self.assertEqual(susc.interpretation, "S")

    def test_get_susceptibility_for_not_found(self):
        culture = CultureWithSusceptibilities(
            fhir_id="C-1", patient_id="P-1", organism="E. coli",
            susceptibilities=[
                Susceptibility(organism="E. coli", antibiotic="meropenem", interpretation="S"),
            ],
        )
        susc = culture.get_susceptibility_for("vancomycin")
        self.assertIsNone(susc)

    def test_get_susceptible_antibiotics(self):
        culture = CultureWithSusceptibilities(
            fhir_id="C-1", patient_id="P-1", organism="E. coli",
            susceptibilities=[
                Susceptibility(organism="E. coli", antibiotic="meropenem", interpretation="S"),
                Susceptibility(organism="E. coli", antibiotic="ceftriaxone", interpretation="S"),
                Susceptibility(organism="E. coli", antibiotic="ampicillin", interpretation="R"),
            ],
        )
        susceptible = culture.get_susceptible_antibiotics()
        self.assertEqual(len(susceptible), 2)

    def test_get_resistant_antibiotics(self):
        culture = CultureWithSusceptibilities(
            fhir_id="C-1", patient_id="P-1", organism="E. coli",
            susceptibilities=[
                Susceptibility(organism="E. coli", antibiotic="ampicillin", interpretation="R"),
            ],
        )
        resistant = culture.get_resistant_antibiotics()
        self.assertEqual(len(resistant), 1)


class MismatchAssessmentTests(TestCase):
    """Test MismatchAssessment dataclass."""

    def test_get_highest_severity_critical(self):
        patient = Patient(fhir_id="P-1", mrn="MRN-1", name="Test")
        culture = CultureWithSusceptibilities(
            fhir_id="C-1", patient_id="P-1", organism="MRSA",
            susceptibilities=[
                Susceptibility(organism="MRSA", antibiotic="ceftriaxone", interpretation="R"),
            ],
        )
        mismatch = DrugBugMismatch(
            culture=culture,
            antibiotic=Antibiotic(fhir_id="A-1", medication_name="ceftriaxone"),
            susceptibility=culture.susceptibilities[0],
            mismatch_type=MismatchType.RESISTANT,
        )
        assessment = MismatchAssessment(
            patient=patient, culture=culture, mismatches=[mismatch],
        )
        self.assertEqual(assessment.get_highest_severity(), AlertSeverity.CRITICAL)

    def test_no_mismatches_severity_info(self):
        patient = Patient(fhir_id="P-1", mrn="MRN-1", name="Test")
        culture = CultureWithSusceptibilities(
            fhir_id="C-1", patient_id="P-1", organism="E. coli",
        )
        assessment = MismatchAssessment(patient=patient, culture=culture)
        self.assertEqual(assessment.get_highest_severity(), AlertSeverity.INFO)

    def test_to_alert_content(self):
        patient = Patient(fhir_id="P-1", mrn="MRN-1", name="Test")
        culture = CultureWithSusceptibilities(
            fhir_id="C-1", patient_id="P-1", organism="E. coli",
            specimen_type="Blood",
            susceptibilities=[
                Susceptibility(organism="E. coli", antibiotic="ampicillin", interpretation="R"),
                Susceptibility(organism="E. coli", antibiotic="meropenem", interpretation="S"),
            ],
        )
        mismatch = DrugBugMismatch(
            culture=culture,
            antibiotic=Antibiotic(fhir_id="A-1", medication_name="ampicillin"),
            susceptibility=culture.susceptibilities[0],
            mismatch_type=MismatchType.RESISTANT,
        )
        assessment = MismatchAssessment(
            patient=patient, culture=culture,
            current_antibiotics=[Antibiotic(fhir_id="A-1", medication_name="ampicillin")],
            mismatches=[mismatch], recommendation="Switch to meropenem",
        )
        content = assessment.to_alert_content()
        self.assertEqual(content["organism"], "E. coli")
        self.assertEqual(content["specimen_type"], "Blood")
        self.assertIn("meropenem", content["susceptible_options"])


class NormalizeAntibioticNameTests(TestCase):
    """Test antibiotic name normalization."""

    def test_lowercase(self):
        self.assertEqual(normalize_antibiotic_name("Vancomycin"), "vancomycin")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_antibiotic_name("  meropenem  "), "meropenem")

    def test_replaces_dash(self):
        self.assertEqual(
            normalize_antibiotic_name("piperacillin-tazobactam"),
            "piperacillin tazobactam",
        )


class RecommendationTests(TestCase):
    """Test get_recommendation logic."""

    def test_no_mismatches(self):
        culture = CultureWithSusceptibilities(
            fhir_id="C-1", patient_id="P-1", organism="E. coli",
        )
        rec = get_recommendation(culture, [])
        self.assertIn("adequate", rec.lower())

    def test_resistant_with_susceptible_options(self):
        culture = CultureWithSusceptibilities(
            fhir_id="C-1", patient_id="P-1", organism="E. coli",
            susceptibilities=[
                Susceptibility(organism="E. coli", antibiotic="meropenem", interpretation="S"),
                Susceptibility(organism="E. coli", antibiotic="ampicillin", interpretation="R"),
            ],
        )
        mismatch = DrugBugMismatch(
            culture=culture,
            antibiotic=Antibiotic(fhir_id="A-1", medication_name="ampicillin"),
            susceptibility=culture.susceptibilities[1],
            mismatch_type=MismatchType.RESISTANT,
        )
        rec = get_recommendation(culture, [mismatch])
        self.assertIn("resistant", rec.lower())
        self.assertIn("meropenem", rec.lower())


class AntibioticMapTests(TestCase):
    """Test the RxNorm to susceptibility mapping."""

    def test_vancomycin_mapping(self):
        self.assertIn("11124", ANTIBIOTIC_SUSCEPTIBILITY_MAP)
        self.assertIn("vancomycin", ANTIBIOTIC_SUSCEPTIBILITY_MAP["11124"])

    def test_meropenem_mapping(self):
        self.assertIn("29561", ANTIBIOTIC_SUSCEPTIBILITY_MAP)
        self.assertIn("meropenem", ANTIBIOTIC_SUSCEPTIBILITY_MAP["29561"])

    def test_reverse_lookup(self):
        self.assertIn("vancomycin", SUSCEPTIBILITY_TO_RXNORM)
        self.assertIn("11124", SUSCEPTIBILITY_TO_RXNORM["vancomycin"])

    def test_ceftriaxone_maps_to_cefotaxime_too(self):
        """Ceftriaxone susceptibility also reported as cefotaxime."""
        self.assertIn("cefotaxime", ANTIBIOTIC_SUSCEPTIBILITY_MAP["2193"])
