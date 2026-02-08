"""Metrics models - Activity tracking for all AEGIS modules."""

from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel

class ProviderActivity(TimeStampedModel):
    """Track provider ASP/IP actions."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action_type = models.CharField(max_length=100, help_text="Type of action")
    module = models.CharField(max_length=100, help_text="AEGIS module")
    patient_mrn = models.CharField(max_length=100, null=True, blank=True)
    details = models.JSONField(default=dict)
    duration_seconds = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'provider_activity'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['module', '-created_at']),
        ]

class DailySnapshot(TimeStampedModel):
    """Daily aggregated metrics."""
    date = models.DateField(unique=True, db_index=True)
    total_alerts = models.IntegerField(default=0)
    alerts_by_type = models.JSONField(default=dict)
    alerts_by_severity = models.JSONField(default=dict)
    total_actions = models.IntegerField(default=0)
    actions_by_module = models.JSONField(default=dict)
    
    class Meta:
        db_table = 'daily_snapshots'
        ordering = ['-date']
