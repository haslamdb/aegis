"""Serializers for the Guideline Adherence API."""

from rest_framework import serializers

from apps.guideline_adherence.models import (
    BundleEpisode, ElementResult, EpisodeAssessment, EpisodeReview,
    ReviewDecision,
)


class ElementResultSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = ElementResult
        fields = [
            'id', 'element_id', 'element_name', 'element_description',
            'status', 'required', 'value', 'notes',
            'deadline', 'completed_at', 'time_window_hours',
            'is_overdue', 'created_at',
        ]


class EpisodeAssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EpisodeAssessment
        fields = [
            'id', 'assessment_type', 'primary_determination', 'confidence',
            'reasoning', 'supporting_evidence', 'extraction_data',
            'model_used', 'response_time_ms', 'created_at',
        ]


class EpisodeReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = EpisodeReview
        fields = [
            'id', 'reviewer', 'reviewer_decision', 'llm_decision',
            'is_override', 'override_reason_category', 'deviation_type',
            'extraction_corrections', 'notes', 'reviewed_at',
        ]


class EpisodeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    class Meta:
        model = BundleEpisode
        fields = [
            'id', 'patient_mrn', 'patient_name', 'patient_unit',
            'bundle_id', 'bundle_name', 'status',
            'adherence_percentage', 'adherence_level',
            'elements_total', 'elements_met', 'elements_not_met', 'elements_pending',
            'trigger_time', 'review_status',
            'created_at',
        ]


class EpisodeDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested elements, latest assessment, and reviews."""
    element_results = ElementResultSerializer(many=True, read_only=True)
    latest_assessment = serializers.SerializerMethodField()
    reviews = EpisodeReviewSerializer(many=True, read_only=True)

    class Meta:
        model = BundleEpisode
        fields = [
            'id', 'patient_id', 'patient_mrn', 'patient_name',
            'encounter_id', 'patient_unit',
            'bundle_id', 'bundle_name',
            'trigger_type', 'trigger_code', 'trigger_description', 'trigger_time',
            'patient_age_days', 'patient_age_months',
            'status', 'adherence_percentage', 'adherence_level',
            'elements_total', 'elements_applicable', 'elements_met',
            'elements_not_met', 'elements_pending',
            'review_status', 'overall_determination',
            'clinical_context', 'last_assessment_at', 'completed_at',
            'created_at', 'updated_at',
            'element_results', 'latest_assessment', 'reviews',
        ]

    def get_latest_assessment(self, obj):
        assessment = obj.assessments.order_by('-created_at').first()
        if assessment:
            return EpisodeAssessmentSerializer(assessment).data
        return None


class EpisodeReviewSubmitSerializer(serializers.Serializer):
    """Input for submitting an episode review."""
    reviewer_decision = serializers.ChoiceField(choices=ReviewDecision.choices)
    override_reason = serializers.CharField(required=False, allow_blank=True, default='')
    deviation_type = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')
