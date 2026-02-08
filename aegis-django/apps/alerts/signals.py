"""Signal handlers for alerts app."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Alert, AlertAudit


@receiver(pre_save, sender=Alert)
def capture_old_status(sender, instance, **kwargs):
    """Capture old status before saving."""
    if instance.pk:
        try:
            old_instance = Alert.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Alert.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Alert)
def create_audit_entry(sender, instance, created, **kwargs):
    """Create audit entry when alert is created or updated."""
    from apps.authentication.middleware import get_current_user
    
    if created:
        action = 'CREATED'
        old_status = None
        new_status = instance.status
    else:
        action = 'UPDATED'
        old_status = getattr(instance, '_old_status', None)
        new_status = instance.status
        
        # Determine specific action based on status change
        if old_status and old_status != new_status:
            if new_status == 'acknowledged':
                action = 'ACKNOWLEDGED'
            elif new_status == 'resolved':
                action = 'RESOLVED'
            elif new_status == 'snoozed':
                action = 'SNOOZED'
    
    AlertAudit.objects.create(
        alert=instance,
        action=action,
        performed_by=get_current_user(),
        old_status=old_status,
        new_status=new_status,
    )
