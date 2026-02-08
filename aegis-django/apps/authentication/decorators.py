"""
Permission decorators for AEGIS Django.

Provides decorators for role-based and permission-based access control.
"""

from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages

from .models import UserRole


def role_required(*roles):
    """
    Decorator to require specific role(s) for a view.

    Usage:
        @role_required(UserRole.ASP_PHARMACIST)
        def view(request):
            ...

        @role_required(UserRole.ASP_PHARMACIST, UserRole.ADMIN)
        def view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request, *args, **kwargs):
            if request.user.role not in roles:
                messages.error(
                    request,
                    f"Access denied. This page requires one of the following roles: "
                    f"{', '.join([UserRole(r).label for r in roles])}"
                )
                raise PermissionDenied(
                    f"User role '{request.user.get_role_display()}' is not authorized. "
                    f"Required: {', '.join([UserRole(r).label for r in roles])}"
                )
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def asp_pharmacist_required(view_func):
    """
    Decorator to require ASP Pharmacist role.

    Usage:
        @asp_pharmacist_required
        def view(request):
            ...
    """
    return role_required(UserRole.ASP_PHARMACIST, UserRole.ADMIN)(view_func)


def infection_preventionist_required(view_func):
    """
    Decorator to require Infection Preventionist role.

    Usage:
        @infection_preventionist_required
        def view(request):
            ...
    """
    return role_required(UserRole.INFECTION_PREVENTIONIST, UserRole.ADMIN)(view_func)


def physician_or_higher_required(view_func):
    """
    Decorator to require at least Physician role (all authenticated users).

    Usage:
        @physician_or_higher_required
        def view(request):
            ...
    """
    return role_required(
        UserRole.PHYSICIAN,
        UserRole.ASP_PHARMACIST,
        UserRole.INFECTION_PREVENTIONIST,
        UserRole.ADMIN
    )(view_func)


def admin_required(view_func):
    """
    Decorator to require Administrator role.

    Usage:
        @admin_required
        def view(request):
            ...
    """
    return role_required(UserRole.ADMIN)(view_func)


def permission_required(permission_codename):
    """
    Decorator to require a specific permission.

    Usage:
        @permission_required('dosing_verification.view_alerts')
        def view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request, *args, **kwargs):
            # Check if user's role has this permission
            from .models import RolePermission

            has_permission = RolePermission.objects.filter(
                role=request.user.role,
                permission__codename=permission_codename
            ).exists()

            if not has_permission:
                messages.error(
                    request,
                    f"Access denied. This action requires permission: {permission_codename}"
                )
                raise PermissionDenied(
                    f"User lacks required permission: {permission_codename}"
                )

            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def can_manage_abx_approvals(view_func):
    """
    Decorator to check if user can manage ABX approvals.

    Usage:
        @can_manage_abx_approvals
        def view(request):
            ...
    """
    @wraps(view_func)
    @login_required
    def wrapped_view(request, *args, **kwargs):
        if not request.user.can_manage_abx_approvals():
            messages.error(
                request,
                "Access denied. This page requires ABX approval management permissions."
            )
            raise PermissionDenied("User cannot manage ABX approvals")
        return view_func(request, *args, **kwargs)
    return wrapped_view


def can_manage_dosing(view_func):
    """
    Decorator to check if user can manage dosing verification.

    Usage:
        @can_manage_dosing
        def view(request):
            ...
    """
    @wraps(view_func)
    @login_required
    def wrapped_view(request, *args, **kwargs):
        if not request.user.can_manage_dosing():
            messages.error(
                request,
                "Access denied. This page requires dosing verification management permissions."
            )
            raise PermissionDenied("User cannot manage dosing verification")
        return view_func(request, *args, **kwargs)
    return wrapped_view


def can_manage_hai_detection(view_func):
    """
    Decorator to check if user can manage HAI detection.

    Usage:
        @can_manage_hai_detection
        def view(request):
            ...
    """
    @wraps(view_func)
    @login_required
    def wrapped_view(request, *args, **kwargs):
        if not request.user.can_manage_hai_detection():
            messages.error(
                request,
                "Access denied. This page requires HAI detection management permissions."
            )
            raise PermissionDenied("User cannot manage HAI detection")
        return view_func(request, *args, **kwargs)
    return wrapped_view


def can_edit_alerts(view_func):
    """
    Decorator to check if user can acknowledge/resolve alerts.

    Usage:
        @can_edit_alerts
        def view(request):
            ...
    """
    @wraps(view_func)
    @login_required
    def wrapped_view(request, *args, **kwargs):
        if not request.user.can_edit_alerts():
            messages.error(
                request,
                "Access denied. You do not have permission to edit alerts."
            )
            raise PermissionDenied("User cannot edit alerts")
        return view_func(request, *args, **kwargs)
    return wrapped_view


def account_not_locked(view_func):
    """
    Decorator to check if user account is not locked.

    Usage:
        @account_not_locked
        def view(request):
            ...
    """
    @wraps(view_func)
    @login_required
    def wrapped_view(request, *args, **kwargs):
        if request.user.is_account_locked():
            messages.error(
                request,
                f"Your account is locked until {request.user.account_locked_until.strftime('%Y-%m-%d %H:%M')}. "
                "Please contact an administrator."
            )
            return redirect('authentication:login')
        return view_func(request, *args, **kwargs)
    return wrapped_view
