"""Tests for the HAI Detection API ViewSet."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.authentication.models import User, UserRole
from apps.hai_detection.models import (
    HAICandidate, HAIClassification, HAIReview,
    HAIType, CandidateStatus, ClassificationDecision,
    ReviewerDecision, ReviewQueueType,
)


class HAIAPITestBase(TestCase):
    """Base class with user fixtures and helper methods."""

    @classmethod
    def setUpTestData(cls):
        cls.ip_user = User.objects.create_user(
            username='ip_hai', email='ip_hai@test.com', password='testpass123',
            role=UserRole.INFECTION_PREVENTIONIST,
        )
        cls.pharmacist = User.objects.create_user(
            username='pharm_hai', email='pharm_hai@test.com', password='testpass123',
            role=UserRole.ASP_PHARMACIST,
        )
        cls.physician = User.objects.create_user(
            username='doc_hai', email='doc_hai@test.com', password='testpass123',
            role=UserRole.PHYSICIAN,
        )
        cls.admin = User.objects.create_user(
            username='admin_hai', email='admin_hai@test.com', password='testpass123',
            role=UserRole.ADMIN,
        )
        cls.ip_token = Token.objects.create(user=cls.ip_user)
        cls.pharm_token = Token.objects.create(user=cls.pharmacist)
        cls.doc_token = Token.objects.create(user=cls.physician)
        cls.admin_token = Token.objects.create(user=cls.admin)

    def setUp(self):
        self.client = APIClient()

    def auth_as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def create_candidate(self, **overrides):
        defaults = {
            'hai_type': HAIType.CLABSI,
            'patient_id': 'PAT-001',
            'patient_mrn': 'MRN001',
            'patient_name': 'Test Patient',
            'patient_location': 'G3 PICU',
            'culture_id': f'CUL-{HAICandidate.objects.count() + 1:04d}',
            'culture_date': timezone.now() - timedelta(hours=12),
            'organism': 'Staphylococcus aureus',
            'status': CandidateStatus.PENDING,
        }
        defaults.update(overrides)
        return HAICandidate.objects.create(**defaults)


class HAICandidateListTests(HAIAPITestBase):
    """GET /api/v1/hai/candidates/ tests."""

    def test_list_requires_auth(self):
        response = self.client.get('/api/v1/hai/candidates/')
        self.assertIn(response.status_code, [401, 403])

    def test_list_returns_candidates(self):
        self.create_candidate()
        self.create_candidate(patient_mrn='MRN002', culture_id='CUL-ALT')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/hai/candidates/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_list_uses_lightweight_serializer(self):
        self.create_candidate()
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/hai/candidates/')
        result = response.data['results'][0]
        self.assertNotIn('classifications', result)
        self.assertNotIn('reviews', result)
        self.assertIn('hai_type', result)
        self.assertIn('status', result)

    def test_filter_by_hai_type(self):
        self.create_candidate(hai_type=HAIType.CLABSI, culture_id='CUL-F1')
        self.create_candidate(hai_type=HAIType.SSI, culture_id='CUL-F2')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/hai/candidates/', {'hai_type': 'clabsi'})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['hai_type'], 'clabsi')

    def test_filter_by_status(self):
        self.create_candidate(status=CandidateStatus.PENDING, culture_id='CUL-S1')
        self.create_candidate(status=CandidateStatus.CONFIRMED, culture_id='CUL-S2')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/hai/candidates/', {'status': 'pending'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_patient_mrn_icontains(self):
        self.create_candidate(patient_mrn='MRN12345', culture_id='CUL-M1')
        self.create_candidate(patient_mrn='MRN99999', culture_id='CUL-M2')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/hai/candidates/', {'patient_mrn': '123'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_date_range(self):
        old = self.create_candidate(culture_id='CUL-D1')
        old.created_at = timezone.now() - timedelta(days=60)
        old.save(update_fields=['created_at'])
        self.create_candidate(culture_id='CUL-D2')
        self.auth_as(self.doc_token)
        after = (timezone.now() - timedelta(days=7)).isoformat()
        response = self.client.get('/api/v1/hai/candidates/', {'created_after': after})
        self.assertEqual(response.data['count'], 1)


class HAICandidateDetailTests(HAIAPITestBase):
    """GET /api/v1/hai/candidates/{uuid}/ tests."""

    def test_detail_returns_full_data(self):
        candidate = self.create_candidate()
        HAIClassification.objects.create(
            candidate=candidate,
            decision=ClassificationDecision.HAI_CONFIRMED,
            confidence=0.92,
            model_used='llama-3-70b',
            prompt_version='v2.1',
        )
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/hai/candidates/{candidate.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('classifications', response.data)
        self.assertIn('reviews', response.data)
        self.assertEqual(len(response.data['classifications']), 1)

    def test_detail_includes_reviews(self):
        candidate = self.create_candidate()
        HAIReview.objects.create(
            candidate=candidate,
            reviewer='Dr. Test',
            reviewer_decision=ReviewerDecision.CONFIRMED,
            reviewed=True,
            reviewed_at=timezone.now(),
        )
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/hai/candidates/{candidate.id}/')
        self.assertEqual(len(response.data['reviews']), 1)
        self.assertEqual(response.data['reviews'][0]['reviewer_decision'], 'confirmed')

    def test_404_for_nonexistent_candidate(self):
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/hai/candidates/00000000-0000-0000-0000-000000000000/')
        self.assertEqual(response.status_code, 404)


class HAISubmitReviewTests(HAIAPITestBase):
    """POST /api/v1/hai/candidates/{uuid}/submit_review/ tests."""

    def test_ip_can_submit_review(self):
        candidate = self.create_candidate(status=CandidateStatus.PENDING_REVIEW)
        self.auth_as(self.ip_token)
        response = self.client.post(
            f'/api/v1/hai/candidates/{candidate.id}/submit_review/',
            {'decision': 'confirmed'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, CandidateStatus.CONFIRMED)
        self.assertEqual(response.data['new_status'], 'confirmed')

    def test_admin_can_submit_review(self):
        candidate = self.create_candidate(status=CandidateStatus.PENDING_REVIEW)
        self.auth_as(self.admin_token)
        response = self.client.post(
            f'/api/v1/hai/candidates/{candidate.id}/submit_review/',
            {'decision': 'rejected', 'notes': 'Not meeting NHSN criteria'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, CandidateStatus.REJECTED)

    def test_physician_cannot_submit_review(self):
        candidate = self.create_candidate()
        self.auth_as(self.doc_token)
        response = self.client.post(
            f'/api/v1/hai/candidates/{candidate.id}/submit_review/',
            {'decision': 'confirmed'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_pharmacist_cannot_submit_review(self):
        candidate = self.create_candidate()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/hai/candidates/{candidate.id}/submit_review/',
            {'decision': 'confirmed'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_review_requires_decision(self):
        candidate = self.create_candidate()
        self.auth_as(self.ip_token)
        response = self.client.post(
            f'/api/v1/hai/candidates/{candidate.id}/submit_review/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_review_rejects_invalid_decision(self):
        candidate = self.create_candidate()
        self.auth_as(self.ip_token)
        response = self.client.post(
            f'/api/v1/hai/candidates/{candidate.id}/submit_review/',
            {'decision': 'invalid_value'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_review_creates_hai_review_record(self):
        candidate = self.create_candidate()
        self.auth_as(self.ip_token)
        self.client.post(
            f'/api/v1/hai/candidates/{candidate.id}/submit_review/',
            {'decision': 'confirmed', 'notes': 'Clear CLABSI case'},
            format='json',
        )
        review = HAIReview.objects.filter(candidate=candidate).first()
        self.assertIsNotNone(review)
        self.assertEqual(review.reviewer_decision, ReviewerDecision.CONFIRMED)
        self.assertTrue(review.reviewed)
        self.assertIn('Clear CLABSI case', review.reviewer_notes)

    def test_review_detects_override(self):
        candidate = self.create_candidate(status=CandidateStatus.CLASSIFIED)
        HAIClassification.objects.create(
            candidate=candidate,
            decision=ClassificationDecision.HAI_CONFIRMED,
            confidence=0.85,
            model_used='llama-3-70b',
            prompt_version='v2.1',
        )
        self.auth_as(self.ip_token)
        response = self.client.post(
            f'/api/v1/hai/candidates/{candidate.id}/submit_review/',
            {
                'decision': 'rejected',
                'notes': 'LLM was wrong',
                'override_reason': 'Missing documentation',
                'override_reason_category': 'missing_documentation',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_override'])
        review = HAIReview.objects.filter(candidate=candidate).first()
        self.assertTrue(review.is_override)
        self.assertEqual(review.override_reason, 'Missing documentation')

    def test_needs_more_info_does_not_change_status(self):
        candidate = self.create_candidate(status=CandidateStatus.PENDING_REVIEW)
        self.auth_as(self.ip_token)
        response = self.client.post(
            f'/api/v1/hai/candidates/{candidate.id}/submit_review/',
            {'decision': 'needs_more_info', 'notes': 'Need culture results'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, CandidateStatus.PENDING_REVIEW)
        review = HAIReview.objects.filter(candidate=candidate).first()
        self.assertFalse(review.reviewed)
        self.assertIsNone(review.reviewed_at)


class HAIStatsTests(HAIAPITestBase):
    """GET /api/v1/hai/candidates/stats/ tests."""

    def test_stats_returns_aggregates(self):
        self.create_candidate(
            hai_type=HAIType.CLABSI, status=CandidateStatus.PENDING, culture_id='CUL-ST1',
        )
        self.create_candidate(
            hai_type=HAIType.SSI, status=CandidateStatus.CONFIRMED, culture_id='CUL-ST2',
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/hai/candidates/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 2)
        self.assertIn('by_type', response.data)
        self.assertIn('by_status', response.data)
        self.assertIn('accuracy_pct', response.data)

    def test_stats_respects_days_param(self):
        old = self.create_candidate(culture_id='CUL-OLD')
        old.created_at = timezone.now() - timedelta(days=60)
        old.save(update_fields=['created_at'])
        self.create_candidate(culture_id='CUL-NEW')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/hai/candidates/stats/', {'days': 7})
        self.assertEqual(response.data['total'], 1)

    def test_stats_includes_active_count(self):
        self.create_candidate(status=CandidateStatus.PENDING, culture_id='CUL-A1')
        self.create_candidate(status=CandidateStatus.PENDING_REVIEW, culture_id='CUL-A2')
        self.create_candidate(status=CandidateStatus.CONFIRMED, culture_id='CUL-A3')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/hai/candidates/stats/')
        self.assertEqual(response.data['active'], 2)
        self.assertEqual(response.data['pending_review'], 1)
