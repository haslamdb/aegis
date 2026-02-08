"""
AEGIS Authentication App

Provides:
- Custom User model with 4-role RBAC
- SAML and LDAP SSO integration
- HIPAA audit logging
- Permission decorators and mixins
"""

default_app_config = 'apps.authentication.apps.AuthenticationConfig'
