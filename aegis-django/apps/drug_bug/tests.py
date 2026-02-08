"""Tests for Drug-Bug Mismatch module."""

from django.test import TestCase

from .data_models import (
    Antibiotic,
    CultureWithSusceptibilities,
    MismatchType,
    Patient,
    Susceptibility,
)
from .matcher import (
    assess_mismatch,
    check_coverage,
    has_any_effective_coverage,
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
