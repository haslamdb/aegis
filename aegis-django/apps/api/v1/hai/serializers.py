"""Serializers for the HAI Detection API."""

from rest_framework import serializers

from apps.hai_detection.models import (
    HAICandidate, HAIClassification, HAIReview,
    ReviewerDecision,
)


class HAIClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = HAIClassification
        fields = [
            'id', 'decision', 'confidence', 'alternative_source',
            'is_mbi_lcbi', 'supporting_evidence', 'contradicting_evidence',
            'reasoning', 'model_used', 'prompt_version',
            'tokens_used', 'processing_time_ms',
            'extraction_data', 'rules_result', 'strictness_level',
            'created_at',
        ]


class HAIReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = HAIReview
        fields = [
            'id', 'queue_type', 'reviewed', 'reviewer',
            'reviewer_decision', 'reviewer_notes',
            'llm_decision', 'is_override', 'override_reason',
            'override_reason_category', 'extraction_corrections',
            'created_at', 'reviewed_at',
        ]


class HAICandidateListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (no classifications/reviews)."""

    class Meta:
        model = HAICandidate
        fields = [
            'id', 'hai_type', 'patient_id', 'patient_mrn',
            'patient_name', 'patient_location',
            'culture_id', 'culture_date', 'organism',
            'device_days_at_culture', 'meets_initial_criteria',
            'status', 'nhsn_reported',
            'created_at', 'updated_at',
        ]


class HAICandidateDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested classifications and reviews."""
    classifications = HAIClassificationSerializer(many=True, read_only=True)
    reviews = HAIReviewSerializer(many=True, read_only=True)

    class Meta:
        model = HAICandidate
        fields = [
            'id', 'hai_type', 'patient_id', 'patient_mrn',
            'patient_name', 'patient_location',
            'culture_id', 'culture_date', 'organism',
            'device_info', 'device_days_at_culture',
            'meets_initial_criteria', 'exclusion_reason',
            'status', 'type_specific_data',
            'nhsn_reported', 'nhsn_reported_at',
            'created_at', 'updated_at',
            'classifications', 'reviews',
        ]


class HAIReviewSubmitSerializer(serializers.Serializer):
    """Input for submitting an IP review."""
    decision = serializers.ChoiceField(choices=[
        ('confirmed', 'Confirmed HAI'),
        ('rejected', 'Not HAI'),
        ('needs_more_info', 'Needs More Information'),
    ])
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    override_reason = serializers.CharField(required=False, allow_blank=True, default='')
    override_reason_category = serializers.CharField(required=False, allow_blank=True, default='')
    extraction_corrections = serializers.JSONField(required=False, default=None)
