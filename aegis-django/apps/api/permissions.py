"""
DRF permission classes for AEGIS API.

Each class delegates to the corresponding User.can_manage_*() method,
keeping authorization logic in one place.
"""

from rest_framework.permissions import BasePermission


class IsPhysicianOrHigher(BasePermission):
    """Any authenticated AEGIS user (all 4 roles can read)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class CanEditAlerts(BasePermission):
    """ASP Pharmacist, Infection Preventionist, or Admin."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.can_edit_alerts()


class CanManageHAIDetection(BasePermission):
    """Infection Preventionist or Admin."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.can_manage_hai_detection()


class CanManageOutbreakDetection(BasePermission):
    """Infection Preventionist or Admin."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.can_manage_outbreak_detection()


class CanManageSurgicalProphylaxis(BasePermission):
    """ASP Pharmacist or Admin."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.can_manage_surgical_prophylaxis()


class CanManageGuidelineAdherence(BasePermission):
    """ASP Pharmacist or Admin."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.can_manage_guideline_adherence()


class CanManageNHSNReporting(BasePermission):
    """Infection Preventionist or Admin."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.can_manage_nhsn_reporting()
