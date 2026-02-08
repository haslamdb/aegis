"""
Authentication app configuration.
"""

from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    """Configuration for the authentication app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.authentication'
    verbose_name = 'Authentication & Authorization'

    def ready(self):
        """
        Import signal handlers when Django starts.

        This ensures login/logout signals are registered.
        """
        # Import middleware to register signals
        from . import middleware  # noqa: F401
