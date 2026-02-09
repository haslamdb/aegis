"""Tests for the Surgical Prophylaxis API ViewSet."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.authentication.models import User, UserRole
from apps.surgical_prophylaxis.models import (
    SurgicalCase, ProphylaxisEvaluation, ProphylaxisMedication,
    ProcedureCategory,
)


class SurgicalAPITestBase(TestCase):
    """Base class with user fixtures and helper methods."""

    @classmethod
    def setUpTestData(cls):
        cls.pharmacist = User.objects.create_user(
            username='pharm_sp', email='pharm_sp@test.com', password='testpass123',
            role=UserRole.ASP_PHARMACIST,
        )
        cls.physician = User.objects.create_user(
            username='doc_sp', email='doc_sp@test.com', password='testpass123',
            role=UserRole.PHYSICIAN,
        )
        cls.admin = User.objects.create_user(
            username='admin_sp', email='admin_sp@test.com', password='testpass123',
            role=UserRole.ADMIN,
        )
        cls.pharm_token = Token.objects.create(user=cls.pharmacist)
        cls.doc_token = Token.objects.create(user=cls.physician)
        cls.admin_token = Token.objects.create(user=cls.admin)

    def setUp(self):
        self.client = APIClient()

    def auth_as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def create_case(self, **overrides):
        defaults = {
            'case_id': f'CASE-{SurgicalCase.objects.count() + 1}',
            'patient_mrn': 'MRN001',
            'patient_name': 'Test Patient',
            'procedure_description': 'Appendectomy',
            'procedure_category': ProcedureCategory.GASTROINTESTINAL_UPPER,
            'scheduled_or_time': timezone.now() + timedelta(hours=2),
        }
        defaults.update(overrides)
        return SurgicalCase.objects.create(**defaults)


class CaseListTests(SurgicalAPITestBase):
    """GET /api/v1/surgical/cases/ tests."""

    def test_list_requires_auth(self):
        response = self.client.get('/api/v1/surgical/cases/')
        self.assertIn(response.status_code, [401, 403])

    def test_list_returns_cases(self):
        self.create_case(case_id='C1')
        self.create_case(case_id='C2', patient_mrn='MRN002')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/surgical/cases/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_list_uses_lightweight_serializer(self):
        self.create_case()
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/surgical/cases/')
        result = response.data['results'][0]
        self.assertNotIn('latest_evaluation', result)
        self.assertNotIn('medications', result)
        self.assertIn('procedure_description', result)
        self.assertIn('procedure_category', result)

    def test_filter_by_procedure_category(self):
        self.create_case(case_id='C1', procedure_category=ProcedureCategory.CARDIAC)
        self.create_case(case_id='C2', procedure_category=ProcedureCategory.ORTHOPEDIC)
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/surgical/cases/',
                                   {'procedure_category': 'cardiac'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_patient_mrn_icontains(self):
        self.create_case(case_id='C1', patient_mrn='MRN12345')
        self.create_case(case_id='C2', patient_mrn='MRN99999')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/surgical/cases/',
                                   {'patient_mrn': '123'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_date_range(self):
        self.create_case(
            case_id='C1',
            scheduled_or_time=timezone.now() - timedelta(days=60),
        )
        self.create_case(
            case_id='C2',
            scheduled_or_time=timezone.now() + timedelta(hours=2),
        )
        self.auth_as(self.doc_token)
        after = (timezone.now() - timedelta(days=7)).isoformat()
        response = self.client.get('/api/v1/surgical/cases/',
                                   {'scheduled_after': after})
        self.assertEqual(response.data['count'], 1)

    def test_pagination(self):
        for i in range(55):
            self.create_case(case_id=f'C{i}')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/surgical/cases/')
        self.assertEqual(len(response.data['results']), 50)
        self.assertIsNotNone(response.data['next'])


class CaseDetailTests(SurgicalAPITestBase):
    """GET /api/v1/surgical/cases/{uuid}/ tests."""

    def test_detail_returns_full_data(self):
        case = self.create_case()
        ProphylaxisEvaluation.objects.create(
            case=case, bundle_compliant=True, compliance_score=100.0,
            elements_met=7, elements_total=7,
        )
        ProphylaxisMedication.objects.create(
            case=case, medication_type='administration',
            medication_name='Cefazolin', dose_mg=1000.0,
            route='IV', event_time=timezone.now(),
        )
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/surgical/cases/{case.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('latest_evaluation', response.data)
        self.assertIn('medications', response.data)
        self.assertTrue(response.data['latest_evaluation']['bundle_compliant'])
        self.assertEqual(len(response.data['medications']), 1)
        self.assertEqual(response.data['medications'][0]['medication_name'], 'Cefazolin')

    def test_detail_no_evaluation(self):
        case = self.create_case()
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/surgical/cases/{case.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['latest_evaluation'])

    def test_404_for_nonexistent(self):
        self.auth_as(self.doc_token)
        response = self.client.get(
            '/api/v1/surgical/cases/00000000-0000-0000-0000-000000000000/'
        )
        self.assertEqual(response.status_code, 404)

    def test_all_roles_can_read(self):
        case = self.create_case()
        for token in [self.doc_token, self.pharm_token, self.admin_token]:
            self.auth_as(token)
            response = self.client.get(f'/api/v1/surgical/cases/{case.id}/')
            self.assertEqual(response.status_code, 200)


class CaseStatsTests(SurgicalAPITestBase):
    """GET /api/v1/surgical/cases/stats/ tests."""

    def test_stats_returns_aggregates(self):
        case1 = self.create_case(case_id='C1', procedure_category=ProcedureCategory.CARDIAC)
        case2 = self.create_case(case_id='C2', procedure_category=ProcedureCategory.ORTHOPEDIC)
        ProphylaxisEvaluation.objects.create(
            case=case1, bundle_compliant=True, compliance_score=100.0,
            elements_met=7, elements_total=7,
        )
        ProphylaxisEvaluation.objects.create(
            case=case2, bundle_compliant=False, compliance_score=57.0,
            elements_met=4, elements_total=7,
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/surgical/cases/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_cases'], 2)
        self.assertIn('compliance_rate', response.data)
        self.assertIn('by_category', response.data)

    def test_stats_respects_days_param(self):
        old = self.create_case(case_id='C-OLD')
        old.created_at = timezone.now() - timedelta(days=60)
        old.save(update_fields=['created_at'])
        self.create_case(case_id='C-NEW')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/surgical/cases/stats/', {'days': 7})
        self.assertEqual(response.data['total_cases'], 1)

    def test_stats_excluded_cases(self):
        case = self.create_case()
        ProphylaxisEvaluation.objects.create(
            case=case, excluded=True, exclusion_reason='Emergency surgery',
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/surgical/cases/stats/')
        self.assertEqual(response.data['excluded_cases'], 1)

    def test_no_write_endpoints(self):
        """Surgical API is read-only."""
        case = self.create_case()
        self.auth_as(self.pharm_token)
        response = self.client.post(f'/api/v1/surgical/cases/{case.id}/submit_review/',
                                    {}, format='json')
        self.assertEqual(response.status_code, 404)
