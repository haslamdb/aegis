"""
Authentication backends for SSO integration.

Supports:
- SAML 2.0 (primary) - For Cincinnati Children's SSO
- LDAP/Active Directory (fallback) - For domain authentication
"""

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

from .models import UserRole

User = get_user_model()


class SAMLAuthBackend(ModelBackend):
    """
    SAML 2.0 authentication backend.

    Integrates with django-saml2-auth for SSO.
    Maps SAML attributes to Django User model and role assignments.
    """

    def authenticate(self, request, saml_attributes=None, **kwargs):
        """
        Authenticate user via SAML assertion.

        SAML attributes expected from Cincinnati Children's IdP:
        - NameID: Unique user identifier (username)
        - mail: Email address
        - givenName: First name
        - sn: Surname (last name)
        - memberOf: AD groups (list)
        - department: Department
        - title: Job title
        """
        if not saml_attributes:
            return None

        # Extract user identifier (NameID)
        username = saml_attributes.get('NameID', [''])[0]
        if not username:
            return None

        # Extract user attributes
        email = saml_attributes.get('mail', [''])[0]
        first_name = saml_attributes.get('givenName', [''])[0]
        last_name = saml_attributes.get('sn', [''])[0]
        department = saml_attributes.get('department', [''])[0]
        job_title = saml_attributes.get('title', [''])[0]
        ad_groups = saml_attributes.get('memberOf', [])

        # Determine role from AD groups
        role = self.map_ad_groups_to_role(ad_groups)

        # Get or create user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'department': department,
                'job_title': job_title,
                'role': role,
                'is_active': True,
            }
        )

        if not created:
            # Update existing user attributes from IdP
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.department = department
            user.job_title = job_title
            user.role = role
            user.ad_groups = ad_groups
            if not user.sso_id:
                user.sso_id = username
            user.save(update_fields=[
                'email', 'first_name', 'last_name', 'department',
                'job_title', 'role', 'ad_groups', 'sso_id',
            ])

        # Mark session as SAML authenticated
        if request and hasattr(request, 'session'):
            request.session['saml_authenticated'] = True

        return user

    def map_ad_groups_to_role(self, ad_groups):
        """
        Map Active Directory groups to AEGIS roles.

        AD Group Mapping (Cincinnati Children's):
        - CN=AEGIS-ASP-Pharmacists,OU=Groups,DC=cchmc,DC=org → ASP_PHARMACIST
        - CN=AEGIS-Infection-Preventionists,OU=Groups,DC=cchmc,DC=org → INFECTION_PREVENTIONIST
        - CN=AEGIS-Physicians,OU=Groups,DC=cchmc,DC=org → PHYSICIAN
        - CN=AEGIS-Admins,OU=Groups,DC=cchmc,DC=org → ADMIN
        """
        # Normalize AD groups to lowercase for case-insensitive matching
        ad_groups_lower = [g.lower() for g in ad_groups]

        # Check for admin role first (highest privilege)
        if any('aegis-admins' in g for g in ad_groups_lower):
            return UserRole.ADMIN

        # Check for ASP Pharmacist
        if any('aegis-asp-pharmacists' in g for g in ad_groups_lower):
            return UserRole.ASP_PHARMACIST

        # Check for Infection Preventionist
        if any('aegis-infection-preventionists' in g for g in ad_groups_lower):
            return UserRole.INFECTION_PREVENTIONIST

        # Check for Physician
        if any('aegis-physicians' in g for g in ad_groups_lower):
            return UserRole.PHYSICIAN

        # Default to Physician role for any authenticated user
        return UserRole.PHYSICIAN


class LDAPAuthBackend:
    """
    LDAP/Active Directory authentication backend.

    Fallback authentication method when SAML is unavailable.
    Uses django-auth-ldap for LDAP integration.

    Configuration in settings.py:
    - AUTH_LDAP_SERVER_URI: LDAP server URL
    - AUTH_LDAP_BIND_DN: Bind DN for LDAP queries
    - AUTH_LDAP_USER_SEARCH: User search base and filter
    - AUTH_LDAP_GROUP_SEARCH: Group search base and filter
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user via LDAP.

        This is a simplified implementation. In production, use django-auth-ldap
        which provides:
        - Connection pooling
        - Caching
        - Attribute mapping
        - Group synchronization
        """
        if not username or not password:
            return None

        try:
            # Import LDAP backend from django-auth-ldap
            from django_auth_ldap.backend import LDAPBackend

            ldap_backend = LDAPBackend()
            user = ldap_backend.authenticate(request, username=username, password=password)

            if user:
                # Mark session as LDAP authenticated
                if request and hasattr(request, 'session'):
                    request.session['ldap_authenticated'] = True

            return user

        except ImportError:
            # django-auth-ldap not installed
            return None
        except Exception as e:
            # Log LDAP authentication error
            import logging
            logger = logging.getLogger('apps.authentication.audit')
            logger.error(f"LDAP authentication failed for {username}: {str(e)}")
            return None

    def get_user(self, user_id):
        """Get user by ID."""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


class MultiAuthBackend(ModelBackend):
    """
    Multi-method authentication backend.

    Attempts authentication in this order:
    1. SAML SSO (if saml_attributes provided)
    2. LDAP (if username and password provided)
    3. Local password (if username and password provided)
    """

    def authenticate(self, request, username=None, password=None, saml_attributes=None, **kwargs):
        """
        Authenticate using multiple methods.
        """
        # Try SAML first
        if saml_attributes:
            saml_backend = SAMLAuthBackend()
            user = saml_backend.authenticate(request, saml_attributes=saml_attributes)
            if user:
                return user

        # Try LDAP next
        if username and password:
            ldap_backend = LDAPAuthBackend()
            user = ldap_backend.authenticate(request, username=username, password=password)
            if user:
                return user

            # Try local password authentication
            user = super().authenticate(request, username=username, password=password)
            if user:
                if request and hasattr(request, 'session'):
                    request.session['local_authenticated'] = True
                return user

        return None
