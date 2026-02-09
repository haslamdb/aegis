"""Tests for the NHSN Reporting API ViewSets."""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.authentication.models import User, UserRole
from apps.nhsn_reporting.models import (
    NHSNEvent, HAIEventType,
    DenominatorMonthly,
    AUMonthlySummary,
    ARQuarterlySummary,
)


class NHSNAPITestBase(TestCase):
    """Base class with user fixtures."""

    @classmethod
    def setUpTestData(cls):
        cls.ip_user = User.objects.create_user(
            username='ipuser', email='ip@test.com', password='testpass123',
            role=UserRole.INFECTION_PREVENTIONIST,
        )
        cls.pharmacist = User.objects.create_user(
            username='pharm', email='pharm@test.com', password='testpass123',
            role=UserRole.ASP_PHARMACIST,
        )
        cls.admin = User.objects.create_user(
            username='admin_user', email='admin@test.com', password='testpass123',
            role=UserRole.ADMIN,
        )
        cls.physician = User.objects.create_user(
            username='doc', email='doc@test.com', password='testpass123',
            role=UserRole.PHYSICIAN,
        )
        cls.ip_token = Token.objects.create(user=cls.ip_user)
        cls.pharm_token = Token.objects.create(user=cls.pharmacist)
        cls.admin_token = Token.objects.create(user=cls.admin)
        cls.doc_token = Token.objects.create(user=cls.physician)

    def setUp(self):
        self.client = APIClient()

    def auth_as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def create_event(self, **overrides):
        defaults = {
            'event_date': date(2026, 1, 15),
            'hai_type': HAIEventType.CLABSI,
            'location_code': 'G3-PICU',
            'pathogen_code': 'MRSA',
        }
        defaults.update(overrides)
        return NHSNEvent.objects.create(**defaults)


class NHSNEventListTests(NHSNAPITestBase):
    """GET /api/v1/nhsn/events/"""

    def test_requires_auth(self):
        response = self.client.get('/api/v1/nhsn/events/')
        self.assertIn(response.status_code, [401, 403])

    def test_pharmacist_denied(self):
        self.auth_as(self.pharm_token)
        response = self.client.get('/api/v1/nhsn/events/')
        self.assertEqual(response.status_code, 403)

    def test_physician_denied(self):
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/nhsn/events/')
        self.assertEqual(response.status_code, 403)

    def test_ip_user_can_list(self):
        self.create_event()
        self.create_event(hai_type=HAIEventType.CAUTI, pathogen_code='E. coli')
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/events/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_admin_can_list(self):
        self.create_event()
        self.auth_as(self.admin_token)
        response = self.client.get('/api/v1/nhsn/events/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_hai_type(self):
        self.create_event(hai_type=HAIEventType.CLABSI)
        self.create_event(hai_type=HAIEventType.SSI, pathogen_code='S. aureus')
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/events/', {'hai_type': 'clabsi'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_reported(self):
        self.create_event(reported=False)
        self.create_event(reported=True, pathogen_code='VRE')
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/events/', {'reported': 'true'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_location(self):
        self.create_event(location_code='G3-PICU')
        self.create_event(location_code='G6-CICU', pathogen_code='E. coli')
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/events/', {'location_code': 'G6-CICU'})
        self.assertEqual(response.data['count'], 1)


class NHSNEventDetailTests(NHSNAPITestBase):
    """GET /api/v1/nhsn/events/{uuid}/"""

    def test_detail_returns_full_data(self):
        event = self.create_event()
        self.auth_as(self.ip_token)
        response = self.client.get(f'/api/v1/nhsn/events/{event.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['hai_type'], 'clabsi')
        self.assertIn('updated_at', response.data)

    def test_404_for_nonexistent(self):
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/events/00000000-0000-0000-0000-000000000000/')
        self.assertEqual(response.status_code, 404)


class NHSNMarkSubmittedTests(NHSNAPITestBase):
    """POST /api/v1/nhsn/events/mark_submitted/"""

    def test_mark_submitted(self):
        e1 = self.create_event()
        e2 = self.create_event(hai_type=HAIEventType.CAUTI, pathogen_code='E. coli')
        self.auth_as(self.ip_token)
        response = self.client.post(
            '/api/v1/nhsn/events/mark_submitted/',
            {'event_ids': [str(e1.id), str(e2.id)]},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['marked_count'], 2)
        e1.refresh_from_db()
        self.assertTrue(e1.reported)
        self.assertIsNotNone(e1.reported_at)

    def test_mark_submitted_empty_ids(self):
        self.auth_as(self.ip_token)
        response = self.client.post(
            '/api/v1/nhsn/events/mark_submitted/',
            {'event_ids': []},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_mark_submitted_no_body(self):
        self.auth_as(self.ip_token)
        response = self.client.post(
            '/api/v1/nhsn/events/mark_submitted/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, 400)


class NHSNDenominatorTests(NHSNAPITestBase):
    """GET /api/v1/nhsn/denominators/"""

    def test_list_denominators(self):
        DenominatorMonthly.objects.create(
            month='2026-01', location_code='G3-PICU',
            patient_days=500, central_line_days=200,
        )
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/denominators/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_month(self):
        DenominatorMonthly.objects.create(month='2026-01', location_code='G3-PICU')
        DenominatorMonthly.objects.create(month='2026-02', location_code='G3-PICU')
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/denominators/', {'month': '2026-01'})
        self.assertEqual(response.data['count'], 1)


class NHSNAUSummaryTests(NHSNAPITestBase):
    """GET /api/v1/nhsn/au-summaries/"""

    def test_list_au_summaries(self):
        AUMonthlySummary.objects.create(
            reporting_month='2026-01', location_code='A6-HM',
            patient_days=300, admissions=50,
        )
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/au-summaries/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_reporting_month(self):
        AUMonthlySummary.objects.create(reporting_month='2026-01', location_code='A6-HM')
        AUMonthlySummary.objects.create(reporting_month='2026-02', location_code='A6-HM')
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/au-summaries/', {'reporting_month': '2026-01'})
        self.assertEqual(response.data['count'], 1)


class NHSNARSummaryTests(NHSNAPITestBase):
    """GET /api/v1/nhsn/ar-summaries/"""

    def test_list_ar_summaries(self):
        ARQuarterlySummary.objects.create(
            reporting_quarter='2026-Q1', location_code='G3-PICU',
        )
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/ar-summaries/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_quarter(self):
        ARQuarterlySummary.objects.create(reporting_quarter='2026-Q1', location_code='G3-PICU')
        ARQuarterlySummary.objects.create(reporting_quarter='2026-Q2', location_code='G3-PICU')
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/ar-summaries/', {'reporting_quarter': '2026-Q1'})
        self.assertEqual(response.data['count'], 1)


class NHSNStatsTests(NHSNAPITestBase):
    """GET /api/v1/nhsn/stats/"""

    def test_stats_returns_data(self):
        self.create_event(reported=False)
        self.create_event(reported=True, pathogen_code='VRE')
        self.auth_as(self.ip_token)
        response = self.client.get('/api/v1/nhsn/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_events'], 2)
        self.assertEqual(response.data['unreported_events'], 1)
        self.assertEqual(response.data['reported_events'], 1)

    def test_stats_denied_for_physician(self):
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/nhsn/stats/')
        self.assertEqual(response.status_code, 403)
