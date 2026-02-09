"""Tests for the Guideline Adherence API ViewSet."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.authentication.models import User, UserRole
from apps.guideline_adherence.models import (
    BundleEpisode, ElementResult, EpisodeAssessment, EpisodeReview,
    EpisodeStatus, ElementCheckStatus, AdherenceLevel, ReviewDecision,
)


class GuidelineAPITestBase(TestCase):
    """Base class with user fixtures and helper methods."""

    @classmethod
    def setUpTestData(cls):
        cls.pharmacist = User.objects.create_user(
            username='pharm_ga', email='pharm_ga@test.com', password='testpass123',
            role=UserRole.ASP_PHARMACIST,
        )
        cls.physician = User.objects.create_user(
            username='doc_ga', email='doc_ga@test.com', password='testpass123',
            role=UserRole.PHYSICIAN,
        )
        cls.admin = User.objects.create_user(
            username='admin_ga', email='admin_ga@test.com', password='testpass123',
            role=UserRole.ADMIN,
        )
        cls.ip_user = User.objects.create_user(
            username='ip_ga', email='ip_ga@test.com', password='testpass123',
            role=UserRole.INFECTION_PREVENTIONIST,
        )
        cls.pharm_token = Token.objects.create(user=cls.pharmacist)
        cls.doc_token = Token.objects.create(user=cls.physician)
        cls.admin_token = Token.objects.create(user=cls.admin)
        cls.ip_token = Token.objects.create(user=cls.ip_user)

    def setUp(self):
        self.client = APIClient()

    def auth_as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def create_episode(self, **overrides):
        defaults = {
            'patient_id': 'PAT-001',
            'patient_mrn': 'MRN001',
            'patient_name': 'Test Patient',
            'encounter_id': 'ENC-001',
            'bundle_id': 'sepsis_peds_2024',
            'bundle_name': 'Pediatric Sepsis Bundle',
            'trigger_type': 'diagnosis',
            'trigger_time': timezone.now(),
            'status': EpisodeStatus.ACTIVE,
            'adherence_percentage': 75.0,
            'adherence_level': AdherenceLevel.PARTIAL,
            'elements_total': 4,
            'elements_met': 3,
            'elements_not_met': 1,
            'elements_pending': 0,
        }
        defaults.update(overrides)
        return BundleEpisode.objects.create(**defaults)


class EpisodeListTests(GuidelineAPITestBase):
    """GET /api/v1/guidelines/episodes/ tests."""

    def test_list_requires_auth(self):
        response = self.client.get('/api/v1/guidelines/episodes/')
        self.assertIn(response.status_code, [401, 403])

    def test_list_returns_episodes(self):
        self.create_episode()
        self.create_episode(
            patient_mrn='MRN002', encounter_id='ENC-002',
            trigger_time=timezone.now() - timedelta(hours=1),
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_list_uses_lightweight_serializer(self):
        self.create_episode()
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/')
        result = response.data['results'][0]
        self.assertNotIn('element_results', result)
        self.assertNotIn('reviews', result)
        self.assertIn('bundle_name', result)
        self.assertIn('adherence_percentage', result)

    def test_filter_by_bundle_id(self):
        self.create_episode(bundle_id='sepsis_peds_2024', encounter_id='ENC-A')
        self.create_episode(bundle_id='cap_peds_2024', encounter_id='ENC-B',
                            bundle_name='CAP Bundle')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/',
                                   {'bundle_id': 'sepsis_peds_2024'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_status(self):
        self.create_episode(status=EpisodeStatus.ACTIVE, encounter_id='ENC-A')
        self.create_episode(status=EpisodeStatus.COMPLETE, encounter_id='ENC-B',
                            completed_at=timezone.now())
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/',
                                   {'status': 'active'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_adherence_level(self):
        self.create_episode(adherence_level=AdherenceLevel.FULL, encounter_id='ENC-A')
        self.create_episode(adherence_level=AdherenceLevel.LOW, encounter_id='ENC-B')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/',
                                   {'adherence_level': 'full'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_patient_mrn_icontains(self):
        self.create_episode(patient_mrn='MRN12345', encounter_id='ENC-A')
        self.create_episode(patient_mrn='MRN99999', encounter_id='ENC-B')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/',
                                   {'patient_mrn': '123'})
        self.assertEqual(response.data['count'], 1)

    def test_pagination(self):
        for i in range(55):
            self.create_episode(
                encounter_id=f'ENC-{i}',
                trigger_time=timezone.now() - timedelta(minutes=i),
            )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/')
        self.assertEqual(len(response.data['results']), 50)
        self.assertIsNotNone(response.data['next'])


class EpisodeDetailTests(GuidelineAPITestBase):
    """GET /api/v1/guidelines/episodes/{uuid}/ tests."""

    def test_detail_returns_full_data(self):
        episode = self.create_episode()
        ElementResult.objects.create(
            episode=episode, element_id='sepsis_blood_cx',
            element_name='Blood Culture', status=ElementCheckStatus.MET,
        )
        EpisodeAssessment.objects.create(
            episode=episode, assessment_type='clinical_impression',
            primary_determination='guideline_appropriate',
            confidence='high', model_used='llama3:70b',
        )
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/guidelines/episodes/{episode.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('element_results', response.data)
        self.assertIn('latest_assessment', response.data)
        self.assertIn('reviews', response.data)
        self.assertEqual(len(response.data['element_results']), 1)
        self.assertEqual(
            response.data['latest_assessment']['primary_determination'],
            'guideline_appropriate',
        )

    def test_detail_no_assessment(self):
        episode = self.create_episode()
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/guidelines/episodes/{episode.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['latest_assessment'])

    def test_404_for_nonexistent(self):
        self.auth_as(self.doc_token)
        response = self.client.get(
            '/api/v1/guidelines/episodes/00000000-0000-0000-0000-000000000000/'
        )
        self.assertEqual(response.status_code, 404)


class EpisodeReviewTests(GuidelineAPITestBase):
    """POST /api/v1/guidelines/episodes/{uuid}/submit_review/ tests."""

    def test_pharmacist_can_submit_review(self):
        episode = self.create_episode()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/guidelines/episodes/{episode.id}/submit_review/',
            {'reviewer_decision': 'guideline_appropriate'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        episode.refresh_from_db()
        self.assertEqual(episode.review_status, 'reviewed')
        self.assertEqual(episode.overall_determination, 'guideline_appropriate')

    def test_admin_can_submit_review(self):
        episode = self.create_episode()
        self.auth_as(self.admin_token)
        response = self.client.post(
            f'/api/v1/guidelines/episodes/{episode.id}/submit_review/',
            {'reviewer_decision': 'guideline_deviation'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)

    def test_physician_cannot_submit_review(self):
        episode = self.create_episode()
        self.auth_as(self.doc_token)
        response = self.client.post(
            f'/api/v1/guidelines/episodes/{episode.id}/submit_review/',
            {'reviewer_decision': 'guideline_appropriate'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_ip_cannot_submit_review(self):
        episode = self.create_episode()
        self.auth_as(self.ip_token)
        response = self.client.post(
            f'/api/v1/guidelines/episodes/{episode.id}/submit_review/',
            {'reviewer_decision': 'guideline_appropriate'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_review_requires_valid_decision(self):
        episode = self.create_episode()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/guidelines/episodes/{episode.id}/submit_review/',
            {'reviewer_decision': 'invalid'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_review_detects_override(self):
        episode = self.create_episode()
        EpisodeAssessment.objects.create(
            episode=episode, assessment_type='clinical_impression',
            primary_determination='guideline_appropriate',
            confidence='high', model_used='llama3:70b',
        )
        self.auth_as(self.pharm_token)
        self.client.post(
            f'/api/v1/guidelines/episodes/{episode.id}/submit_review/',
            {'reviewer_decision': 'guideline_deviation'},
            format='json',
        )
        review = EpisodeReview.objects.filter(episode=episode).first()
        self.assertTrue(review.is_override)
        self.assertEqual(review.llm_decision, 'guideline_appropriate')

    def test_review_with_notes(self):
        episode = self.create_episode()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/guidelines/episodes/{episode.id}/submit_review/',
            {
                'reviewer_decision': 'needs_more_info',
                'notes': 'Need to check lab results',
                'deviation_type': 'documentation',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        review = EpisodeReview.objects.filter(episode=episode).first()
        self.assertEqual(review.notes, 'Need to check lab results')
        self.assertEqual(review.deviation_type, 'documentation')


class EpisodeStatsTests(GuidelineAPITestBase):
    """GET /api/v1/guidelines/episodes/stats/ tests."""

    def test_stats_returns_aggregates(self):
        self.create_episode(
            status=EpisodeStatus.ACTIVE, encounter_id='ENC-A',
        )
        self.create_episode(
            status=EpisodeStatus.COMPLETE, encounter_id='ENC-B',
            adherence_level=AdherenceLevel.FULL,
            completed_at=timezone.now(),
        )
        self.create_episode(
            status=EpisodeStatus.COMPLETE, encounter_id='ENC-C',
            adherence_level=AdherenceLevel.LOW,
            completed_at=timezone.now(),
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['active_episodes'], 1)
        self.assertEqual(response.data['completed_episodes'], 2)
        self.assertEqual(response.data['full_adherence'], 1)
        self.assertEqual(response.data['overall_compliance'], 50.0)

    def test_stats_respects_days_param(self):
        old = self.create_episode(
            status=EpisodeStatus.COMPLETE, encounter_id='ENC-OLD',
            adherence_level=AdherenceLevel.FULL,
            completed_at=timezone.now() - timedelta(days=60),
        )
        self.create_episode(
            status=EpisodeStatus.COMPLETE, encounter_id='ENC-NEW',
            adherence_level=AdherenceLevel.FULL,
            completed_at=timezone.now(),
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/stats/', {'days': 7})
        self.assertEqual(response.data['completed_episodes'], 1)

    def test_stats_includes_review_data(self):
        episode = self.create_episode(
            status=EpisodeStatus.COMPLETE, encounter_id='ENC-R',
            completed_at=timezone.now(),
        )
        EpisodeReview.objects.create(
            episode=episode, reviewer='pharm',
            reviewer_decision=ReviewDecision.GUIDELINE_DEVIATION,
            is_override=True,
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/stats/')
        self.assertEqual(response.data['reviews'], 1)
        self.assertEqual(response.data['overrides'], 1)

    def test_stats_by_bundle(self):
        self.create_episode(
            bundle_id='sepsis_peds_2024', encounter_id='ENC-S',
            status=EpisodeStatus.COMPLETE, adherence_level=AdherenceLevel.FULL,
            completed_at=timezone.now(),
        )
        self.create_episode(
            bundle_id='cap_peds_2024', bundle_name='CAP Bundle',
            encounter_id='ENC-C', status=EpisodeStatus.COMPLETE,
            adherence_level=AdherenceLevel.LOW,
            completed_at=timezone.now(),
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/guidelines/episodes/stats/')
        bundles = response.data['by_bundle']
        self.assertEqual(len(bundles), 2)
        bundle_ids = [b['bundle_id'] for b in bundles]
        self.assertIn('sepsis_peds_2024', bundle_ids)
        self.assertIn('cap_peds_2024', bundle_ids)
