"""
Audit middleware for HIPAA compliance.

Logs all authenticated requests to audit.log with 7-year retention.
Tracks user sessions and login/logout events.
"""

import logging
import threading
from django.utils import timezone
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .models import UserSession

# Thread-local storage for current user
_thread_locals = threading.local()

# Audit logger (configured in settings.py to write to audit.log)
audit_logger = logging.getLogger('apps.authentication.audit')


def get_current_user():
    """
    Get the current user from thread-local storage.

    Used by models to automatically set created_by/updated_by fields.
    """
    return getattr(_thread_locals, 'user', None)


def get_client_ip(request):
    """
    Extract client IP address from request.

    Handles both direct connections and proxied connections (X-Forwarded-For).
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class AuditMiddleware:
    """
    Middleware to log all authenticated requests for HIPAA compliance.

    Logs:
    - User who made the request
    - Timestamp
    - HTTP method and path
    - IP address
    - User agent
    - Response status code
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store user in thread-local storage
        if hasattr(request, 'user') and request.user.is_authenticated:
            _thread_locals.user = request.user
        else:
            _thread_locals.user = None

        try:
            # Process request
            response = self.get_response(request)

            # Log audit entry for authenticated requests
            if hasattr(request, 'user') and request.user.is_authenticated:
                self.log_request(request, response)

            return response
        finally:
            _thread_locals.user = None

    def log_request(self, request, response):
        """Log authenticated request to audit log."""
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        audit_logger.info(
            f"USER={request.user.username} "
            f"ROLE={request.user.get_role_display()} "
            f"METHOD={request.method} "
            f"PATH={request.path} "
            f"STATUS={response.status_code} "
            f"IP={ip_address} "
            f"USER_AGENT={user_agent}"
        )


class SessionTrackingMiddleware:
    """
    Middleware to track user sessions for HIPAA audit compliance.

    Creates UserSession records on login and updates them on logout.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response


@receiver(user_logged_in)
def create_user_session(sender, request, user, **kwargs):
    """
    Signal handler to create UserSession on login.

    Called automatically by Django when user logs in.
    """
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    # Determine login method
    login_method = 'local'
    if hasattr(request, 'session'):
        if request.session.get('saml_authenticated'):
            login_method = 'saml'
        elif request.session.get('ldap_authenticated'):
            login_method = 'ldap'

    # Ensure session is saved so session_key is available
    if not request.session.session_key:
        request.session.save()

    # Create session record
    session = UserSession.objects.create(
        user=user,
        session_key=request.session.session_key,
        ip_address=ip_address,
        user_agent=user_agent,
        login_method=login_method,
        is_active=True
    )

    # Update user's last login IP
    user.last_login_ip = ip_address
    user.reset_failed_login()  # Reset failed login counter
    user.save(update_fields=['last_login_ip'])

    # Log to audit log
    audit_logger.info(
        f"LOGIN SUCCESS: USER={user.username} "
        f"ROLE={user.get_role_display()} "
        f"METHOD={login_method} "
        f"IP={ip_address} "
        f"SESSION={session.id}"
    )


@receiver(user_logged_out)
def end_user_session(sender, request, user, **kwargs):
    """
    Signal handler to end UserSession on logout.

    Called automatically by Django when user logs out.
    """
    if user and request.session.session_key:
        try:
            session = UserSession.objects.get(
                user=user,
                session_key=request.session.session_key,
                is_active=True
            )
            session.end_session()

            # Log to audit log
            audit_logger.info(
                f"LOGOUT: USER={user.username} "
                f"SESSION={session.id} "
                f"DURATION={session.duration}"
            )
        except UserSession.DoesNotExist:
            pass


def log_failed_login(username, ip_address, reason='Invalid credentials'):
    """
    Log failed login attempt.

    Call this function when a login attempt fails.
    """
    audit_logger.warning(
        f"LOGIN FAILED: USERNAME={username} "
        f"REASON={reason} "
        f"IP={ip_address}"
    )


def log_account_locked(user, ip_address):
    """
    Log account lockout event.

    Call this function when an account is locked due to failed login attempts.
    """
    audit_logger.warning(
        f"ACCOUNT LOCKED: USER={user.username} "
        f"FAILED_ATTEMPTS={user.failed_login_attempts} "
        f"LOCKED_UNTIL={user.account_locked_until} "
        f"IP={ip_address}"
    )


def log_permission_denied(user, permission, ip_address, path):
    """
    Log permission denied event.

    Call this function when a user attempts to access a resource they don't have permission for.
    """
    audit_logger.warning(
        f"PERMISSION DENIED: USER={user.username} "
        f"ROLE={user.get_role_display()} "
        f"PERMISSION={permission} "
        f"PATH={path} "
        f"IP={ip_address}"
    )


def log_sensitive_data_access(user, data_type, record_id, ip_address):
    """
    Log access to sensitive patient data.

    Use this function to log when users access PHI (Protected Health Information).

    Example:
        log_sensitive_data_access(request.user, 'patient_record', patient_id, get_client_ip(request))
    """
    audit_logger.info(
        f"DATA ACCESS: USER={user.username} "
        f"ROLE={user.get_role_display()} "
        f"DATA_TYPE={data_type} "
        f"RECORD_ID={record_id} "
        f"IP={ip_address}"
    )


def log_data_modification(user, action, model, record_id, ip_address, changes=None):
    """
    Log modifications to sensitive data.

    Use this function to log when users create/update/delete PHI.

    Example:
        log_data_modification(request.user, 'UPDATE', 'Alert', alert_id, get_client_ip(request), changes={'status': 'resolved'})
    """
    changes_str = str(changes) if changes else ''
    audit_logger.info(
        f"DATA {action}: USER={user.username} "
        f"ROLE={user.get_role_display()} "
        f"MODEL={model} "
        f"RECORD_ID={record_id} "
        f"IP={ip_address} "
        f"CHANGES={changes_str}"
    )
