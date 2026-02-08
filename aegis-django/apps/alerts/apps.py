"""Alerts app configuration."""

from django.apps import AppConfig


class AlertsConfig(AppConfig):
    """Configuration for the alerts app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.alerts'
    verbose_name = 'Alerts'

    def ready(self):
        """Import signal handlers when Django starts."""
        from . import signals  # noqa: F401
