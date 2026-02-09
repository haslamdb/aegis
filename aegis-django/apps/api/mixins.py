"""
DRF mixins for AEGIS API ViewSets.
"""

import logging

logger = logging.getLogger('apps.api')


class AuditLogMixin:
    """
    Mixin that creates an audit trail entry on write operations.

    Logs the action, user, and IP address for HIPAA compliance.
    Works with any ViewSet whose model has a create_audit_entry() method.
    """

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    def perform_create(self, serializer):
        instance = serializer.save()
        if hasattr(instance, 'create_audit_entry'):
            instance.create_audit_entry(
                action='created',
                user=self.request.user,
                ip_address=self.get_client_ip(self.request),
            )
        return instance

    def perform_update(self, serializer):
        instance = serializer.save()
        if hasattr(instance, 'create_audit_entry'):
            instance.create_audit_entry(
                action='updated',
                user=self.request.user,
                ip_address=self.get_client_ip(self.request),
            )
        return instance
