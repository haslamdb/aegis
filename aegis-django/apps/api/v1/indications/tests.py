"""Tests for the ABX Indications API ViewSet."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.authentication.models import User, UserRole
from apps.alerts.models import Alert, AlertType, AlertStatus, AlertSeverity
from apps.abx_indications.models import (
    IndicationCandidate, IndicationReview,
    CandidateStatus, SyndromeDecision, AgentDecision,
    AgentCategoryChoice,
)


class IndicationAPITestBase(TestCase):
    """Base class with user fixtures and helper methods."""

    @classmethod
    def setUpTestData(cls):
        cls.pharmacist = User.objects.create_user(
            username='pharm_ind', email='pharm_ind@test.com', password='testpass123',
            role=UserRole.ASP_PHARMACIST,
        )
        cls.physician = User.objects.create_user(
            username='doc_ind', email='doc_ind@test.com', password='testpass123',
            role=UserRole.PHYSICIAN,
        )
        cls.admin = User.objects.create_user(
            username='admin_ind', email='admin_ind@test.com', password='testpass123',
            role=UserRole.ADMIN,
        )
        cls.ip_user = User.objects.create_user(
            username='ip_ind', email='ip_ind@test.com', password='testpass123',
            role=UserRole.INFECTION_PREVENTIONIST,
        )
        cls.pharm_token = Token.objects.create(user=cls.pharmacist)
        cls.doc_token = Token.objects.create(user=cls.physician)
        cls.admin_token = Token.objects.create(user=cls.admin)
        cls.ip_token = Token.objects.create(user=cls.ip_user)

    def setUp(self):
        self.client = APIClient()
        self._candidate_counter = 0

    def auth_as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def create_candidate(self, **overrides):
        self._candidate_counter += 1
        defaults = {
            'patient_id': 'PAT-001',
            'patient_mrn': 'MRN001',
            'patient_name': 'Test Patient',
            'medication_request_id': f'MR-{self._candidate_counter}-{timezone.now().timestamp()}',
            'medication_name': 'Ceftriaxone',
            'order_date': timezone.now(),
            'clinical_syndrome': 'cap',
            'clinical_syndrome_display': 'Community-Acquired Pneumonia',
            'syndrome_category': 'respiratory',
            'status': CandidateStatus.PENDING,
        }
        defaults.update(overrides)
        return IndicationCandidate.objects.create(**defaults)


class CandidateListTests(IndicationAPITestBase):
    """GET /api/v1/indications/candidates/ tests."""

    def test_list_requires_auth(self):
        response = self.client.get('/api/v1/indications/candidates/')
        self.assertIn(response.status_code, [401, 403])

    def test_list_returns_candidates(self):
        self.create_candidate()
        self.create_candidate(patient_mrn='MRN002')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_list_uses_lightweight_serializer(self):
        self.create_candidate()
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/')
        result = response.data['results'][0]
        self.assertNotIn('reviews', result)
        self.assertNotIn('supporting_evidence', result)
        self.assertIn('medication_name', result)
        self.assertIn('has_red_flag', result)

    def test_filter_by_status(self):
        self.create_candidate(status=CandidateStatus.PENDING)
        self.create_candidate(status=CandidateStatus.REVIEWED)
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/',
                                   {'status': 'pending'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_medication_name(self):
        self.create_candidate(medication_name='Ceftriaxone')
        self.create_candidate(medication_name='Vancomycin')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/',
                                   {'medication_name': 'Ceftriaxone'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_clinical_syndrome(self):
        self.create_candidate(clinical_syndrome='cap')
        self.create_candidate(clinical_syndrome='uti_simple')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/',
                                   {'clinical_syndrome': 'cap'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_patient_mrn_icontains(self):
        self.create_candidate(patient_mrn='MRN12345')
        self.create_candidate(patient_mrn='MRN99999')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/',
                                   {'patient_mrn': '123'})
        self.assertEqual(response.data['count'], 1)

    def test_pagination(self):
        for i in range(55):
            self.create_candidate()
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/')
        self.assertEqual(len(response.data['results']), 50)
        self.assertIsNotNone(response.data['next'])


class CandidateDetailTests(IndicationAPITestBase):
    """GET /api/v1/indications/candidates/{uuid}/ tests."""

    def test_detail_returns_full_data(self):
        candidate = self.create_candidate(
            supporting_evidence=['Fever', 'CXR consolidation'],
        )
        IndicationReview.objects.create(
            candidate=candidate, reviewer=self.pharmacist,
            syndrome_decision=SyndromeDecision.CONFIRM_SYNDROME,
            agent_decision=AgentDecision.APPROPRIATE,
        )
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/indications/candidates/{candidate.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('reviews', response.data)
        self.assertIn('supporting_evidence', response.data)
        self.assertEqual(len(response.data['reviews']), 1)
        self.assertEqual(response.data['supporting_evidence'], ['Fever', 'CXR consolidation'])

    def test_detail_has_red_flag_field(self):
        candidate = self.create_candidate(never_appropriate=True)
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/indications/candidates/{candidate.id}/')
        self.assertTrue(response.data['has_red_flag'])

    def test_404_for_nonexistent(self):
        self.auth_as(self.doc_token)
        response = self.client.get(
            '/api/v1/indications/candidates/00000000-0000-0000-0000-000000000000/'
        )
        self.assertEqual(response.status_code, 404)


class CandidateReviewTests(IndicationAPITestBase):
    """POST /api/v1/indications/candidates/{uuid}/submit_review/ tests."""

    def test_pharmacist_can_submit_review(self):
        candidate = self.create_candidate()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/indications/candidates/{candidate.id}/submit_review/',
            {'syndrome_decision': 'confirm_syndrome'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, CandidateStatus.REVIEWED)

    def test_ip_can_submit_review(self):
        candidate = self.create_candidate()
        self.auth_as(self.ip_token)
        response = self.client.post(
            f'/api/v1/indications/candidates/{candidate.id}/submit_review/',
            {'syndrome_decision': 'confirm_syndrome'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)

    def test_admin_can_submit_review(self):
        candidate = self.create_candidate()
        self.auth_as(self.admin_token)
        response = self.client.post(
            f'/api/v1/indications/candidates/{candidate.id}/submit_review/',
            {'syndrome_decision': 'no_indication'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)

    def test_physician_cannot_submit_review(self):
        candidate = self.create_candidate()
        self.auth_as(self.doc_token)
        response = self.client.post(
            f'/api/v1/indications/candidates/{candidate.id}/submit_review/',
            {'syndrome_decision': 'confirm_syndrome'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_review_requires_valid_decision(self):
        candidate = self.create_candidate()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/indications/candidates/{candidate.id}/submit_review/',
            {'syndrome_decision': 'invalid'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_review_with_full_data(self):
        candidate = self.create_candidate()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/indications/candidates/{candidate.id}/submit_review/',
            {
                'syndrome_decision': 'correct_syndrome',
                'confirmed_syndrome': 'uti_simple',
                'confirmed_syndrome_display': 'Simple UTI',
                'agent_decision': 'appropriate',
                'agent_notes': 'Good coverage for UTI',
                'is_override': True,
                'notes': 'Changed from CAP to UTI based on culture',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        review = IndicationReview.objects.filter(candidate=candidate).first()
        self.assertEqual(review.confirmed_syndrome, 'uti_simple')
        self.assertEqual(review.agent_decision, 'appropriate')
        self.assertTrue(review.is_override)

    def test_review_resolves_associated_alert(self):
        alert = Alert.objects.create(
            alert_type=AlertType.ABX_NO_INDICATION,
            source_module='abx_indications',
            source_id='test-001',
            title='No Indication',
            summary='No indication documented',
            severity=AlertSeverity.HIGH,
            status=AlertStatus.PENDING,
        )
        candidate = self.create_candidate(alert=alert)
        self.auth_as(self.pharm_token)
        self.client.post(
            f'/api/v1/indications/candidates/{candidate.id}/submit_review/',
            {'syndrome_decision': 'confirm_syndrome'},
            format='json',
        )
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.RESOLVED)


class CandidateStatsTests(IndicationAPITestBase):
    """GET /api/v1/indications/candidates/stats/ tests."""

    def test_stats_returns_aggregates(self):
        self.create_candidate(status=CandidateStatus.PENDING)
        self.create_candidate(
            status=CandidateStatus.ALERTED,
            never_appropriate=True,
        )
        self.create_candidate(status=CandidateStatus.REVIEWED)
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['pending_count'], 2)
        self.assertIn('red_flag_count', response.data)
        self.assertIn('by_status', response.data)

    def test_stats_respects_days_param(self):
        old = self.create_candidate(status=CandidateStatus.REVIEWED)
        old.created_at = timezone.now() - timedelta(days=60)
        old.save(update_fields=['created_at'])
        self.create_candidate()
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/stats/', {'days': 7})
        by_status = response.data['by_status']
        total = sum(by_status.values())
        self.assertEqual(total, 1)

    def test_stats_top_syndromes(self):
        for _ in range(3):
            self.create_candidate(clinical_syndrome='cap',
                                  clinical_syndrome_display='CAP')
        for _ in range(2):
            self.create_candidate(clinical_syndrome='uti_simple',
                                  clinical_syndrome_display='Simple UTI')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/stats/')
        syndromes = response.data['top_syndromes']
        self.assertEqual(len(syndromes), 2)
        self.assertEqual(syndromes[0]['syndrome'], 'cap')
        self.assertEqual(syndromes[0]['count'], 3)

    def test_stats_off_guideline_count(self):
        self.create_candidate(
            cchmc_agent_category=AgentCategoryChoice.OFF_GUIDELINE,
            status=CandidateStatus.PENDING,
        )
        self.create_candidate(
            cchmc_agent_category=AgentCategoryChoice.FIRST_LINE,
            status=CandidateStatus.PENDING,
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/indications/candidates/stats/')
        self.assertEqual(response.data['off_guideline_count'], 1)
