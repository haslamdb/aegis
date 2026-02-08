"""Notifications models - Multi-channel notification system."""

from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel, UUIDModel

class NotificationChannel(models.TextChoices):
    """Notification delivery channels."""
    EMAIL = 'email', 'Email'
    TEAMS = 'teams', 'Microsoft Teams'
    SMS = 'sms', 'SMS'

class NotificationStatus(models.TextChoices):
    """Notification delivery status."""
    PENDING = 'pending', 'Pending'
    SENT = 'sent', 'Sent'
    DELIVERED = 'delivered', 'Delivered'
    FAILED = 'failed', 'Failed'

class NotificationLog(UUIDModel, TimeStampedModel):
    """Log of all sent notifications."""
    alert = models.ForeignKey('alerts.Alert', on_delete=models.CASCADE, related_name='notifications', null=True)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    recipient = models.CharField(max_length=255, help_text="Email, Teams ID, or phone number")
    status = models.CharField(max_length=20, choices=NotificationStatus.choices, default=NotificationStatus.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'notification_log'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['alert', '-created_at']),
            models.Index(fields=['channel', 'status']),
        ]
