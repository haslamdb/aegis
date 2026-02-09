"""Serializers for the Alert API."""

from rest_framework import serializers

from apps.alerts.models import (
    Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity, ResolutionReason,
)


class AlertAuditSerializer(serializers.ModelSerializer):
    performed_by = serializers.StringRelatedField()

    class Meta:
        model = AlertAudit
        fields = [
            'id', 'action', 'performed_by', 'performed_at',
            'old_status', 'new_status', 'details',
        ]


class AlertListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (no details/audit)."""

    class Meta:
        model = Alert
        fields = [
            'id', 'alert_type', 'source_module', 'title', 'summary',
            'patient_mrn', 'patient_name', 'patient_location',
            'severity', 'status', 'priority_score',
            'created_at', 'acknowledged_at', 'resolved_at',
        ]


class AlertDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested audit log and user references."""
    audit_log = AlertAuditSerializer(many=True, read_only=True)
    acknowledged_by = serializers.StringRelatedField()
    resolved_by = serializers.StringRelatedField()
    snoozed_by = serializers.StringRelatedField()

    class Meta:
        model = Alert
        fields = [
            'id', 'alert_type', 'source_module', 'source_id',
            'title', 'summary', 'details',
            'patient_id', 'patient_mrn', 'patient_name', 'patient_location',
            'severity', 'priority_score', 'status',
            'sent_at', 'acknowledged_at', 'acknowledged_by',
            'resolved_at', 'resolved_by', 'resolution_reason', 'resolution_notes',
            'snoozed_until', 'snoozed_by',
            'notes', 'expires_at',
            'notification_sent', 'notification_channels',
            'created_at', 'updated_at',
            'audit_log',
        ]


class AlertAcknowledgeSerializer(serializers.Serializer):
    """Input for acknowledging an alert."""
    pass  # No required input


class AlertSnoozeSerializer(serializers.Serializer):
    """Input for snoozing an alert."""
    hours = serializers.FloatField(min_value=0.25, max_value=72)


class AlertResolveSerializer(serializers.Serializer):
    """Input for resolving an alert."""
    reason = serializers.ChoiceField(choices=ResolutionReason.choices)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class AlertAddNoteSerializer(serializers.Serializer):
    """Input for adding a note to an alert."""
    note = serializers.CharField(min_length=1)
