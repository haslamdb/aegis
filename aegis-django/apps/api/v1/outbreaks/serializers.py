"""Serializers for the Outbreak Detection API."""

from rest_framework import serializers

from apps.outbreak_detection.models import OutbreakCluster, ClusterCase, ClusterStatus


class ClusterCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClusterCase
        fields = [
            'id', 'source', 'source_id',
            'patient_id', 'patient_mrn',
            'event_date', 'organism', 'infection_type', 'unit',
            'added_at',
        ]


class OutbreakClusterListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (no cases)."""

    class Meta:
        model = OutbreakCluster
        fields = [
            'id', 'infection_type', 'organism', 'unit',
            'case_count', 'first_case_date', 'last_case_date',
            'window_days', 'status', 'severity',
            'created_at', 'updated_at',
        ]


class OutbreakClusterDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested cases."""
    cases = ClusterCaseSerializer(many=True, read_only=True)

    class Meta:
        model = OutbreakCluster
        fields = [
            'id', 'infection_type', 'organism', 'unit',
            'case_count', 'first_case_date', 'last_case_date',
            'window_days', 'status', 'severity',
            'resolved_at', 'resolved_by', 'resolution_notes',
            'created_at', 'updated_at',
            'cases',
        ]


class ClusterStatusUpdateSerializer(serializers.Serializer):
    """Input for updating cluster status."""
    status = serializers.ChoiceField(choices=ClusterStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
