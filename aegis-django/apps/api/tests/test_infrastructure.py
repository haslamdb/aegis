"""Tests for AEGIS API infrastructure: throttling, exceptions, Swagger."""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.authentication.models import User, UserRole
from apps.api.exceptions import phi_safe_exception_handler, _scrub_phi_fields


class ExceptionHandlerTests(TestCase):
    """PHI-safe exception handler tests."""

    def test_scrubs_phi_fields_from_dict(self):
        data = {
            'patient_mrn': ['This field is required.'],
            'patient_name': ['Too long.'],
            'title': ['This field is required.'],
        }
        _scrub_phi_fields(data)
        self.assertEqual(data['patient_mrn'], ['This field has an error.'])
        self.assertEqual(data['patient_name'], ['This field has an error.'])
        # Non-PHI field should be untouched
        self.assertEqual(data['title'], ['This field is required.'])

    def test_scrub_is_case_insensitive(self):
        data = {'Patient_MRN': ['Error']}
        _scrub_phi_fields(data)
        self.assertEqual(data['Patient_MRN'], ['This field has an error.'])

    def test_scrub_handles_non_dict(self):
        # Should not raise
        _scrub_phi_fields(['not', 'a', 'dict'])
        _scrub_phi_fields(None)


class ThrottleConfigTests(TestCase):
    """Verify throttle rates are configured in settings."""

    def test_throttle_rates_configured(self):
        from django.conf import settings
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        self.assertIn('read', rates)
        self.assertIn('write', rates)
        self.assertEqual(rates['read'], '100/min')
        self.assertEqual(rates['write'], '30/min')


class SwaggerUITests(TestCase):
    """Verify API documentation endpoints are accessible."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='testuser', email='test@test.com', password='testpass123',
            role=UserRole.PHYSICIAN,
        )
        cls.token = Token.objects.create(user=cls.user)

    def test_schema_endpoint_returns_200(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        response = client.get('/api/schema/')
        self.assertEqual(response.status_code, 200)

    def test_docs_endpoint_returns_200(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        response = client.get('/api/docs/')
        self.assertEqual(response.status_code, 200)

    def test_v1_root_returns_200(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        response = client.get('/api/v1/')
        self.assertEqual(response.status_code, 200)

    def test_anonymous_gets_401(self):
        client = APIClient()
        response = client.get('/api/v1/')
        self.assertIn(response.status_code, [401, 403])
