"""Tests for AEGIS API permission classes."""

from django.test import TestCase, RequestFactory
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.authentication.models import User, UserRole
from apps.api.permissions import (
    IsPhysicianOrHigher,
    CanEditAlerts,
    CanManageHAIDetection,
    CanManageOutbreakDetection,
    CanManageSurgicalProphylaxis,
    CanManageGuidelineAdherence,
    CanManageNHSNReporting,
)


class PermissionTestBase(TestCase):
    """Base class with user fixtures for all 4 roles."""

    @classmethod
    def setUpTestData(cls):
        cls.pharmacist = User.objects.create_user(
            username='pharm', email='pharm@test.com', password='testpass123',
            role=UserRole.ASP_PHARMACIST,
        )
        cls.ip_user = User.objects.create_user(
            username='ipuser', email='ip@test.com', password='testpass123',
            role=UserRole.INFECTION_PREVENTIONIST,
        )
        cls.physician = User.objects.create_user(
            username='doc', email='doc@test.com', password='testpass123',
            role=UserRole.PHYSICIAN,
        )
        cls.admin = User.objects.create_user(
            username='admin_user', email='admin@test.com', password='testpass123',
            role=UserRole.ADMIN,
        )
        cls.factory = APIRequestFactory()

    def _make_request(self, user=None):
        request = self.factory.get('/api/v1/test/')
        request.user = user
        return request


class IsPhysicianOrHigherTests(PermissionTestBase):
    """All 4 roles should pass; anonymous should not."""

    def test_allows_pharmacist(self):
        perm = IsPhysicianOrHigher()
        self.assertTrue(perm.has_permission(self._make_request(self.pharmacist), None))

    def test_allows_ip(self):
        perm = IsPhysicianOrHigher()
        self.assertTrue(perm.has_permission(self._make_request(self.ip_user), None))

    def test_allows_physician(self):
        perm = IsPhysicianOrHigher()
        self.assertTrue(perm.has_permission(self._make_request(self.physician), None))

    def test_allows_admin(self):
        perm = IsPhysicianOrHigher()
        self.assertTrue(perm.has_permission(self._make_request(self.admin), None))

    def test_denies_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        perm = IsPhysicianOrHigher()
        request = self._make_request()
        request.user = AnonymousUser()
        self.assertFalse(perm.has_permission(request, None))


class CanEditAlertsTests(PermissionTestBase):
    """Pharmacist, IP, Admin can edit; Physician cannot."""

    def test_allows_pharmacist(self):
        perm = CanEditAlerts()
        self.assertTrue(perm.has_permission(self._make_request(self.pharmacist), None))

    def test_allows_ip(self):
        perm = CanEditAlerts()
        self.assertTrue(perm.has_permission(self._make_request(self.ip_user), None))

    def test_allows_admin(self):
        perm = CanEditAlerts()
        self.assertTrue(perm.has_permission(self._make_request(self.admin), None))

    def test_denies_physician(self):
        perm = CanEditAlerts()
        self.assertFalse(perm.has_permission(self._make_request(self.physician), None))


class CanManageHAIDetectionTests(PermissionTestBase):
    """IP and Admin can manage; Pharmacist and Physician cannot."""

    def test_allows_ip(self):
        perm = CanManageHAIDetection()
        self.assertTrue(perm.has_permission(self._make_request(self.ip_user), None))

    def test_allows_admin(self):
        perm = CanManageHAIDetection()
        self.assertTrue(perm.has_permission(self._make_request(self.admin), None))

    def test_denies_pharmacist(self):
        perm = CanManageHAIDetection()
        self.assertFalse(perm.has_permission(self._make_request(self.pharmacist), None))

    def test_denies_physician(self):
        perm = CanManageHAIDetection()
        self.assertFalse(perm.has_permission(self._make_request(self.physician), None))


class CanManageOutbreakDetectionTests(PermissionTestBase):
    """IP and Admin can manage."""

    def test_allows_ip(self):
        perm = CanManageOutbreakDetection()
        self.assertTrue(perm.has_permission(self._make_request(self.ip_user), None))

    def test_allows_admin(self):
        perm = CanManageOutbreakDetection()
        self.assertTrue(perm.has_permission(self._make_request(self.admin), None))

    def test_denies_pharmacist(self):
        perm = CanManageOutbreakDetection()
        self.assertFalse(perm.has_permission(self._make_request(self.pharmacist), None))


class CanManageSurgicalProphylaxisTests(PermissionTestBase):
    """Pharmacist and Admin can manage."""

    def test_allows_pharmacist(self):
        perm = CanManageSurgicalProphylaxis()
        self.assertTrue(perm.has_permission(self._make_request(self.pharmacist), None))

    def test_allows_admin(self):
        perm = CanManageSurgicalProphylaxis()
        self.assertTrue(perm.has_permission(self._make_request(self.admin), None))

    def test_denies_ip(self):
        perm = CanManageSurgicalProphylaxis()
        self.assertFalse(perm.has_permission(self._make_request(self.ip_user), None))


class CanManageGuidelineAdherenceTests(PermissionTestBase):
    """Pharmacist and Admin can manage."""

    def test_allows_pharmacist(self):
        perm = CanManageGuidelineAdherence()
        self.assertTrue(perm.has_permission(self._make_request(self.pharmacist), None))

    def test_allows_admin(self):
        perm = CanManageGuidelineAdherence()
        self.assertTrue(perm.has_permission(self._make_request(self.admin), None))

    def test_denies_physician(self):
        perm = CanManageGuidelineAdherence()
        self.assertFalse(perm.has_permission(self._make_request(self.physician), None))


class CanManageNHSNReportingTests(PermissionTestBase):
    """IP and Admin can manage."""

    def test_allows_ip(self):
        perm = CanManageNHSNReporting()
        self.assertTrue(perm.has_permission(self._make_request(self.ip_user), None))

    def test_allows_admin(self):
        perm = CanManageNHSNReporting()
        self.assertTrue(perm.has_permission(self._make_request(self.admin), None))

    def test_denies_pharmacist(self):
        perm = CanManageNHSNReporting()
        self.assertFalse(perm.has_permission(self._make_request(self.pharmacist), None))
