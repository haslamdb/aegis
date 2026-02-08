"""
Authentication models for AEGIS Django.

Implements:
- Custom User model with 4-role RBAC
- Role-based permissions
- User session tracking for HIPAA audit compliance
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class UserRole(models.TextChoices):
    """
    Four-role RBAC system for AEGIS.

    - ASP_PHARMACIST: Full access to antimicrobial stewardship functions
    - INFECTION_PREVENTIONIST: Full access to HAI detection and outbreak surveillance
    - PHYSICIAN: Read-only access, can view alerts and dashboards
    - ADMIN: System administration, user management
    """
    ASP_PHARMACIST = 'asp_pharmacist', _('ASP Pharmacist')
    INFECTION_PREVENTIONIST = 'infection_preventionist', _('Infection Preventionist')
    PHYSICIAN = 'physician', _('Physician')
    ADMIN = 'admin', _('Administrator')


class UserManager(BaseUserManager):
    """Custom user manager for AEGIS User model."""

    def create_user(self, username, email=None, password=None, **extra_fields):
        """Create and return a regular user."""
        if not username:
            raise ValueError('The Username field must be set')

        email = self.normalize_email(email) if email else None
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """Create and return a superuser with admin role."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom User model for AEGIS with RBAC.

    Extends Django's AbstractUser with:
    - Role-based access control (4 roles)
    - Department/location tracking
    - SSO integration fields
    - HIPAA audit fields
    """

    # Core identification
    # username, email, first_name, last_name inherited from AbstractUser

    # Role-based access control
    role = models.CharField(
        max_length=50,
        choices=UserRole.choices,
        default=UserRole.PHYSICIAN,
        help_text="User's primary role in AEGIS system"
    )

    # Organization fields
    department = models.CharField(
        max_length=255,
        blank=True,
        help_text="Department (e.g., 'Pharmacy', 'Infection Control')"
    )

    job_title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Job title (e.g., 'Clinical Pharmacist', 'Physician')"
    )

    location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Primary work location"
    )

    # SSO integration fields
    sso_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text="SSO provider's unique user ID (SAML NameID or LDAP DN)"
    )

    ldap_dn = models.CharField(
        max_length=500,
        blank=True,
        help_text="LDAP Distinguished Name"
    )

    ad_groups = models.JSONField(
        default=list,
        blank=True,
        help_text="Active Directory groups (synced from LDAP)"
    )

    # Audit fields
    last_login_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of last login"
    )

    failed_login_attempts = models.IntegerField(
        default=0,
        help_text="Count of consecutive failed login attempts"
    )

    account_locked_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Account locked until this time (after failed login attempts)"
    )

    # Preferences
    email_notifications_enabled = models.BooleanField(
        default=True,
        help_text="Receive email notifications for alerts"
    )

    teams_notifications_enabled = models.BooleanField(
        default=True,
        help_text="Receive Microsoft Teams notifications"
    )

    objects = UserManager()

    class Meta:
        db_table = 'auth_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['username']
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['sso_id']),
            models.Index(fields=['department']),
        ]

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return self.role == role

    def is_asp_pharmacist(self) -> bool:
        """Check if user is an ASP Pharmacist."""
        return self.role == UserRole.ASP_PHARMACIST

    def is_infection_preventionist(self) -> bool:
        """Check if user is an Infection Preventionist."""
        return self.role == UserRole.INFECTION_PREVENTIONIST

    def is_physician(self) -> bool:
        """Check if user is a Physician."""
        return self.role == UserRole.PHYSICIAN

    def is_admin_role(self) -> bool:
        """Check if user is an Administrator."""
        return self.role == UserRole.ADMIN

    def can_manage_abx_approvals(self) -> bool:
        """Check if user can manage antibiotic approvals."""
        return self.role in [UserRole.ASP_PHARMACIST, UserRole.ADMIN]

    def can_manage_dosing(self) -> bool:
        """Check if user can manage dosing verification."""
        return self.role in [UserRole.ASP_PHARMACIST, UserRole.ADMIN]

    def can_manage_hai_detection(self) -> bool:
        """Check if user can manage HAI detection."""
        return self.role in [UserRole.INFECTION_PREVENTIONIST, UserRole.ADMIN]

    def can_manage_outbreak_detection(self) -> bool:
        """Check if user can manage outbreak detection."""
        return self.role in [UserRole.INFECTION_PREVENTIONIST, UserRole.ADMIN]

    def can_edit_alerts(self) -> bool:
        """Check if user can acknowledge/resolve alerts."""
        return self.role in [
            UserRole.ASP_PHARMACIST,
            UserRole.INFECTION_PREVENTIONIST,
            UserRole.ADMIN
        ]

    def is_account_locked(self) -> bool:
        """Check if account is currently locked."""
        if not self.account_locked_until:
            return False
        return timezone.now() < self.account_locked_until

    def increment_failed_login(self):
        """Increment failed login counter and lock account if threshold reached."""
        self.failed_login_attempts += 1

        # Lock account after 5 failed attempts for 30 minutes
        if self.failed_login_attempts >= 5:
            self.account_locked_until = timezone.now() + timezone.timedelta(minutes=30)

        self.save(update_fields=['failed_login_attempts', 'account_locked_until'])

    def reset_failed_login(self):
        """Reset failed login counter on successful login."""
        if self.failed_login_attempts > 0 or self.account_locked_until:
            self.failed_login_attempts = 0
            self.account_locked_until = None
            self.save(update_fields=['failed_login_attempts', 'account_locked_until'])


class UserSession(TimeStampedModel):
    """
    Track user sessions for HIPAA audit compliance.

    Logs:
    - Who logged in (user)
    - When (login_time, logout_time)
    - From where (ip_address, user_agent)
    - Session duration
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sessions',
        help_text="User who created this session"
    )

    session_key = models.CharField(
        max_length=40,
        unique=True,
        help_text="Django session key"
    )

    ip_address = models.GenericIPAddressField(
        help_text="IP address of the client"
    )

    user_agent = models.TextField(
        blank=True,
        help_text="Browser user agent string"
    )

    login_method = models.CharField(
        max_length=50,
        choices=[
            ('saml', 'SAML SSO'),
            ('ldap', 'LDAP'),
            ('local', 'Local Password'),
        ],
        default='saml',
        help_text="Authentication method used"
    )

    login_time = models.DateTimeField(
        auto_now_add=True,
        help_text="When the user logged in"
    )

    logout_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user logged out (null if still active)"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this session is currently active"
    )

    class Meta:
        db_table = 'user_sessions'
        verbose_name = 'User Session'
        verbose_name_plural = 'User Sessions'
        ordering = ['-login_time']
        indexes = [
            models.Index(fields=['user', '-login_time']),
            models.Index(fields=['session_key']),
            models.Index(fields=['is_active', '-login_time']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.login_time.strftime('%Y-%m-%d %H:%M:%S')}"

    @property
    def duration(self):
        """Calculate session duration."""
        if self.logout_time:
            return self.logout_time - self.login_time
        return timezone.now() - self.login_time

    def end_session(self):
        """Mark session as ended."""
        self.logout_time = timezone.now()
        self.is_active = False
        self.save(update_fields=['logout_time', 'is_active'])


class Permission(models.Model):
    """
    Module-level permissions for fine-grained access control.

    Permissions can be assigned to roles or individual users.
    Examples:
    - 'dosing_verification.view_alerts'
    - 'hai_detection.manage_clabsi'
    - 'abx_approvals.approve_requests'
    """

    codename = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique permission identifier (e.g., 'dosing_verification.view_alerts')"
    )

    name = models.CharField(
        max_length=255,
        help_text="Human-readable permission name"
    )

    description = models.TextField(
        blank=True,
        help_text="Detailed description of what this permission allows"
    )

    module = models.CharField(
        max_length=100,
        help_text="AEGIS module this permission belongs to"
    )

    class Meta:
        db_table = 'auth_permissions'
        verbose_name = 'Permission'
        verbose_name_plural = 'Permissions'
        ordering = ['module', 'codename']
        indexes = [
            models.Index(fields=['module']),
            models.Index(fields=['codename']),
        ]

    def __str__(self):
        return f"{self.name} ({self.codename})"


class RolePermission(models.Model):
    """
    Maps roles to permissions.

    Defines which permissions are granted to each role.
    """

    role = models.CharField(
        max_length=50,
        choices=UserRole.choices,
        help_text="User role"
    )

    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name='role_permissions',
        help_text="Permission granted to this role"
    )

    class Meta:
        db_table = 'role_permissions'
        unique_together = ['role', 'permission']
        verbose_name = 'Role Permission'
        verbose_name_plural = 'Role Permissions'
        ordering = ['role', 'permission']

    def __str__(self):
        return f"{self.get_role_display()} - {self.permission.codename}"
