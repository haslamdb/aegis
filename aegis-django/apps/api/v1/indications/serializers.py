"""Serializers for the ABX Indications API."""

from rest_framework import serializers

from apps.abx_indications.models import (
    IndicationCandidate, IndicationReview,
    SyndromeDecision, AgentDecision,
)


class IndicationReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = IndicationReview
        fields = [
            'id', 'reviewer_name', 'syndrome_decision',
            'confirmed_syndrome', 'confirmed_syndrome_display',
            'agent_decision', 'agent_notes',
            'is_override', 'notes', 'reviewed_at',
        ]

    def get_reviewer_name(self, obj):
        if obj.reviewer:
            return obj.reviewer.username
        return 'System'


class CandidateListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    has_red_flag = serializers.BooleanField(read_only=True)

    class Meta:
        model = IndicationCandidate
        fields = [
            'id', 'patient_mrn', 'patient_name', 'patient_location',
            'medication_name', 'clinical_syndrome', 'clinical_syndrome_display',
            'syndrome_category', 'syndrome_confidence',
            'cchmc_agent_category', 'status',
            'has_red_flag',
            'indication_not_documented', 'likely_viral',
            'never_appropriate', 'asymptomatic_bacteriuria',
            'created_at',
        ]


class CandidateDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested reviews."""
    reviews = IndicationReviewSerializer(many=True, read_only=True)
    has_red_flag = serializers.BooleanField(read_only=True)

    class Meta:
        model = IndicationCandidate
        fields = [
            'id', 'patient_id', 'patient_mrn', 'patient_name', 'patient_location',
            'medication_request_id', 'medication_name', 'rxnorm_code',
            'order_date', 'location', 'service',
            'clinical_syndrome', 'clinical_syndrome_display',
            'syndrome_category', 'syndrome_confidence', 'therapy_intent',
            'supporting_evidence', 'evidence_quotes', 'guideline_disease_ids',
            'indication_not_documented', 'likely_viral',
            'asymptomatic_bacteriuria', 'never_appropriate',
            'has_red_flag',
            'cchmc_disease_matched', 'cchmc_agent_category',
            'cchmc_first_line_agents', 'cchmc_recommendation',
            'status', 'created_at', 'updated_at',
            'reviews',
        ]


class CandidateReviewSubmitSerializer(serializers.Serializer):
    """Input for submitting a candidate review."""
    syndrome_decision = serializers.ChoiceField(choices=SyndromeDecision.choices)
    confirmed_syndrome = serializers.CharField(required=False, allow_blank=True, default='')
    confirmed_syndrome_display = serializers.CharField(required=False, allow_blank=True, default='')
    agent_decision = serializers.ChoiceField(
        choices=AgentDecision.choices, required=False, allow_blank=True, default='',
    )
    agent_notes = serializers.CharField(required=False, allow_blank=True, default='')
    is_override = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
