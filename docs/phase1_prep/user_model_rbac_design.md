# User Model & RBAC Design for AEGIS

**Purpose:** Define the User model and Role-Based Access Control (RBAC) for AEGIS Django application.

---

## User Model Design

### Base User Model (extends AbstractUser)

```python
# apps/authentication/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

class UserRole(models.TextChoices):
    """User roles in AEGIS system."""
    ASP_PHARMACIST = 'asp_pharmacist', _('ASP Pharmacist')
    INFECTION_PREVENTIONIST = 'infection_preventionist', _('Infection Preventionist')
    PHYSICIAN = 'physician', _('Physician')
    ADMIN = 'admin', _('Administrator')


class User(AbstractUser):
    """
    Custom User model for AEGIS.
    Extends Django's AbstractUser with AEGIS-specific fields.
    """

    # Role-based access control
    role = models.CharField(
        max_length=50,
        choices=UserRole.choices,
        default=UserRole.PHYSICIAN,
        help_text=_('User role determines access permissions')
    )

    # Cincinnati Children's employee data
    employee_id = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        help_text=_('Cincinnati Children\'s employee ID')
    )

    department = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('Department or unit')
    )

    # Contact information
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text=_('Work phone number')
    )

    pager = models.CharField(
        max_length=20,
        blank=True,
        help_text=_('Pager number')
    )

    # SSO integration
    ldap_dn = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('LDAP Distinguished Name')
    )

    saml_nameid = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text=_('SAML NameID')
    )

    # Preferences
    notification_email = models.EmailField(
        blank=True,
        help_text=_('Email for AEGIS notifications (if different from primary)')
    )

    receive_sms = models.BooleanField(
        default=False,
        help_text=_('Receive SMS notifications')
    )

    receive_teams = models.BooleanField(
        default=True,
        help_text=_('Receive Microsoft Teams notifications')
    )

    # Audit fields
    last_login_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text=_('IP address of last login')
    )

    failed_login_attempts = models.PositiveIntegerField(
        default=0,
        help_text=_('Number of failed login attempts')
    )

    account_locked_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Account locked until this time (brute force protection)')
    )

    # Timestamps (inherited from AbstractUser)
    # date_joined, last_login

    class Meta:
        db_table = 'users'
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['role']),
            models.Index(fields=['department']),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    def get_full_name(self):
        """Return first_name + last_name, or username if names not set."""
        full_name = super().get_full_name()
        return full_name if full_name else self.username

    @property
    def is_asp_pharmacist(self):
        """Check if user is an ASP pharmacist."""
        return self.role == UserRole.ASP_PHARMACIST

    @property
    def is_infection_preventionist(self):
        """Check if user is an infection preventionist."""
        return self.role == UserRole.INFECTION_PREVENTIONIST

    @property
    def is_physician(self):
        """Check if user is a physician."""
        return self.role == UserRole.PHYSICIAN

    @property
    def is_admin_user(self):
        """Check if user is an administrator."""
        return self.role == UserRole.ADMIN or self.is_superuser

    def has_module_access(self, module_name):
        """Check if user has access to a specific module."""
        from apps.authentication.permissions import ModulePermissions
        return ModulePermissions.can_access(self, module_name)

    def can_modify_alerts(self):
        """Check if user can modify (acknowledge, resolve) alerts."""
        return self.role in [
            UserRole.ASP_PHARMACIST,
            UserRole.INFECTION_PREVENTIONIST,
            UserRole.ADMIN,
        ]

    def can_view_phi(self):
        """Check if user can view Protected Health Information."""
        # All authenticated users can view PHI (they're hospital staff)
        return self.is_active

    def is_account_locked(self):
        """Check if account is currently locked due to failed login attempts."""
        if not self.account_locked_until:
            return False
        from django.utils import timezone
        return timezone.now() < self.account_locked_until
```

---

## Role-Based Access Control (RBAC)

### Role Permissions Matrix

| Module | ASP Pharmacist | Infection Preventionist | Physician | Admin |
|--------|----------------|-------------------------|-----------|-------|
| **HAI Detection** | View | Full Access | View | Full Access |
| **ABX Approvals** | Full Access | View | View | Full Access |
| **Dosing Verification** | Full Access | View | View | Full Access |
| **Guideline Adherence** | Full Access | View | View | Full Access |
| **Drug-Bug Mismatch** | Full Access | View | View | Full Access |
| **MDRO Surveillance** | View | Full Access | View | Full Access |
| **Surgical Prophylaxis** | Full Access | View | View | Full Access |
| **NHSN Reporting** | View | Full Access | View | Full Access |
| **Outbreak Detection** | View | Full Access | View | Full Access |
| **Action Analytics** | View | View | View | Full Access |
| **ASP Metrics** | Full Access | View | View | Full Access |
| **Alert Management** | Modify | Modify | View Only | Modify |
| **User Management** | No Access | No Access | No Access | Full Access |

**Legend:**
- **View:** Read-only access
- **Full Access:** Read, create, update, delete
- **Modify:** Can acknowledge, resolve, add notes to alerts

### Permission Model

```python
# apps/authentication/models.py

class ModuleAccess(models.TextChoices):
    """Module access levels."""
    NO_ACCESS = 'none', _('No Access')
    VIEW = 'view', _('View Only')
    MODIFY = 'modify', _('Modify')
    FULL = 'full', _('Full Access')


class ModulePermission(models.Model):
    """
    Custom per-module permissions for users or roles.
    Allows override of default role-based permissions.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='module_permissions',
        null=True,
        blank=True,
        help_text=_('User (if user-specific override)')
    )

    role = models.CharField(
        max_length=50,
        choices=UserRole.choices,
        null=True,
        blank=True,
        help_text=_('Role (if role-wide permission)')
    )

    module = models.CharField(
        max_length=100,
        help_text=_('Module name (e.g., hai_detection, abx_approvals)')
    )

    access_level = models.CharField(
        max_length=20,
        choices=ModuleAccess.choices,
        default=ModuleAccess.VIEW,
    )

    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='permissions_granted',
        help_text=_('Admin who granted this permission')
    )

    granted_at = models.DateTimeField(auto_now_add=True)

    notes = models.TextField(
        blank=True,
        help_text=_('Reason for permission override')
    )

    class Meta:
        db_table = 'module_permissions'
        unique_together = [
            ('user', 'module'),  # One permission per user per module
            ('role', 'module'),  # One permission per role per module
        ]
        indexes = [
            models.Index(fields=['user', 'module']),
            models.Index(fields=['role', 'module']),
        ]

    def __str__(self):
        target = self.user if self.user else f"Role: {self.get_role_display()}"
        return f"{target} - {self.module}: {self.get_access_level_display()}"
```

---

## Permission Helpers

### Module Permissions Helper

```python
# apps/authentication/permissions.py

from django.core.cache import cache
from apps.authentication.models import User, UserRole, ModuleAccess, ModulePermission


class ModulePermissions:
    """Helper class for checking module permissions."""

    # Default permissions per role per module
    DEFAULT_PERMISSIONS = {
        UserRole.ASP_PHARMACIST: {
            'hai_detection': ModuleAccess.VIEW,
            'abx_approvals': ModuleAccess.FULL,
            'dosing_verification': ModuleAccess.FULL,
            'guideline_adherence': ModuleAccess.FULL,
            'drug_bug_mismatch': ModuleAccess.FULL,
            'mdro_surveillance': ModuleAccess.VIEW,
            'surgical_prophylaxis': ModuleAccess.FULL,
            'nhsn_reporting': ModuleAccess.VIEW,
            'outbreak_detection': ModuleAccess.VIEW,
            'action_analytics': ModuleAccess.VIEW,
            'asp_metrics': ModuleAccess.FULL,
        },
        UserRole.INFECTION_PREVENTIONIST: {
            'hai_detection': ModuleAccess.FULL,
            'abx_approvals': ModuleAccess.VIEW,
            'dosing_verification': ModuleAccess.VIEW,
            'guideline_adherence': ModuleAccess.VIEW,
            'drug_bug_mismatch': ModuleAccess.VIEW,
            'mdro_surveillance': ModuleAccess.FULL,
            'surgical_prophylaxis': ModuleAccess.VIEW,
            'nhsn_reporting': ModuleAccess.FULL,
            'outbreak_detection': ModuleAccess.FULL,
            'action_analytics': ModuleAccess.VIEW,
            'asp_metrics': ModuleAccess.VIEW,
        },
        UserRole.PHYSICIAN: {
            'hai_detection': ModuleAccess.VIEW,
            'abx_approvals': ModuleAccess.VIEW,
            'dosing_verification': ModuleAccess.VIEW,
            'guideline_adherence': ModuleAccess.VIEW,
            'drug_bug_mismatch': ModuleAccess.VIEW,
            'mdro_surveillance': ModuleAccess.VIEW,
            'surgical_prophylaxis': ModuleAccess.VIEW,
            'nhsn_reporting': ModuleAccess.VIEW,
            'outbreak_detection': ModuleAccess.VIEW,
            'action_analytics': ModuleAccess.VIEW,
            'asp_metrics': ModuleAccess.VIEW,
        },
        UserRole.ADMIN: {
            # Admins have full access to all modules
            'hai_detection': ModuleAccess.FULL,
            'abx_approvals': ModuleAccess.FULL,
            'dosing_verification': ModuleAccess.FULL,
            'guideline_adherence': ModuleAccess.FULL,
            'drug_bug_mismatch': ModuleAccess.FULL,
            'mdro_surveillance': ModuleAccess.FULL,
            'surgical_prophylaxis': ModuleAccess.FULL,
            'nhsn_reporting': ModuleAccess.FULL,
            'outbreak_detection': ModuleAccess.FULL,
            'action_analytics': ModuleAccess.FULL,
            'asp_metrics': ModuleAccess.FULL,
        },
    }

    @classmethod
    def get_access_level(cls, user: User, module: str) -> str:
        """Get user's access level for a module."""
        if user.is_superuser:
            return ModuleAccess.FULL

        # Check cache first
        cache_key = f'user_perm_{user.id}_{module}'
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Check for user-specific override
        user_perm = ModulePermission.objects.filter(
            user=user,
            module=module
        ).first()

        if user_perm:
            access = user_perm.access_level
        else:
            # Check for role-based override
            role_perm = ModulePermission.objects.filter(
                role=user.role,
                module=module
            ).first()

            if role_perm:
                access = role_perm.access_level
            else:
                # Use default permissions
                role_perms = cls.DEFAULT_PERMISSIONS.get(user.role, {})
                access = role_perms.get(module, ModuleAccess.NO_ACCESS)

        # Cache for 5 minutes
        cache.set(cache_key, access, 300)
        return access

    @classmethod
    def can_access(cls, user: User, module: str) -> bool:
        """Check if user can access module at all."""
        access = cls.get_access_level(user, module)
        return access != ModuleAccess.NO_ACCESS

    @classmethod
    def can_view(cls, user: User, module: str) -> bool:
        """Check if user can view module."""
        access = cls.get_access_level(user, module)
        return access in [ModuleAccess.VIEW, ModuleAccess.MODIFY, ModuleAccess.FULL]

    @classmethod
    def can_modify(cls, user: User, module: str) -> bool:
        """Check if user can modify data in module."""
        access = cls.get_access_level(user, module)
        return access in [ModuleAccess.MODIFY, ModuleAccess.FULL]

    @classmethod
    def has_full_access(cls, user: User, module: str) -> bool:
        """Check if user has full access to module."""
        access = cls.get_access_level(user, module)
        return access == ModuleAccess.FULL
```

---

## Permission Decorators

### View Decorators

```python
# apps/authentication/decorators.py

from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from apps.authentication.permissions import ModulePermissions


def role_required(*roles):
    """Decorator to require specific role(s)."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request, *args, **kwargs):
            if request.user.role not in roles and not request.user.is_superuser:
                raise PermissionDenied("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def module_access_required(module, access_level='view'):
    """Decorator to require module access."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request, *args, **kwargs):
            if access_level == 'view':
                has_access = ModulePermissions.can_view(request.user, module)
            elif access_level == 'modify':
                has_access = ModulePermissions.can_modify(request.user, module)
            elif access_level == 'full':
                has_access = ModulePermissions.has_full_access(request.user, module)
            else:
                has_access = ModulePermissions.can_access(request.user, module)

            if not has_access:
                raise PermissionDenied(f"You do not have {access_level} access to this module.")

            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


# Example usage:
# @role_required(UserRole.ASP_PHARMACIST, UserRole.ADMIN)
# def abx_approval_view(request):
#     ...
#
# @module_access_required('hai_detection', access_level='modify')
# def update_hai_case(request, case_id):
#     ...
```

---

## DRF Permission Classes

### REST API Permissions

```python
# apps/api/permissions.py

from rest_framework import permissions
from apps.authentication.permissions import ModulePermissions


class IsASPPharmacist(permissions.BasePermission):
    """Permission class for ASP Pharmacists."""
    def has_permission(self, request, view):
        return request.user.is_asp_pharmacist or request.user.is_admin_user


class IsInfectionPreventionist(permissions.BasePermission):
    """Permission class for Infection Preventionists."""
    def has_permission(self, request, view):
        return request.user.is_infection_preventionist or request.user.is_admin_user


class HasModuleAccess(permissions.BasePermission):
    """
    Permission class to check module access.
    Views must define `module_name` attribute.
    """
    def has_permission(self, request, view):
        module = getattr(view, 'module_name', None)
        if not module:
            return False

        # GET/HEAD/OPTIONS = view access
        if request.method in permissions.SAFE_METHODS:
            return ModulePermissions.can_view(request.user, module)

        # POST/PUT/PATCH/DELETE = modify/full access
        return ModulePermissions.can_modify(request.user, module)


class CanModifyAlerts(permissions.BasePermission):
    """Permission to modify alerts."""
    def has_permission(self, request, view):
        return request.user.can_modify_alerts()


# Example DRF ViewSet:
# class AlertViewSet(viewsets.ModelViewSet):
#     module_name = 'alerts'
#     permission_classes = [IsAuthenticated, HasModuleAccess]
#     ...
```

---

## LDAP Group Mapping

### Active Directory to Django Role Mapping

```python
# apps/authentication/backends.py

LDAP_ROLE_MAPPING = {
    # AD Group Name → Django UserRole
    'CN=AEGIS_ASP_Pharmacists,OU=Groups,DC=cchmc,DC=org': UserRole.ASP_PHARMACIST,
    'CN=AEGIS_Infection_Preventionists,OU=Groups,DC=cchmc,DC=org': UserRole.INFECTION_PREVENTIONIST,
    'CN=AEGIS_Physicians,OU=Groups,DC=cchmc,DC=org': UserRole.PHYSICIAN,
    'CN=AEGIS_Admins,OU=Groups,DC=cchmc,DC=org': UserRole.ADMIN,
}


def map_ldap_groups_to_role(ldap_groups):
    """Map LDAP groups to Django role."""
    for group_dn in ldap_groups:
        if group_dn in LDAP_ROLE_MAPPING:
            return LDAP_ROLE_MAPPING[group_dn]

    # Default to physician if no matching group
    return UserRole.PHYSICIAN
```

---

## Database Migrations

### Initial Migration

```python
# Generated migration file
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                # All fields from User model above
            ],
            options={
                'db_table': 'users',
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
                'ordering': ['last_name', 'first_name'],
            },
            bases=('auth.abstractuser',),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['employee_id'], name='users_employ_idx'),
        ),
        # ... more indexes
    ]
```

---

## Admin Interface

### User Admin

```python
# apps/authentication/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from apps.authentication.models import User, ModulePermission


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom User admin."""

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'pager')}),
        ('AEGIS info', {'fields': ('role', 'employee_id', 'department')}),
        ('SSO', {'fields': ('ldap_dn', 'saml_nameid')}),
        ('Notifications', {'fields': ('notification_email', 'receive_sms', 'receive_teams')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Security', {'fields': ('last_login_ip', 'failed_login_attempts', 'account_locked_until')}),
    )

    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'department', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active', 'department')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'employee_id')
    ordering = ('last_name', 'first_name')


@admin.register(ModulePermission)
class ModulePermissionAdmin(admin.ModelAdmin):
    """Module Permission admin."""

    list_display = ('get_target', 'module', 'access_level', 'granted_by', 'granted_at')
    list_filter = ('access_level', 'module', 'role')
    search_fields = ('user__username', 'user__email', 'module')

    def get_target(self, obj):
        return obj.user if obj.user else f"Role: {obj.get_role_display()}"
    get_target.short_description = 'Target'
```

---

## Testing

### Permission Tests

```python
# apps/authentication/tests/test_permissions.py

from django.test import TestCase
from apps.authentication.models import User, UserRole
from apps.authentication.permissions import ModulePermissions


class PermissionTests(TestCase):
    def setUp(self):
        self.asp_user = User.objects.create_user(
            username='asp1',
            role=UserRole.ASP_PHARMACIST
        )
        self.ip_user = User.objects.create_user(
            username='ip1',
            role=UserRole.INFECTION_PREVENTIONIST
        )
        self.physician = User.objects.create_user(
            username='doc1',
            role=UserRole.PHYSICIAN
        )

    def test_asp_pharmacist_abx_approval_access(self):
        """ASP pharmacist should have full access to ABX approvals."""
        self.assertTrue(
            ModulePermissions.has_full_access(self.asp_user, 'abx_approvals')
        )

    def test_physician_read_only_access(self):
        """Physician should have view-only access."""
        self.assertTrue(
            ModulePermissions.can_view(self.physician, 'hai_detection')
        )
        self.assertFalse(
            ModulePermissions.can_modify(self.physician, 'hai_detection')
        )

    def test_ip_hai_detection_access(self):
        """IP should have full access to HAI detection."""
        self.assertTrue(
            ModulePermissions.has_full_access(self.ip_user, 'hai_detection')
        )
```

---

## Summary

**User Model:**
- Extends Django AbstractUser
- 4 roles: ASP Pharmacist, Infection Preventionist, Physician, Admin
- Cincinnati Children's employee fields (employee_id, department)
- SSO integration fields (ldap_dn, saml_nameid)
- Notification preferences
- Audit fields (last_login_ip, failed_login_attempts)

**RBAC:**
- Role-based default permissions
- User/role-specific permission overrides
- Module-level access control (none, view, modify, full)
- Permission caching for performance
- View decorators and DRF permission classes

**Next Steps:**
1. Implement User model in Django
2. Create migrations
3. Test RBAC permissions
4. Integrate with LDAP/SAML backends

---

**Last Updated:** 2026-02-07
**Author:** Django Architect
