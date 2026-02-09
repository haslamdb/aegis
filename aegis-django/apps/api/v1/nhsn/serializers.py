"""Serializers for the NHSN Reporting API."""

from rest_framework import serializers

from apps.nhsn_reporting.models import (
    NHSNEvent,
    DenominatorMonthly,
    AUMonthlySummary,
    ARQuarterlySummary,
)


class NHSNEventListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    class Meta:
        model = NHSNEvent
        fields = [
            'id', 'event_date', 'hai_type', 'location_code',
            'pathogen_code', 'reported', 'reported_at',
            'created_at',
        ]


class NHSNEventDetailSerializer(serializers.ModelSerializer):
    """Full serializer with candidate info."""
    candidate_id = serializers.UUIDField(source='candidate.id', read_only=True, default=None)

    class Meta:
        model = NHSNEvent
        fields = [
            'id', 'candidate_id', 'event_date', 'hai_type',
            'location_code', 'pathogen_code',
            'reported', 'reported_at',
            'created_at', 'updated_at',
        ]


class MarkSubmittedSerializer(serializers.Serializer):
    """Input for batch mark-submitted action."""
    event_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
    )


class DenominatorMonthlySerializer(serializers.ModelSerializer):
    class Meta:
        model = DenominatorMonthly
        fields = [
            'id', 'month', 'location_code', 'location_type',
            'patient_days', 'central_line_days', 'urinary_catheter_days',
            'ventilator_days', 'admissions',
            'central_line_utilization', 'urinary_catheter_utilization',
            'ventilator_utilization', 'submitted_at',
            'created_at',
        ]


class AUMonthlySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = AUMonthlySummary
        fields = [
            'id', 'reporting_month', 'location_code', 'location_type',
            'patient_days', 'admissions', 'submitted_at',
            'created_at',
        ]


class ARQuarterlySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ARQuarterlySummary
        fields = [
            'id', 'reporting_quarter', 'location_code', 'location_type',
            'submitted_at', 'created_at',
        ]
