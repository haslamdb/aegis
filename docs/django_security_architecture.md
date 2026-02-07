# AEGIS Django Security Architecture
**Enterprise Healthcare Deployment - Cincinnati Children's Hospital**

**Last Updated:** 2026-02-07
**Status:** Architecture & Planning Phase
**HIPAA Compliance:** 2026 Security Rule Requirements

---

## Executive Summary

This document defines the security architecture for migrating AEGIS from Flask to Django for enterprise healthcare deployment at Cincinnati Children's Hospital. The architecture addresses:

- **Single Sign-On (SSO):** SAML 2.0 and LDAP integration with hospital Active Directory
- **Audit Logging:** Comprehensive PHI access logging for HIPAA compliance
- **Role-Based Access Control:** 4-tier permission system (asp_pharmacist, infection_preventionist, physician, admin)
- **2026 HIPAA Requirements:** Mandatory encryption at rest, MFA, and enhanced security controls
- **Cincinnati Children's IT Integration:** SSO, SIEM, network security, and compliance documentation

**Technology Stack (All Healthcare-Proven):**
- `django-saml2-auth` (Grafana fork) - SAML SSO
- `django-auth-ldap` - Active Directory integration
- `django-auditlog` - HIPAA-compliant audit logging
- `django-csp` - Content Security Policy
- `django-ratelimit` - API rate limiting
- PostgreSQL 15+ with encryption at rest
- Redis with SSL for caching/Celery

---

## Table of Contents

1. [Authentication & Single Sign-On](#1-authentication--single-sign-on)
2. [Audit Logging Architecture](#2-audit-logging-architecture)
3. [Role-Based Access Control](#3-role-based-access-control)
4. [Security Hardening](#4-security-hardening)
5. [2026 HIPAA Compliance Requirements](#5-2026-hipaa-compliance-requirements)
6. [Encryption Strategy](#6-encryption-strategy)
7. [Rate Limiting & DDoS Protection](#7-rate-limiting--ddos-protection)
8. [Cincinnati Children's IT Requirements](#8-cincinnati-childrens-it-requirements)
9. [Implementation Checklist](#9-implementation-checklist)
10. [Security Testing Plan](#10-security-testing-plan)
11. [Monitoring & Alerting](#11-monitoring--alerting)
12. [Documentation for IT Approval](#12-documentation-for-it-approval)

---

## 1. Authentication & Single Sign-On

### 1.1 SSO Architecture

**Primary Authentication Method:** SAML 2.0 SSO via hospital identity provider

**Flow:**
```
User → AEGIS Login Page → Redirect to Hospital SAML IdP (Okta/Azure AD)
       → User authenticates with hospital credentials + MFA
       → SAML assertion returned to AEGIS
       → Django creates session with user attributes
       → AEGIS grants access based on role mapping
```

### 1.2 Technology Stack

**SAML Integration: django-saml2-auth (Grafana Fork)**

**Why This Library:**
- Proven in mission-critical healthcare production environments
- Supports any SAML2-based SSO provider (Okta, Azure AD, Ping Identity, etc.)
- Handles both Identity Provider (IdP) and Service Provider (SP)-initiated SSO
- Dynamic metadata configuration
- Active maintenance by Grafana team
- Compatible with Django 1.1.4 through 6.0+

**Installation:**
```bash
pip install django-saml2-auth==3.9.0  # Or latest 3.x version
```

**LDAP Integration: django-auth-ldap**

**For Direct Active Directory Access (Fallback/Internal):**
```bash
pip install django-auth-ldap==4.7.0
```

### 1.3 SAML Configuration

**settings/production.py:**
```python
INSTALLED_APPS = [
    ...
    'django_saml2_auth',
]

# SAML SSO Configuration
SAML2_AUTH = {
    # Metadata is required, choose either remote URL or local file
    'METADATA_AUTO_CONF_URL': 'https://sso.cincinnatichildrens.org/metadata',
    # Or local file:
    # 'METADATA_LOCAL_FILE_PATH': '/etc/aegis/saml/metadata.xml',

    # Entity ID
    'ENTITY_ID': 'https://aegis.cincinnatichildrens.org/saml/metadata/',

    # Assertion Consumer Service URL
    'ASSERTION_URL': 'https://aegis.cincinnatichildrens.org/saml/acs/',

    # Default redirect after successful login
    'DEFAULT_NEXT_URL': '/',

    # Create new user on first login
    'CREATE_USER': True,

    # User attributes mapping (from SAML assertion to Django user model)
    'ATTRIBUTES_MAP': {
        'email': 'email',
        'username': 'username',
        'first_name': 'firstName',
        'last_name': 'lastName',
    },

    # Custom attributes for AEGIS user model
    'CUSTOM_ATTRIBUTES': {
        'employee_id': 'employeeID',
        'department': 'department',
        'title': 'title',
    },

    # Group/role mapping (SAML groups → Django groups)
    'GROUPS_MAP': {
        'asp_pharmacist': 'AEGIS-ASP-Pharmacist',
        'infection_preventionist': 'AEGIS-Infection-Preventionist',
        'physician': 'AEGIS-Physician',
        'admin': 'AEGIS-Admin',
    },

    # Trigger function to customize user creation
    'TRIGGER': {
        'CREATE_USER': 'apps.authentication.saml.create_aegis_user',
        'BEFORE_LOGIN': 'apps.authentication.saml.before_login_check',
    },

    # Use Django's default User model or custom user model
    'NEW_USER_PROFILE': {
        'USER_GROUPS': [],  # Groups assigned to new users
        'ACTIVE_STATUS': True,
        'STAFF_STATUS': False,  # Only admins get staff status
    },

    # Enable MFA check (verify SAML assertion includes MFA claim)
    'MFA_REQUIRED': True,
    'MFA_ATTRIBUTE': 'AuthnContextClassRef',  # SAML attribute for MFA confirmation
    'MFA_REQUIRED_VALUES': [
        'urn:oasis:names:tc:SAML:2.0:ac:classes:MFA',
        'urn:oasis:names:tc:SAML:2.0:ac:classes:TimeSyncToken',
    ],
}

# Authentication backends (order matters)
AUTHENTICATION_BACKENDS = [
    'django_saml2_auth.backends.Saml2Backend',  # SAML SSO (primary)
    'django.contrib.auth.backends.ModelBackend',  # Fallback for local admin
]
```

**Custom User Creation Hook (apps/authentication/saml.py):**
```python
from apps.core.models import AegisUser
from django.contrib.auth.models import Group
import logging

logger = logging.getLogger(__name__)

def create_aegis_user(created, user, saml_data):
    """
    Custom trigger called when new user is created via SAML SSO.
    Maps SAML attributes to AEGIS user model and assigns roles.
    """
    if created:
        # Extract custom attributes
        employee_id = saml_data.get('employeeID', [''])[0]
        department = saml_data.get('department', [''])[0]
        title = saml_data.get('title', [''])[0]

        # Update user model
        user.employee_id = employee_id
        user.department = department
        user.title = title
        user.save()

        # Assign role based on SAML groups
        saml_groups = saml_data.get('groups', [])
        role_assigned = False

        if 'AEGIS-ASP-Pharmacist' in saml_groups:
            user.role = 'asp_pharmacist'
            group = Group.objects.get(name='asp_pharmacist')
            user.groups.add(group)
            role_assigned = True

        elif 'AEGIS-Infection-Preventionist' in saml_groups:
            user.role = 'infection_preventionist'
            group = Group.objects.get(name='infection_preventionist')
            user.groups.add(group)
            role_assigned = True

        elif 'AEGIS-Physician' in saml_groups:
            user.role = 'physician'
            group = Group.objects.get(name='physician')
            user.groups.add(group)
            role_assigned = True

        elif 'AEGIS-Admin' in saml_groups:
            user.role = 'admin'
            group = Group.objects.get(name='admin')
            user.groups.add(group)
            user.is_staff = True
            role_assigned = True

        if role_assigned:
            user.save()
            logger.info(f"Created AEGIS user {user.username} with role {user.role}")
        else:
            logger.warning(f"User {user.username} created without AEGIS role assignment")

def before_login_check(user, saml_data):
    """
    Verification checks before allowing login.
    Validates MFA and user status.
    """
    # Check MFA assertion
    authn_context = saml_data.get('AuthnContextClassRef', [''])[0]
    if 'MFA' not in authn_context and 'TimeSyncToken' not in authn_context:
        logger.error(f"MFA not confirmed for user {user.username}")
        raise PermissionDenied("Multi-factor authentication required")

    # Check user is active
    if not user.is_active:
        logger.error(f"Inactive user attempted login: {user.username}")
        raise PermissionDenied("Account is inactive")

    # Check user has AEGIS role
    if not hasattr(user, 'role') or not user.role:
        logger.error(f"User {user.username} has no AEGIS role assigned")
        raise PermissionDenied("No AEGIS role assigned to this account")

    logger.info(f"User {user.username} passed pre-login checks")
```

### 1.4 LDAP Configuration (Fallback/Internal)

**For internal tools or fallback authentication:**

**settings/production.py:**
```python
import ldap
from django_auth_ldap.config import LDAPSearch, GroupOfNamesType

# LDAP Configuration
AUTH_LDAP_SERVER_URI = "ldap://ad.cincinnatichildrens.org"
AUTH_LDAP_BIND_DN = "cn=aegis-service,ou=serviceaccounts,dc=cincinnatichildrens,dc=org"
AUTH_LDAP_BIND_PASSWORD = os.environ['LDAP_BIND_PASSWORD']

# User search
AUTH_LDAP_USER_SEARCH = LDAPSearch(
    "ou=users,dc=cincinnatichildrens,dc=org",
    ldap.SCOPE_SUBTREE,
    "(sAMAccountName=%(user)s)"  # Active Directory username format
)

# User attributes mapping
AUTH_LDAP_USER_ATTR_MAP = {
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",
    "employee_id": "employeeID",
    "department": "department",
}

# Group search
AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
    "ou=groups,dc=cincinnatichildrens,dc=org",
    ldap.SCOPE_SUBTREE,
    "(objectClass=group)"
)
AUTH_LDAP_GROUP_TYPE = GroupOfNamesType(name_attr="cn")

# Group to Django group mapping
AUTH_LDAP_FIND_GROUP_PERMS = True
AUTH_LDAP_MIRROR_GROUPS = True

# User flags based on groups
AUTH_LDAP_USER_FLAGS_BY_GROUP = {
    "is_superuser": "cn=AEGIS-Admin,ou=groups,dc=cincinnatichildrens,dc=org",
    "is_staff": "cn=AEGIS-Admin,ou=groups,dc=cincinnatichildrens,dc=org",
}

# Require membership in AEGIS user group
AUTH_LDAP_REQUIRE_GROUP = "cn=AEGIS-Users,ou=groups,dc=cincinnatichildrens,dc=org"

# Cache settings for LDAP
AUTH_LDAP_CACHE_TIMEOUT = 3600  # 1 hour

# Add LDAP backend to authentication backends
AUTHENTICATION_BACKENDS = [
    'django_saml2_auth.backends.Saml2Backend',  # Primary: SAML SSO
    'django_auth_ldap.backend.LDAPBackend',  # Fallback: Direct LDAP
    'django.contrib.auth.backends.ModelBackend',  # Emergency: Local admin
]
```

### 1.5 Multi-Factor Authentication (MFA)

**MFA Enforcement via SAML IdP:**

MFA is enforced at the hospital's SAML identity provider (Okta/Azure AD), not at the Django application level. AEGIS validates that the SAML assertion includes an MFA confirmation claim.

**SAML MFA Validation:**
```python
# In SAML2_AUTH configuration
'MFA_REQUIRED': True,
'MFA_ATTRIBUTE': 'AuthnContextClassRef',
'MFA_REQUIRED_VALUES': [
    'urn:oasis:names:tc:SAML:2.0:ac:classes:MFA',
    'urn:oasis:names:tc:SAML:2.0:ac:classes:TimeSyncToken',
]
```

**MFA Methods (Managed by Hospital IdP):**
- Duo Mobile push notification
- SMS/text message codes
- Hardware tokens (YubiKey, RSA SecurID)
- Microsoft Authenticator
- Biometric authentication

**2026 HIPAA Requirement:** MFA is now mandatory for all PHI access. No exceptions for "vendor doesn't support MFA."

---

## 2. Audit Logging Architecture

### 2.1 Audit Logging Requirements (HIPAA)

**HIPAA Security Rule § 164.312(b):** Audit controls to record and examine activity in systems containing PHI.

**Required Logging:**
- **Who:** User ID, employee ID, IP address, workstation
- **What:** PHI accessed (patient MRN, specific data fields)
- **When:** Timestamp (UTC, millisecond precision)
- **How:** Action type (create, read, update, delete)
- **Why:** Application/module used, purpose (if applicable)
- **Result:** Success or failure

**Retention:** 6 years minimum from date of creation or last use (HIPAA § 164.316(b)(2)(i))

### 2.2 Technology Stack

**Primary Solution: django-auditlog**

**Why This Library:**
- Lightweight field-level change tracking with JSON diffs
- Automatic user association via middleware
- Immutable append-only log entries
- Captures timestamp, user, and action automatically
- Proven in fintech handling $2B daily transactions (HIPAA/GDPR compliant)
- PostgreSQL-optimized for enterprise scale

**Installation:**
```bash
pip install django-auditlog==3.0.0
```

**Configuration:**
```python
# settings.py
INSTALLED_APPS = [
    ...
    'auditlog',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'auditlog.middleware.AuditlogMiddleware',  # MUST be after auth middleware
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Auditlog settings
AUDITLOG_INCLUDE_ALL_MODELS = False  # Explicitly register models
AUDITLOG_EXCLUDE_TRACKING_MODELS = (
    'django.contrib.sessions.models.Session',
    'django.contrib.contenttypes.models.ContentType',
)
```

### 2.3 Model Registration

**Register all models containing PHI:**

```python
# apps/core/models.py (or apps/*/models.py)
from auditlog.registry import auditlog
from django.db import models

class Patient(models.Model):
    """
    Patient demographics (PHI - audit all access).
    """
    mrn = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    # ... other fields

# Register for audit logging
auditlog.register(Patient)

class ApprovalRequest(models.Model):
    """
    Antibiotic approval requests (PHI - audit all access).
    """
    patient_mrn = models.CharField(max_length=20)
    antibiotic = models.CharField(max_length=100)
    indication = models.TextField()
    requested_by = models.ForeignKey('AegisUser', on_delete=models.PROTECT)
    # ... other fields

auditlog.register(ApprovalRequest)

class HAICase(models.Model):
    """
    Healthcare-associated infection cases (PHI - audit all access).
    """
    patient_mrn = models.CharField(max_length=20)
    hai_type = models.CharField(max_length=20)  # CLABSI, CAUTI, etc.
    detection_date = models.DateTimeField()
    # ... other fields

auditlog.register(HAICase)

# Register ALL models containing PHI:
# - DoseAlert, DoseAssessment
# - MDROCase, MDRODetection
# - DrugBugAlert
# - GuidelineCheck
# - SurgicalCase
# - OutbreakCluster
# - NHSNReport
```

### 2.4 Custom Audit Log Model

**Extend django-auditlog to capture additional HIPAA-required fields:**

```python
# apps/core/models.py
from auditlog.models import LogEntry
from django.db import models

class AegisAuditLog(models.Model):
    """
    Extended audit log with HIPAA-specific fields.
    Links to django-auditlog LogEntry.
    """
    log_entry = models.OneToOneField(LogEntry, on_delete=models.CASCADE)

    # HIPAA-required fields
    ip_address = models.GenericIPAddressField()
    workstation_name = models.CharField(max_length=255, blank=True)
    employee_id = models.CharField(max_length=20)
    department = models.CharField(max_length=100)

    # PHI access details
    patient_mrn = models.CharField(max_length=20, blank=True)
    phi_fields_accessed = models.JSONField(default=list)  # List of field names
    access_purpose = models.CharField(max_length=255, blank=True)  # Optional

    # Application context
    module_name = models.CharField(max_length=100)  # HAI Detection, ABX Approvals, etc.
    view_name = models.CharField(max_length=255)

    # Compliance
    hipaa_compliant = models.BooleanField(default=True)
    retention_date = models.DateField()  # Auto-calculated: created + 6 years

    class Meta:
        db_table = 'aegis_audit_log'
        indexes = [
            models.Index(fields=['patient_mrn', '-log_entry__timestamp']),
            models.Index(fields=['employee_id', '-log_entry__timestamp']),
            models.Index(fields=['retention_date']),
        ]

# Middleware to create AegisAuditLog entries
# apps/core/middleware.py
from apps.core.models import AegisAuditLog
from auditlog.models import LogEntry
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)

class AegisAuditMiddleware:
    """
    Creates AegisAuditLog entries for every request that accesses PHI.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only log for authenticated users
        if request.user.is_authenticated:
            # Check if PHI was accessed (implement logic based on view/model)
            if self._is_phi_access(request):
                self._create_audit_log(request, response)

        return response

    def _is_phi_access(self, request):
        """
        Determine if request accessed PHI.
        """
        # Check if request includes patient MRN parameter
        if request.GET.get('mrn') or request.POST.get('mrn'):
            return True

        # Check if view is PHI-related (based on URL pattern)
        phi_patterns = [
            '/patients/', '/hai-detection/', '/abx-approvals/',
            '/dosing-verification/', '/drug-bug-mismatch/',
        ]
        return any(pattern in request.path for pattern in phi_patterns)

    def _create_audit_log(self, request, response):
        """
        Create AegisAuditLog entry.
        """
        # Get latest LogEntry for this user (created by auditlog middleware)
        recent_entries = LogEntry.objects.filter(
            actor=request.user,
        ).order_by('-timestamp')[:5]  # Last 5 entries

        # Create AegisAuditLog for each new LogEntry
        for entry in recent_entries:
            if not hasattr(entry, 'aegisauditlog'):
                AegisAuditLog.objects.create(
                    log_entry=entry,
                    ip_address=self._get_client_ip(request),
                    workstation_name=request.META.get('REMOTE_HOST', ''),
                    employee_id=request.user.employee_id,
                    department=request.user.department,
                    patient_mrn=request.GET.get('mrn', '') or request.POST.get('mrn', ''),
                    phi_fields_accessed=self._extract_phi_fields(entry),
                    module_name=self._get_module_name(request),
                    view_name=request.resolver_match.view_name if request.resolver_match else '',
                    retention_date=date.today() + timedelta(days=365*6),  # 6 years
                )
                logger.info(f"Audit log created for {request.user.username} accessing {request.path}")

    def _get_client_ip(self, request):
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')

    def _extract_phi_fields(self, log_entry):
        """Extract PHI field names from LogEntry changes."""
        if not log_entry.changes:
            return []

        phi_fields = ['mrn', 'first_name', 'last_name', 'date_of_birth', 'ssn']
        accessed = [field for field in log_entry.changes.keys() if field in phi_fields]
        return accessed

    def _get_module_name(self, request):
        """Determine AEGIS module from URL path."""
        module_map = {
            '/hai-detection/': 'HAI Detection',
            '/abx-approvals/': 'ABX Approvals',
            '/dosing-verification/': 'Dosing Verification',
            '/drug-bug-mismatch/': 'Drug-Bug Mismatch',
            '/mdro/': 'MDRO Surveillance',
            '/guideline-adherence/': 'Guideline Adherence',
            '/surgical-prophylaxis/': 'Surgical Prophylaxis',
            '/outbreak-detection/': 'Outbreak Detection',
        }
        for pattern, module in module_map.items():
            if pattern in request.path:
                return module
        return 'General'
```

**Add middleware to settings:**
```python
MIDDLEWARE = [
    ...
    'auditlog.middleware.AuditlogMiddleware',
    'apps.core.middleware.AegisAuditMiddleware',  # AFTER auditlog middleware
    ...
]
```

### 2.5 Audit Log Queries

**Common audit queries for compliance:**

```python
from auditlog.models import LogEntry
from apps.core.models import AegisAuditLog
from datetime import datetime, timedelta

# Who accessed a specific patient's data?
patient_mrn = 'MRN123456'
logs = AegisAuditLog.objects.filter(
    patient_mrn=patient_mrn
).select_related('log_entry', 'log_entry__actor').order_by('-log_entry__timestamp')

for log in logs:
    print(f"{log.log_entry.timestamp}: {log.employee_id} ({log.log_entry.actor.username}) "
          f"accessed {log.phi_fields_accessed} from {log.ip_address}")

# All actions by a specific user in last 30 days
user = AegisUser.objects.get(username='jsmith')
logs = LogEntry.objects.filter(
    actor=user,
    timestamp__gte=datetime.now() - timedelta(days=30)
).order_by('-timestamp')

# Failed access attempts (requires custom logging)
failed_logins = AegisAuditLog.objects.filter(
    view_name='login',
    log_entry__changes__icontains='failed'
)

# Export audit logs for compliance review (CSV)
import csv
from django.http import HttpResponse

def export_audit_logs(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="audit_logs.csv"'

    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'User', 'Employee ID', 'Patient MRN',
                     'Action', 'Module', 'IP Address', 'PHI Fields'])

    logs = AegisAuditLog.objects.select_related('log_entry', 'log_entry__actor').all()
    for log in logs:
        writer.writerow([
            log.log_entry.timestamp,
            log.log_entry.actor.username,
            log.employee_id,
            log.patient_mrn,
            log.log_entry.action,
            log.module_name,
            log.ip_address,
            ', '.join(log.phi_fields_accessed),
        ])

    return response
```

### 2.6 Log Retention & Archival

**HIPAA Requirement:** 6 years from creation or last use

**Archival Strategy:**
```python
# management/commands/archive_old_audit_logs.py
from django.core.management.base import BaseCommand
from apps.core.models import AegisAuditLog
from datetime import date
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Archive audit logs older than 6 years to cold storage'

    def handle(self, *args, **options):
        # Find logs eligible for archival (retention_date has passed)
        eligible = AegisAuditLog.objects.filter(retention_date__lt=date.today())
        count = eligible.count()

        if count > 0:
            # Export to cold storage (S3 Glacier, Azure Archive, etc.)
            self._export_to_archive(eligible)

            # Delete from database
            eligible.delete()
            logger.info(f"Archived {count} audit log entries")
            self.stdout.write(self.style.SUCCESS(f"Archived {count} logs"))
        else:
            self.stdout.write("No logs eligible for archival")

    def _export_to_archive(self, queryset):
        """Export logs to cold storage before deletion."""
        # Implementation depends on storage backend
        # Example: AWS S3 Glacier, Azure Archive Storage
        pass

# Schedule this command to run monthly via cron or Celery
```

---

## 3. Role-Based Access Control

### 3.1 User Roles

AEGIS implements 4 distinct user roles aligned with hospital clinical workflows:

| Role | Description | Permissions |
|------|-------------|-------------|
| **asp_pharmacist** | Antimicrobial Stewardship Pharmacist | Full access to ABX approvals, dosing verification, drug-bug mismatch, guideline adherence, NHSN reporting. Read access to HAI detection. |
| **infection_preventionist** | Infection Control Specialist | Full access to HAI detection, MDRO surveillance, outbreak detection. Read access to ABX approvals and dosing verification. |
| **physician** | Physician/Provider | Read-only access to all modules. Can add notes and comments. Cannot approve/reject or modify data. |
| **admin** | System Administrator | Full access to all modules, Django admin interface, user management, system configuration. |

### 3.2 Django Groups & Permissions

**Create groups and assign permissions:**

```python
# apps/core/management/commands/setup_roles.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from apps.abx_approvals.models import ApprovalRequest
from apps.hai_detection.models import HAICase
from apps.dosing_verification.models import DoseAlert
# ... import all models

class Command(BaseCommand):
    help = 'Set up AEGIS user roles and permissions'

    def handle(self, *args, **options):
        # Create groups
        asp_group, _ = Group.objects.get_or_create(name='asp_pharmacist')
        ip_group, _ = Group.objects.get_or_create(name='infection_preventionist')
        physician_group, _ = Group.objects.get_or_create(name='physician')
        admin_group, _ = Group.objects.get_or_create(name='admin')

        # ASP Pharmacist permissions
        asp_permissions = [
            # ABX Approvals - full access
            'view_approvalrequest', 'add_approvalrequest', 'change_approvalrequest', 'delete_approvalrequest',

            # Dosing Verification - full access
            'view_dosealert', 'add_dosealert', 'change_dosealert', 'delete_dosealert',
            'view_doseassessment', 'add_doseassessment', 'change_doseassessment',

            # Drug-Bug Mismatch - full access
            'view_drugbugalert', 'add_drugbugalert', 'change_drugbugalert',

            # Guideline Adherence - full access
            'view_guidelinecheck', 'add_guidelinecheck', 'change_guidelinecheck',

            # NHSN Reporting - full access
            'view_nhsnreport', 'add_nhsnreport', 'change_nhsnreport',

            # HAI Detection - read only
            'view_haicase',

            # MDRO - read only
            'view_mdrocase',
        ]
        self._assign_permissions(asp_group, asp_permissions)

        # Infection Preventionist permissions
        ip_permissions = [
            # HAI Detection - full access
            'view_haicase', 'add_haicase', 'change_haicase', 'delete_haicase',

            # MDRO Surveillance - full access
            'view_mdrocase', 'add_mdrocase', 'change_mdrocase', 'delete_mdrocase',

            # Outbreak Detection - full access
            'view_outbreakcluster', 'add_outbreakcluster', 'change_outbreakcluster',

            # ABX Approvals - read only
            'view_approvalrequest',

            # Dosing Verification - read only
            'view_dosealert', 'view_doseassessment',
        ]
        self._assign_permissions(ip_group, ip_permissions)

        # Physician permissions (read-only all modules)
        physician_permissions = [
            'view_approvalrequest',
            'view_haicase',
            'view_dosealert', 'view_doseassessment',
            'view_drugbugalert',
            'view_guidelinecheck',
            'view_mdrocase',
            'view_outbreakcluster',
            # Can add notes/comments
            'add_note', 'view_note',
        ]
        self._assign_permissions(physician_group, physician_permissions)

        # Admin - all permissions
        admin_group.permissions.set(Permission.objects.all())

        self.stdout.write(self.style.SUCCESS('Successfully set up AEGIS roles'))

    def _assign_permissions(self, group, permission_codenames):
        """Assign permissions to group by codename."""
        permissions = Permission.objects.filter(codename__in=permission_codenames)
        group.permissions.set(permissions)
```

**Run setup command:**
```bash
python manage.py setup_roles
```

### 3.3 Permission Decorators

**Protect views with permission checks:**

```python
# apps/abx_approvals/views.py
from django.contrib.auth.decorators import permission_required, login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect

@login_required
@permission_required('abx_approvals.add_approvalrequest', raise_exception=True)
def create_approval(request):
    """
    Create antibiotic approval request.
    Only asp_pharmacist role can create approvals.
    """
    if request.method == 'POST':
        # Handle form submission
        pass
    return render(request, 'abx_approvals/create.html')

@login_required
@permission_required('abx_approvals.view_approvalrequest', raise_exception=True)
def view_approval(request, approval_id):
    """
    View approval request.
    All roles can view (physician read-only, asp_pharmacist can edit).
    """
    approval = ApprovalRequest.objects.get(id=approval_id)

    # Check if user can edit
    can_edit = request.user.has_perm('abx_approvals.change_approvalrequest')

    return render(request, 'abx_approvals/view.html', {
        'approval': approval,
        'can_edit': can_edit,
    })

# Custom permission check for complex logic
@login_required
def approve_request(request, approval_id):
    """
    Approve antibiotic request.
    Only asp_pharmacist can approve.
    """
    if not request.user.has_perm('abx_approvals.change_approvalrequest'):
        raise PermissionDenied("Only ASP pharmacists can approve requests")

    approval = ApprovalRequest.objects.get(id=approval_id)
    approval.status = 'approved'
    approval.approved_by = request.user
    approval.save()

    return redirect('approval_detail', approval_id=approval_id)
```

**Django REST Framework permissions:**

```python
# apps/api/permissions.py
from rest_framework import permissions

class IsASPPharmacist(permissions.BasePermission):
    """
    Permission check for ASP pharmacist role.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'asp_pharmacist'

class IsInfectionPreventionist(permissions.BasePermission):
    """
    Permission check for infection preventionist role.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'infection_preventionist'

class IsPhysicianReadOnly(permissions.BasePermission):
    """
    Physicians have read-only access.
    """
    def has_permission(self, request, view):
        if request.user.is_authenticated and request.user.role == 'physician':
            return request.method in permissions.SAFE_METHODS
        return False

# apps/api/views.py
from rest_framework import viewsets
from apps.abx_approvals.models import ApprovalRequest
from apps.api.serializers import ApprovalRequestSerializer
from apps.api.permissions import IsASPPharmacist, IsPhysicianReadOnly

class ApprovalRequestViewSet(viewsets.ModelViewSet):
    """
    API endpoint for approval requests.
    ASP pharmacists can create/edit, physicians can read.
    """
    queryset = ApprovalRequest.objects.all()
    serializer_class = ApprovalRequestSerializer
    permission_classes = [IsASPPharmacist | IsPhysicianReadOnly]
```

### 3.4 Template Permission Checks

**Show/hide UI elements based on permissions:**

```django
<!-- templates/abx_approvals/detail.html -->
{% load static %}

<div class="approval-detail">
    <h2>Approval Request #{{ approval.id }}</h2>

    <!-- All users can view -->
    <div class="approval-info">
        <p><strong>Patient:</strong> {{ approval.patient_mrn }}</p>
        <p><strong>Antibiotic:</strong> {{ approval.antibiotic }}</p>
        <p><strong>Indication:</strong> {{ approval.indication }}</p>
        <p><strong>Status:</strong> {{ approval.status }}</p>
    </div>

    <!-- Only ASP pharmacists can approve/reject -->
    {% if perms.abx_approvals.change_approvalrequest %}
    <div class="approval-actions">
        <form method="post" action="{% url 'approve_request' approval.id %}">
            {% csrf_token %}
            <button type="submit" class="btn btn-success">Approve</button>
        </form>
        <form method="post" action="{% url 'reject_request' approval.id %}">
            {% csrf_token %}
            <button type="submit" class="btn btn-danger">Reject</button>
        </form>
    </div>
    {% endif %}

    <!-- All users can add notes -->
    {% if perms.abx_approvals.add_note %}
    <div class="add-note">
        <form method="post" action="{% url 'add_note' approval.id %}">
            {% csrf_token %}
            <textarea name="note_text" rows="4"></textarea>
            <button type="submit" class="btn btn-primary">Add Note</button>
        </form>
    </div>
    {% endif %}
</div>
```

---

## 4. Security Hardening

### 4.1 Django Security Settings

**File: settings/production.py**

```python
import os
from pathlib import Path

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']  # Never hardcode!

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Allowed hosts
ALLOWED_HOSTS = ['aegis.cincinnatichildrens.org', 'aegis-internal.cchmc.org']

# Database (PostgreSQL with SSL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'],
        'USER': os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': os.environ['DB_HOST'],
        'PORT': '5432',
        'OPTIONS': {
            'sslmode': 'require',  # Enforce SSL connection
            'connect_timeout': 10,
        },
        'CONN_MAX_AGE': 600,  # Connection pooling (10 minutes)
    }
}

# HTTPS/SSL Enforcement
SECURE_SSL_REDIRECT = True  # Redirect all HTTP to HTTPS
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # Behind load balancer

# HTTP Strict Transport Security (HSTS)
SECURE_HSTS_SECONDS = 31536000  # 1 year (31,536,000 seconds)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookie Security
SESSION_COOKIE_SECURE = True  # Only send cookies over HTTPS
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookies
SESSION_COOKIE_SAMESITE = 'Strict'  # CSRF protection
SESSION_COOKIE_AGE = 1800  # 30 minutes (auto-logout)
SESSION_COOKIE_NAME = 'aegis_sessionid'  # Custom cookie name

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_NAME = 'aegis_csrftoken'
CSRF_TRUSTED_ORIGINS = ['https://aegis.cincinnatichildrens.org']

# Security Headers
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME-sniffing
SECURE_BROWSER_XSS_FILTER = True  # Enable browser XSS filter
X_FRAME_OPTIONS = 'DENY'  # Prevent clickjacking (no iframes)

# Content Security Policy (requires django-csp)
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")  # Minimize unsafe-inline usage
CSP_IMG_SRC = ("'self'", "data:")
CSP_FONT_SRC = ("'self'",)
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_ANCESTORS = ("'none'",)  # Same as X-Frame-Options: DENY
CSP_BASE_URI = ("'self'",)
CSP_FORM_ACTION = ("'self'",)
CSP_REPORT_URI = '/csp-report/'  # Log CSP violations
# Start in report-only mode, then enforce
# CSP_REPORT_ONLY = True

# Password Validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 12}},  # 12 character minimum
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Session Security
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'  # Performance + persistence
SESSION_SAVE_EVERY_REQUEST = True  # Update session expiry on every request
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # Clear session when browser closes

# File Upload Security
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
FILE_UPLOAD_PERMISSIONS = 0o644

# Admin Security
ADMINS = [('AEGIS Admin', 'aegis-admin@cincinnatichildrens.org')]
MANAGERS = ADMINS
ADMIN_URL = 'secure-admin-panel/'  # Obscure admin URL (not /admin/)

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/aegis/django.log',
            'maxBytes': 1024 * 1024 * 15,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/aegis/security.log',
            'maxBytes': 1024 * 1024 * 15,
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['require_debug_false'],
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.security': {
            'handlers': ['security', 'mail_admins'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'auditlog': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Middleware (Order is critical!)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',  # MUST be first
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'auditlog.middleware.AuditlogMiddleware',  # AFTER auth middleware
    'apps.core.middleware.AegisAuditMiddleware',  # AFTER auditlog middleware
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'csp.middleware.CSPMiddleware',  # Content Security Policy
]
```

### 4.2 Content Security Policy (CSP)

**Install django-csp:**
```bash
pip install django-csp==3.8
```

**Gradual CSP Implementation:**

**Phase 1: Report-Only Mode (Week 1)**
```python
# settings.py
CSP_REPORT_ONLY = True  # Don't enforce, just report violations
CSP_REPORT_URI = '/csp-report/'

# All other CSP directives as defined above
```

**Create CSP violation report endpoint:**
```python
# apps/core/views.py
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
import json
import logging

logger = logging.getLogger('django.security')

@csrf_exempt  # CSP reports don't include CSRF token
def csp_report(request):
    """
    Receive and log Content Security Policy violation reports.
    """
    if request.method == 'POST':
        try:
            report = json.loads(request.body.decode('utf-8'))
            logger.warning(f"CSP Violation: {report}")
        except Exception as e:
            logger.error(f"Error processing CSP report: {e}")

    return HttpResponse('')

# urls.py
urlpatterns = [
    path('csp-report/', csp_report, name='csp_report'),
    ...
]
```

**Phase 2: Analyze Violations (Week 2)**
- Review logged CSP violations
- Identify legitimate external resources (CDNs, fonts, etc.)
- Update CSP directives to allow necessary sources

**Phase 3: Enforce CSP (Week 3+)**
```python
CSP_REPORT_ONLY = False  # Enforce CSP, block violations
```

### 4.3 Security Headers Testing

**Test security headers with SecurityHeaders.com or Mozilla Observatory:**

```bash
# Test headers
curl -I https://aegis.cincinnatichildrens.org

# Expected headers:
# Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
# X-Frame-Options: DENY
# X-Content-Type-Options: nosniff
# Content-Security-Policy: default-src 'self'; ...
# Referrer-Policy: strict-origin-when-cross-origin
```

**Django middleware to add custom headers:**
```python
# apps/core/middleware.py
class SecurityHeadersMiddleware:
    """
    Add additional security headers not covered by Django's SecurityMiddleware.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Referrer Policy
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Permissions Policy (formerly Feature-Policy)
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

        # Expect-CT (Certificate Transparency)
        response['Expect-CT'] = 'max-age=86400, enforce'

        return response

# Add to MIDDLEWARE
MIDDLEWARE = [
    ...
    'apps.core.middleware.SecurityHeadersMiddleware',
]
```

---

## 5. 2026 HIPAA Compliance Requirements

### 5.1 Critical Changes in 2026 HIPAA Security Rule

**New Mandatory Requirements (Effective 2026):**

#### 1. Encryption at Rest (Previously Optional, Now Mandatory)

**Previous Rule (through 2025):** Encryption at rest was "addressable" (recommended but optional with documented risk assessment).

**2026 Rule:** Encryption at rest is **REQUIRED** for all ePHI.

**Impact on AEGIS:**
- Database encryption mandatory (PostgreSQL)
- File storage encryption mandatory
- Backup encryption mandatory
- Log file encryption recommended

**Implementation:** See Section 6 (Encryption Strategy)

#### 2. Multi-Factor Authentication (MFA) Required

**Previous Rule:** MFA was recommended but not explicitly required.

**2026 Rule:** MFA is **MANDATORY** for all user access to systems containing ePHI.

**No Exceptions:** "Our vendor doesn't support MFA" is no longer a valid excuse.

**Impact on AEGIS:**
- All users must authenticate with MFA via hospital SAML IdP
- SAML assertion must include MFA confirmation claim
- Backup/emergency access also requires MFA

**Implementation:**
- MFA enforcement at hospital IdP (Okta/Azure AD)
- AEGIS validates MFA claim in SAML assertion (see Section 1.5)
- No local password-only authentication allowed

#### 3. Annual Vendor Verification

**Previous Rule:** Business Associate Agreements (BAAs) were sufficient.

**2026 Rule:** **Annual written verification** required from all business associates confirming technical safeguards are implemented.

**Impact on AEGIS:**
- If using cloud services (AWS, Azure), must obtain annual verification
- Cannot rely solely on signed BAA
- Must document vendor security controls

**Implementation:**
- Maintain vendor compliance documentation
- Annual review of cloud provider security attestations
- Document in security plan

#### 4. NIST Alignment

**2026 Rule:** Encryption and security controls must align with **NIST cybersecurity standards**.

**NIST Standards:**
- NIST SP 800-53 (Security Controls)
- NIST SP 800-111 (Storage Encryption)
- NIST SP 800-57 (Key Management)

**Impact on AEGIS:**
- Use NIST-approved encryption algorithms (AES-256)
- Implement NIST key management practices
- Document alignment with NIST standards

### 5.2 HIPAA Security Rule Compliance Matrix

| HIPAA Control | Requirement | AEGIS Implementation |
|---------------|-------------|---------------------|
| **Access Control (§164.312(a)(1))** | Unique user IDs, emergency access, automatic logoff, encryption | SAML SSO with unique IDs, 30-minute session timeout, emergency admin account |
| **Audit Controls (§164.312(b))** | Log and examine activity in systems with ePHI | django-auditlog + AegisAuditLog, 6-year retention |
| **Integrity (§164.312(c)(1))** | Protect ePHI from improper alteration/destruction | Database integrity constraints, audit log immutability |
| **Person/Entity Authentication (§164.312(d))** | Verify identity before granting access | SAML SSO + MFA via hospital IdP |
| **Transmission Security (§164.312(e)(1))** | Protect ePHI in transit | TLS 1.2+, HTTPS enforcement, PostgreSQL SSL |
| **Encryption at Rest (§164.312(a)(2)(iv))** | **MANDATORY (2026)** Encrypt stored ePHI | PostgreSQL TDE or LUKS encryption, encrypted backups |
| **Emergency Access (§164.312(a)(2)(ii))** | Establish procedures for emergency access | Local admin account (MFA via TOTP), documented procedures |
| **Automatic Logoff (§164.312(a)(2)(iii))** | Terminate session after inactivity | 30-minute session timeout |
| **Encryption in Transit (§164.312(e)(2)(i))** | Encrypt ePHI during transmission | HTTPS (TLS 1.2+), PostgreSQL SSL, Redis SSL |

### 5.3 Breach Notification Requirements

**HIPAA § 164.404:** Notify individuals of breach within **60 days**.

**Breach Detection:**
```python
# apps/core/models.py
class SecurityIncident(models.Model):
    """
    Track potential security incidents and breaches.
    """
    INCIDENT_TYPES = [
        ('unauthorized_access', 'Unauthorized Access'),
        ('data_exfiltration', 'Data Exfiltration'),
        ('malware', 'Malware'),
        ('phishing', 'Phishing'),
        ('other', 'Other'),
    ]

    SEVERITY = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    incident_type = models.CharField(max_length=30, choices=INCIDENT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY)
    detected_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField()
    affected_patients = models.ManyToManyField('Patient', blank=True)
    affected_users = models.ManyToManyField('AegisUser', blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    # Breach determination
    is_breach = models.BooleanField(default=False)  # >500 records or high-risk
    breach_notification_sent = models.BooleanField(default=False)
    breach_reported_to_hhs = models.BooleanField(default=False)

    class Meta:
        db_table = 'security_incidents'

# Automated breach detection
from apps.core.models import SecurityIncident, AegisAuditLog
from datetime import datetime, timedelta

def detect_unusual_access_patterns():
    """
    Detect unusual PHI access patterns that may indicate breach.
    Run daily via Celery task.
    """
    # Example: User accessing >100 patient records in 1 hour
    one_hour_ago = datetime.now() - timedelta(hours=1)

    high_volume_users = AegisAuditLog.objects.filter(
        log_entry__timestamp__gte=one_hour_ago
    ).values('employee_id').annotate(
        access_count=Count('patient_mrn', distinct=True)
    ).filter(access_count__gt=100)

    for user_access in high_volume_users:
        SecurityIncident.objects.create(
            incident_type='unauthorized_access',
            severity='high',
            description=f"User {user_access['employee_id']} accessed {user_access['access_count']} patient records in 1 hour",
        )
```

### 5.4 Risk Assessment Documentation

**HIPAA § 164.308(a)(1)(ii)(A):** Conduct accurate and thorough risk assessment.

**Risk Assessment Template:**
```
AEGIS Risk Assessment - 2026

1. Asset Inventory
   - Databases: PostgreSQL (ePHI storage)
   - Application servers: Django/Gunicorn
   - Web servers: Nginx
   - Authentication: SAML IdP integration
   - Third-party services: Cloud storage, SIEM

2. Threat Identification
   - External threats: Hacking, malware, phishing
   - Internal threats: Insider access, accidental disclosure
   - System failures: Hardware failure, software bugs
   - Natural disasters: Fire, flood, power outage

3. Vulnerability Assessment
   - Unpatched software: [Risk: High, Mitigation: Automated patching]
   - Weak passwords: [Risk: Low, Mitigation: MFA + SSO]
   - SQL injection: [Risk: Low, Mitigation: Django ORM]
   - XSS: [Risk: Low, Mitigation: CSP + Django templates]
   - Session hijacking: [Risk: Low, Mitigation: Secure cookies + HTTPS]

4. Current Security Measures
   - See HIPAA Security Rule Compliance Matrix (Section 5.2)

5. Likelihood and Impact Analysis
   - [Threat] x [Likelihood] x [Impact] = Risk Score
   - Document each risk with score and mitigation plan

6. Risk Mitigation Recommendations
   - Implement encryption at rest (MANDATORY 2026)
   - Enforce MFA for all users (MANDATORY 2026)
   - Deploy WAF for DDoS protection
   - Implement SIEM integration
   - Conduct penetration testing annually
```

---

## 6. Encryption Strategy

### 6.1 Encryption Requirements Summary

**2026 HIPAA Mandate:** Encryption at rest is now **REQUIRED** (not addressable).

**NIST Standards Compliance:**
- **Algorithm:** AES-256 (NIST FIPS 140-2 approved)
- **Key Management:** NIST SP 800-57 guidelines
- **Implementation:** NIST SP 800-111 (Storage Encryption)

**What Must Be Encrypted:**
1. Database (PostgreSQL) - ePHI storage
2. File storage - uploaded files, attachments
3. Backups - database backups, file backups
4. Log files - audit logs (recommended)
5. Temporary files - CSV exports, reports

### 6.2 PostgreSQL Encryption at Rest

**Two Options:**

#### Option 1: Azure Database for PostgreSQL Encryption (Recommended for Azure Cloud)

**Features:**
- Transparent Data Encryption (TDE) via Azure Storage Service Encryption
- Automatic encryption of data at rest
- Microsoft-managed keys or customer-managed keys (CMK)
- FIPS 140-2 Level 2 validated
- No application code changes required

**Configuration:**
```bash
# Azure CLI - Enable encryption with customer-managed key
az postgres server key create \
    --resource-group aegis-rg \
    --server-name aegis-postgres \
    --key-name aegis-db-key \
    --vault-name aegis-keyvault

az postgres server update \
    --resource-group aegis-rg \
    --name aegis-postgres \
    --minimal-tls-version TLS1_2 \
    --ssl-enforcement Enabled
```

**Advantages:**
- Fully managed by Azure
- No performance overhead
- Integrated with Azure Key Vault
- Automatic key rotation
- HIPAA compliance built-in

**Disadvantages:**
- Azure-specific (vendor lock-in)
- Requires Azure subscription

**Recommended for AEGIS:** ✅ Yes - if deploying to Azure cloud

#### Option 2: LUKS Full-Disk Encryption (On-Premises or IaaS)

**Features:**
- OS-level disk encryption (Linux Unified Key Setup)
- Works with any PostgreSQL version
- Encrypts entire disk partition
- FIPS 140-2 compliant when using approved ciphers

**Configuration:**
```bash
# Set up LUKS encryption on data partition
cryptsetup luksFormat /dev/sdb1 --cipher aes-xts-plain64 --key-size 512 --hash sha256
cryptsetup luksOpen /dev/sdb1 postgres_encrypted
mkfs.ext4 /dev/mapper/postgres_encrypted
mount /dev/mapper/postgres_encrypted /var/lib/postgresql

# Add to /etc/crypttab for auto-mount
postgres_encrypted /dev/sdb1 /root/keyfile luks

# Secure key file
chmod 400 /root/keyfile
```

**Advantages:**
- Works with any cloud or on-premises
- No vendor lock-in
- Operating system native

**Disadvantages:**
- Manual key management
- Performance overhead (~10-15%)
- Requires OS-level configuration

**Recommended for AEGIS:** ⚠️ Only if on-premises deployment at Cincinnati Children's data center

#### Option 3: PostgreSQL pgcrypto Extension (Column-Level)

**Features:**
- Encrypt specific columns containing ePHI
- Application-level encryption
- Granular control over encrypted data

**Configuration:**
```sql
-- Enable pgcrypto extension
CREATE EXTENSION pgcrypto;

-- Encrypt column
CREATE TABLE patients (
    id SERIAL PRIMARY KEY,
    mrn VARCHAR(20),
    first_name_encrypted BYTEA,  -- Encrypted column
    last_name_encrypted BYTEA,
    ssn_encrypted BYTEA
);

-- Insert encrypted data
INSERT INTO patients (mrn, first_name_encrypted, last_name_encrypted)
VALUES ('MRN123', pgp_sym_encrypt('John', 'encryption_key'), pgp_sym_encrypt('Doe', 'encryption_key'));

-- Query decrypted data
SELECT mrn, pgp_sym_decrypt(first_name_encrypted, 'encryption_key') AS first_name
FROM patients;
```

**Advantages:**
- Fine-grained encryption control
- Works with any PostgreSQL version
- No OS changes required

**Disadvantages:**
- Application code changes required (Django models must encrypt/decrypt)
- Performance overhead on every query
- Complex key management
- Cannot index encrypted columns

**Recommended for AEGIS:** ❌ No - too complex, performance issues

### 6.3 Recommendation: Azure Database for PostgreSQL

**For Cincinnati Children's deployment, recommend:**

**Azure Database for PostgreSQL with Transparent Data Encryption (TDE)**

**Rationale:**
- Fully HIPAA compliant out-of-the-box
- No application code changes (transparent to Django)
- Managed key rotation and backup encryption
- FIPS 140-2 Level 2 validated
- Integrates with Azure Key Vault for customer-managed keys (CMK)
- No performance overhead
- Azure provides Business Associate Agreement (BAA)

**Key Management:**
- Store encryption keys in **Azure Key Vault**
- Enable key rotation policy (rotate every 90 days)
- Use Managed Identity for Django app to access Key Vault
- Separate keys for production, staging, development

**Django Configuration (No Changes Required):**
```python
# settings.py - Same as before
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'],
        'USER': os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': 'aegis-postgres.postgres.database.azure.com',
        'PORT': '5432',
        'OPTIONS': {
            'sslmode': 'require',  # Enforce SSL
        },
    }
}
# Encryption is handled transparently by Azure
```

### 6.4 File Storage Encryption

**Azure Blob Storage with Encryption**

```python
# settings.py
DEFAULT_FILE_STORAGE = 'storages.backends.azure_storage.AzureStorage'

AZURE_ACCOUNT_NAME = os.environ['AZURE_STORAGE_ACCOUNT']
AZURE_ACCOUNT_KEY = os.environ['AZURE_STORAGE_KEY']
AZURE_CONTAINER = 'aegis-files'

# Enable server-side encryption (automatic)
AZURE_SSL = True
AZURE_CUSTOM_DOMAIN = None
```

**Azure Storage automatically encrypts all data at rest using AES-256.**

### 6.5 Backup Encryption

**Automated Encrypted Backups:**

```bash
# Azure Database for PostgreSQL - Automatic encrypted backups
# Retention: 35 days (configurable)
# Encryption: Same key as database (TDE)

# Verify backup encryption
az postgres server backup list \
    --resource-group aegis-rg \
    --server-name aegis-postgres
```

**Manual Backup Encryption (if needed):**
```bash
# Backup database with encryption
pg_dump -h aegis-postgres.postgres.database.azure.com -U aegis_admin aegis_db | \
gpg --symmetric --cipher-algo AES256 > aegis_backup_$(date +%Y%m%d).sql.gpg

# Restore from encrypted backup
gpg --decrypt aegis_backup_20260207.sql.gpg | \
psql -h aegis-postgres.postgres.database.azure.com -U aegis_admin aegis_db
```

### 6.6 Encryption in Transit

**All network communication encrypted:**

| Connection | Protocol | Configuration |
|------------|----------|---------------|
| User → AEGIS | HTTPS (TLS 1.2+) | `SECURE_SSL_REDIRECT = True` |
| AEGIS → PostgreSQL | PostgreSQL SSL | `'sslmode': 'require'` |
| AEGIS → Redis | Redis SSL (rediss://) | `'ssl_cert_reqs': 'required'` |
| AEGIS → Azure Blob | HTTPS | `AZURE_SSL = True` |
| AEGIS → SAML IdP | HTTPS (SAML) | Configured in IdP metadata |

**TLS Configuration (Nginx):**
```nginx
# /etc/nginx/sites-available/aegis
server {
    listen 443 ssl http2;
    server_name aegis.cincinnatichildrens.org;

    # TLS certificates
    ssl_certificate /etc/letsencrypt/live/aegis.cincinnatichildrens.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aegis.cincinnatichildrens.org/privkey.pem;

    # TLS version and ciphers (HIPAA-compliant)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers on;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;

    # Session cache
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
}
```

### 6.7 Key Management Best Practices

**Azure Key Vault Configuration:**

```bash
# Create Key Vault
az keyvault create \
    --name aegis-keyvault \
    --resource-group aegis-rg \
    --location eastus \
    --enable-soft-delete true \
    --enable-purge-protection true

# Create encryption key
az keyvault key create \
    --vault-name aegis-keyvault \
    --name aegis-db-encryption-key \
    --protection software \
    --size 2048 \
    --ops encrypt decrypt

# Grant Django app access to Key Vault (using Managed Identity)
az keyvault set-policy \
    --name aegis-keyvault \
    --object-id <django-app-managed-identity-object-id> \
    --secret-permissions get list \
    --key-permissions get list decrypt
```

**NIST SP 800-57 Compliance:**
- **Key rotation:** Every 90 days (automate with Azure Policy)
- **Key separation:** Different keys for prod/staging/dev
- **Key backup:** Automatic in Azure Key Vault (geo-redundant)
- **Key access control:** Role-based access (least privilege)
- **Key audit:** All key operations logged in Azure Monitor

---

## 7. Rate Limiting & DDoS Protection

### 7.1 Application-Level Rate Limiting

**Library: django-ratelimit**

```bash
pip install django-ratelimit==4.1.0
```

**Configuration:**

```python
# settings.py
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'  # Use Redis cache for rate limiting

# Cache configuration (Redis)
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'rediss://aegis-redis.redis.cache.windows.net:6380/0',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {'ssl_cert_reqs': 'required'},
            'PASSWORD': os.environ['REDIS_PASSWORD'],
        },
    },
}
```

**View-Level Rate Limiting:**

```python
# apps/authentication/views.py
from django_ratelimit.decorators import ratelimit
from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect

@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def login_view(request):
    """
    Login view with rate limiting.
    Max 5 login attempts per minute per IP address.
    """
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials'})

    return render(request, 'login.html')

# apps/api/views.py
from django_ratelimit.decorators import ratelimit
from rest_framework.decorators import api_view
from rest_framework.response import Response

@ratelimit(key='user', rate='100/h', method='GET')
@api_view(['GET'])
def patient_search(request):
    """
    Patient search API endpoint.
    Max 100 requests per hour per authenticated user.
    """
    # ... search logic
    return Response(results)

@ratelimit(key='user_or_ip', rate='20/m', method='POST')
@api_view(['POST'])
def create_approval(request):
    """
    Create approval request.
    Max 20 requests per minute (per user or IP if unauthenticated).
    """
    # ... create logic
    return Response(approval_data)
```

**Custom Rate Limit Key Functions:**

```python
# apps/core/ratelimit.py
def user_or_ip(group, request):
    """
    Rate limit by authenticated user, fall back to IP for anonymous.
    """
    if request.user.is_authenticated:
        return f'user:{request.user.pk}'
    return f'ip:{request.META.get("REMOTE_ADDR")}'

# Use in decorator
@ratelimit(key=user_or_ip, rate='50/h')
def some_view(request):
    pass
```

### 7.2 Django REST Framework Throttling

**Global Throttling Configuration:**

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',  # Anonymous users: 100 requests/hour
        'user': '1000/hour',  # Authenticated users: 1000 requests/hour
        'burst': '60/minute',  # Burst protection: 60/minute
        'sustained': '1000/day',  # Sustained: 1000/day
    },
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

**Custom Throttle Classes:**

```python
# apps/api/throttles.py
from rest_framework.throttling import UserRateThrottle

class BurstRateThrottle(UserRateThrottle):
    """
    Burst protection: 60 requests per minute.
    """
    scope = 'burst'

class SustainedRateThrottle(UserRateThrottle):
    """
    Sustained protection: 1000 requests per day.
    """
    scope = 'sustained'

# apps/api/views.py
from rest_framework import viewsets
from apps.api.throttles import BurstRateThrottle, SustainedRateThrottle

class ApprovalRequestViewSet(viewsets.ModelViewSet):
    """
    API endpoint with multi-level throttling.
    """
    queryset = ApprovalRequest.objects.all()
    serializer_class = ApprovalRequestSerializer
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
```

### 7.3 DDoS Protection (Infrastructure Level)

**IMPORTANT:** Application-level rate limiting is NOT sufficient DDoS protection.

**Recommended DDoS Protection:**

#### Option 1: Azure DDoS Protection Standard (Recommended for Azure)

**Features:**
- 100 Gbps+ DDoS mitigation capacity
- Always-on traffic monitoring
- Automatic attack mitigation
- Real-time attack metrics and alerts
- Integration with Azure Monitor

**Configuration:**
```bash
# Enable DDoS Protection on Virtual Network
az network ddos-protection create \
    --resource-group aegis-rg \
    --name aegis-ddos-protection

az network vnet update \
    --resource-group aegis-rg \
    --name aegis-vnet \
    --ddos-protection true \
    --ddos-protection-plan aegis-ddos-protection
```

**Cost:** ~$2,944/month (includes all resources in VNet)

#### Option 2: Cloudflare WAF + DDoS Protection

**Features:**
- Global CDN with DDoS protection
- Web Application Firewall (WAF)
- Rate limiting at edge
- Bot detection and mitigation
- OWASP Top 10 protection

**Configuration:**
```nginx
# Point DNS to Cloudflare
aegis.cincinnatichildrens.org → Cloudflare → Azure Load Balancer

# Cloudflare settings:
- SSL/TLS: Full (strict)
- Always Use HTTPS: On
- Automatic HTTPS Rewrites: On
- DDoS Protection: On
- WAF: On (OWASP ModSecurity Core Rule Set)
- Rate Limiting: Custom rules
```

**Cost:** ~$200-300/month (Pro or Business plan)

#### Option 3: Nginx Rate Limiting (Basic Protection)

**Free but limited protection:**

```nginx
# /etc/nginx/nginx.conf
http {
    # Rate limit zone (10 MB can track ~160,000 IPs)
    limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=60r/m;
    limit_req_zone $binary_remote_addr zone=general_limit:10m rate=10r/s;

    # Connection limit
    limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

    server {
        # General connection limit: 20 connections per IP
        limit_conn conn_limit 20;

        # Login endpoint: 5 requests per minute
        location /login/ {
            limit_req zone=login_limit burst=10 nodelay;
            proxy_pass http://django;
        }

        # API endpoint: 60 requests per minute
        location /api/ {
            limit_req zone=api_limit burst=120 nodelay;
            proxy_pass http://django;
        }

        # General: 10 requests per second
        location / {
            limit_req zone=general_limit burst=20 nodelay;
            proxy_pass http://django;
        }
    }
}
```

**Recommended for AEGIS:** Azure DDoS Protection Standard (if Azure cloud) or Cloudflare WAF (if on-premises/hybrid).

---

## 8. Cincinnati Children's IT Requirements

### 8.1 Known Requirements (Public Information)

Based on publicly available information and typical enterprise healthcare IT requirements:

**Security Practices:**
- **Least Privilege Access:** Users only access programs needed for their job
- **Cyber Threat Awareness:** Participates in policy discussions with law enforcement and healthcare groups
- **Privacy Compliance:** HIPAA privacy notices and breach notification procedures
- **Employee Training:** Regular cybersecurity awareness training

**Expected Integration Points:**
- Hospital Active Directory / LDAP
- SAML SSO identity provider (likely Okta or Azure AD)
- SIEM system for centralized log aggregation (likely Splunk or QRadar)
- Network segmentation (separate VLANs for clinical systems)
- Vulnerability scanning and penetration testing requirements

### 8.2 Pre-Deployment Coordination Checklist

**Information Needed from Cincinnati Children's IT:**

#### Authentication & Access
- [ ] SAML Identity Provider metadata URL or XML file
- [ ] LDAP/Active Directory server details:
  - Server URI (ldap://ad.cincinnatichildrens.org)
  - Base DN (dc=cincinnatichildrens,dc=org)
  - Service account credentials for LDAP bind
  - User search base (ou=users,dc=...)
  - Group search base (ou=groups,dc=...)
- [ ] SAML group names for role mapping:
  - ASP Pharmacist group (e.g., "AEGIS-ASP-Pharmacist")
  - Infection Preventionist group
  - Physician group
  - Admin group
- [ ] MFA requirements and configuration
- [ ] Session timeout requirements (default: 30 minutes)
- [ ] Password policy requirements

#### Network & Infrastructure
- [ ] IP address allocation for AEGIS servers
- [ ] Firewall rules required:
  - Inbound: HTTPS (443) from hospital network
  - Outbound: PostgreSQL (5432), Redis (6379), LDAP (389/636), SAML IdP (443)
- [ ] DNS records:
  - aegis.cincinnatichildrens.org (primary)
  - aegis-internal.cchmc.org (if internal-only)
- [ ] Load balancer configuration (if HA required)
- [ ] VPN requirements for remote administration
- [ ] Network segmentation requirements (DMZ placement, VLANs)

#### SIEM & Logging
- [ ] SIEM system details (Splunk, QRadar, etc.)
- [ ] Log forwarding method:
  - Syslog (UDP 514, TCP 514, TLS 6514)
  - HTTP/HTTPS endpoint
  - Agent-based (Splunk Universal Forwarder, etc.)
- [ ] Log format requirements (JSON, CEF, LEEF, syslog)
- [ ] Required log fields and retention period

#### Security & Compliance
- [ ] Vulnerability scanning schedule and approved scanners (Nessus, Qualys, etc.)
- [ ] Penetration testing requirements (annual, biannual?)
- [ ] Security assessment questionnaire
- [ ] HIPAA compliance documentation requirements
- [ ] Business Associate Agreement (BAA) process
- [ ] Incident response contact information
- [ ] Change management process for production deployments

#### EHR Integration (If Applicable)
- [ ] Epic/Cerner FHIR API endpoints
- [ ] HL7 interface requirements
- [ ] Patient matching algorithm (MRN format, validation)
- [ ] Interface engine details (Rhapsody, Mirth, etc.)

### 8.3 Documentation to Prepare for IT Approval

**Required Documentation:**

#### 1. Security Architecture Diagram
- Network topology (servers, load balancers, databases)
- Data flow diagrams (user → AEGIS → database → external systems)
- Security boundaries and controls
- External integrations (SAML IdP, EHR, SIEM)

**Template:**
```
[Users] → [Firewall] → [Load Balancer] → [Nginx Web Server] → [Django App Servers]
                                                                      ↓
                                                               [PostgreSQL Database]
                                                                      ↓
                                                               [Encrypted Storage]
                                                                      ↓
                                                               [Backup Storage]

External Integrations:
- SAML IdP (Azure AD) - Authentication
- LDAP (Active Directory) - User lookup
- EHR (Epic FHIR API) - Patient data
- SIEM (Splunk) - Log aggregation
```

#### 2. HIPAA Security Rule Compliance Matrix
- Checklist of all HIPAA Security Rule requirements
- AEGIS implementation for each control
- Evidence/documentation references

**See Section 5.2 for full matrix.**

#### 3. Risk Assessment
- Asset inventory (servers, databases, applications)
- Threat identification (external/internal threats)
- Vulnerability assessment
- Likelihood and impact analysis
- Mitigation plans

**See Section 5.4 for template.**

#### 4. System Security Plan (SSP)
- System description and purpose
- Authentication and authorization mechanisms
- Encryption methods (in transit, at rest)
- Audit logging procedures
- Incident response plan
- Disaster recovery plan
- Backup and retention policies

#### 5. Data Flow Diagram
- Patient data ingestion (EHR → AEGIS)
- PHI access and processing
- Audit log generation
- Data export and reporting
- Encryption points

#### 6. Disaster Recovery Plan
- Backup procedures (frequency, retention, testing)
- Recovery Time Objective (RTO): 4 hours
- Recovery Point Objective (RPO): 1 hour
- Failover procedures
- Backup verification and restoration testing

#### 7. Incident Response Plan
- Incident detection and reporting procedures
- Escalation path (AEGIS team → IT security → CISO)
- Containment and eradication steps
- Breach determination criteria
- Notification procedures (patients, HHS, media)

### 8.4 Deployment Timeline with IT Coordination

**Week 1-2: Initial Coordination**
- Meet with Cincinnati Children's IT Security team
- Present security architecture and documentation
- Obtain SSO and LDAP integration details
- Discuss firewall and network requirements
- Establish communication channels (IT contact, ticketing system)

**Week 3-4: Integration Testing (Non-Production)**
- Test SAML SSO with hospital credentials in staging environment
- Validate LDAP group mapping to AEGIS roles
- Test MFA flow
- Configure network access and firewall rules
- Set up SIEM log forwarding (test environment)

**Week 5-6: Security Assessment**
- Vulnerability scanning (by IT or approved vendor)
- Address scan findings (patch, configure, document)
- Penetration testing (if required)
- Security code review (if required)

**Week 7-8: Production Deployment Preparation**
- Finalize production firewall rules
- Configure production SAML/LDAP integration
- Set up production monitoring and alerting
- Deploy to production network (behind firewall)
- SIEM integration (production logs)

**Week 9: User Acceptance Testing (UAT)**
- Pharmacists test ABX approvals workflow
- Infection preventionists test HAI detection
- Physicians test read-only access
- Validate audit logging and reporting

**Week 10: Go-Live**
- Final IT approval sign-off
- Production cutover
- Monitor for 48 hours (on-call support)
- Post-deployment review

---

## 9. Implementation Checklist

### Week 1: Django Security Settings

- [ ] **Install security libraries:**
  ```bash
  pip install django-saml2-auth==3.9.0
  pip install django-auth-ldap==4.7.0
  pip install django-auditlog==3.0.0
  pip install django-csp==3.8
  pip install django-ratelimit==4.1.0
  pip install django-defender==0.9.7
  ```

- [ ] **Configure production settings (settings/production.py):**
  - [ ] `SECRET_KEY` from environment variable
  - [ ] `DEBUG = False`
  - [ ] `ALLOWED_HOSTS` configured
  - [ ] `SECURE_SSL_REDIRECT = True`
  - [ ] HSTS headers (31536000 seconds, includeSubDomains, preload)
  - [ ] Secure cookies (SECURE, HTTPONLY, SAMESITE)
  - [ ] 30-minute session timeout
  - [ ] X-Frame-Options DENY
  - [ ] SECURE_CONTENT_TYPE_NOSNIFF
  - [ ] Password validators (12 character minimum)

- [ ] **Set up Content Security Policy:**
  - [ ] Install django-csp
  - [ ] Configure CSP directives (default-src, script-src, style-src, etc.)
  - [ ] Enable CSP_REPORT_ONLY mode initially
  - [ ] Create CSP violation report endpoint

- [ ] **Configure logging:**
  - [ ] Application logs (/var/log/aegis/django.log)
  - [ ] Security logs (/var/log/aegis/security.log)
  - [ ] Audit logs (database + file backup)
  - [ ] Error notifications (email admins on errors)

- [ ] **Test security headers:**
  ```bash
  curl -I https://aegis-staging.cincinnatichildrens.org
  ```

### Week 2: SSO Integration & Audit Logging

- [ ] **Coordinate with Cincinnati Children's IT:**
  - [ ] Obtain SAML IdP metadata URL or XML file
  - [ ] Obtain LDAP server details and service account credentials
  - [ ] Get SAML group names for role mapping
  - [ ] Clarify MFA requirements

- [ ] **Configure SAML SSO (django-saml2-auth):**
  - [ ] Install library
  - [ ] Configure SAML2_AUTH settings
  - [ ] Create custom user creation hook (apps/authentication/saml.py)
  - [ ] Implement MFA validation (AuthnContextClassRef check)
  - [ ] Add SAML URLs to urlpatterns
  - [ ] Test SSO flow in staging

- [ ] **Configure LDAP (django-auth-ldap):**
  - [ ] Install library
  - [ ] Configure AUTH_LDAP_* settings
  - [ ] Test LDAP user lookup
  - [ ] Test group mapping

- [ ] **Set up audit logging (django-auditlog):**
  - [ ] Install library
  - [ ] Add auditlog to INSTALLED_APPS
  - [ ] Add AuditlogMiddleware to MIDDLEWARE
  - [ ] Register all PHI-containing models
  - [ ] Create AegisAuditLog extended model
  - [ ] Create AegisAuditMiddleware for PHI tracking
  - [ ] Test audit log creation on model changes
  - [ ] Verify user association in logs

- [ ] **Test audit logging:**
  ```python
  # Create/update a patient record
  # Check LogEntry and AegisAuditLog tables
  # Verify employee_id, IP address, patient_mrn captured
  ```

### Week 3: RBAC & Permissions

- [ ] **Create AEGIS user model:**
  - [ ] Extend Django User model (AegisUser)
  - [ ] Add role field (asp_pharmacist, infection_preventionist, physician, admin)
  - [ ] Add employee_id, department fields
  - [ ] Run migrations

- [ ] **Create management command for role setup:**
  - [ ] apps/core/management/commands/setup_roles.py
  - [ ] Create 4 Django groups
  - [ ] Assign permissions to each group
  - [ ] Run command: `python manage.py setup_roles`

- [ ] **Implement permission decorators:**
  - [ ] Add @permission_required to all views
  - [ ] Create custom DRF permission classes
  - [ ] Test each role's access (asp_pharmacist full, physician read-only, etc.)

- [ ] **Template permission checks:**
  - [ ] Add {% if perms.app.permission %} checks to templates
  - [ ] Show/hide edit buttons based on role
  - [ ] Test UI for each role

- [ ] **Test RBAC:**
  - [ ] Create test users for each role
  - [ ] Verify asp_pharmacist can create/edit approvals
  - [ ] Verify infection_preventionist can access HAI detection
  - [ ] Verify physician can only view (no edit/delete)
  - [ ] Verify admin has full access

### Week 4: Encryption & Database Security

- [ ] **Set up Azure Database for PostgreSQL:**
  - [ ] Create PostgreSQL instance
  - [ ] Enable SSL enforcement
  - [ ] Configure firewall rules (allow Django app servers)
  - [ ] Enable Transparent Data Encryption (TDE)
  - [ ] Set up customer-managed key (CMK) in Azure Key Vault
  - [ ] Configure automated backups (35-day retention)
  - [ ] Test SSL connection from Django

- [ ] **Configure Azure Key Vault:**
  - [ ] Create Key Vault
  - [ ] Create encryption keys
  - [ ] Enable soft delete and purge protection
  - [ ] Grant Django app Managed Identity access
  - [ ] Configure key rotation policy (90 days)

- [ ] **Configure Azure Blob Storage (file storage):**
  - [ ] Create storage account
  - [ ] Enable encryption at rest (automatic)
  - [ ] Configure Django DEFAULT_FILE_STORAGE
  - [ ] Test file upload and encryption

- [ ] **Verify encryption:**
  - [ ] Database: Check Azure TDE status
  - [ ] Storage: Verify AES-256 encryption enabled
  - [ ] Backups: Verify backup encryption
  - [ ] In-transit: Test PostgreSQL SSL connection

### Week 5: Rate Limiting & DDoS Protection

- [ ] **Install django-ratelimit:**
  - [ ] pip install django-ratelimit
  - [ ] Configure Redis cache backend
  - [ ] Add @ratelimit decorator to login view (5/minute)
  - [ ] Add @ratelimit to API endpoints (100/hour per user)
  - [ ] Test rate limiting (trigger limit, verify 429 response)

- [ ] **Configure DRF throttling:**
  - [ ] Set DEFAULT_THROTTLE_CLASSES
  - [ ] Set DEFAULT_THROTTLE_RATES (anon, user, burst, sustained)
  - [ ] Create custom throttle classes if needed
  - [ ] Test API throttling

- [ ] **Set up infrastructure DDoS protection:**
  - [ ] Option A: Azure DDoS Protection Standard
    - [ ] Create DDoS protection plan
    - [ ] Enable on VNet
    - [ ] Configure alerts
  - [ ] Option B: Cloudflare WAF
    - [ ] Set up Cloudflare account
    - [ ] Point DNS to Cloudflare
    - [ ] Configure WAF rules
    - [ ] Enable DDoS protection
  - [ ] Option C: Nginx rate limiting (basic)
    - [ ] Configure limit_req_zone in nginx.conf
    - [ ] Test rate limits

- [ ] **Test DDoS protection:**
  - [ ] Use load testing tool (Apache Bench, Locust)
  - [ ] Simulate high request volume
  - [ ] Verify rate limiting kicks in
  - [ ] Verify legitimate traffic still works

### Week 6: Monitoring & Logging

- [ ] **Set up application monitoring (Sentry):**
  - [ ] Create Sentry project
  - [ ] Install sentry-sdk
  - [ ] Configure Django Sentry integration
  - [ ] Test error reporting (trigger exception)
  - [ ] Set up error alerts

- [ ] **Configure Django logging:**
  - [ ] File-based logging (django.log, security.log)
  - [ ] Email admins on errors
  - [ ] Auditlog logging
  - [ ] Test log rotation

- [ ] **Set up SIEM integration:**
  - [ ] Coordinate with IT for SIEM details (Splunk, QRadar)
  - [ ] Configure log forwarding:
    - Syslog (if syslog-based)
    - Splunk Universal Forwarder (if Splunk)
    - HTTP endpoint (if cloud SIEM)
  - [ ] Test log forwarding
  - [ ] Verify logs appear in SIEM

- [ ] **Configure Azure Monitor (if Azure):**
  - [ ] Enable Application Insights
  - [ ] Set up log analytics workspace
  - [ ] Configure alerts (high CPU, memory, errors)
  - [ ] Create dashboard

- [ ] **Set up health check endpoint:**
  ```python
  # apps/core/views.py
  from django.http import JsonResponse

  def health_check(request):
      return JsonResponse({
          'status': 'healthy',
          'database': check_database(),
          'cache': check_cache(),
      })
  ```

- [ ] **Test monitoring:**
  - [ ] Trigger error, verify Sentry notification
  - [ ] Check logs in SIEM
  - [ ] Verify health check endpoint works

### Week 7: Security Testing

- [ ] **Run vulnerability scanner:**
  - [ ] Use hospital-approved scanner (Nessus, Qualys, OpenVAS)
  - [ ] Scan staging environment
  - [ ] Review findings
  - [ ] Address critical/high findings
  - [ ] Document medium/low findings

- [ ] **OWASP Top 10 testing:**
  - [ ] SQL Injection (should be prevented by Django ORM)
  - [ ] XSS (should be prevented by Django templates + CSP)
  - [ ] CSRF (should be prevented by Django middleware)
  - [ ] Authentication bypass testing
  - [ ] Authorization testing (verify RBAC)
  - [ ] Sensitive data exposure (verify encryption)
  - [ ] Security misconfiguration (check headers, settings)

- [ ] **Penetration testing (if required):**
  - [ ] Coordinate with IT or approved vendor
  - [ ] Provide test environment
  - [ ] Review pentest report
  - [ ] Address findings

- [ ] **Code security review:**
  - [ ] Use Bandit (Python security linter)
    ```bash
    pip install bandit
    bandit -r apps/
    ```
  - [ ] Use Safety (check dependencies for vulnerabilities)
    ```bash
    pip install safety
    safety check
    ```
  - [ ] Address findings

### Week 8: Production Deployment & Go-Live

- [ ] **Final IT coordination:**
  - [ ] Submit all compliance documentation
  - [ ] Obtain production firewall rules
  - [ ] Configure production SSO integration
  - [ ] Set up production monitoring
  - [ ] Schedule go-live date

- [ ] **Production deployment:**
  - [ ] Deploy Django app to production servers
  - [ ] Configure production database
  - [ ] Run migrations
  - [ ] Load initial data (roles, permissions)
  - [ ] Configure Nginx/load balancer
  - [ ] Test production SSO login
  - [ ] Verify SIEM log forwarding

- [ ] **User Acceptance Testing (UAT):**
  - [ ] ASP pharmacists test ABX approvals workflow
  - [ ] Infection preventionists test HAI detection
  - [ ] Physicians test read-only access
  - [ ] Admins test user management
  - [ ] Validate audit logging

- [ ] **Go-live:**
  - [ ] Final IT approval sign-off
  - [ ] Production cutover
  - [ ] Monitor for 48 hours (on-call)
  - [ ] Address any issues
  - [ ] Post-deployment review

---

## 10. Security Testing Plan

### 10.1 Automated Security Scanning

**Tools:**
- **Bandit:** Python security linter
- **Safety:** Check Python dependencies for known vulnerabilities
- **OWASP ZAP:** Web application security scanner
- **Nessus/Qualys:** Vulnerability scanner (hospital-provided)

**Schedule:**
- Pre-commit: Bandit on all code changes
- Daily: Safety check on dependencies
- Weekly: OWASP ZAP scan on staging
- Monthly: Nessus/Qualys vulnerability scan

**CI/CD Integration:**
```yaml
# .github/workflows/security.yml
name: Security Scan

on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install bandit safety
      - name: Run Bandit
        run: bandit -r apps/ -f json -o bandit-report.json
      - name: Run Safety
        run: safety check --json > safety-report.json
      - name: Upload reports
        uses: actions/upload-artifact@v3
        with:
          name: security-reports
          path: |
            bandit-report.json
            safety-report.json
```

### 10.2 Manual Security Testing

**Authentication & Authorization:**
- [ ] Test SSO login flow (success and failure)
- [ ] Test MFA enforcement
- [ ] Test session timeout (30 minutes)
- [ ] Test logout functionality
- [ ] Test password reset (if applicable)
- [ ] Test role-based access control:
  - asp_pharmacist can create/edit approvals
  - infection_preventionist can access HAI detection
  - physician read-only access enforced
  - admin full access
- [ ] Test permission escalation prevention
- [ ] Test cross-user data access prevention

**Input Validation:**
- [ ] Test SQL injection (should be prevented by ORM)
- [ ] Test XSS (should be prevented by templates + CSP)
- [ ] Test CSRF (should be prevented by middleware)
- [ ] Test file upload restrictions (size, type)
- [ ] Test input length limits
- [ ] Test special character handling

**Session Management:**
- [ ] Test session fixation prevention
- [ ] Test session hijacking prevention (secure cookies)
- [ ] Test concurrent session handling
- [ ] Test session invalidation on logout

**Data Protection:**
- [ ] Verify database encryption at rest
- [ ] Verify file storage encryption
- [ ] Verify HTTPS enforcement (HTTP redirects to HTTPS)
- [ ] Verify PostgreSQL SSL connection
- [ ] Verify Redis SSL connection (if used)
- [ ] Test backup encryption

**Audit Logging:**
- [ ] Verify all PHI access is logged
- [ ] Verify user, timestamp, IP address captured
- [ ] Verify audit logs are immutable
- [ ] Test audit log queries
- [ ] Test audit log export (CSV)

**Rate Limiting:**
- [ ] Test login rate limiting (5 attempts/minute)
- [ ] Test API rate limiting (100 requests/hour)
- [ ] Verify 429 response on limit exceeded
- [ ] Verify legitimate users not affected

### 10.3 Penetration Testing

**Scope:**
- Web application (AEGIS Django app)
- API endpoints
- Authentication and authorization
- Data access and manipulation

**Out of Scope:**
- DDoS attacks (infrastructure testing only)
- Social engineering
- Physical security

**Methodology:**
- OWASP Testing Guide
- OWASP Top 10
- NIST SP 800-115 (Technical Guide to Information Security Testing)

**Deliverables:**
- Penetration test report
- Findings with severity ratings
- Remediation recommendations
- Re-test results after fixes

**Schedule:**
- Initial pentest: Before production go-live
- Annual pentest: Every 12 months
- Ad-hoc pentest: After major changes

---

## 11. Monitoring & Alerting

### 11.1 Application Monitoring

**Sentry (Error Tracking):**

```python
# settings/production.py
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn=os.environ['SENTRY_DSN'],
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
    send_default_pii=False,  # Don't send PII to Sentry
    environment='production',
    release=os.environ.get('RELEASE_VERSION', 'unknown'),
)
```

**Alert On:**
- Uncaught exceptions
- 500 errors (server errors)
- High error rate (>1% of requests)
- Slow transactions (>2 seconds)

### 11.2 Security Monitoring

**Monitor:**
- Failed login attempts (>5 in 5 minutes)
- Unusual PHI access patterns (>100 patients in 1 hour)
- Privilege escalation attempts
- Admin actions (user creation, permission changes)
- Configuration changes
- Database queries (slow query log)

**Alert On:**
- Multiple failed logins (potential brute force)
- Bulk PHI access (potential breach)
- Admin privilege changes
- Security log errors

**Implementation:**
```python
# apps/core/monitoring.py
from django.core.mail import send_mail
from apps.core.models import AegisAuditLog
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('django.security')

def check_unusual_access():
    """
    Check for unusual PHI access patterns.
    Run every hour via Celery task.
    """
    one_hour_ago = datetime.now() - timedelta(hours=1)

    # Check for high-volume access
    high_volume = AegisAuditLog.objects.filter(
        log_entry__timestamp__gte=one_hour_ago
    ).values('employee_id').annotate(
        patient_count=Count('patient_mrn', distinct=True)
    ).filter(patient_count__gt=100)

    if high_volume:
        for user_access in high_volume:
            alert_message = (
                f"SECURITY ALERT: User {user_access['employee_id']} accessed "
                f"{user_access['patient_count']} patient records in the last hour"
            )
            logger.warning(alert_message)
            send_mail(
                'AEGIS Security Alert: Unusual PHI Access',
                alert_message,
                'aegis-security@cincinnatichildrens.org',
                ['security-team@cincinnatichildrens.org'],
                fail_silently=False,
            )
```

### 11.3 Infrastructure Monitoring

**Azure Monitor (if Azure):**
- CPU usage (alert if >80% for 10 minutes)
- Memory usage (alert if >90% for 5 minutes)
- Disk usage (alert if >85%)
- Database connections (alert if near max)
- Response time (alert if >2 seconds average)
- Error rate (alert if >1%)

**Uptime Monitoring:**
- Use UptimeRobot or Pingdom
- Check every 5 minutes
- Alert if down for 3 consecutive checks
- Monitor: https://aegis.cincinnatichildrens.org/health/

**SSL Certificate Monitoring:**
- Alert 30 days before expiration
- Auto-renewal with Let's Encrypt (if applicable)

---

## 12. Documentation for IT Approval

### 12.1 Security Architecture Diagram

**Create diagram showing:**
- User access flow (user → firewall → load balancer → web server → app server)
- Data flow (app → database → encrypted storage → backup)
- External integrations (SAML IdP, LDAP, EHR, SIEM)
- Security controls at each layer (firewall, WAF, encryption, audit logging)

**Tools:** Draw.io, Lucidchart, Microsoft Visio

### 12.2 HIPAA Security Rule Compliance Documentation

**Create spreadsheet with columns:**
- HIPAA Control (§ citation)
- Requirement Description
- AEGIS Implementation
- Evidence/Documentation
- Status (Implemented, In Progress, Not Applicable)

**See Section 5.2 for full compliance matrix.**

### 12.3 Risk Assessment Report

**Use NIST SP 800-30 framework:**
1. Prepare for Assessment
2. Conduct Assessment (identify threats, vulnerabilities, impacts)
3. Communicate Results
4. Maintain Assessment (annual updates)

**See Section 5.4 for template.**

### 12.4 System Security Plan (SSP)

**NIST SP 800-18 format:**
- System Identification
- System Categorization (FIPS 199)
- Security Controls (NIST SP 800-53)
- Encryption Implementation
- Audit Logging Procedures
- Incident Response Plan
- Disaster Recovery Plan

### 12.5 Business Associate Agreement (BAA)

**If using cloud services (Azure, AWS):**
- Obtain signed BAA from cloud provider
- Azure: BAA available in Online Services Terms
- AWS: Request BAA through AWS support
- Document annual verification process

---

## Appendix: Technology Stack Summary

### Core Framework
- **Django:** 4.2 LTS or 5.0+
- **Python:** 3.11+
- **Database:** PostgreSQL 15+ (Azure Database for PostgreSQL)
- **Cache:** Redis 7+ (Azure Cache for Redis)
- **Web Server:** Nginx 1.24+
- **App Server:** Gunicorn 21+

### Authentication & Authorization
- **django-saml2-auth:** 3.9.0 (Grafana fork preferred)
- **django-auth-ldap:** 4.7.0
- **Multi-factor:** Enforced at SAML IdP (Okta/Azure AD)

### Audit Logging
- **django-auditlog:** 3.0.0
- **Custom:** AegisAuditLog extended model

### Security
- **django-csp:** 3.8 (Content Security Policy)
- **django-ratelimit:** 4.1.0 (Rate limiting)
- **django-defender:** 0.9.7 (Brute force protection)

### Encryption
- **Database:** Azure PostgreSQL TDE (AES-256)
- **Storage:** Azure Blob Storage encryption (AES-256)
- **In-Transit:** TLS 1.2+ (HTTPS, PostgreSQL SSL, Redis SSL)
- **Key Management:** Azure Key Vault

### DDoS Protection
- **Recommended:** Azure DDoS Protection Standard or Cloudflare WAF
- **Fallback:** Nginx rate limiting

### Monitoring & Logging
- **Error Tracking:** Sentry
- **APM:** Azure Application Insights or New Relic
- **Logging:** Python logging + file rotation
- **SIEM:** Splunk or QRadar (hospital-provided)
- **Uptime:** UptimeRobot or Pingdom

### Development & Deployment
- **Version Control:** Git (GitHub/GitLab)
- **CI/CD:** GitHub Actions or Azure DevOps
- **Containerization:** Docker + Docker Compose
- **Orchestration:** Azure App Service or Kubernetes (optional)

---

## References

**Django Official Documentation:**
- Security in Django: https://docs.djangoproject.com/en/6.0/topics/security/
- Settings Reference: https://docs.djangoproject.com/en/6.0/ref/settings/

**Security Standards:**
- HIPAA Security Rule: https://www.hhs.gov/hipaa/for-professionals/security/
- NIST SP 800-53: Security and Privacy Controls
- NIST SP 800-111: Guide to Storage Encryption
- NIST SP 800-57: Key Management Recommendations
- OWASP Top 10: https://owasp.org/www-project-top-ten/

**Library Documentation:**
- django-saml2-auth: https://github.com/grafana/django-saml2-auth
- django-auth-ldap: https://django-auth-ldap.readthedocs.io/
- django-auditlog: https://django-auditlog.readthedocs.io/
- django-csp: https://django-csp.readthedocs.io/
- django-ratelimit: https://django-ratelimit.readthedocs.io/
- Django REST Framework: https://www.django-rest-framework.org/

**Healthcare Security:**
- 2026 HIPAA Changes: https://www.hipaavault.com/resources/2026-hipaa-changes/
- HIPAA Audit Log Requirements: https://www.kiteworks.com/hipaa-compliance/hipaa-audit-log-requirements/
- HIPAA Retention Requirements: https://www.hipaajournal.com/hipaa-retention-requirements/

**Azure Security:**
- Azure Database for PostgreSQL Security: https://learn.microsoft.com/en-us/azure/postgresql/
- Azure Key Vault: https://learn.microsoft.com/en-us/azure/key-vault/
- Azure DDoS Protection: https://learn.microsoft.com/en-us/azure/ddos-protection/

---

**Document Version:** 1.0
**Last Updated:** 2026-02-07
**Next Review:** 2026-03-07
**Owner:** AEGIS Security Team
