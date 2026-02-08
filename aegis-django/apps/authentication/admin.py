"""
Django admin interface for authentication models.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils import timezone

from .models import User, UserRole, UserSession, Permission, RolePermission


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin interface for User model."""

    list_display = [
        'username',
        'email',
        'full_name',
        'role_badge',
        'department',
        'is_active',
        'is_staff',
        'last_login',
        'account_status'
    ]

    list_filter = [
        'role',
        'is_active',
        'is_staff',
        'is_superuser',
        'department',
    ]

    search_fields = [
        'username',
        'email',
        'first_name',
        'last_name',
        'sso_id',
        'department',
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('username', 'password', 'email', 'first_name', 'last_name')
        }),
        ('Role & Permissions', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Organization', {
            'fields': ('department', 'job_title', 'location')
        }),
        ('SSO Integration', {
            'fields': ('sso_id', 'ldap_dn', 'ad_groups'),
            'classes': ('collapse',)
        }),
        ('Security & Audit', {
            'fields': (
                'last_login',
                'last_login_ip',
                'failed_login_attempts',
                'account_locked_until',
                'date_joined'
            ),
            'classes': ('collapse',)
        }),
        ('Notifications', {
            'fields': ('email_notifications_enabled', 'teams_notifications_enabled'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'role'),
        }),
    )

    ordering = ['-date_joined']
    filter_horizontal = ('groups', 'user_permissions')

    def full_name(self, obj):
        """Display full name."""
        return obj.get_full_name() or '-'
    full_name.short_description = 'Full Name'

    def role_badge(self, obj):
        """Display role as colored badge."""
        colors = {
            UserRole.ASP_PHARMACIST: '#28a745',
            UserRole.INFECTION_PREVENTIONIST: '#007bff',
            UserRole.PHYSICIAN: '#6c757d',
            UserRole.ADMIN: '#dc3545',
        }
        color = colors.get(obj.role, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_role_display()
        )
    role_badge.short_description = 'Role'

    def account_status(self, obj):
        """Display account status."""
        if obj.is_account_locked():
            return format_html(
                '<span style="color: red;">🔒 Locked until {}</span>',
                obj.account_locked_until.strftime('%Y-%m-%d %H:%M')
            )
        elif obj.failed_login_attempts > 0:
            return format_html(
                '<span style="color: orange;">⚠️ {} failed attempts</span>',
                obj.failed_login_attempts
            )
        return format_html('<span style="color: green;">✓ Active</span>')
    account_status.short_description = 'Status'

    def login_method(self, obj):
        """Display login method from most recent session."""
        session = obj.sessions.filter(is_active=True).first()
        if session:
            return session.get_login_method_display()
        return '-'
    login_method.short_description = 'Login Method'


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    """Admin interface for UserSession model."""

    list_display = [
        'user',
        'login_method',
        'login_time',
        'logout_time',
        'duration_display',
        'ip_address',
        'is_active'
    ]

    list_filter = [
        'login_method',
        'is_active',
        'login_time',
    ]

    search_fields = [
        'user__username',
        'user__email',
        'ip_address',
        'session_key',
    ]

    readonly_fields = [
        'user',
        'session_key',
        'ip_address',
        'user_agent',
        'login_method',
        'login_time',
        'logout_time',
        'duration_display',
    ]

    date_hierarchy = 'login_time'
    ordering = ['-login_time']

    def duration_display(self, obj):
        """Display session duration."""
        duration = obj.duration
        hours = duration.total_seconds() // 3600
        minutes = (duration.total_seconds() % 3600) // 60
        return f"{int(hours)}h {int(minutes)}m"
    duration_display.short_description = 'Duration'

    def has_add_permission(self, request):
        """Disable manual creation of sessions."""
        return False

    def has_change_permission(self, request, obj=None):
        """Make sessions read-only."""
        return False


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """Admin interface for Permission model."""

    list_display = [
        'name',
        'codename',
        'module',
        'assigned_roles',
    ]

    list_filter = ['module']

    search_fields = [
        'name',
        'codename',
        'module',
        'description',
    ]

    ordering = ['module', 'codename']

    def assigned_roles(self, obj):
        """Display which roles have this permission."""
        role_perms = obj.role_permissions.all()
        if not role_perms:
            return '-'

        roles = [rp.get_role_display() for rp in role_perms]
        return ', '.join(roles)
    assigned_roles.short_description = 'Assigned to Roles'


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    """Admin interface for RolePermission model."""

    list_display = [
        'role_display',
        'permission_name',
        'permission_module',
    ]

    list_filter = ['role', 'permission__module']

    search_fields = [
        'permission__name',
        'permission__codename',
    ]

    ordering = ['role', 'permission__module', 'permission__codename']

    def role_display(self, obj):
        """Display role name."""
        return obj.get_role_display()
    role_display.short_description = 'Role'

    def permission_name(self, obj):
        """Display permission name."""
        return obj.permission.name
    permission_name.short_description = 'Permission'

    def permission_module(self, obj):
        """Display permission module."""
        return obj.permission.module
    permission_module.short_description = 'Module'
