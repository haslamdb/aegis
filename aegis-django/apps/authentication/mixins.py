"""
View mixins for role-based and permission-based access control.

Use with Django class-based views.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.shortcuts import redirect

from .models import UserRole


class RoleRequiredMixin(LoginRequiredMixin):
    """
    Mixin to require specific role(s) for a class-based view.

    Usage:
        class MyView(RoleRequiredMixin, View):
            required_roles = [UserRole.ASP_PHARMACIST, UserRole.ADMIN]
    """
    required_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if request.user.role not in self.required_roles:
            messages.error(
                request,
                f"Access denied. This page requires one of the following roles: "
                f"{', '.join([UserRole(r).label for r in self.required_roles])}"
            )
            raise PermissionDenied(
                f"User role '{request.user.get_role_display()}' is not authorized."
            )

        return super().dispatch(request, *args, **kwargs)


class ASPPharmacistRequiredMixin(RoleRequiredMixin):
    """
    Mixin to require ASP Pharmacist role.

    Usage:
        class MyView(ASPPharmacistRequiredMixin, View):
            ...
    """
    required_roles = [UserRole.ASP_PHARMACIST, UserRole.ADMIN]


class InfectionPreventionistRequiredMixin(RoleRequiredMixin):
    """
    Mixin to require Infection Preventionist role.

    Usage:
        class MyView(InfectionPreventionistRequiredMixin, View):
            ...
    """
    required_roles = [UserRole.INFECTION_PREVENTIONIST, UserRole.ADMIN]


class PhysicianOrHigherRequiredMixin(RoleRequiredMixin):
    """
    Mixin to require at least Physician role (all authenticated users).

    Usage:
        class MyView(PhysicianOrHigherRequiredMixin, View):
            ...
    """
    required_roles = [
        UserRole.PHYSICIAN,
        UserRole.ASP_PHARMACIST,
        UserRole.INFECTION_PREVENTIONIST,
        UserRole.ADMIN
    ]


class AdminRequiredMixin(RoleRequiredMixin):
    """
    Mixin to require Administrator role.

    Usage:
        class MyView(AdminRequiredMixin, View):
            ...
    """
    required_roles = [UserRole.ADMIN]


class PermissionRequiredMixin(LoginRequiredMixin):
    """
    Mixin to require a specific permission.

    Usage:
        class MyView(PermissionRequiredMixin, View):
            required_permission = 'dosing_verification.view_alerts'
    """
    required_permission = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not self.required_permission:
            raise ValueError("required_permission must be set")

        # Check if user's role has this permission
        from .models import RolePermission

        has_permission = RolePermission.objects.filter(
            role=request.user.role,
            permission__codename=self.required_permission
        ).exists()

        if not has_permission:
            messages.error(
                request,
                f"Access denied. This action requires permission: {self.required_permission}"
            )
            raise PermissionDenied(
                f"User lacks required permission: {self.required_permission}"
            )

        return super().dispatch(request, *args, **kwargs)


class CanManageABXApprovalsMixin(LoginRequiredMixin):
    """
    Mixin to check if user can manage ABX approvals.

    Usage:
        class MyView(CanManageABXApprovalsMixin, View):
            ...
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not request.user.can_manage_abx_approvals():
            messages.error(
                request,
                "Access denied. This page requires ABX approval management permissions."
            )
            raise PermissionDenied("User cannot manage ABX approvals")

        return super().dispatch(request, *args, **kwargs)


class CanManageDosingMixin(LoginRequiredMixin):
    """
    Mixin to check if user can manage dosing verification.

    Usage:
        class MyView(CanManageDosingMixin, View):
            ...
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not request.user.can_manage_dosing():
            messages.error(
                request,
                "Access denied. This page requires dosing verification management permissions."
            )
            raise PermissionDenied("User cannot manage dosing verification")

        return super().dispatch(request, *args, **kwargs)


class CanManageHAIDetectionMixin(LoginRequiredMixin):
    """
    Mixin to check if user can manage HAI detection.

    Usage:
        class MyView(CanManageHAIDetectionMixin, View):
            ...
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not request.user.can_manage_hai_detection():
            messages.error(
                request,
                "Access denied. This page requires HAI detection management permissions."
            )
            raise PermissionDenied("User cannot manage HAI detection")

        return super().dispatch(request, *args, **kwargs)


class CanEditAlertsMixin(LoginRequiredMixin):
    """
    Mixin to check if user can acknowledge/resolve alerts.

    Usage:
        class MyView(CanEditAlertsMixin, View):
            ...
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not request.user.can_edit_alerts():
            messages.error(
                request,
                "Access denied. You do not have permission to edit alerts."
            )
            raise PermissionDenied("User cannot edit alerts")

        return super().dispatch(request, *args, **kwargs)


class AccountNotLockedMixin(LoginRequiredMixin):
    """
    Mixin to check if user account is not locked.

    Usage:
        class MyView(AccountNotLockedMixin, View):
            ...
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if request.user.is_account_locked():
            messages.error(
                request,
                f"Your account is locked until {request.user.account_locked_until.strftime('%Y-%m-%d %H:%M')}. "
                "Please contact an administrator."
            )
            return redirect('login')

        return super().dispatch(request, *args, **kwargs)
