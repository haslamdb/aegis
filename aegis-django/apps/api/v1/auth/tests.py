"""Tests for the Auth API."""

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.authentication.models import User, UserRole


class AuthAPITestBase(TestCase):
    """Base class with user fixtures."""

    @classmethod
    def setUpTestData(cls):
        cls.pharmacist = User.objects.create_user(
            username='pharm', email='pharm@test.com', password='testpass123',
            role=UserRole.ASP_PHARMACIST,
            department='Pharmacy', job_title='Clinical Pharmacist',
        )
        cls.physician = User.objects.create_user(
            username='doc', email='doc@test.com', password='testpass123',
            role=UserRole.PHYSICIAN,
        )
        cls.pharm_token = Token.objects.create(user=cls.pharmacist)
        cls.doc_token = Token.objects.create(user=cls.physician)

    def setUp(self):
        self.client = APIClient()

    def auth_as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')


class CurrentUserGetTests(AuthAPITestBase):
    """GET /api/v1/auth/me/"""

    def test_requires_auth(self):
        response = self.client.get('/api/v1/auth/me/')
        self.assertIn(response.status_code, [401, 403])

    def test_returns_profile(self):
        self.auth_as(self.pharm_token)
        response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'pharm')
        self.assertEqual(response.data['role'], 'asp_pharmacist')
        self.assertEqual(response.data['department'], 'Pharmacy')
        self.assertEqual(response.data['job_title'], 'Clinical Pharmacist')
        self.assertIn('email_notifications_enabled', response.data)
        self.assertIn('teams_notifications_enabled', response.data)

    def test_physician_can_view_profile(self):
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'doc')


class CurrentUserPatchTests(AuthAPITestBase):
    """PATCH /api/v1/auth/me/"""

    def test_update_email_notifications(self):
        self.auth_as(self.pharm_token)
        response = self.client.patch(
            '/api/v1/auth/me/',
            {'email_notifications_enabled': False},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['email_notifications_enabled'])
        self.pharmacist.refresh_from_db()
        self.assertFalse(self.pharmacist.email_notifications_enabled)

    def test_update_teams_notifications(self):
        self.auth_as(self.doc_token)
        response = self.client.patch(
            '/api/v1/auth/me/',
            {'teams_notifications_enabled': False},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['teams_notifications_enabled'])

    def test_update_both_prefs(self):
        self.auth_as(self.pharm_token)
        response = self.client.patch(
            '/api/v1/auth/me/',
            {'email_notifications_enabled': False, 'teams_notifications_enabled': False},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['email_notifications_enabled'])
        self.assertFalse(response.data['teams_notifications_enabled'])

    def test_empty_patch_is_ok(self):
        self.auth_as(self.pharm_token)
        response = self.client.patch('/api/v1/auth/me/', {}, format='json')
        self.assertEqual(response.status_code, 200)


class ObtainTokenTests(AuthAPITestBase):
    """POST /api/v1/auth/token/"""

    def test_obtain_token(self):
        response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'pharm', 'password': 'testpass123'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        self.assertEqual(response.data['username'], 'pharm')
        self.assertEqual(response.data['role'], 'asp_pharmacist')

    def test_token_rotates(self):
        old_key = self.pharm_token.key
        response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'pharm', 'password': 'testpass123'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        new_key = response.data['token']
        self.assertNotEqual(old_key, new_key)
        # Old token no longer valid
        self.assertEqual(Token.objects.filter(user=self.pharmacist).count(), 1)

    def test_invalid_credentials(self):
        response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'pharm', 'password': 'wrongpassword'},
            format='json',
        )
        self.assertEqual(response.status_code, 401)

    def test_missing_fields(self):
        response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'pharm'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_no_body(self):
        response = self.client.post('/api/v1/auth/token/', {}, format='json')
        self.assertEqual(response.status_code, 400)
