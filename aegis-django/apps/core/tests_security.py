"""Security audit tests for AEGIS API."""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.authentication.models import User, UserRole
from apps.alerts.models import Alert, AlertType, AlertSeverity
from apps.api.exceptions import _scrub_phi_fields


class APIAuthRequiredTests(TestCase):
    """All API v1 endpoints must require authentication (return 401/403 for anonymous)."""

    def setUp(self):
        self.client = APIClient()

    def _assert_auth_required(self, url):
        response = self.client.get(url)
        self.assertIn(
            response.status_code, [401, 403],
            f'{url} returned {response.status_code}, expected 401 or 403',
        )

    def test_alerts_list_requires_auth(self):
        self._assert_auth_required('/api/v1/alerts/')

    def test_hai_candidates_requires_auth(self):
        self._assert_auth_required('/api/v1/hai/candidates/')

    def test_outbreak_clusters_requires_auth(self):
        self._assert_auth_required('/api/v1/outbreaks/clusters/')

    def test_guideline_episodes_requires_auth(self):
        self._assert_auth_required('/api/v1/guidelines/episodes/')

    def test_surgical_cases_requires_auth(self):
        self._assert_auth_required('/api/v1/surgical/cases/')

    def test_indication_candidates_requires_auth(self):
        self._assert_auth_required('/api/v1/indications/candidates/')

    def test_nhsn_events_requires_auth(self):
        self._assert_auth_required('/api/v1/nhsn/events/')

    def test_nhsn_denominators_requires_auth(self):
        self._assert_auth_required('/api/v1/nhsn/denominators/')

    def test_nhsn_au_summaries_requires_auth(self):
        self._assert_auth_required('/api/v1/nhsn/au-summaries/')

    def test_nhsn_ar_summaries_requires_auth(self):
        self._assert_auth_required('/api/v1/nhsn/ar-summaries/')

    def test_nhsn_stats_requires_auth(self):
        self._assert_auth_required('/api/v1/nhsn/stats/')

    def test_auth_me_requires_auth(self):
        self._assert_auth_required('/api/v1/auth/me/')

    def test_api_root_requires_auth(self):
        self._assert_auth_required('/api/v1/')

    def test_post_alerts_requires_auth(self):
        response = self.client.post('/api/v1/alerts/', {})
        self.assertIn(response.status_code, [401, 403, 405])


class TokenAuthTests(TestCase):
    """Verify token-based authentication works for API endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='token_user', email='token@test.com',
            password='testpass123', role=UserRole.PHYSICIAN,
        )
        cls.token = Token.objects.create(user=cls.user)

    def test_token_auth_allows_access(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        response = client.get('/api/v1/alerts/')
        self.assertEqual(response.status_code, 200)

    def test_invalid_token_denied(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token invalid-token-xyz')
        response = client.get('/api/v1/alerts/')
        self.assertIn(response.status_code, [401, 403])

    def test_token_auth_on_me_endpoint(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        response = client.get('/api/v1/auth/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'token_user')


class ObtainTokenEndpointTests(TestCase):
    """Test the token obtain endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='auth_user', email='auth@test.com',
            password='testpass123', role=UserRole.PHYSICIAN,
        )

    def test_obtain_token_with_valid_credentials(self):
        client = APIClient()
        response = client.post('/api/v1/auth/token/', {
            'username': 'auth_user',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)

    def test_obtain_token_with_invalid_password(self):
        client = APIClient()
        response = client.post('/api/v1/auth/token/', {
            'username': 'auth_user',
            'password': 'wrong',
        })
        self.assertIn(response.status_code, [400, 401])


class PHISafetyTests(TestCase):
    """Verify that PHI is scrubbed from API error responses."""

    def test_scrub_phi_removes_patient_mrn(self):
        data = {
            'patient_mrn': ['Enter a valid MRN: MRN-12345'],
            'title': ['This field is required.'],
        }
        _scrub_phi_fields(data)
        self.assertEqual(data['patient_mrn'], ['This field has an error.'])
        self.assertEqual(data['title'], ['This field is required.'])

    def test_scrub_phi_removes_patient_name(self):
        data = {'patient_name': ['John Doe is too long.']}
        _scrub_phi_fields(data)
        self.assertEqual(data['patient_name'], ['This field has an error.'])

    def test_scrub_phi_removes_patient_id(self):
        data = {'patient_id': ['Invalid format.']}
        _scrub_phi_fields(data)
        self.assertEqual(data['patient_id'], ['This field has an error.'])

    def test_scrub_phi_removes_patient_location(self):
        data = {'patient_location': ['Unknown unit.']}
        _scrub_phi_fields(data)
        self.assertEqual(data['patient_location'], ['This field has an error.'])

    def test_scrub_phi_case_insensitive(self):
        data = {'PATIENT_MRN': ['Error'], 'Patient_Name': ['Error']}
        _scrub_phi_fields(data)
        self.assertEqual(data['PATIENT_MRN'], ['This field has an error.'])
        self.assertEqual(data['Patient_Name'], ['This field has an error.'])

    def test_non_phi_fields_preserved(self):
        data = {
            'alert_type': ['Invalid choice.'],
            'severity': ['This field is required.'],
            'source_module': ['Max length exceeded.'],
        }
        _scrub_phi_fields(data)
        self.assertEqual(data['alert_type'], ['Invalid choice.'])
        self.assertEqual(data['severity'], ['This field is required.'])
        self.assertEqual(data['source_module'], ['Max length exceeded.'])


class APIResponseSecurityTests(TestCase):
    """Test that API responses don't leak PHI in errors."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='sec_admin', email='sec@test.com',
            password='testpass123', role=UserRole.ADMIN,
        )
        cls.token = Token.objects.create(user=cls.user)
        cls.alert = Alert.objects.create(
            alert_type=AlertType.CLABSI,
            source_module='hai_detection',
            source_id='sec-1',
            title='Security test', summary='Test',
            patient_mrn='SECRET-MRN-123',
            patient_name='Secret Patient',
        )

    def test_alert_detail_does_not_return_404_body_with_phi(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        response = client.get('/api/v1/alerts/00000000-0000-0000-0000-000000000000/')
        self.assertEqual(response.status_code, 404)
        body = str(response.data)
        self.assertNotIn('SECRET-MRN-123', body)
        self.assertNotIn('Secret Patient', body)


class RBACEndpointTests(TestCase):
    """Role-based access control on write endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.physician = User.objects.create_user(
            username='rbac_doc', email='rbac_doc@test.com',
            password='testpass123', role=UserRole.PHYSICIAN,
        )
        cls.doc_token = Token.objects.create(user=cls.physician)
        cls.ip_user = User.objects.create_user(
            username='rbac_ip', email='rbac_ip@test.com',
            password='testpass123', role=UserRole.INFECTION_PREVENTIONIST,
        )
        cls.ip_token = Token.objects.create(user=cls.ip_user)
        cls.alert = Alert.objects.create(
            alert_type=AlertType.CLABSI,
            source_module='hai_detection',
            source_id='rbac-1',
            title='RBAC test alert', summary='Test',
        )

    def test_physician_cannot_acknowledge_alert(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.doc_token.key}')
        response = client.post(f'/api/v1/alerts/{self.alert.id}/acknowledge/')
        self.assertEqual(response.status_code, 403)

    def test_ip_can_acknowledge_alert(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.ip_token.key}')
        response = client.post(f'/api/v1/alerts/{self.alert.id}/acknowledge/')
        self.assertEqual(response.status_code, 200)

    def test_physician_cannot_resolve_alert(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.doc_token.key}')
        response = client.post(f'/api/v1/alerts/{self.alert.id}/resolve/', {
            'reason': 'accepted',
        })
        self.assertEqual(response.status_code, 403)
