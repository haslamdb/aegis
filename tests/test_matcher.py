"""Tests for coverage matching logic."""

import pytest
from src.matcher import assess_coverage, should_alert
from src.models import Patient, CultureResult, Antibiotic, CoverageStatus
from src.coverage_rules import RXNORM


@pytest.fixture
def sample_patient():
    return Patient(
        fhir_id="patient-123",
        mrn="TEST001",
        name="Test Patient",
    )


class TestCoverageAssessment:
    """Test coverage assessment logic."""

    def test_mrsa_with_vancomycin_is_adequate(self, sample_patient):
        culture = CultureResult(
            fhir_id="culture-1",
            patient_id="patient-123",
            organism="MRSA - Methicillin resistant Staphylococcus aureus",
        )
        antibiotics = [
            Antibiotic(
                fhir_id="med-1",
                medication_name="Vancomycin",
                rxnorm_code=RXNORM["vancomycin"],
            )
        ]

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.ADEQUATE
        assert not should_alert(assessment)

    def test_mrsa_with_cefazolin_is_inadequate(self, sample_patient):
        culture = CultureResult(
            fhir_id="culture-2",
            patient_id="patient-123",
            organism="MRSA - Methicillin resistant Staphylococcus aureus",
        )
        antibiotics = [
            Antibiotic(
                fhir_id="med-2",
                medication_name="Cefazolin",
                rxnorm_code=RXNORM["cefazolin"],
            )
        ]

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.INADEQUATE
        assert should_alert(assessment)

    def test_pseudomonas_with_cefepime_is_adequate(self, sample_patient):
        culture = CultureResult(
            fhir_id="culture-3",
            patient_id="patient-123",
            organism="Pseudomonas aeruginosa",
        )
        antibiotics = [
            Antibiotic(
                fhir_id="med-3",
                medication_name="Cefepime",
                rxnorm_code=RXNORM["cefepime"],
            )
        ]

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.ADEQUATE

    def test_pseudomonas_with_ceftriaxone_is_inadequate(self, sample_patient):
        culture = CultureResult(
            fhir_id="culture-4",
            patient_id="patient-123",
            organism="Pseudomonas aeruginosa",
        )
        antibiotics = [
            Antibiotic(
                fhir_id="med-4",
                medication_name="Ceftriaxone",
                rxnorm_code=RXNORM["ceftriaxone"],
            )
        ]

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.INADEQUATE

    def test_candida_without_antifungal_is_inadequate(self, sample_patient):
        culture = CultureResult(
            fhir_id="culture-5",
            patient_id="patient-123",
            organism="Candida albicans",
        )
        antibiotics = [
            Antibiotic(
                fhir_id="med-5",
                medication_name="Vancomycin",
                rxnorm_code=RXNORM["vancomycin"],
            ),
            Antibiotic(
                fhir_id="med-6",
                medication_name="Cefepime",
                rxnorm_code=RXNORM["cefepime"],
            ),
        ]

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.INADEQUATE

    def test_candida_with_micafungin_is_adequate(self, sample_patient):
        culture = CultureResult(
            fhir_id="culture-6",
            patient_id="patient-123",
            organism="Candida albicans",
        )
        antibiotics = [
            Antibiotic(
                fhir_id="med-7",
                medication_name="Micafungin",
                rxnorm_code=RXNORM["micafungin"],
            ),
        ]

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.ADEQUATE

    def test_no_antibiotics_is_inadequate(self, sample_patient):
        culture = CultureResult(
            fhir_id="culture-7",
            patient_id="patient-123",
            organism="Escherichia coli",
        )
        antibiotics = []

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.INADEQUATE

    def test_vre_with_vancomycin_is_inadequate(self, sample_patient):
        culture = CultureResult(
            fhir_id="culture-8",
            patient_id="patient-123",
            organism="VRE - Vancomycin resistant Enterococcus faecium",
        )
        antibiotics = [
            Antibiotic(
                fhir_id="med-8",
                medication_name="Vancomycin",
                rxnorm_code=RXNORM["vancomycin"],
            ),
        ]

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.INADEQUATE

    def test_vre_with_daptomycin_is_adequate(self, sample_patient):
        culture = CultureResult(
            fhir_id="culture-9",
            patient_id="patient-123",
            organism="VRE - Vancomycin resistant Enterococcus faecium",
        )
        antibiotics = [
            Antibiotic(
                fhir_id="med-9",
                medication_name="Daptomycin",
                rxnorm_code=RXNORM["daptomycin"],
            ),
        ]

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.ADEQUATE

    def test_gpc_clusters_needs_mrsa_coverage(self, sample_patient):
        """Gram positive cocci in clusters should trigger MRSA coverage check."""
        culture = CultureResult(
            fhir_id="culture-10",
            patient_id="patient-123",
            organism="Pending identification",
            gram_stain="Gram positive cocci in clusters",
        )
        antibiotics = [
            Antibiotic(
                fhir_id="med-10",
                medication_name="Cefazolin",
                rxnorm_code=RXNORM["cefazolin"],
            ),
        ]

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.INADEQUATE

    def test_unknown_organism_returns_unknown_status(self, sample_patient):
        culture = CultureResult(
            fhir_id="culture-11",
            patient_id="patient-123",
            organism="",  # No organism info
        )
        antibiotics = [
            Antibiotic(
                fhir_id="med-11",
                medication_name="Vancomycin",
                rxnorm_code=RXNORM["vancomycin"],
            ),
        ]

        assessment = assess_coverage(sample_patient, culture, antibiotics)
        assert assessment.coverage_status == CoverageStatus.UNKNOWN
        assert not should_alert(assessment)  # Don't alert for unknown
