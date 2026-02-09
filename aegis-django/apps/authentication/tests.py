"""
Tests for Authentication models, managers, and decorators.

Tests cover:
- UserRole enum values
- UserManager.create_user() and create_superuser()
- Role check methods
- Permission methods (can_manage_*)
- Account locking (is_account_locked, increment/reset_failed_login)
- UserSession model (duration, end_session)
- All decorators using RequestFactory
- __str__ methods
"""

from datetime import timedelta

from django.test import TestCase, RequestFactory
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse

from .models import User, UserRole, UserSession, Permission, RolePermission
from .decorators import (
    role_required,
    asp_pharmacist_required,
    infection_preventionist_required,
    physician_or_higher_required,
    admin_required,
    permission_required,
    can_manage_abx_approvals,
    can_manage_dosing,
    can_manage_hai_detection,
    can_manage_outbreak_detection,
    can_manage_surgical_prophylaxis,
    can_manage_guideline_adherence,
    can_manage_nhsn_reporting,
    can_edit_alerts,
    account_not_locked,
)


def _make_user(role, username=None, **kwargs):
    """Helper to create a user with a given role."""
    if username is None:
        username = f'user_{role}'
    return User.objects.create_user(
        username=username,
        email=f'{username}@test.com',
        password='testpass123',
        role=role,
        **kwargs,
    )


# =============================================================================
# UserRole Enum Tests
# =============================================================================


class UserRoleTests(TestCase):
    """Test UserRole enum values and labels."""

    def test_four_roles_exist(self):
        self.assertEqual(len(UserRole.choices), 4)

    def test_asp_pharmacist_value(self):
        self.assertEqual(UserRole.ASP_PHARMACIST, 'asp_pharmacist')

    def test_infection_preventionist_value(self):
        self.assertEqual(UserRole.INFECTION_PREVENTIONIST, 'infection_preventionist')

    def test_physician_value(self):
        self.assertEqual(UserRole.PHYSICIAN, 'physician')

    def test_admin_value(self):
        self.assertEqual(UserRole.ADMIN, 'admin')

    def test_labels(self):
        self.assertEqual(UserRole.ASP_PHARMACIST.label, 'ASP Pharmacist')
        self.assertEqual(UserRole.INFECTION_PREVENTIONIST.label, 'Infection Preventionist')
        self.assertEqual(UserRole.PHYSICIAN.label, 'Physician')
        self.assertEqual(UserRole.ADMIN.label, 'Administrator')


# =============================================================================
# UserManager Tests
# =============================================================================


class UserManagerTests(TestCase):
    """Test UserManager.create_user() and create_superuser()."""

    def test_create_user_basic(self):
        user = User.objects.create_user(
            username='testuser', email='test@test.com', password='pass123',
        )
        self.assertEqual(user.username, 'testuser')
        self.assertEqual(user.email, 'test@test.com')
        self.assertTrue(user.check_password('pass123'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_default_role_is_physician(self):
        user = User.objects.create_user(
            username='doc', email='doc@test.com', password='pass',
        )
        self.assertEqual(user.role, UserRole.PHYSICIAN)

    def test_create_user_with_custom_role(self):
        user = User.objects.create_user(
            username='pharma', email='pharma@test.com', password='pass',
            role=UserRole.ASP_PHARMACIST,
        )
        self.assertEqual(user.role, UserRole.ASP_PHARMACIST)

    def test_create_user_normalizes_email(self):
        user = User.objects.create_user(
            username='norm', email='Test@EXAMPLE.COM', password='pass',
        )
        self.assertEqual(user.email, 'Test@example.com')

    def test_create_user_with_email(self):
        user = User.objects.create_user(
            username='withemail', email='test@example.com', password='pass',
        )
        self.assertEqual(user.email, 'test@example.com')

    def test_create_user_requires_username(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(username='', email='e@t.com', password='p')

    def test_create_superuser(self):
        su = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='adminpass',
        )
        self.assertTrue(su.is_staff)
        self.assertTrue(su.is_superuser)
        self.assertEqual(su.role, UserRole.ADMIN)

    def test_create_superuser_rejects_is_staff_false(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                username='bad', email='b@t.com', password='p', is_staff=False,
            )

    def test_create_superuser_rejects_is_superuser_false(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                username='bad2', email='b2@t.com', password='p', is_superuser=False,
            )


# =============================================================================
# User Model Tests
# =============================================================================


class UserModelTests(TestCase):
    """Test User model methods and properties."""

    def setUp(self):
        self.pharmacist = _make_user(UserRole.ASP_PHARMACIST, 'pharmacist')
        self.ip = _make_user(UserRole.INFECTION_PREVENTIONIST, 'ip_user')
        self.physician = _make_user(UserRole.PHYSICIAN, 'physician')
        self.admin = _make_user(UserRole.ADMIN, 'admin_user')

    def test_str_with_full_name(self):
        self.pharmacist.first_name = 'Jane'
        self.pharmacist.last_name = 'Doe'
        self.pharmacist.save()
        self.assertEqual(str(self.pharmacist), 'Jane Doe (ASP Pharmacist)')

    def test_str_without_full_name(self):
        self.assertEqual(str(self.physician), 'physician (Physician)')

    def test_has_role(self):
        self.assertTrue(self.pharmacist.has_role(UserRole.ASP_PHARMACIST))
        self.assertFalse(self.pharmacist.has_role(UserRole.PHYSICIAN))

    def test_is_asp_pharmacist(self):
        self.assertTrue(self.pharmacist.is_asp_pharmacist())
        self.assertFalse(self.physician.is_asp_pharmacist())

    def test_is_infection_preventionist(self):
        self.assertTrue(self.ip.is_infection_preventionist())
        self.assertFalse(self.pharmacist.is_infection_preventionist())

    def test_is_physician(self):
        self.assertTrue(self.physician.is_physician())
        self.assertFalse(self.admin.is_physician())

    def test_is_admin_role(self):
        self.assertTrue(self.admin.is_admin_role())
        self.assertFalse(self.physician.is_admin_role())

    # Permission methods
    def test_can_manage_abx_approvals(self):
        self.assertTrue(self.pharmacist.can_manage_abx_approvals())
        self.assertTrue(self.admin.can_manage_abx_approvals())
        self.assertFalse(self.physician.can_manage_abx_approvals())
        self.assertFalse(self.ip.can_manage_abx_approvals())

    def test_can_manage_dosing(self):
        self.assertTrue(self.pharmacist.can_manage_dosing())
        self.assertTrue(self.admin.can_manage_dosing())
        self.assertFalse(self.physician.can_manage_dosing())

    def test_can_manage_hai_detection(self):
        self.assertTrue(self.ip.can_manage_hai_detection())
        self.assertTrue(self.admin.can_manage_hai_detection())
        self.assertFalse(self.pharmacist.can_manage_hai_detection())
        self.assertFalse(self.physician.can_manage_hai_detection())

    def test_can_manage_outbreak_detection(self):
        self.assertTrue(self.ip.can_manage_outbreak_detection())
        self.assertTrue(self.admin.can_manage_outbreak_detection())
        self.assertFalse(self.pharmacist.can_manage_outbreak_detection())

    def test_can_manage_surgical_prophylaxis(self):
        self.assertTrue(self.pharmacist.can_manage_surgical_prophylaxis())
        self.assertTrue(self.admin.can_manage_surgical_prophylaxis())
        self.assertFalse(self.ip.can_manage_surgical_prophylaxis())

    def test_can_manage_guideline_adherence(self):
        self.assertTrue(self.pharmacist.can_manage_guideline_adherence())
        self.assertTrue(self.admin.can_manage_guideline_adherence())
        self.assertFalse(self.physician.can_manage_guideline_adherence())

    def test_can_manage_nhsn_reporting(self):
        self.assertTrue(self.ip.can_manage_nhsn_reporting())
        self.assertTrue(self.admin.can_manage_nhsn_reporting())
        self.assertFalse(self.pharmacist.can_manage_nhsn_reporting())

    def test_can_edit_alerts(self):
        self.assertTrue(self.pharmacist.can_edit_alerts())
        self.assertTrue(self.ip.can_edit_alerts())
        self.assertTrue(self.admin.can_edit_alerts())
        self.assertFalse(self.physician.can_edit_alerts())


# =============================================================================
# Account Locking Tests
# =============================================================================


class AccountLockingTests(TestCase):
    """Test account locking after failed login attempts."""

    def setUp(self):
        self.user = _make_user(UserRole.PHYSICIAN, 'locktest')

    def test_not_locked_by_default(self):
        self.assertFalse(self.user.is_account_locked())

    def test_increment_failed_login(self):
        self.user.increment_failed_login()
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 1)
        self.assertIsNone(self.user.account_locked_until)

    def test_account_locks_after_5_failures(self):
        for _ in range(5):
            self.user.increment_failed_login()
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 5)
        self.assertIsNotNone(self.user.account_locked_until)
        self.assertTrue(self.user.is_account_locked())

    def test_lock_duration_30_minutes(self):
        for _ in range(5):
            self.user.increment_failed_login()
        self.user.refresh_from_db()
        expected = timezone.now() + timedelta(minutes=30)
        self.assertAlmostEqual(
            self.user.account_locked_until, expected, delta=timedelta(seconds=5)
        )

    def test_expired_lock_not_locked(self):
        self.user.account_locked_until = timezone.now() - timedelta(minutes=1)
        self.user.save()
        self.assertFalse(self.user.is_account_locked())

    def test_reset_failed_login(self):
        for _ in range(5):
            self.user.increment_failed_login()
        self.user.reset_failed_login()
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.account_locked_until)

    def test_reset_noop_when_no_failures(self):
        """reset_failed_login is safe to call with zero failures."""
        self.user.reset_failed_login()
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)


# =============================================================================
# UserSession Tests
# =============================================================================


class UserSessionTests(TestCase):
    """Test UserSession model."""

    def setUp(self):
        self.user = _make_user(UserRole.PHYSICIAN, 'session_user')

    def _create_session(self, **kwargs):
        defaults = {
            'user': self.user,
            'session_key': 'abc123def456',
            'ip_address': '192.168.1.100',
            'user_agent': 'Mozilla/5.0',
            'login_method': 'saml',
        }
        defaults.update(kwargs)
        return UserSession.objects.create(**defaults)

    def test_create_session(self):
        session = self._create_session()
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.ip_address, '192.168.1.100')
        self.assertTrue(session.is_active)
        self.assertIsNone(session.logout_time)

    def test_str(self):
        session = self._create_session()
        s = str(session)
        self.assertIn('session_user', s)

    def test_duration_active_session(self):
        session = self._create_session()
        duration = session.duration
        self.assertGreaterEqual(duration, timedelta(seconds=0))

    def test_duration_ended_session(self):
        session = self._create_session()
        session.login_time = timezone.now() - timedelta(hours=2)
        session.logout_time = timezone.now() - timedelta(hours=1)
        session.save(update_fields=['login_time', 'logout_time'])
        session.refresh_from_db()
        self.assertAlmostEqual(
            session.duration, timedelta(hours=1), delta=timedelta(seconds=5)
        )

    def test_end_session(self):
        session = self._create_session()
        session.end_session()
        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.assertIsNotNone(session.logout_time)

    def test_login_methods(self):
        for method in ('saml', 'ldap', 'local'):
            s = self._create_session(
                session_key=f'key_{method}', login_method=method,
            )
            self.assertEqual(s.login_method, method)


# =============================================================================
# Decorator Tests (using RequestFactory)
# =============================================================================


def _dummy_view(request):
    """Simple view for decorator testing."""
    return HttpResponse('OK')


class DecoratorTestBase(TestCase):
    """Base class for decorator tests with RequestFactory."""

    def setUp(self):
        self.factory = RequestFactory()
        self.pharmacist = _make_user(UserRole.ASP_PHARMACIST, 'dec_pharma')
        self.ip = _make_user(UserRole.INFECTION_PREVENTIONIST, 'dec_ip')
        self.physician = _make_user(UserRole.PHYSICIAN, 'dec_doc')
        self.admin = _make_user(UserRole.ADMIN, 'dec_admin')

    def _get_request(self, user):
        request = self.factory.get('/test/')
        request.user = user
        # Add session and messages support for decorators that call messages.error()
        request.session = SessionStore()
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request


class RoleRequiredDecoratorTests(DecoratorTestBase):
    """Test role_required decorator."""

    def test_matching_role_allowed(self):
        view = role_required(UserRole.ASP_PHARMACIST)(_dummy_view)
        request = self._get_request(self.pharmacist)
        response = view(request)
        self.assertEqual(response.status_code, 200)

    def test_non_matching_role_denied(self):
        view = role_required(UserRole.ASP_PHARMACIST)(_dummy_view)
        request = self._get_request(self.physician)
        with self.assertRaises(PermissionDenied):
            view(request)

    def test_multiple_roles_allowed(self):
        view = role_required(UserRole.ASP_PHARMACIST, UserRole.ADMIN)(_dummy_view)
        request = self._get_request(self.admin)
        response = view(request)
        self.assertEqual(response.status_code, 200)


class ASPPharmacistRequiredTests(DecoratorTestBase):
    """Test asp_pharmacist_required decorator."""

    def test_pharmacist_allowed(self):
        view = asp_pharmacist_required(_dummy_view)
        response = view(self._get_request(self.pharmacist))
        self.assertEqual(response.status_code, 200)

    def test_admin_allowed(self):
        view = asp_pharmacist_required(_dummy_view)
        response = view(self._get_request(self.admin))
        self.assertEqual(response.status_code, 200)

    def test_physician_denied(self):
        view = asp_pharmacist_required(_dummy_view)
        with self.assertRaises(PermissionDenied):
            view(self._get_request(self.physician))


class InfectionPreventionistRequiredTests(DecoratorTestBase):
    """Test infection_preventionist_required decorator."""

    def test_ip_allowed(self):
        view = infection_preventionist_required(_dummy_view)
        response = view(self._get_request(self.ip))
        self.assertEqual(response.status_code, 200)

    def test_admin_allowed(self):
        view = infection_preventionist_required(_dummy_view)
        response = view(self._get_request(self.admin))
        self.assertEqual(response.status_code, 200)

    def test_physician_denied(self):
        view = infection_preventionist_required(_dummy_view)
        with self.assertRaises(PermissionDenied):
            view(self._get_request(self.physician))


class PhysicianOrHigherRequiredTests(DecoratorTestBase):
    """Test physician_or_higher_required — all authenticated roles pass."""

    def test_physician_allowed(self):
        view = physician_or_higher_required(_dummy_view)
        response = view(self._get_request(self.physician))
        self.assertEqual(response.status_code, 200)

    def test_pharmacist_allowed(self):
        view = physician_or_higher_required(_dummy_view)
        response = view(self._get_request(self.pharmacist))
        self.assertEqual(response.status_code, 200)

    def test_ip_allowed(self):
        view = physician_or_higher_required(_dummy_view)
        response = view(self._get_request(self.ip))
        self.assertEqual(response.status_code, 200)

    def test_admin_allowed(self):
        view = physician_or_higher_required(_dummy_view)
        response = view(self._get_request(self.admin))
        self.assertEqual(response.status_code, 200)


class AdminRequiredTests(DecoratorTestBase):
    """Test admin_required decorator."""

    def test_admin_allowed(self):
        view = admin_required(_dummy_view)
        response = view(self._get_request(self.admin))
        self.assertEqual(response.status_code, 200)

    def test_pharmacist_denied(self):
        view = admin_required(_dummy_view)
        with self.assertRaises(PermissionDenied):
            view(self._get_request(self.pharmacist))


class CanManageDecoratorsTests(DecoratorTestBase):
    """Test all can_manage_* decorators."""

    def test_can_manage_abx_approvals_pharmacist(self):
        view = can_manage_abx_approvals(_dummy_view)
        response = view(self._get_request(self.pharmacist))
        self.assertEqual(response.status_code, 200)

    def test_can_manage_abx_approvals_physician_denied(self):
        view = can_manage_abx_approvals(_dummy_view)
        with self.assertRaises(PermissionDenied):
            view(self._get_request(self.physician))

    def test_can_manage_dosing_pharmacist(self):
        view = can_manage_dosing(_dummy_view)
        response = view(self._get_request(self.pharmacist))
        self.assertEqual(response.status_code, 200)

    def test_can_manage_hai_detection_ip(self):
        view = can_manage_hai_detection(_dummy_view)
        response = view(self._get_request(self.ip))
        self.assertEqual(response.status_code, 200)

    def test_can_manage_hai_detection_pharmacist_denied(self):
        view = can_manage_hai_detection(_dummy_view)
        with self.assertRaises(PermissionDenied):
            view(self._get_request(self.pharmacist))

    def test_can_manage_outbreak_detection_ip(self):
        view = can_manage_outbreak_detection(_dummy_view)
        response = view(self._get_request(self.ip))
        self.assertEqual(response.status_code, 200)

    def test_can_manage_surgical_prophylaxis_pharmacist(self):
        view = can_manage_surgical_prophylaxis(_dummy_view)
        response = view(self._get_request(self.pharmacist))
        self.assertEqual(response.status_code, 200)

    def test_can_manage_guideline_adherence_admin(self):
        view = can_manage_guideline_adherence(_dummy_view)
        response = view(self._get_request(self.admin))
        self.assertEqual(response.status_code, 200)

    def test_can_manage_nhsn_reporting_ip(self):
        view = can_manage_nhsn_reporting(_dummy_view)
        response = view(self._get_request(self.ip))
        self.assertEqual(response.status_code, 200)

    def test_can_manage_nhsn_reporting_pharmacist_denied(self):
        view = can_manage_nhsn_reporting(_dummy_view)
        with self.assertRaises(PermissionDenied):
            view(self._get_request(self.pharmacist))

    def test_can_edit_alerts_pharmacist(self):
        view = can_edit_alerts(_dummy_view)
        response = view(self._get_request(self.pharmacist))
        self.assertEqual(response.status_code, 200)

    def test_can_edit_alerts_physician_denied(self):
        view = can_edit_alerts(_dummy_view)
        with self.assertRaises(PermissionDenied):
            view(self._get_request(self.physician))


class PermissionRequiredDecoratorTests(DecoratorTestBase):
    """Test permission_required decorator with DB permissions."""

    def test_with_permission_granted(self):
        perm = Permission.objects.create(
            codename='test.view', name='Test View', module='test',
        )
        RolePermission.objects.create(
            role=UserRole.ASP_PHARMACIST, permission=perm,
        )
        view = permission_required('test.view')(_dummy_view)
        response = view(self._get_request(self.pharmacist))
        self.assertEqual(response.status_code, 200)

    def test_without_permission_denied(self):
        view = permission_required('nonexistent.perm')(_dummy_view)
        with self.assertRaises(PermissionDenied):
            view(self._get_request(self.pharmacist))
