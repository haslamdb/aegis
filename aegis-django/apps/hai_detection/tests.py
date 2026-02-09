"""
Tests for HAI Detection module.

Tests cover:
- Enum values (HAIType, CandidateStatus, ClassificationDecision, etc.)
- HAICandidate model CRUD for all 5 HAI types
- HAIClassification model linked to candidates
- HAIReview model with override tracking
- LLMAuditLog model
- Model __str__ methods and properties
- Status transitions through the pipeline
- HAIDetectionService (mocked)
- Alert integration
"""

import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.alerts.models import Alert, AlertType, AlertSeverity, AlertStatus

from .models import (
    HAICandidate, HAIClassification, HAIReview, LLMAuditLog,
    HAIType, CandidateStatus, ClassificationDecision,
    ReviewQueueType, ReviewerDecision, OverrideReasonCategory,
)
from .services import HAIDetectionService


# ============================================================================
# Enum Tests
# ============================================================================

class HAITypeEnumTests(TestCase):
    """Test HAIType enum values and labels."""

    def test_hai_type_values(self):
        self.assertEqual(HAIType.CLABSI, 'clabsi')
        self.assertEqual(HAIType.SSI, 'ssi')
        self.assertEqual(HAIType.CAUTI, 'cauti')
        self.assertEqual(HAIType.VAE, 'vae')
        self.assertEqual(HAIType.CDI, 'cdi')

    def test_hai_type_count(self):
        self.assertEqual(len(HAIType.choices), 5)

    def test_hai_type_labels(self):
        self.assertEqual(HAIType.CLABSI.label, 'Central Line-Associated BSI')
        self.assertEqual(HAIType.CDI.label, 'C. difficile Infection')


class CandidateStatusEnumTests(TestCase):
    """Test CandidateStatus enum."""

    def test_status_values(self):
        self.assertEqual(CandidateStatus.PENDING, 'pending')
        self.assertEqual(CandidateStatus.CLASSIFIED, 'classified')
        self.assertEqual(CandidateStatus.PENDING_REVIEW, 'pending_review')
        self.assertEqual(CandidateStatus.CONFIRMED, 'confirmed')
        self.assertEqual(CandidateStatus.REJECTED, 'rejected')
        self.assertEqual(CandidateStatus.EXCLUDED, 'excluded')

    def test_status_count(self):
        self.assertEqual(len(CandidateStatus.choices), 6)


class ClassificationDecisionEnumTests(TestCase):
    """Test ClassificationDecision enum."""

    def test_decision_values(self):
        self.assertEqual(ClassificationDecision.HAI_CONFIRMED, 'hai_confirmed')
        self.assertEqual(ClassificationDecision.NOT_HAI, 'not_hai')
        self.assertEqual(ClassificationDecision.PENDING_REVIEW, 'pending_review')

    def test_decision_count(self):
        self.assertEqual(len(ClassificationDecision.choices), 3)


class ReviewerDecisionEnumTests(TestCase):
    """Test ReviewerDecision enum."""

    def test_decision_values(self):
        self.assertEqual(ReviewerDecision.CONFIRMED, 'confirmed')
        self.assertEqual(ReviewerDecision.REJECTED, 'rejected')
        self.assertEqual(ReviewerDecision.NEEDS_MORE_INFO, 'needs_more_info')


class OverrideReasonCategoryEnumTests(TestCase):
    """Test OverrideReasonCategory enum."""

    def test_category_values(self):
        self.assertEqual(OverrideReasonCategory.EXTRACTION_ERROR, 'extraction_error')
        self.assertEqual(OverrideReasonCategory.CLINICAL_JUDGMENT, 'clinical_judgment')
        self.assertEqual(OverrideReasonCategory.NHSN_INTERPRETATION, 'nhsn_interpretation')
        self.assertEqual(OverrideReasonCategory.OTHER, 'other')

    def test_category_count(self):
        self.assertEqual(len(OverrideReasonCategory.choices), 6)


# ============================================================================
# HAICandidate Model Tests
# ============================================================================

class HAICandidateModelTests(TestCase):
    """Test HAICandidate model CRUD and properties."""

    def _create_candidate(self, hai_type=HAIType.CLABSI, **kwargs):
        defaults = {
            'hai_type': hai_type,
            'patient_id': 'patient-001',
            'patient_mrn': 'MRN001',
            'patient_name': 'Test Patient',
            'patient_location': 'G3 PICU',
            'culture_id': f'culture-{uuid.uuid4().hex[:8]}',
            'culture_date': timezone.now(),
            'organism': 'Staphylococcus aureus',
        }
        defaults.update(kwargs)
        return HAICandidate.objects.create(**defaults)

    def test_create_clabsi_candidate(self):
        c = self._create_candidate(HAIType.CLABSI, device_days_at_culture=5)
        self.assertEqual(c.hai_type, 'clabsi')
        self.assertEqual(c.status, CandidateStatus.PENDING)
        self.assertEqual(c.device_days_at_culture, 5)
        self.assertIsNotNone(c.id)
        self.assertFalse(c.nhsn_reported)

    def test_create_ssi_candidate(self):
        c = self._create_candidate(
            HAIType.SSI,
            organism='Enterococcus faecalis',
            type_specific_data={'ssi': {'procedure_name': 'Appendectomy'}},
        )
        self.assertEqual(c.hai_type, 'ssi')
        self.assertEqual(c.type_specific_data['ssi']['procedure_name'], 'Appendectomy')

    def test_create_cauti_candidate(self):
        c = self._create_candidate(HAIType.CAUTI, organism='E. coli')
        self.assertEqual(c.hai_type, 'cauti')

    def test_create_vae_candidate(self):
        c = self._create_candidate(
            HAIType.VAE,
            type_specific_data={'vae': {'ventilator_day_at_onset': 4}},
        )
        self.assertEqual(c.hai_type, 'vae')
        self.assertEqual(c.type_specific_data['vae']['ventilator_day_at_onset'], 4)

    def test_create_cdi_candidate(self):
        c = self._create_candidate(
            HAIType.CDI,
            organism='Clostridioides difficile',
            type_specific_data={'cdi': {'onset_type': 'hco', 'is_recurrent': False}},
        )
        self.assertEqual(c.hai_type, 'cdi')
        self.assertFalse(c.type_specific_data['cdi']['is_recurrent'])

    def test_default_status_is_pending(self):
        c = self._create_candidate()
        self.assertEqual(c.status, CandidateStatus.PENDING)

    def test_excluded_status(self):
        c = self._create_candidate(
            status=CandidateStatus.EXCLUDED,
            meets_initial_criteria=False,
            exclusion_reason='Failed day-of-admission rule',
        )
        self.assertEqual(c.status, CandidateStatus.EXCLUDED)
        self.assertFalse(c.meets_initial_criteria)
        self.assertIn('day-of-admission', c.exclusion_reason)

    def test_str_representation(self):
        c = self._create_candidate(HAIType.CLABSI)
        s = str(c)
        self.assertIn('Central Line-Associated BSI', s)
        self.assertIn('MRN001', s)
        self.assertIn('Pending Classification', s)

    def test_unique_constraint_hai_type_culture(self):
        self._create_candidate(culture_id='culture-dup')
        with self.assertRaises(Exception):
            self._create_candidate(culture_id='culture-dup')

    def test_uuid_primary_key(self):
        c = self._create_candidate()
        self.assertIsInstance(c.id, uuid.UUID)

    def test_timestamps(self):
        c = self._create_candidate()
        self.assertIsNotNone(c.created_at)
        self.assertIsNotNone(c.updated_at)

    def test_latest_classification_none(self):
        c = self._create_candidate()
        self.assertIsNone(c.latest_classification)

    def test_latest_review_none(self):
        c = self._create_candidate()
        self.assertIsNone(c.latest_review)

    def test_pending_review_none(self):
        c = self._create_candidate()
        self.assertIsNone(c.pending_review)

    def test_ordering_by_created_at_desc(self):
        c1 = self._create_candidate(culture_id='culture-first')
        c2 = self._create_candidate(culture_id='culture-second')
        candidates = list(HAICandidate.objects.all())
        self.assertEqual(candidates[0].id, c2.id)


# ============================================================================
# HAIClassification Model Tests
# ============================================================================

class HAIClassificationModelTests(TestCase):
    """Test HAIClassification model."""

    def setUp(self):
        self.candidate = HAICandidate.objects.create(
            hai_type=HAIType.CLABSI,
            patient_id='patient-cls',
            patient_mrn='MRN-CLS',
            culture_id='culture-cls-001',
            culture_date=timezone.now(),
            organism='Staph aureus',
        )

    def test_create_classification(self):
        cls = HAIClassification.objects.create(
            candidate=self.candidate,
            decision=ClassificationDecision.HAI_CONFIRMED,
            confidence=0.92,
            model_used='llama3.1:70b',
            prompt_version='v2.1',
            tokens_used=1500,
            processing_time_ms=3200,
            reasoning='Blood culture positive with central line in place >2 days.',
        )
        self.assertEqual(cls.decision, ClassificationDecision.HAI_CONFIRMED)
        self.assertAlmostEqual(cls.confidence, 0.92)
        self.assertEqual(cls.model_used, 'llama3.1:70b')

    def test_classification_not_hai(self):
        cls = HAIClassification.objects.create(
            candidate=self.candidate,
            decision=ClassificationDecision.NOT_HAI,
            confidence=0.85,
            model_used='llama3.1:70b',
            prompt_version='v2.1',
            alternative_source='Skin contaminant',
        )
        self.assertEqual(cls.decision, ClassificationDecision.NOT_HAI)
        self.assertEqual(cls.alternative_source, 'Skin contaminant')

    def test_classification_str(self):
        cls = HAIClassification.objects.create(
            candidate=self.candidate,
            decision=ClassificationDecision.HAI_CONFIRMED,
            confidence=0.75,
            model_used='test-model',
            prompt_version='v1',
        )
        s = str(cls)
        self.assertIn('HAI Confirmed', s)
        self.assertIn('75%', s)

    def test_candidate_latest_classification_property(self):
        HAIClassification.objects.create(
            candidate=self.candidate,
            decision=ClassificationDecision.NOT_HAI,
            confidence=0.5,
            model_used='m1',
            prompt_version='v1',
        )
        cls2 = HAIClassification.objects.create(
            candidate=self.candidate,
            decision=ClassificationDecision.HAI_CONFIRMED,
            confidence=0.95,
            model_used='m2',
            prompt_version='v2',
        )
        self.assertEqual(self.candidate.latest_classification.id, cls2.id)

    def test_evidence_json_fields(self):
        cls = HAIClassification.objects.create(
            candidate=self.candidate,
            decision=ClassificationDecision.HAI_CONFIRMED,
            confidence=0.88,
            model_used='test',
            prompt_version='v1',
            supporting_evidence=[{'text': 'Positive BC', 'source': 'lab'}],
            contradicting_evidence=[{'text': 'No fever', 'source': 'vitals'}],
        )
        self.assertEqual(len(cls.supporting_evidence), 1)
        self.assertEqual(cls.contradicting_evidence[0]['source'], 'vitals')


# ============================================================================
# HAIReview Model Tests
# ============================================================================

class HAIReviewModelTests(TestCase):
    """Test HAIReview model with override tracking."""

    def setUp(self):
        self.candidate = HAICandidate.objects.create(
            hai_type=HAIType.CAUTI,
            patient_id='patient-rev',
            patient_mrn='MRN-REV',
            culture_id='culture-rev-001',
            culture_date=timezone.now(),
            organism='Klebsiella pneumoniae',
        )
        self.classification = HAIClassification.objects.create(
            candidate=self.candidate,
            decision=ClassificationDecision.HAI_CONFIRMED,
            confidence=0.80,
            model_used='test',
            prompt_version='v1',
        )

    def test_create_pending_review(self):
        review = HAIReview.objects.create(
            candidate=self.candidate,
            classification=self.classification,
            queue_type=ReviewQueueType.IP_REVIEW,
        )
        self.assertFalse(review.reviewed)
        self.assertEqual(review.queue_type, ReviewQueueType.IP_REVIEW)

    def test_review_confirmed(self):
        review = HAIReview.objects.create(
            candidate=self.candidate,
            classification=self.classification,
        )
        review.reviewed = True
        review.reviewer = 'ip_johnson'
        review.reviewer_decision = ReviewerDecision.CONFIRMED
        review.reviewer_notes = 'Agree with LLM classification.'
        review.reviewed_at = timezone.now()
        review.save()

        review.refresh_from_db()
        self.assertTrue(review.reviewed)
        self.assertEqual(review.reviewer_decision, ReviewerDecision.CONFIRMED)

    def test_review_override(self):
        review = HAIReview.objects.create(
            candidate=self.candidate,
            classification=self.classification,
        )
        review.reviewed = True
        review.reviewer = 'ip_smith'
        review.reviewer_decision = ReviewerDecision.REJECTED
        review.is_override = True
        review.llm_decision = ClassificationDecision.HAI_CONFIRMED
        review.override_reason = 'Catheter was removed 48h before culture.'
        review.override_reason_category = OverrideReasonCategory.CLINICAL_JUDGMENT
        review.reviewed_at = timezone.now()
        review.save()

        review.refresh_from_db()
        self.assertTrue(review.is_override)
        self.assertEqual(review.override_reason_category, OverrideReasonCategory.CLINICAL_JUDGMENT)

    def test_review_str_pending(self):
        review = HAIReview.objects.create(
            candidate=self.candidate,
            classification=self.classification,
        )
        s = str(review)
        self.assertIn('Pending', s)

    def test_review_str_reviewed(self):
        review = HAIReview.objects.create(
            candidate=self.candidate,
            classification=self.classification,
            reviewed=True,
        )
        s = str(review)
        self.assertIn('Reviewed', s)

    def test_pending_review_property(self):
        review = HAIReview.objects.create(
            candidate=self.candidate,
            classification=self.classification,
            reviewed=False,
        )
        self.assertEqual(self.candidate.pending_review.id, review.id)

    def test_pending_review_returns_none_when_reviewed(self):
        HAIReview.objects.create(
            candidate=self.candidate,
            classification=self.classification,
            reviewed=True,
        )
        self.assertIsNone(self.candidate.pending_review)


# ============================================================================
# LLMAuditLog Model Tests
# ============================================================================

class LLMAuditLogModelTests(TestCase):
    """Test LLMAuditLog model."""

    def setUp(self):
        self.candidate = HAICandidate.objects.create(
            hai_type=HAIType.SSI,
            patient_id='patient-llm',
            patient_mrn='MRN-LLM',
            culture_id='culture-llm-001',
            culture_date=timezone.now(),
            organism='E. coli',
        )

    def test_create_success_log(self):
        log = LLMAuditLog.objects.create(
            candidate=self.candidate,
            model='llama3.1:70b',
            success=True,
            input_tokens=2000,
            output_tokens=500,
            response_time_ms=4500,
        )
        self.assertTrue(log.success)
        self.assertEqual(log.input_tokens, 2000)

    def test_create_error_log(self):
        log = LLMAuditLog.objects.create(
            candidate=self.candidate,
            model='llama3.1:70b',
            success=False,
            error_message='Connection timeout',
            response_time_ms=30000,
        )
        self.assertFalse(log.success)
        self.assertIn('timeout', log.error_message)

    def test_str_success(self):
        log = LLMAuditLog.objects.create(
            candidate=self.candidate,
            model='llama3.1:70b',
            success=True,
            input_tokens=1000,
            output_tokens=200,
        )
        s = str(log)
        self.assertIn('OK', s)
        self.assertIn('1000+200 tokens', s)

    def test_str_error(self):
        log = LLMAuditLog.objects.create(
            candidate=self.candidate,
            model='llama3.1:70b',
            success=False,
            input_tokens=500,
            output_tokens=0,
        )
        s = str(log)
        self.assertIn('ERROR', s)

    def test_log_without_candidate(self):
        log = LLMAuditLog.objects.create(
            candidate=None,
            model='test-model',
            success=True,
        )
        self.assertIsNone(log.candidate)


# ============================================================================
# Status Transition Tests
# ============================================================================

class HAIStatusTransitionTests(TestCase):
    """Test status transitions through the HAI pipeline."""

    def setUp(self):
        self.candidate = HAICandidate.objects.create(
            hai_type=HAIType.CLABSI,
            patient_id='patient-trans',
            patient_mrn='MRN-TRANS',
            culture_id='culture-trans-001',
            culture_date=timezone.now(),
            organism='Staph aureus',
        )

    def test_pending_to_pending_review(self):
        self.assertEqual(self.candidate.status, CandidateStatus.PENDING)
        self.candidate.status = CandidateStatus.PENDING_REVIEW
        self.candidate.save(update_fields=['status', 'updated_at'])
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, CandidateStatus.PENDING_REVIEW)

    def test_pending_review_to_confirmed(self):
        self.candidate.status = CandidateStatus.PENDING_REVIEW
        self.candidate.save(update_fields=['status', 'updated_at'])
        self.candidate.status = CandidateStatus.CONFIRMED
        self.candidate.save(update_fields=['status', 'updated_at'])
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, CandidateStatus.CONFIRMED)

    def test_pending_review_to_rejected(self):
        self.candidate.status = CandidateStatus.PENDING_REVIEW
        self.candidate.save(update_fields=['status', 'updated_at'])
        self.candidate.status = CandidateStatus.REJECTED
        self.candidate.save(update_fields=['status', 'updated_at'])
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, CandidateStatus.REJECTED)

    def test_full_pipeline_to_confirmed(self):
        """Test full workflow: PENDING -> PENDING_REVIEW -> CONFIRMED."""
        self.assertEqual(self.candidate.status, CandidateStatus.PENDING)

        # Classify
        HAIClassification.objects.create(
            candidate=self.candidate,
            decision=ClassificationDecision.HAI_CONFIRMED,
            confidence=0.91,
            model_used='test',
            prompt_version='v1',
        )
        self.candidate.status = CandidateStatus.PENDING_REVIEW
        self.candidate.save(update_fields=['status', 'updated_at'])

        # Review
        HAIReview.objects.create(
            candidate=self.candidate,
            reviewed=True,
            reviewer_decision=ReviewerDecision.CONFIRMED,
        )
        self.candidate.status = CandidateStatus.CONFIRMED
        self.candidate.save(update_fields=['status', 'updated_at'])

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, CandidateStatus.CONFIRMED)


# ============================================================================
# HAIDetectionService Tests (mocked)
# ============================================================================

class HAIDetectionServiceTests(TestCase):
    """Test HAIDetectionService with mocked detectors."""

    def test_service_init(self):
        service = HAIDetectionService()
        self.assertIsInstance(service._classifiers, dict)
        self.assertIsInstance(service._detectors, dict)

    @patch.object(HAIDetectionService, '_get_detector')
    def test_run_detection_no_detectors(self, mock_get_detector):
        mock_get_detector.return_value = None
        service = HAIDetectionService()
        result = service.run_detection()
        self.assertEqual(result['new_candidates'], 0)
        self.assertIsInstance(result['by_type'], dict)
        self.assertIsInstance(result['errors'], list)

    def test_run_classification_no_pending(self):
        service = HAIDetectionService()
        result = service.run_classification()
        self.assertEqual(result['classified'], 0)
        self.assertEqual(result['errors'], 0)

    def test_run_classification_dry_run(self):
        HAICandidate.objects.create(
            hai_type=HAIType.CLABSI,
            patient_id='patient-dry',
            patient_mrn='MRN-DRY',
            culture_id='culture-dry-001',
            culture_date=timezone.now(),
            organism='Staph aureus',
            status=CandidateStatus.PENDING,
        )
        service = HAIDetectionService()
        # dry_run won't actually classify without a real classifier
        # but won't error if no classifier is available
        with patch.object(service, '_get_classifier', return_value=None):
            result = service.run_classification(dry_run=True)
            self.assertEqual(result['classified'], 0)

    @patch.object(HAIDetectionService, '_get_detector')
    def test_run_detection_dry_run(self, mock_get_detector):
        mock_detector = MagicMock()
        mock_detector.detect_candidates.return_value = []
        mock_get_detector.return_value = mock_detector
        service = HAIDetectionService()
        result = service.run_detection(dry_run=True)
        self.assertEqual(result['new_candidates'], 0)

    def test_run_full_pipeline_returns_both_keys(self):
        service = HAIDetectionService()
        with patch.object(service, 'run_detection', return_value={'new_candidates': 0, 'by_type': {}, 'errors': []}):
            with patch.object(service, 'run_classification', return_value={'classified': 0, 'errors': 0, 'by_decision': {}, 'details': []}):
                result = service.run_full_pipeline()
                self.assertIn('detection', result)
                self.assertIn('classification', result)


# ============================================================================
# Alert Integration Tests
# ============================================================================

class HAIAlertIntegrationTests(TestCase):
    """Test that HAI types map to correct AlertTypes."""

    def test_alert_types_exist(self):
        self.assertEqual(AlertType.CLABSI, 'clabsi')
        self.assertEqual(AlertType.SSI, 'ssi')
        self.assertEqual(AlertType.CAUTI, 'cauti')
        self.assertEqual(AlertType.VAE, 'vae')
        self.assertEqual(AlertType.CDI, 'cdi')

    def test_create_hai_alert(self):
        alert = Alert.objects.create(
            alert_type=AlertType.CLABSI,
            source_module='hai_detection',
            source_id='test-hai-alert',
            title='CLABSI Candidate: MRN001',
            summary='Positive blood culture with central line.',
            severity=AlertSeverity.HIGH,
            patient_mrn='MRN001',
        )
        self.assertEqual(alert.alert_type, 'clabsi')
        self.assertEqual(alert.status, AlertStatus.PENDING)
