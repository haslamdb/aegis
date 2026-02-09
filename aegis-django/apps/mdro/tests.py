"""
Tests for MDRO Surveillance module.

Tests cover:
- MDROClassifier logic (MRSA, VRE, CRE, ESBL, CRPA, CRAB, not-MDRO)
- Enum values (MDROTypeChoices, TransmissionStatusChoices)
- MDROCase model CRUD, custom manager, properties, methods
- MDROReview model
- MDROProcessingLog model
- MDROMonitorService (mocked)
- Model __str__ methods
- Alert integration
"""

import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.alerts.models import Alert, AlertType, AlertSeverity, AlertStatus
from apps.authentication.models import User, UserRole

from .classifier import MDROClassifier, MDROType, MDROClassification
from .models import (
    MDROCase, MDROReview, MDROProcessingLog,
    MDROTypeChoices, TransmissionStatusChoices,
    MDRO_TYPE_FULL_NAMES,
)
from .services import MDROMonitorService


# ============================================================================
# Classifier Tests (original 3 + expanded)
# ============================================================================

class MDROClassifierTest(TestCase):
    """Tests for MDRO classification logic."""

    def setUp(self):
        self.classifier = MDROClassifier()

    def test_mrsa_detection(self):
        result = self.classifier.classify(
            "Staphylococcus aureus",
            [{"antibiotic": "oxacillin", "result": "R"}]
        )
        self.assertTrue(result.is_mdro)
        self.assertEqual(result.mdro_type, MDROType.MRSA)

    def test_vre_detection(self):
        result = self.classifier.classify(
            "Enterococcus faecium",
            [{"antibiotic": "vancomycin", "result": "R"}]
        )
        self.assertTrue(result.is_mdro)
        self.assertEqual(result.mdro_type, MDROType.VRE)

    def test_not_mdro(self):
        result = self.classifier.classify(
            "Staphylococcus aureus",
            [{"antibiotic": "oxacillin", "result": "S"}]
        )
        self.assertFalse(result.is_mdro)

    def test_cre_detection(self):
        result = self.classifier.classify(
            "Klebsiella pneumoniae",
            [{"antibiotic": "meropenem", "result": "R"}]
        )
        self.assertTrue(result.is_mdro)
        self.assertEqual(result.mdro_type, MDROType.CRE)

    def test_esbl_detection(self):
        result = self.classifier.classify(
            "Escherichia coli",
            [
                {"antibiotic": "ceftriaxone", "result": "R"},
                {"antibiotic": "meropenem", "result": "S"},
            ]
        )
        self.assertTrue(result.is_mdro)
        self.assertEqual(result.mdro_type, MDROType.ESBL)

    def test_crpa_detection(self):
        result = self.classifier.classify(
            "Pseudomonas aeruginosa",
            [{"antibiotic": "imipenem", "result": "R"}]
        )
        self.assertTrue(result.is_mdro)
        self.assertEqual(result.mdro_type, MDROType.CRPA)

    def test_crab_detection(self):
        result = self.classifier.classify(
            "Acinetobacter baumannii",
            [{"antibiotic": "meropenem", "result": "R"}]
        )
        self.assertTrue(result.is_mdro)
        self.assertEqual(result.mdro_type, MDROType.CRAB)

    def test_mrsa_cefoxitin(self):
        """MRSA detected via cefoxitin resistance."""
        result = self.classifier.classify(
            "S. aureus",
            [{"antibiotic": "cefoxitin", "result": "R"}]
        )
        self.assertTrue(result.is_mdro)
        self.assertEqual(result.mdro_type, MDROType.MRSA)

    def test_sensitive_enterococcus_not_vre(self):
        result = self.classifier.classify(
            "Enterococcus faecalis",
            [{"antibiotic": "vancomycin", "result": "S"}]
        )
        self.assertFalse(result.is_mdro)

    def test_classification_to_dict(self):
        result = self.classifier.classify(
            "Staphylococcus aureus",
            [{"antibiotic": "oxacillin", "result": "R"}]
        )
        d = result.to_dict()
        self.assertTrue(d['is_mdro'])
        self.assertEqual(d['mdro_type'], 'mrsa')
        self.assertIn('oxacillin', d['resistant_antibiotics'])


# ============================================================================
# Enum Tests
# ============================================================================

class MDROTypeChoicesEnumTests(TestCase):
    """Test MDROTypeChoices enum."""

    def test_type_values(self):
        self.assertEqual(MDROTypeChoices.MRSA, 'mrsa')
        self.assertEqual(MDROTypeChoices.VRE, 'vre')
        self.assertEqual(MDROTypeChoices.CRE, 'cre')
        self.assertEqual(MDROTypeChoices.ESBL, 'esbl')
        self.assertEqual(MDROTypeChoices.CRPA, 'crpa')
        self.assertEqual(MDROTypeChoices.CRAB, 'crab')

    def test_type_count(self):
        self.assertEqual(len(MDROTypeChoices.choices), 6)

    def test_labels(self):
        self.assertEqual(MDROTypeChoices.MRSA.label, 'MRSA')
        self.assertEqual(MDROTypeChoices.ESBL.label, 'ESBL')


class TransmissionStatusChoicesEnumTests(TestCase):
    """Test TransmissionStatusChoices enum."""

    def test_values(self):
        self.assertEqual(TransmissionStatusChoices.PENDING, 'pending')
        self.assertEqual(TransmissionStatusChoices.COMMUNITY, 'community')
        self.assertEqual(TransmissionStatusChoices.HEALTHCARE, 'healthcare')

    def test_count(self):
        self.assertEqual(len(TransmissionStatusChoices.choices), 3)


# ============================================================================
# MDROCase Model Tests
# ============================================================================

class MDROCaseModelTests(TestCase):
    """Test MDROCase model CRUD, properties, and methods."""

    def _create_case(self, mdro_type=MDROTypeChoices.MRSA, **kwargs):
        defaults = {
            'patient_id': 'patient-mdro-001',
            'patient_mrn': 'MRN-MDRO1',
            'patient_name': 'Test Patient',
            'culture_id': f'culture-{uuid.uuid4().hex[:8]}',
            'culture_date': timezone.now(),
            'organism': 'Staphylococcus aureus',
            'mdro_type': mdro_type,
            'resistant_antibiotics': ['oxacillin'],
            'susceptibilities': [{'antibiotic': 'oxacillin', 'result': 'R'}],
            'classification_reason': 'Staph aureus resistant to oxacillin',
            'unit': 'G3 PICU',
        }
        defaults.update(kwargs)
        return MDROCase.objects.create(**defaults)

    def test_create_mrsa_case(self):
        case = self._create_case(MDROTypeChoices.MRSA)
        self.assertEqual(case.mdro_type, 'mrsa')
        self.assertTrue(case.is_new)
        self.assertFalse(case.prior_history)

    def test_create_vre_case(self):
        case = self._create_case(
            MDROTypeChoices.VRE,
            organism='Enterococcus faecium',
            resistant_antibiotics=['vancomycin'],
        )
        self.assertEqual(case.mdro_type, 'vre')

    def test_create_cre_case(self):
        case = self._create_case(
            MDROTypeChoices.CRE,
            organism='Klebsiella pneumoniae',
            resistant_antibiotics=['meropenem'],
        )
        self.assertEqual(case.mdro_type, 'cre')

    def test_create_esbl_case(self):
        case = self._create_case(
            MDROTypeChoices.ESBL,
            organism='E. coli',
            resistant_antibiotics=['ceftriaxone', 'ceftazidime'],
        )
        self.assertEqual(case.mdro_type, 'esbl')

    def test_create_crpa_case(self):
        case = self._create_case(
            MDROTypeChoices.CRPA,
            organism='Pseudomonas aeruginosa',
            resistant_antibiotics=['imipenem'],
        )
        self.assertEqual(case.mdro_type, 'crpa')

    def test_create_crab_case(self):
        case = self._create_case(
            MDROTypeChoices.CRAB,
            organism='Acinetobacter baumannii',
            resistant_antibiotics=['meropenem'],
        )
        self.assertEqual(case.mdro_type, 'crab')

    def test_str_representation(self):
        case = self._create_case()
        s = str(case)
        self.assertIn('MRSA', s)
        self.assertIn('MRN-MDRO1', s)
        self.assertIn('Staphylococcus aureus', s)

    def test_mdro_type_full_name_property(self):
        case = self._create_case(MDROTypeChoices.MRSA)
        self.assertEqual(case.mdro_type_full_name, 'Methicillin-resistant Staph aureus')

    def test_mdro_type_full_name_vre(self):
        case = self._create_case(MDROTypeChoices.VRE, organism='Enterococcus')
        self.assertEqual(case.mdro_type_full_name, 'Vancomycin-resistant Enterococcus')

    def test_is_healthcare_onset_true(self):
        case = self._create_case(days_since_admission=5)
        self.assertTrue(case.is_healthcare_onset())

    def test_is_healthcare_onset_false_community(self):
        case = self._create_case(days_since_admission=1)
        self.assertFalse(case.is_healthcare_onset())

    def test_is_healthcare_onset_borderline(self):
        """Exactly 2 days is NOT healthcare onset (> 2 required)."""
        case = self._create_case(days_since_admission=2)
        self.assertFalse(case.is_healthcare_onset())

    def test_is_healthcare_onset_none(self):
        case = self._create_case(days_since_admission=None)
        self.assertFalse(case.is_healthcare_onset())

    def test_uuid_primary_key(self):
        case = self._create_case()
        self.assertIsInstance(case.id, uuid.UUID)

    def test_unique_culture_id(self):
        self._create_case(culture_id='dup-culture')
        with self.assertRaises(Exception):
            self._create_case(culture_id='dup-culture')

    def test_transmission_status_default(self):
        case = self._create_case()
        self.assertEqual(case.transmission_status, TransmissionStatusChoices.PENDING)

    def test_timestamps(self):
        case = self._create_case()
        self.assertIsNotNone(case.created_at)
        self.assertIsNotNone(case.updated_at)


# ============================================================================
# MDROCaseManager Tests
# ============================================================================

class MDROCaseManagerTests(TestCase):
    """Test custom MDROCaseManager query methods."""

    def setUp(self):
        now = timezone.now()
        self.recent_mrsa = MDROCase.objects.create(
            patient_id='p1', patient_mrn='MRN001',
            culture_id='c-recent-mrsa', culture_date=now - timedelta(days=5),
            organism='Staph aureus', mdro_type=MDROTypeChoices.MRSA,
            unit='G3 PICU',
            transmission_status=TransmissionStatusChoices.HEALTHCARE,
        )
        self.old_vre = MDROCase.objects.create(
            patient_id='p2', patient_mrn='MRN002',
            culture_id='c-old-vre', culture_date=now - timedelta(days=60),
            organism='Enterococcus', mdro_type=MDROTypeChoices.VRE,
            unit='A6 Hosp Med',
            transmission_status=TransmissionStatusChoices.COMMUNITY,
        )
        self.recent_cre = MDROCase.objects.create(
            patient_id='p3', patient_mrn='MRN003',
            culture_id='c-recent-cre', culture_date=now - timedelta(days=2),
            organism='Klebsiella', mdro_type=MDROTypeChoices.CRE,
            unit='G3 PICU',
            transmission_status=TransmissionStatusChoices.HEALTHCARE,
        )

    def test_recent_default_30_days(self):
        cases = MDROCase.objects.recent()
        self.assertEqual(cases.count(), 2)

    def test_recent_custom_days(self):
        cases = MDROCase.objects.recent(days=90)
        self.assertEqual(cases.count(), 3)

    def test_by_type(self):
        cases = MDROCase.objects.by_type(MDROTypeChoices.MRSA)
        self.assertEqual(cases.count(), 1)
        self.assertEqual(cases.first().patient_mrn, 'MRN001')

    def test_by_unit(self):
        cases = MDROCase.objects.by_unit('G3 PICU')
        self.assertEqual(cases.count(), 2)

    def test_healthcare_onset(self):
        cases = MDROCase.objects.healthcare_onset()
        self.assertEqual(cases.count(), 2)

    def test_community_onset(self):
        cases = MDROCase.objects.community_onset()
        self.assertEqual(cases.count(), 1)
        self.assertEqual(cases.first().patient_mrn, 'MRN002')


# ============================================================================
# MDROReview Model Tests
# ============================================================================

class MDROReviewModelTests(TestCase):
    """Test MDROReview model."""

    def setUp(self):
        self.case = MDROCase.objects.create(
            patient_id='p-rev', patient_mrn='MRN-REV',
            culture_id='c-rev-001', culture_date=timezone.now(),
            organism='Staph aureus', mdro_type=MDROTypeChoices.MRSA,
            unit='G3 PICU',
        )

    def test_create_review(self):
        review = MDROReview.objects.create(
            case=self.case,
            reviewer='ip_jones',
            decision='confirmed',
            notes='Confirmed MRSA, initiate contact precautions.',
        )
        self.assertEqual(review.case, self.case)
        self.assertEqual(review.decision, 'confirmed')
        self.assertIsNotNone(review.created_at)

    def test_review_str(self):
        review = MDROReview.objects.create(
            case=self.case,
            reviewer='ip_jones',
            decision='confirmed',
        )
        s = str(review)
        self.assertIn('confirmed', s)
        self.assertIn('ip_jones', s)
        self.assertIn('MRN-REV', s)

    def test_multiple_reviews(self):
        MDROReview.objects.create(
            case=self.case, reviewer='ip_jones', decision='needs_info',
        )
        MDROReview.objects.create(
            case=self.case, reviewer='ip_smith', decision='confirmed',
        )
        self.assertEqual(self.case.reviews.count(), 2)


# ============================================================================
# MDROProcessingLog Model Tests
# ============================================================================

class MDROProcessingLogModelTests(TestCase):
    """Test MDROProcessingLog model."""

    def test_create_mdro_log(self):
        log = MDROProcessingLog.objects.create(
            culture_id='culture-log-001',
            is_mdro=True,
            mdro_type='mrsa',
        )
        self.assertTrue(log.is_mdro)
        self.assertEqual(log.mdro_type, 'mrsa')
        self.assertIsNotNone(log.processed_at)

    def test_create_non_mdro_log(self):
        log = MDROProcessingLog.objects.create(
            culture_id='culture-log-002',
            is_mdro=False,
        )
        self.assertFalse(log.is_mdro)
        self.assertIsNone(log.mdro_type)

    def test_str_mdro(self):
        log = MDROProcessingLog.objects.create(
            culture_id='c-str-001', is_mdro=True, mdro_type='mrsa',
        )
        s = str(log)
        self.assertIn('c-str-001', s)
        self.assertIn('MDRO', s)

    def test_str_not_mdro(self):
        log = MDROProcessingLog.objects.create(
            culture_id='c-str-002', is_mdro=False,
        )
        s = str(log)
        self.assertIn('Not MDRO', s)

    def test_unique_culture_id(self):
        MDROProcessingLog.objects.create(
            culture_id='dup-log', is_mdro=False,
        )
        with self.assertRaises(Exception):
            MDROProcessingLog.objects.create(
                culture_id='dup-log', is_mdro=True, mdro_type='mrsa',
            )

    def test_log_with_case_fk(self):
        case = MDROCase.objects.create(
            patient_id='p-log', patient_mrn='MRN-LOG',
            culture_id='c-fk-001', culture_date=timezone.now(),
            organism='Staph aureus', mdro_type=MDROTypeChoices.MRSA,
        )
        log = MDROProcessingLog.objects.create(
            culture_id='c-fk-001-log', is_mdro=True, mdro_type='mrsa',
            case=case,
        )
        self.assertEqual(log.case, case)
        self.assertEqual(case.processing_logs.count(), 1)


# ============================================================================
# MDROMonitorService Tests (mocked)
# ============================================================================

class MDROMonitorServiceTests(TestCase):
    """Test MDROMonitorService with mocked FHIR client."""

    @patch('apps.mdro.services.MDROFHIRClient')
    def test_run_detection_no_cultures(self, mock_fhir_cls):
        mock_fhir = MagicMock()
        mock_fhir.get_recent_cultures.return_value = []
        mock_fhir_cls.return_value = mock_fhir

        service = MDROMonitorService()
        result = service.run_detection()

        self.assertEqual(result['cultures_checked'], 0)
        self.assertEqual(result['new_mdro_cases'], 0)

    @patch('apps.mdro.services.MDROFHIRClient')
    def test_run_detection_fhir_error(self, mock_fhir_cls):
        mock_fhir = MagicMock()
        mock_fhir.get_recent_cultures.side_effect = Exception('FHIR server down')
        mock_fhir_cls.return_value = mock_fhir

        service = MDROMonitorService()
        result = service.run_detection()

        self.assertTrue(len(result['errors']) > 0)
        self.assertEqual(result['new_mdro_cases'], 0)


# ============================================================================
# MDRO Full Names Tests
# ============================================================================

class MDROFullNamesTests(TestCase):
    """Test MDRO_TYPE_FULL_NAMES dictionary."""

    def test_all_types_have_full_names(self):
        for choice_value, _ in MDROTypeChoices.choices:
            self.assertIn(choice_value, MDRO_TYPE_FULL_NAMES)

    def test_mrsa_full_name(self):
        self.assertEqual(
            MDRO_TYPE_FULL_NAMES['mrsa'],
            'Methicillin-resistant Staph aureus',
        )

    def test_cre_full_name(self):
        self.assertEqual(
            MDRO_TYPE_FULL_NAMES['cre'],
            'Carbapenem-resistant Enterobacteriaceae',
        )


# ============================================================================
# Alert Integration Tests
# ============================================================================

class MDROAlertIntegrationTests(TestCase):
    """Test MDRO alert type integration."""

    def test_mdro_detection_alert_type(self):
        self.assertEqual(AlertType.MDRO_DETECTION, 'mdro_detection')

    def test_create_mdro_alert(self):
        alert = Alert.objects.create(
            alert_type=AlertType.MDRO_DETECTION,
            source_module='mdro_surveillance',
            source_id='test-mdro-1',
            title='MRSA Detection - Staph aureus',
            summary='Staph aureus classified as MRSA in G3 PICU.',
            severity=AlertSeverity.MEDIUM,
            patient_mrn='MRN001',
        )
        self.assertEqual(alert.alert_type, 'mdro_detection')
        self.assertEqual(alert.status, AlertStatus.PENDING)
