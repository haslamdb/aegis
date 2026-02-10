"""Tests for Bacteremia Monitoring module."""

from django.test import TestCase

from apps.asp_alerts.coverage_rules import (
    categorize_organism,
    OrganismCategory,
    RXNORM,
)

from .data_models import (
    Antibiotic,
    CoverageAssessment,
    CoverageStatus,
    CultureResult,
    Patient,
)
from .matcher import assess_coverage, extract_rxnorm_codes, should_alert

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus


class OrganismCategorizationTests(TestCase):
    """Test organism categorization from coverage_rules."""

    def test_mrsa_explicit(self):
        self.assertEqual(categorize_organism("MRSA"), OrganismCategory.MRSA)

    def test_mrsa_methicillin_resistant(self):
        self.assertEqual(
            categorize_organism("Methicillin resistant Staphylococcus aureus"),
            OrganismCategory.MRSA,
        )

    def test_mssa_explicit(self):
        self.assertEqual(
            categorize_organism("MSSA Staphylococcus aureus"),
            OrganismCategory.MSSA,
        )

    def test_mssa_methicillin_susceptible(self):
        self.assertEqual(
            categorize_organism("Methicillin susceptible Staphylococcus aureus"),
            OrganismCategory.MSSA,
        )

    def test_vre(self):
        self.assertEqual(
            categorize_organism("VRE Enterococcus faecium"),
            OrganismCategory.VRE,
        )

    def test_vse(self):
        self.assertEqual(
            categorize_organism("Enterococcus faecalis"),
            OrganismCategory.VSE,
        )

    def test_pseudomonas(self):
        self.assertEqual(
            categorize_organism("Pseudomonas aeruginosa"),
            OrganismCategory.PSEUDOMONAS,
        )

    def test_candida(self):
        self.assertEqual(
            categorize_organism("Candida albicans"),
            OrganismCategory.CANDIDA,
        )

    def test_ecoli(self):
        self.assertEqual(
            categorize_organism("Escherichia coli"),
            OrganismCategory.GRAM_NEG_SUSCEPTIBLE,
        )

    def test_klebsiella(self):
        self.assertEqual(
            categorize_organism("Klebsiella pneumoniae"),
            OrganismCategory.GRAM_NEG_SUSCEPTIBLE,
        )

    def test_esbl(self):
        self.assertEqual(
            categorize_organism("ESBL-producing E. coli"),
            OrganismCategory.ESBL,
        )

    def test_gpc_clusters_gram_stain(self):
        self.assertEqual(
            categorize_organism("", "Gram positive cocci in clusters"),
            OrganismCategory.GPC_CLUSTERS,
        )

    def test_gpc_chains_gram_stain(self):
        self.assertEqual(
            categorize_organism("", "Gram positive cocci in chains"),
            OrganismCategory.GPC_CHAINS,
        )

    def test_gnr_gram_stain(self):
        self.assertEqual(
            categorize_organism("", "Gram negative rods"),
            OrganismCategory.GNR,
        )

    def test_unknown_empty(self):
        self.assertEqual(categorize_organism(""), OrganismCategory.UNKNOWN)

    def test_unknown_pending(self):
        self.assertEqual(
            categorize_organism("Pending identification"),
            OrganismCategory.UNKNOWN,
        )


class CoverageAssessmentTests(TestCase):
    """Test coverage assessment logic."""

    def setUp(self):
        self.patient = Patient(
            fhir_id="P-123",
            mrn="MRN-100234",
            name="Test Patient",
        )

    def _make_culture(self, organism, gram_stain=None):
        return CultureResult(
            fhir_id="C-123",
            patient_id="P-123",
            organism=organism,
            gram_stain=gram_stain,
        )

    def _make_antibiotic(self, name, rxnorm_code):
        return Antibiotic(
            fhir_id=f"A-{rxnorm_code}",
            medication_name=name,
            rxnorm_code=rxnorm_code,
        )

    def test_mrsa_with_vancomycin_adequate(self):
        culture = self._make_culture("MRSA")
        antibiotics = [self._make_antibiotic("vancomycin", RXNORM["vancomycin"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.ADEQUATE)
        self.assertFalse(should_alert(assessment))

    def test_mrsa_with_cefazolin_inadequate(self):
        culture = self._make_culture("MRSA")
        antibiotics = [self._make_antibiotic("cefazolin", RXNORM["cefazolin"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.INADEQUATE)
        self.assertTrue(should_alert(assessment))

    def test_pseudomonas_with_cefepime_adequate(self):
        culture = self._make_culture("Pseudomonas aeruginosa")
        antibiotics = [self._make_antibiotic("cefepime", RXNORM["cefepime"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.ADEQUATE)

    def test_pseudomonas_with_ceftriaxone_inadequate(self):
        culture = self._make_culture("Pseudomonas aeruginosa")
        antibiotics = [self._make_antibiotic("ceftriaxone", RXNORM["ceftriaxone"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.INADEQUATE)

    def test_candida_with_antibacterial_inadequate(self):
        culture = self._make_culture("Candida albicans")
        antibiotics = [self._make_antibiotic("vancomycin", RXNORM["vancomycin"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.INADEQUATE)

    def test_candida_with_micafungin_adequate(self):
        culture = self._make_culture("Candida albicans")
        antibiotics = [self._make_antibiotic("micafungin", RXNORM["micafungin"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.ADEQUATE)

    def test_no_antibiotics_inadequate(self):
        culture = self._make_culture("MRSA")
        assessment = assess_coverage(self.patient, culture, [])
        self.assertEqual(assessment.coverage_status, CoverageStatus.INADEQUATE)
        self.assertTrue(should_alert(assessment))

    def test_vre_with_vancomycin_inadequate(self):
        culture = self._make_culture("VRE Enterococcus faecium")
        antibiotics = [self._make_antibiotic("vancomycin", RXNORM["vancomycin"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.INADEQUATE)

    def test_vre_with_daptomycin_adequate(self):
        culture = self._make_culture("VRE Enterococcus faecium")
        antibiotics = [self._make_antibiotic("daptomycin", RXNORM["daptomycin"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.ADEQUATE)

    def test_gpc_clusters_with_cefazolin_inadequate(self):
        culture = self._make_culture("", "Gram positive cocci in clusters")
        antibiotics = [self._make_antibiotic("cefazolin", RXNORM["cefazolin"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.INADEQUATE)

    def test_unknown_organism_no_alert(self):
        culture = self._make_culture("Pending identification")
        antibiotics = [self._make_antibiotic("vancomycin", RXNORM["vancomycin"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.UNKNOWN)
        self.assertFalse(should_alert(assessment))

    def test_organism_category_stored(self):
        culture = self._make_culture("MRSA")
        antibiotics = [self._make_antibiotic("vancomycin", RXNORM["vancomycin"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.organism_category, "mrsa")

    def test_esbl_with_meropenem_adequate(self):
        culture = self._make_culture("ESBL-producing Klebsiella")
        antibiotics = [self._make_antibiotic("meropenem", RXNORM["meropenem"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.ADEQUATE)

    def test_esbl_with_ceftriaxone_inadequate(self):
        culture = self._make_culture("ESBL-producing E. coli")
        antibiotics = [self._make_antibiotic("ceftriaxone", RXNORM["ceftriaxone"])]
        assessment = assess_coverage(self.patient, culture, antibiotics)
        self.assertEqual(assessment.coverage_status, CoverageStatus.INADEQUATE)


class DataModelTests(TestCase):
    """Test data model utilities."""

    def test_extract_rxnorm_codes(self):
        antibiotics = [
            Antibiotic(fhir_id="A-1", medication_name="vanc", rxnorm_code="11124"),
            Antibiotic(fhir_id="A-2", medication_name="ceftriaxone", rxnorm_code="2193"),
            Antibiotic(fhir_id="A-3", medication_name="tylenol", rxnorm_code=None),
        ]
        codes = extract_rxnorm_codes(antibiotics)
        self.assertEqual(codes, {"11124", "2193"})

    def test_to_alert_content(self):
        patient = Patient(fhir_id="P-1", mrn="MRN-1", name="Test")
        culture = CultureResult(
            fhir_id="C-1",
            patient_id="P-1",
            organism="MRSA",
            gram_stain="Gram positive cocci in clusters",
        )
        assessment = CoverageAssessment(
            patient=patient,
            culture=culture,
            coverage_status=CoverageStatus.INADEQUATE,
            organism_category="mrsa",
            recommendation="Add vancomycin",
        )
        content = assessment.to_alert_content()
        self.assertEqual(content["organism"], "MRSA")
        self.assertEqual(content["organism_category"], "mrsa")
        self.assertEqual(content["coverage_status"], "inadequate")
        self.assertEqual(content["recommendation"], "Add vancomycin")


class BacteremiaServiceTests(TestCase):
    """Test the BacteremiaMonitorService."""

    def setUp(self):
        self.patient = Patient(
            fhir_id="P-123",
            mrn="MRN-100234",
            name="Test Patient",
            location="PICU",
        )

    def test_alert_creation(self):
        """Service creates Alert and AlertAudit in database."""
        from .services import BacteremiaMonitorService

        service = BacteremiaMonitorService()

        assessment = CoverageAssessment(
            patient=self.patient,
            culture=CultureResult(
                fhir_id="C-999",
                patient_id="P-123",
                organism="MRSA",
            ),
            coverage_status=CoverageStatus.INADEQUATE,
            organism_category="mrsa",
            recommendation="Add vancomycin for MRSA coverage",
        )
        service._create_alert(assessment)

        alert = Alert.objects.get(source_id="C-999")
        self.assertEqual(alert.alert_type, AlertType.BACTEREMIA)
        self.assertEqual(alert.source_module, 'bacteremia_monitor')
        self.assertEqual(alert.severity, 'high')
        self.assertEqual(alert.priority_score, 80)
        self.assertEqual(alert.patient_mrn, "MRN-100234")
        self.assertIn("MRSA", alert.title)

        audit = AlertAudit.objects.filter(alert=alert, action='created').first()
        self.assertIsNotNone(audit)

    def test_deduplication(self):
        """Service does not create duplicate alerts for same culture."""
        from .services import BacteremiaMonitorService

        # Create an existing alert
        Alert.objects.create(
            alert_type=AlertType.BACTEREMIA,
            source_module='bacteremia_monitor',
            source_id='C-DUP',
            title='Existing',
            summary='Existing alert',
            severity='high',
            priority_score=80,
            status=AlertStatus.PENDING,
        )

        service = BacteremiaMonitorService()
        culture = CultureResult(
            fhir_id="C-DUP",
            patient_id="P-123",
            organism="MRSA",
        )
        processed = set()
        result = service._check_culture(None, culture, processed)
        self.assertFalse(result)

    def test_run_detection_returns_dict(self):
        """run_detection returns correct result structure."""
        from unittest.mock import MagicMock
        from .services import BacteremiaMonitorService

        mock_client = MagicMock()
        mock_client.get_recent_blood_cultures.return_value = []

        service = BacteremiaMonitorService()
        result = service.run_detection(fhir_client=mock_client)

        self.assertIn('cultures_checked', result)
        self.assertIn('alerts_created', result)
        self.assertIn('errors', result)
        self.assertEqual(result['cultures_checked'], 0)
        self.assertEqual(result['alerts_created'], 0)
